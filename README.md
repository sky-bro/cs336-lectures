# Spring 2026 CS336 lectures

This repository contains the lecture materials for Stanford's Language Modeling from Scratch (CS336).

## Executable lectures

Executable lecture sources are named `lecture_XX.py`. Generated traces are
committed under `var/traces`, so viewing the lectures does not require Python,
PyTorch, a GPU, or a dependency install.

### Local preview

For the simplest local preview:

        make serve PORT=8080

Then open:

        http://localhost:8080/

To open a generated trace directly:

        http://localhost:8080/?trace=var/traces/lecture_01.json

`make serve` only serves committed files and deliberately does not install
build dependencies.

### Build setup

Maintainers who need to regenerate traces can install the appropriate PyTorch
profile for the current machine:

        make setup

The default `PROFILE=auto` selects CUDA 13 on a Linux host with `nvidia-smi`,
and otherwise selects CPU-only PyTorch. It can be overridden explicitly:

        make setup PROFILE=cpu
        make setup PROFILE=cu130

Inspect the active machine and see which lectures it can build:

        make doctor

### Building traces

Build a single missing or stale trace:

        make trace LECTURE=lecture_14

Build all portable CPU traces:

        make traces

Build every trace supported by the current host, skipping unsupported hardware
instead of failing the whole build:

        make traces-all

Lecture 6 requires Linux, NVIDIA CUDA, and Triton. Build it explicitly on a
compatible machine with:

        make traces-gpu

Generated traces are written to a temporary file, validated, and atomically
moved into `var/traces`, so a failed build does not overwrite a known-good
trace. Some lectures fetch and cache remote assets or tokenizer files on their
first build.

Check whether committed traces contain the current Python sources:

        make check-traces

On a platform without Make, the equivalent commands are:

        uv sync --frozen --extra cpu
        uv run --frozen --extra cpu python tools/trace_build.py doctor
        uv run --frozen --extra cpu python tools/trace_build.py build lecture_14

`EDTRACE_DEVICE=cpu|cuda|mps|auto` controls device selection inside lectures.
Published portable traces default to CPU for reproducibility.

### Remote GPU build

Lecture 6 can be generated through Modal when no local NVIDIA GPU is available:

        make setup-remote
        uv run --frozen --extra cpu --extra remote modal run modal_execute.py \
          --module lecture_06 --gpu H100

The GPU type is configurable; an empty `--gpu` value runs the remote function
on CPU.

### Frontend development

If you are working on the edtrace frontend itself, clone and run the frontend
dev server:

        [ -d edtrace ] || git clone https://github.com/percyliang/edtrace
        npm --prefix=edtrace/frontend install
        mkdir -p edtrace/frontend/public
        ln -sfn ../../../var edtrace/frontend/public/var
        ln -sfn ../../../images edtrace/frontend/public/images
        npm --prefix=edtrace/frontend run dev

Then open:

        http://localhost:5173/?trace=var/traces/lecture_01.json

Deploy to the main website:

        npm run --prefix=edtrace/frontend build
        git add assets
        git ci -am "<some message>"
        git push

## Non-executable lectures

These are named `lecture_XX.pdf`.

## Container deployment

The production image contains only the committed static viewer, traces, images,
and PDFs. It does not install Python, PyTorch, CUDA, or lecture build
dependencies, so the same image runs on Linux `amd64` and `arm64` hosts
regardless of GPU availability.

Build and preview it locally:

        make container-build
        make container-run PORT=8080

Then open `http://localhost:8080/`. The container listens on port 8080 and
provides `/healthz` for health checks.

Pushes to `main` publish both architectures as
`ghcr.io/sky-bro/cs336-lectures-site:latest`. Version tags such as `v1.0.0` also
publish a matching image tag. The GitHub package must be public, or the NAS
must be configured with credentials that can pull it.
