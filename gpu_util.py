import os

import torch


def cuda_if_available(index: int = 0) -> torch.device:
    """Select the requested accelerator, falling back to CPU in auto mode.

    EDTRACE_DEVICE can be auto, cpu, cuda, or mps. The historical function
    name is kept so existing lecture source and trace links stay stable.
    """
    requested = os.environ.get("EDTRACE_DEVICE", "auto").lower()
    if requested not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError(
            "EDTRACE_DEVICE must be one of: auto, cpu, cuda, mps "
            f"(got {requested!r})"
        )

    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("EDTRACE_DEVICE=cuda, but CUDA is unavailable")
        return torch.device(f"cuda:{index}")
    if requested == "mps":
        if not _mps_available():
            raise RuntimeError("EDTRACE_DEVICE=mps, but Apple MPS is unavailable")
        return torch.device("mps")

    if torch.cuda.is_available():
        return torch.device(f"cuda:{index}")
    if _mps_available():
        return torch.device("mps")
    return torch.device("cpu")


def _mps_available() -> bool:
    mps = getattr(torch.backends, "mps", None)
    return bool(mps and mps.is_available())


def get_max_memory_usage(func):
    """Measure CUDA memory used by func, or return 0 on other backends."""
    if not torch.cuda.is_available():
        return 0  # Can't measure it without GPUs!

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    func()
    return torch.cuda.max_memory_allocated()
