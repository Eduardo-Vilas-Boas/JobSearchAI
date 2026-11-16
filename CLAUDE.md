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

Review guard decisions on stored postings (table of scores + verdict per posting, with a
drill-in to the full guard-formatted text):
```
uv run streamlit run src/jobfit/ui/guard_review.py
```

Tests:
```
uv run pytest tests/                                    # full suite
uv run pytest tests/ingest/test_dedup.py -v              # one module
uv run pytest tests/ingest/test_dedup.py::test_content_hash_differs_for_different_locations -v  # one test
```
`tests/ingest/test_pipeline.py` is an integration test and needs the local Postgres running
(`docker compose up -d`). Tests run against a separate `_test` database in the same
container, created and migrated automatically by `tests/conftest.py`, so the suite never
touches data the CLI ingested. Everything else mocks HTTP via `respx`; no test hits a live API.
Guard tests come in two kinds: `test_guard_unit.py` checks the guard's own logic with fake
scanners (fast, no models); `test_guard.py` runs the real models, so it's slower.

Lint/format: `uv run ruff check .` / `uv run ruff format .`. A `PostToolUse` hook
(`.claude/settings.json`) also auto-runs ruff + pylint via `uvx` after every `Write`/`Edit`
on a `.py` file — if a diff looks reformatted beyond what you changed, that's why.

Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`.

Database URL comes from `JOBFIT_DATABASE_URL` in `.env` (see `jobfit.config.Settings`,
`pydantic-settings` with `env_prefix="JOBFIT_"`).

## Architecture

Pipeline shape, in `jobfit.ingest.pipeline.run_ingest`: **fetch → normalize → guard → dedup →
store**, one company at a time, driven by `config/companies.yaml`. Every stage is a pure
function operating on plain data (no DB, no network) except the fetchers and the store calls
— that's what keeps the test suite fast and fixture-based. PII redaction is not a separate
step: it's the guard's `Anonymize` scanner (see below) — there used to be a hand-written
`redact.py` doing this with regex, removed in favor of the off-the-shelf scanner.

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

**Guard** (`jobfit.ingest.guard`) is off-the-shelf only, by design — the project plan
explicitly says "don't build your own sanitiser, use LLM Guard, only tune thresholds." Four
LLM Guard input scanners run in sequence, each one's sanitized output feeding the next:
`Anonymize` (PII redaction, replaces the old hand-written `redact.py`) → `InvisibleText`
(zero-width/hidden character stripping) → `PromptInjection`
(`protectai/deberta-v3-base-prompt-injection-v2`) → `Regex`, seeded with a pattern derived
from Rebuff's `generateInjectionKeywords()` (https://github.com/protectai/rebuff, MIT,
ProtectAI) rather than one written for this project. Configuration is kept to library options
(thresholds, match type, Regex's pattern). A posting is quarantined (`Posting.is_quarantined`) if *any* scanner
flags it; per-scanner scores are kept in the `guard_results` table (one row per posting per
scanner) for `jobfit.ui.guard_review`'s review page. Quarantined postings are stored, not
discarded, so a human can review and release them later.

Known, measured gaps — not assumed, found by running this against real postings:
- The guard doesn't catch every hand-written adversarial posting, and the Rebuff-derived
  pattern is English only. `test_guard.py` pins a minimum catch rate as a baseline, not the
  plan's target. Thresholds and match type should be tuned against real postings (false
  positives) as well as attacks, not against the small fixture set alone.
- `Anonymize`'s NER model repeatedly misreads short proper nouns as `PERSON` on real
  postings: Swiss place names ("Geneva") and company names/short-forms ("Sonar" for
  "SonarSource") both false-positived at measured 1.0 confidence before being added to
  `allowed_names` (a real Presidio `allow_list` exemption, not a custom recognizer).
  `_SWISS_PLACE_NAMES` is a static list in `guard.py`; company names/`aliases` come live from
  `config/companies.yaml` via `CompanyConfig.aliases` — add a short form there (see
  `SonarSource`'s entry) if a new company's postings false-positive the same way. Not every
  false positive found this way got chased down: templated page furniture (social-share-icon
  labels) and at least one US-state-abbreviation-as-`CRYPTO` miss are known, accepted residual
  gaps rather than further custom detection code.

**Idempotency**: re-running the pipeline against the same postings stores nothing new.
`find_existing_posting` checks `(source_id, external_id)` before any processing runs for that
posting. `store.iter_canonical_postings` is explicitly ordered by `first_seen` — without that,
Postgres gives no row-order guarantee, and which existing posting "wins" as canonical when a
new posting matches more than one near-dup candidate would differ between runs.

**Storage**: Postgres + pgvector via Alembic migrations (`companies`, `sources`, `postings`,
`ingest_runs`, `guard_results`). pgvector is enabled on the dev DB now but not yet used by
anything in this section — it's reserved for the embeddings work in the ranking section. Raw
ATS payloads are kept as a JSON column on `Posting` rather than in S3; that's a deliberate
"local-first" choice for this stage, not a placeholder for one not yet wired up.

## Tests

`tests/` mirrors `src/jobfit/` (e.g. `tests/ingest/test_dedup.py` tests
`src/jobfit/ingest/dedup.py`). Shared fixtures (`tests/fixtures/`) stay flat since they're used
across multiple modules' tests, not tied to one.
