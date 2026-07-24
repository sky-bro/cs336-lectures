# Spring 2026 CS336 lectures

This repository contains the lecture materials for Stanford's Language Modeling from Scratch (CS336).

## Executable lectures

These are named `lecture_XX.py`.

### Setup

        uv sync

You can compile a lecture by running:

        uv run python -m edtrace.execute -m lecture_01

which generates a `var/traces/lecture_01.json` and caches any images as
appropriate.
Some lectures fetch remote assets or tokenizer files the first time they run.

### Local preview

For the simplest local preview, serve this repository:

        python -m http.server 8000

Then open:

        http://localhost:8000/

This opens a lecture index page with links to all generated executable lectures
and PDF lectures.

You can also open a generated trace directly:

        http://localhost:8000/?trace=var/traces/lecture_01.json

You can replace `lecture_01` with any generated trace, for example
`lecture_02`, `lecture_06`, `lecture_07`, `lecture_10`, or `lecture_12`.

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
