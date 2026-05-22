# Contributing

This repository is organized as a workspace, not a single template package.

## Before you start

1. Decide whether your change belongs in:
   - `apps/jiwenlong-rag-console/`
   - `src/power_rag_pipeline/`
   - `docs/`
   - `archive/` only if you are preserving historical material
2. Keep runtime data out of Git.
3. Prefer small, reviewable commits.

## Local setup

```bash
uv sync
uv run pre-commit install
```

## Common commands

```bash
make check
make test
make docs-test
```

## Contribution rules

- New product-facing work should go to `apps/`.
- Root `src/` is for prototype or reusable pipeline code only.
- `archive/` is reference-only by default.
- If you change repository structure, update `README.md` and `docs/repository-layout.md`.
- If you change the runnable app, verify `http://localhost:8000/api/health`.
