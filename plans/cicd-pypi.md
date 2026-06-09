---
description: CI/CD pipeline to test, build and publish followthemoney-graph to PyPI
date: 2026-06-09
tags: [ci, cd, packaging, pypi, github-actions]
---

# CI/CD for `followthemoney-graph` → PyPI

## Goal

Stand up GitHub Actions CI/CD so that:
- every push / PR runs tests + type-check on a Python version matrix;
- a clean wheel + sdist is built once and provenance-attested;
- pushing a version tag publishes to PyPI via **Trusted Publishing (OIDC)** — no API token stored in the repo.

This mirrors the `followthemoney` repo's `build.yml` so the two stay consistent.

## Current state

- Pure-Python package `ftmg/`, hatchling backend, console script `ftmg`.
- Version is hard-coded as `0.0.1` in `pyproject.toml`.
- Tests (`tests/test_read.py`) are pure — they read a fixture file and never touch Neo4j, so **CI needs no database service**.
- `[project.optional-dependencies].dev` already has `pytest`, `pytest-cov`, `mypy`, `build`, `twine`, `bump2version`, `types-PyYAML`.
- No `.github/workflows`, no Makefile, no lint config.
- `requires-python = ">= 3.10"` but classifiers only list 3.12 / 3.13.

## Decisions (settled)

1. **Python: 3.13 only.** Wheel is pure-Python (`py3-none-any`), so a single CI Python is sufficient. `requires-python` set to `>=3.12` so 3.12 users can still install.
2. **Publish trigger: tag push** (`refs/tags/*`) → PyPI.
3. **Trusted Publishing (OIDC).** No token stored. One-time PyPI setup required (see step 5).
4. **TestPyPI dry-run:** skipped.
5. **Linting: ruff** (lint + format-check) adopted; existing source modernized to pass.

## Plan

### Step 1 — Fix packaging metadata in `pyproject.toml`
- Correct `[project.urls]` — they currently point at the `followthemoney` repo, not this one:
  - `Repository = "https://github.com/opensanctions/followthemoney-graph.git"`
  - `Issues   = "https://github.com/opensanctions/followthemoney-graph/issues"`
- Align `classifiers` Python list with `requires-python` (add 3.10/3.11 or bump `requires-python` to `>=3.12` — pick one; the matrix must match whatever is chosen).
- Drop the obsolete `[tool.distutils.bdist_wheel] universal = true` (meaningless for a py3 hatchling wheel).
- (Optional) add `[tool.ruff]` config if linting is adopted.

### Step 2 — Add a `Makefile` (mirror sibling ergonomics)
Targets used by CI and locally:
- `make install` → `pip install -e ".[dev]"`
- `make test` → `pytest --cov=ftmg --cov-report=term-missing tests/`
- `make typecheck` → `mypy ftmg/`
- `make lint` → `ruff check ftmg tests` + `ruff format --check ftmg tests` (if linting adopted)
- `make build` → `python -m build`

### Step 3 — `.github/workflows/build.yml` — the `python` test job
- Triggers: `push`, `pull_request`, `workflow_dispatch`.
- `strategy.matrix.python` over the chosen versions.
- Steps: checkout → `setup-python` → `pip install -e ".[dev]"` → `make test` → `make typecheck` → `make lint`.
- No services block (tests are DB-free). Note in a comment that `backend.py` is intentionally not covered and would need a Neo4j service if tests start exercising it.

### Step 4 — `build.yml` — the `wheel` (build + publish) job
- `needs: python`, runs once on `ubuntu-latest` / one Python (3.13).
- `python -m build` → wheel + sdist into `dist/`.
- `actions/attest-build-provenance@v4` with `subject-path: 'dist/*'`.
- Publish step gated on `github.event_name == 'push' && startsWith(github.ref, 'refs/tags')`, using `pypa/gh-action-pypi-publish@release/v1` with `skip-existing: true`.
- Job/workflow `permissions`: `id-token: write` (OIDC), `contents: read`, `attestations: write`.

### Step 5 — One-time external setup (user action, document in PR)
- Register the project on PyPI and add a **Trusted Publisher**: owner `opensanctions`, repo `followthemoney-graph`, workflow `build.yml`, environment optional.
- (Recommended) add a `release` GitHub Environment and reference it in the publish job for an approval gate.
- If Trusted Publishing is declined: create `PYPI_API_TOKEN` secret and pass `password:` to the publish action instead.

### Step 6 — Release process / versioning
- `version` is static in `pyproject.toml`. Release flow:
  1. bump version (`bump2version patch|minor|major`, already a dev dep) → creates commit + tag,
  2. `git push --follow-tags`,
  3. tag push triggers build → publish.
- Document this 3-line flow in `README.md` (or a `CONTRIBUTING.md`).

### Step 7 — Validate
- Open the PR; confirm the `python` matrix + `wheel` build jobs go green (publish is skipped on PRs).
- Optionally push a `0.0.1` tag to a TestPyPI trusted publisher first to rehearse, or rely on `skip-existing` and bump to `0.0.2` for the first real publish.

## Out of scope
- Neo4j integration tests (would need a `services.neo4j` container + `FTMG_*` env). Add later when `backend.py`/`transform.py` get coverage.
- Docs site / mkdocs publishing.
- Building the JS bits referenced in `.gitignore` (none present here).

## Files touched
- `pyproject.toml` (metadata fixes; optional ruff config)
- `Makefile` (new)
- `.github/workflows/build.yml` (new)
- `README.md` or `CONTRIBUTING.md` (release docs)
