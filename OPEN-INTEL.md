# Open Intel — product fork of Open Notebook

Multi-organization competitor-intelligence SaaS, built as a maintained fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook). Architecture source of truth: `planning/open-notebook-multiteam-saas-plan-2.md` (folded into this repo from the former planning workspace; `bugscoderlab/opennotebook` now serves as the issue tracker only).

## Open Notebook upstream baseline

- Repository: https://github.com/lfnovo/open-notebook
- Release/tag: v1.14.0
- Commit: 30c7e2a63e43b7f270fc2c638f0b6246934a53f4
- Fork date: 2026-09-12

## Branches and remotes

- `upstream` → original lfnovo/open-notebook repository
- `fork` → this repository (bugscoderlab/open-intel-saas)
- `main` → upstream mirror; never develop here
- `upstream-integration` → receives upstream merges; never merge upstream directly into the product branch
- `product/open-intel-v1` → the product; all development happens here

## Layout (plan §19)

Product-owned modules live under `modules/`; upstream code (`api/`, `open_notebook/`, `frontend/`) remains in the tree for now as **reference-to-port** — it is never run in place. The Research module migration (Phase 2) ports from `open_notebook/` (seam: `open_notebook/database/repository.py`) and removes the leftover upstream code. Product planning (plan, glossary, agent docs, research) lives in `planning/`; see `planning/AGENTS.md` for conventions.

`shell/` is the product's Next.js frontend (upstream's `frontend/` name is occupied until Phase 2 removes the leftover upstream code). `serve.py` at the root is the API composition root.

## Product scaffold commands (ticket 10)

```bash
uv venv .venv && uv pip install --python .venv/bin/python fastapi 'uvicorn[standard]' pytest import-linter httpx mypy ruff python-dotenv
.venv/bin/pytest tests/product -q        # product tests only (upstream tests/ is reference)
.venv/bin/lint-imports                   # architecture contracts (plan §14)
.venv/bin/mypy modules/platform tests/product --ignore-missing-imports
.venv/bin/ruff check modules tests/product serve.py
.venv/bin/uvicorn serve:app --reload --port 5055
cd shell && npm install && npm run lint && npm run build
```

Optional modules are disabled with `OPEN_INTEL_DISABLED_MODULES=research,analytics`; the API must still start (plan §20). CI: `.github/workflows/product-ci.yml`.

## License

Upstream MIT license and copyright notices are preserved in `LICENSE`; product-owned modifications are identified in this file and per-module READMEs.
