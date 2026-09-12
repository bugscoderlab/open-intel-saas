# Open Intel — product fork of Open Notebook

Multi-organization competitor-intelligence SaaS, built as a maintained fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook). Architecture source of truth: the planning workspace (`bugscoderlab/opennotebook`, plan doc `open-notebook-multiteam-saas-plan-2.md`).

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

Product-owned modules live under `modules/`; upstream code (`api/`, `open_notebook/`, `frontend/`) remains in the tree for now as **reference-to-port** — it is never run in place. The Research module migration (Phase 2) ports from `open_notebook/` (seam: `open_notebook/database/repository.py`) and removes the leftover upstream code. See `AGENTS.md` in the planning workspace for conventions.

## License

Upstream MIT license and copyright notices are preserved in `LICENSE`; product-owned modifications are identified in this file and per-module READMEs.
