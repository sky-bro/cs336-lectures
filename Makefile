PYTHON ?= python3
UV ?= uv
PORT ?= 8080
PROFILE ?= auto
DEVICE ?= auto
LECTURE ?=

UV_EXTRA := $(shell $(PYTHON) tools/trace_build.py profile --profile $(PROFILE))
UV_RUN := $(UV) run --frozen --extra $(UV_EXTRA)

.PHONY: help setup setup-remote serve doctor check-traces trace traces traces-all traces-gpu container-build container-run

help:
	@echo "make setup [PROFILE=auto|cpu|cu130]  Install dependencies for this host"
	@echo "make serve [PORT=8080]               Serve committed lectures and traces"
	@echo "make doctor                           Report hardware/build capabilities"
	@echo "make check-traces                     Detect missing or stale traces"
	@echo "make trace LECTURE=lecture_14         Build one trace"
	@echo "make traces                           Build portable CPU traces"
	@echo "make traces-all                       Build everything supported; skip the rest"
	@echo "make traces-gpu                       Build CUDA/Triton-only traces"
	@echo "make container-build                  Build the static production image"
	@echo "make container-run [PORT=8080]        Run the production image locally"

setup:
	$(UV) sync --frozen --extra $(UV_EXTRA)

setup-remote:
	$(UV) sync --frozen --extra $(UV_EXTRA) --extra remote

serve:
	$(PYTHON) -m http.server $(PORT)

doctor:
	$(UV_RUN) python tools/trace_build.py doctor

check-traces:
	$(UV_RUN) python tools/trace_build.py check

trace:
	@test -n "$(LECTURE)" || (echo "LECTURE is required, e.g. make trace LECTURE=lecture_14" >&2; exit 2)
	$(UV_RUN) python tools/trace_build.py build "$(LECTURE)" --device "$(DEVICE)"

traces:
	$(UV_RUN) python tools/trace_build.py build --group portable --device cpu

traces-all:
	$(UV_RUN) python tools/trace_build.py build --group all --device "$(DEVICE)"

traces-gpu:
	$(UV) run --frozen --extra cu130 python tools/trace_build.py build lecture_06 --device cuda --strict

container-build:
	docker build --tag cs336-lectures:local .

container-run:
	docker run --rm --init --publish "$(PORT):8080" cs336-lectures:local
