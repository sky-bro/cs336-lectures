"""
Usage:
    uv run --extra remote modal run modal_execute.py --module lecture_06
    uv run --extra remote modal run modal_execute.py --module lecture_06 --gpu H100
"""

import glob
import os
import modal

app = modal.App("cs336-edtrace-execute")

IGNORE = [".venv", "__pycache__", "var", ".git", "node_modules"]

# Files to copy back after execution (glob patterns relative to /root/lectures)
def output_patterns(module: str) -> list[str]:
    return [
        f"var/traces/{module}.json",
        "var/*-ptx.txt",
        "var/profiles.txt",
    ]

def _ignore(path) -> bool:
    return any(p in IGNORE for p in str(path).split("/"))

image = (
    modal.Image.from_registry("nvidia/cuda:13.2.0-cudnn-devel-ubuntu24.04", add_python="3.11")
    .pip_install(
        "edtrace>=0.1.12",
        "einops>=0.8.2",
        "mmh3>=5.2.1",
        "tiktoken>=0.12.0",
        "torch>=2.11.0,<2.12",
    )
    .add_local_dir(".", "/root/lectures", ignore=_ignore)
)


@app.function(
    image=image,
    timeout=900,
)
def execute(module: str) -> dict[str, str]:
    import subprocess
    import sys

    os.chdir("/root/lectures")
    os.makedirs("var/traces", exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            "tools/trace_build.py",
            "build",
            module,
            "--device",
            "cuda" if module == "lecture_06" else "cpu",
            "--force",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        raise RuntimeError(f"edtrace.execute failed with exit code {result.returncode}")

    # Collect all output files matching the patterns
    files = {}
    for pattern in output_patterns(module):
        for path in glob.glob(pattern):
            files[path] = open(path).read()
    return files


@app.local_entrypoint()
def main(module: str = "lecture_06", gpu: str = "H100"):
    resource = gpu or "CPU"
    print(f"Running edtrace.execute on Modal for {module} using {resource}")
    remote_execute = execute.with_options(gpu=gpu) if gpu else execute
    files = remote_execute.remote(module)

    for path, content in files.items():
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        print(f"Saved {path} ({len(content):,} bytes)")
