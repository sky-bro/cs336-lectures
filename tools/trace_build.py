#!/usr/bin/env python3
"""Build, validate, and diagnose CS336 executable lecture traces."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = ROOT / "var" / "traces"


@dataclass(frozen=True)
class Lecture:
    module: str
    tier: str
    description: str
    dependencies: tuple[str, ...] = ()


LECTURES = (
    Lecture(
        "lecture_01",
        "portable",
        "CPU-portable; first run may populate tokenizer caches",
        ("lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_02",
        "adaptive",
        "CPU fallback; CUDA changes benchmark results",
        ("gpu_util.py", "facts.py", "lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_06",
        "cuda",
        "Requires Linux, NVIDIA CUDA, and Triton",
        ("gpu_util.py", "lecture_util.py"),
    ),
    Lecture(
        "lecture_07",
        "adaptive",
        "Tracing disables multiprocessing/distributed collectives",
        ("gpu_util.py", "lecture_util.py"),
    ),
    Lecture(
        "lecture_10",
        "portable",
        "CPU-portable",
        ("lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_12",
        "portable",
        "CPU-portable",
        ("lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_13",
        "portable",
        "CPU-portable",
        ("lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_14",
        "portable",
        "CPU-portable; may download cached source material",
        ("lecture_13.py", "lecture_util.py", "references.py"),
    ),
    Lecture(
        "lecture_17",
        "portable",
        "CPU-portable",
        ("lecture_util.py", "references.py"),
    ),
)
LECTURE_BY_MODULE = {lecture.module: lecture for lecture in LECTURES}


@dataclass(frozen=True)
class Capabilities:
    system: str
    machine: str
    python: str
    torch_version: str | None
    cuda_available: bool
    cuda_devices: int
    mps_available: bool
    triton_available: bool


def detect_capabilities() -> Capabilities:
    torch_version = None
    cuda_available = False
    cuda_devices = 0
    mps_available = False
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch

            torch_version = torch.__version__
            cuda_available = bool(torch.cuda.is_available())
            cuda_devices = torch.cuda.device_count() if cuda_available else 0
            mps = getattr(torch.backends, "mps", None)
            mps_available = bool(mps and mps.is_available())
        except Exception:
            # Doctor should still work when a partially installed torch is broken.
            pass

    triton_available = importlib.util.find_spec("triton") is not None
    return Capabilities(
        system=platform.system(),
        machine=platform.machine(),
        python=platform.python_version(),
        torch_version=torch_version,
        cuda_available=cuda_available,
        cuda_devices=cuda_devices,
        mps_available=mps_available,
        triton_available=triton_available,
    )


def support_reason(lecture: Lecture, capabilities: Capabilities) -> str | None:
    if lecture.tier != "cuda":
        return None
    if capabilities.system != "Linux":
        return "requires Linux"
    if not capabilities.cuda_available:
        return "requires an available NVIDIA CUDA device"
    if not capabilities.triton_available:
        return "requires Triton"
    return None


def normalize_module(value: str) -> str:
    value = value.removesuffix(".py")
    if value.isdigit():
        value = f"lecture_{int(value):02d}"
    if value not in LECTURE_BY_MODULE:
        choices = ", ".join(LECTURE_BY_MODULE)
        raise ValueError(f"unknown lecture {value!r}; choose one of: {choices}")
    return value


def trace_path(module: str) -> Path:
    return TRACE_DIR / f"{module}.json"


def input_paths(lecture: Lecture) -> tuple[str, ...]:
    return (f"{lecture.module}.py", *lecture.dependencies)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trace_status(module: str) -> tuple[str, list[str]]:
    path = trace_path(module)
    if not path.exists():
        return "missing", [str(path.relative_to(ROOT))]
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return "invalid", [str(error)]

    mismatches = []
    files = data.get("files")
    if not isinstance(files, dict):
        return "invalid", ["trace has no files mapping"]
    for relative, embedded_source in files.items():
        source_path = ROOT / relative
        if source_path.is_file() and source_path.suffix == ".py":
            if source_path.read_text() != embedded_source:
                mismatches.append(relative)
    if mismatches:
        return "stale", sorted(mismatches)

    metadata = data.get("_build", {})
    recorded_inputs = metadata.get("inputs") if isinstance(metadata, dict) else None
    if isinstance(recorded_inputs, dict):
        for relative, recorded_digest in recorded_inputs.items():
            source_path = ROOT / relative
            if not source_path.is_file() or file_digest(source_path) != recorded_digest:
                mismatches.append(relative)
    if mismatches:
        return "stale", sorted(set(mismatches))
    return "current", []


def selected_lectures(modules: list[str], group: str | None) -> list[Lecture]:
    if modules:
        return [LECTURE_BY_MODULE[normalize_module(module)] for module in modules]
    if group == "portable":
        return [lecture for lecture in LECTURES if lecture.tier == "portable"]
    if group == "supported":
        capabilities = detect_capabilities()
        return [
            lecture
            for lecture in LECTURES
            if support_reason(lecture, capabilities) is None
        ]
    return list(LECTURES)


def effective_device(lecture: Lecture, requested: str, capabilities: Capabilities) -> str:
    if lecture.tier == "cuda":
        return "cuda"
    if requested != "auto":
        if requested == "cuda" and not capabilities.cuda_available:
            raise RuntimeError("CUDA was requested but is unavailable")
        if requested == "mps" and not capabilities.mps_available:
            raise RuntimeError("MPS was requested but is unavailable")
        return requested
    # Published traces should be reproducible across maintainers' machines.
    return "cpu"


def build_one(
    lecture: Lecture,
    *,
    capabilities: Capabilities,
    requested_device: str,
    force: bool,
    timeout: int,
) -> str:
    reason = support_reason(lecture, capabilities)
    if reason:
        raise RuntimeError(reason)

    status, _ = trace_status(lecture.module)
    if status == "current" and not force:
        return "current"

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    temporary_directory = Path(tempfile.mkdtemp(
        prefix=f".{lecture.module}.",
        dir=TRACE_DIR,
    ))
    temporary_path = temporary_directory / f"{lecture.module}.json"

    device = effective_device(lecture, requested_device, capabilities)
    environment = os.environ.copy()
    environment["EDTRACE_DEVICE"] = device
    command = [
        sys.executable,
        "-m",
        "edtrace.execute",
        "-m",
        lecture.module,
        "-o",
        str(temporary_directory),
    ]
    print(f"BUILD   {lecture.module} (device={device})", flush=True)
    try:
        subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Validate before replacing a known-good committed trace.
        trace_data = json.loads(temporary_path.read_text())
        trace_data["_build"] = {
            "schema": 1,
            "module": lecture.module,
            "tier": lecture.tier,
            "device": device,
            "platform": f"{capabilities.system}-{capabilities.machine}",
            "python": capabilities.python,
            "edtrace": importlib.metadata.version("edtrace"),
            "inputs": {
                relative: file_digest(ROOT / relative)
                for relative in input_paths(lecture)
            },
        }
        temporary_path.write_text(json.dumps(trace_data, indent=2) + "\n")
        os.replace(temporary_path, trace_path(lecture.module))
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout[-4000:], file=sys.stderr)
        if error.stderr:
            print(error.stderr[-4000:], file=sys.stderr)
        raise
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)

    status, details = trace_status(lecture.module)
    if status != "current":
        raise RuntimeError(
            f"generated trace failed freshness validation: {status} {details}"
        )
    return "built"


def command_doctor(_: argparse.Namespace) -> int:
    capabilities = detect_capabilities()
    print(f"Platform: {capabilities.system} {capabilities.machine}")
    print(f"Python:   {capabilities.python}")
    print(f"PyTorch:  {capabilities.torch_version or 'not installed'}")
    print(
        "CUDA:    "
        + (
            f"available ({capabilities.cuda_devices} device(s))"
            if capabilities.cuda_available
            else "unavailable"
        )
    )
    print(f"MPS:      {'available' if capabilities.mps_available else 'unavailable'}")
    print(
        f"Triton:   {'available' if capabilities.triton_available else 'unavailable'}"
    )
    print()
    for lecture in LECTURES:
        reason = support_reason(lecture, capabilities)
        state = f"unsupported: {reason}" if reason else "supported"
        print(f"{lecture.module}: {state} [{lecture.tier}]")
    return 0


def command_check(arguments: argparse.Namespace) -> int:
    lectures = selected_lectures(arguments.modules, arguments.group)
    failures = 0
    for lecture in lectures:
        status, details = trace_status(lecture.module)
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"{status.upper():7} {lecture.module}{suffix}")
        if status != "current":
            failures += 1
    return 1 if failures else 0


def command_build(arguments: argparse.Namespace) -> int:
    capabilities = detect_capabilities()
    lectures = selected_lectures(arguments.modules, arguments.group)
    failures = 0
    skipped = 0
    for lecture in lectures:
        reason = support_reason(lecture, capabilities)
        if reason:
            if arguments.strict or arguments.modules:
                print(f"ERROR   {lecture.module}: {reason}", file=sys.stderr)
                failures += 1
            else:
                print(f"SKIP    {lecture.module}: {reason}")
                skipped += 1
            continue
        try:
            result = build_one(
                lecture,
                capabilities=capabilities,
                requested_device=arguments.device,
                force=arguments.force,
                timeout=arguments.timeout,
            )
            print(f"{result.upper():7} {lecture.module}")
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as error:
            print(f"ERROR   {lecture.module}: {error}", file=sys.stderr)
            failures += 1
            if arguments.fail_fast:
                break
    print(f"Summary: {len(lectures) - failures - skipped} ok, {skipped} skipped, {failures} failed")
    return 1 if failures else 0


def command_profile(arguments: argparse.Namespace) -> int:
    requested = arguments.profile
    if requested == "auto":
        system = platform.system()
        has_nvidia_smi = shutil.which("nvidia-smi") is not None
        requested = "cu130" if system == "Linux" and has_nvidia_smi else "cpu"
    print(requested)
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="report platform capabilities")
    doctor.set_defaults(handler=command_doctor)

    check = subparsers.add_parser("check", help="check whether committed traces are fresh")
    check.add_argument("modules", nargs="*")
    check.add_argument(
        "--group",
        choices=("portable", "supported", "all"),
        default="all",
    )
    check.set_defaults(handler=command_check)

    build = subparsers.add_parser("build", help="build one or more traces")
    build.add_argument("modules", nargs="*")
    build.add_argument(
        "--group",
        choices=("portable", "supported", "all"),
        default="all",
    )
    build.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda", "mps"),
        default="auto",
    )
    build.add_argument("--force", action="store_true")
    build.add_argument("--strict", action="store_true")
    build.add_argument("--fail-fast", action="store_true")
    build.add_argument("--timeout", type=int, default=900)
    build.set_defaults(handler=command_build)

    profile = subparsers.add_parser(
        "profile", help="select the uv dependency profile for this host"
    )
    profile.add_argument(
        "--profile",
        choices=("auto", "cpu", "cu130"),
        default="auto",
    )
    profile.set_defaults(handler=command_profile)
    return parser


def main() -> int:
    parser = create_parser()
    arguments = parser.parse_args()
    try:
        return arguments.handler(arguments)
    except ValueError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
