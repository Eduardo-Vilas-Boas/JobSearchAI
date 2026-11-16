# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Section 1 ("Data in") of a larger project: a job-fit ranking system for the Swiss AI job
market. The full plan, including sections not yet built (LLM extraction, ranking, agents,
AWS deployment), is in `Swiss AI Job-Fit Ranker — Project Plan.md` at the repo root — read
it for context on where this pipeline fits, but it's large; don't load it by default.

This stage is deliberately agent-free and LLM-free: a plain, testable pipeline that fetches
job postings, cleans them, and stores them in Postgres.

## Commands

Setup:
```
uv sync                    # installs deps into .venv (Python 3.12, pinned via .python-version)
docker compose up -d       # starts local Postgres+pgvector (pgvector/pgvector:pg16)
uv run alembic upgrade head
```

Run the ingestion pipeline end to end (fetches from live ATS APIs):
```
uv run python -m jobfit.ingest.cli
```

Tests:
```
uv run pytest tests/                                    # full suite
uv run pytest tests/ingest/test_dedup.py -v              # one module
uv run pytest tests/ingest/test_dedup.py::test_content_hash_differs_for_different_locations -v  # one test
```
`tests/ingest/test_pipeline.py` is an integration test and needs the local Postgres running
(`docker compose up -d`) — it uses the `clean_db` fixture to truncate tables, since there's
no separate test database. Everything else mocks HTTP via `respx`; no test hits a live API.
`tests/ingest/test_guard.py` loads the real transformer model (no mocking), so it's slower
(~3-5s) but deterministic — see the dedup/guard notes below.

Lint/format: `uv run ruff check .` / `uv run ruff format .`. A `PostToolUse` hook
(`.claude/settings.json`) also auto-runs ruff + pylint via `uvx` after every `Write`/`Edit`
on a `.py` file — if a diff looks reformatted beyond what you changed, that's why.

Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`.

Database URL comes from `JOBFIT_DATABASE_URL` in `.env` (see `jobfit.config.Settings`,
`pydantic-settings` with `env_prefix="JOBFIT_"`).

## Architecture

Pipeline shape, in `jobfit.ingest.pipeline.run_ingest`: **fetch → normalize → redact → guard
→ dedup → store**, one company at a time, driven by `config/companies.yaml`. Every stage is
a pure function operating on plain data (no DB, no network) except the fetchers and the
store calls — that's what keeps the test suite fast and fixture-based.

**Fetchers** (`jobfit.ingest.fetchers`): one class per ATS type (`greenhouse.py`, `lever.py`),
selected at runtime via `registry.get_fetcher(ats)`. Both hit the ATS's *public, unauthenticated
job-board API* — the same endpoint the company embeds on its own careers page — not the
authenticated internal recruiting API, and not a third-party scraper library; neither Greenhouse
nor Lever ships an official SDK for this, so these are thin `httpx` clients written against the
real response shapes (recorded as fixtures in `tests/fixtures/`). Gotcha: Greenhouse's `content`
field is **double HTML-escaped** (literal `&lt;p&gt;` text, not a real tag) — `normalize.html_to_text`
calls `html.unescape()` before parsing to handle this; don't remove that without checking.

Only add a company to `config/companies.yaml` after confirming its board endpoint actually
returns 200 — every current entry was verified live before being committed, not guessed.

**Dedup** (`jobfit.ingest.dedup`) is two-layer and both layers are location-aware, which was
not the first design:
- Exact: `content_hash(title, company, location)`. Title+company alone collapses genuinely
  different open reqs (same role title posted separately per city) into one — location is
  part of the key for that reason.
- Near-dup: MinHash over word shingles, gated by *both* title-word-overlap and
  location-non-conflict before the body-Jaccard check fires. Without the title gate, two
  different roles at the same company can share 90%+ of their body text purely from shared
  company boilerplate ("who we are", diversity statement) sitting ahead of the role-specific
  text. Without the location gate, identically-templated postings for the same title in
  different cities get wrongly collapsed. Both were added after real false positives showed
  up running this against live postings, not from a priori design.
- `MinHash` (datasketch) is constructed with its **fixed default seed (1)**, not a random one
  — this is what makes signatures comparable across separate runs/processes. Don't pass a
  custom seed without re-checking this.

**Guard** (`jobfit.ingest.guard`) is a hybrid, not just the off-the-shelf scanner: LLM Guard's
`PromptInjection` scanner (`protectai/deberta-v3-base-prompt-injection-v2`, loaded once via
`get_guard()`'s `lru_cache`) plus a multilingual (EN/FR/DE) regex layer for phrasings the ML
scanner missed in testing — it caught 5/8 of a hand-written adversarial set alone (missed
German-language injections and non-imperative "scoring override" framings); the regex layer
brings that to 8/8. A posting is quarantined (`Posting.is_quarantined`) if *either* signal
fires — it's stored, not discarded, so a human can review and release it later.

**Idempotency**: re-running the pipeline against the same postings stores nothing new.
`find_existing_posting` checks `(source_id, external_id)` before any processing runs for that
posting. `store.iter_canonical_postings` is explicitly ordered by `first_seen` — without that,
Postgres gives no row-order guarantee, and which existing posting "wins" as canonical when a
new posting matches more than one near-dup candidate would differ between runs.

**Storage**: Postgres + pgvector via Alembic migrations (`companies`, `sources`, `postings`,
`ingest_runs`). pgvector is enabled on the dev DB now but not yet used by anything in this
section — it's reserved for the embeddings work in the ranking section. Raw ATS payloads are
kept as a JSON column on `Posting` rather than in S3; that's a deliberate "local-first" choice
for this stage, not a placeholder for one not yet wired up.

## Repo quirk worth knowing

This directory's git root is `/Users/a_` (your home directory), not this project folder —
`git status`/`git log` here therefore reflect the whole home directory's state, not just this
repo. Nothing is committed yet. Be careful with any broad `git add`/`commit` run from here.

## Tests

`tests/` mirrors `src/jobfit/` (e.g. `tests/ingest/test_dedup.py` tests
`src/jobfit/ingest/dedup.py`). Shared fixtures (`tests/fixtures/`) stay flat since they're used
across multiple modules' tests, not tied to one.
