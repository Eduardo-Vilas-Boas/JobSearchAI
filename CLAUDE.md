# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Section 1 ("Data in") of a larger project: a job-fit ranking system for the Swiss AI job
market. The full plan, including sections not yet built (LLM extraction, ranking, agents,
AWS deployment), is in `tmp/Swiss AI Job-Fit Ranker — Project Plan.md` (local only, gitignored) — read
it for context on where this pipeline fits, but it's large; don't load it by default. Where
this file and the plan disagree (e.g. the plan says to use LLM Guard), this file reflects
later decisions; the reasoning is in `docs/`.

This stage is deliberately agent-free and LLM-free: a plain, testable pipeline that fetches
job postings, cleans them, and stores them in Postgres. Applications go to jobs across
Europe, so postings in any language are normal postings.

## Commands

Setup:
```
uv sync                    # installs deps into .venv (Python 3.12, pinned via .python-version)
docker compose up -d       # starts local Postgres+pgvector and the guard review page
uv run alembic upgrade head
uv run pre-commit install  # git hook: ruff + the full test suite before every commit
```

Run the ingestion pipeline end to end (fetches from live ATS APIs):
```
uv run python -m jobfit.ingest.cli
```

Review guard decisions on stored postings (table of per-check scores, the verdict and which
checks flagged it, with a drill-in to the stored text): `docker compose up -d` serves it at
http://localhost:8501 (`Dockerfile.ui`). `src/` and `config/` are mounted into the container
and Streamlit re-runs on save, so code changes show without a rebuild; rebuild with
`docker compose up -d --build ui` only after changing the `ui` dependency group or
`Dockerfile.ui`. It installs only the `ui` dependency group in
`pyproject.toml`, not torch or the models; keep that group in step with the page's imports.
Without Docker: `uv run streamlit run src/jobfit/ui/guard_review.py`.

Verdicts are decided once, at ingest, and never recomputed: re-running the CLI skips postings
already stored. After a guard change, stored verdicts are stale until the data is re-ingested
(there's no re-scan step yet).

All of `data/` is gitignored and never published: it can hold real postings' text, which
isn't ours to publish. Only results are disclosed, in `docs/`.

Tests:
```
uv run pytest tests/                                    # full suite
uv run pytest tests/ingest/test_anonymize.py -v          # one module
uv run pytest tests/ingest/test_anonymize.py::test_redacts_email -v  # one test
uv run pytest -m live                                   # live ATS smoke tests (network)
```
`tests/ingest/test_pipeline.py` is an integration test and needs the local Postgres running
(`docker compose up -d`). Tests run against a separate `_test` database in the same
container, created and migrated automatically by `tests/conftest.py`, so the suite never
touches data the CLI ingested.

Tests check behaviour, not implementation details or library behaviour. Pipeline tests pass
fake fetchers (`run_ingest(fetchers=...)`) that return `RawPosting`s directly, so they don't
depend on ATS URLs or JSON formats. Shared fakes live in `tests/fakes.py`; don't import
helpers from other test modules. ATS formats are covered twice: `test_fetchers.py` maps
recorded responses (`tests/fixtures/`) through an `httpx.MockTransport` client and asserts
values copied by hand, and `test_fetchers_live.py` (marker `live`, deselected by default)
checks one real board per ATS. Only the live test notices an ATS changing its format.
Guard tests come in two kinds: `test_guard_unit.py` checks the guard's own logic with fake
scanners (fast, no models); `test_guard.py` runs the real model on hand-written fixtures
(`tests/fixtures/adversarial_postings.json`), so it's slower. Its catch rate is a baseline,
not a target. `test_anonymize.py` runs the real Presidio recognizers. There are no
duplicate-detection tests, by decision (see Dedup).

Lint/format: `uv run ruff check .` / `uv run ruff format .`. A `PostToolUse` hook
(`.claude/settings.json`) also auto-runs ruff + pylint via `uvx` after every `Write`/`Edit`
on a `.py` file — if a diff looks reformatted beyond what you changed, that's why.
`.pre-commit-config.yaml` runs `ruff check`, `ruff format --check` and the full test suite
(live tests excluded) before every commit, and aborts the commit if any fails, so Postgres
must be running to commit. `alembic/versions/` is excluded from ruff (generated code).

Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`.

Database URL comes from `JOBFIT_DATABASE_URL` in `.env` (see `jobfit.config.Settings`,
`pydantic-settings` with `env_prefix="JOBFIT_"`). Inside Docker Compose the UI reaches
Postgres as `postgres:5432` instead. Both containers publish on `127.0.0.1` only.

## Architecture

Pipeline shape, in `jobfit.ingest.pipeline.run_ingest`: **fetch → normalize → anonymize →
guard → dedup → store**, one company at a time, driven by `config/companies.yaml`. Every
stage is a pure function operating on plain data (no DB, no network) except the fetchers and
the store calls — that's what keeps the test suite fast and fixture-based.

**Anonymize** (`jobfit.ingest.anonymize`): PII redaction with Microsoft Presidio's pattern
recognizers for email addresses and phone numbers only (`<EMAIL_ADDRESS>`,
`<PHONE_NUMBER>`). No name detection (NER): the PII that matters in a posting is a
recruiter's contact details, and NER misread place and company names ("Geneva", "Sonar") as
people. The recognizers are called directly, not through Presidio's `AnalyzerEngine`, which
would load a spaCy model they don't need. Phone numbers use `PHONE_REGIONS` (Switzerland and
the main European countries; Presidio's default list lacks Switzerland). It only redacts and
never quarantines: a PII hit isn't an attack. It runs before the guard, so neither the guard
nor any LLM step sees the original PII. Whether PII was found is not recorded yet.

**Normalize** (`jobfit.ingest.normalize`): HTML to text with BeautifulSoup, plus a language
tag per posting (stored as data; nothing is filtered on it).

**Fetchers** (`jobfit.ingest.fetchers`): one class per ATS type (`greenhouse.py`, `lever.py`),
selected at runtime via `registry.get_fetcher(ats)`. Both hit the ATS's *public, unauthenticated
job-board API* — the same endpoint the company embeds on its own careers page — not the
authenticated internal recruiting API, and not a third-party scraper library; neither Greenhouse
nor Lever ships an official SDK for this, so these are thin `httpx` clients written against the
real response shapes (recorded as fixtures in `tests/fixtures/`). Gotcha: Greenhouse's `content`
field is **double HTML-escaped** (literal `&lt;p&gt;` text, not a real tag) — `normalize.html_to_text`
calls `html.unescape()` before parsing to handle this; don't remove that without checking.

Only add a company to `config/companies.yaml` after confirming its board endpoint actually
returns 200 — every current entry was verified live before being committed, not guessed. A
board can return 200 with no postings (Squirro and DFINITY did on 2026-11-22).

**Dedup** (`jobfit.ingest.dedup`) is two-layer and both layers are location-aware:
- Exact: `content_hash(title, company, location)`. Title+company alone collapses genuinely
  different open reqs (same role title posted separately per city) into one — location is
  part of the key for that reason.
- Near-dup: MinHash over word shingles, gated by *both* title-word-overlap and
  location-non-conflict before the body-Jaccard check fires. Without the title gate, two
  different roles at the same company can share 90%+ of their body text purely from shared
  company boilerplate. Without the location gate, identically-templated postings for the
  same title in different cities get wrongly collapsed. Both were added after real false
  positives on live postings.
- Locations are compared as plain lowercased strings, so "Zurich" and "Zurich, Metropolitan
  Area" count as different and both postings are kept. Accepted by the user: occasional
  duplicates are fine, and there are no dedup tests by decision.
- `MinHash` (datasketch) is constructed with its **fixed default seed (1)**, not a random one
  — this is what makes signatures comparable across separate runs/processes. Don't pass a
  custom seed without re-checking this.

**Guard** (`jobfit.ingest.guard`) is off-the-shelf models with their default decisions: no
threshold tuning, by the user's decision (there are no real attacked postings to tune on). It
doesn't use the LLM Guard library (no longer maintained); models run directly with
`transformers`. Two checks run in order, each one's output text feeding the next:
- `InvisibleText`: strips Unicode format/private-use/unassigned characters (zero-width
  spaces, tag characters) and flags the posting if it found any. A short port of LLM Guard's
  scanner of the same name (MIT), kept as a flag by the user's decision.
- `PromptInjection`: one Hugging Face classifier, `PROMPT_INJECTION_MODEL` pinned to
  `PROMPT_INJECTION_REVISION` (a repo commit, so upstream updates can't change behaviour
  silently). Currently `protectai/deberta-v3-base-prompt-injection-v2` (mainly English).
  Flagged when the attack probability is above 0.5 (the model's own top label). Text is
  split into overlapping 512-token chunks (the model's limit) and the highest score counts.
  The check keeps the name "PromptInjection" whichever model backs it, so stored scores stay
  comparable.

Planned: switch to Meta's `meta-llama/Llama-Prompt-Guard-2-86M` (multilingual) once access to
the gated repo is approved. Then: update the model name and revision, verify which class index
is the attack class (assumed 1), log in with `hf auth login`, and remove the `xfail` on the
German test in `test_guard.py`. Don't add a second model or a custom detector without asking:
the user chose one classifier.

A posting is quarantined (`Posting.is_quarantined`) if any check flags it; per-check scores
are kept in the `guard_results` table (one row per posting per check) for the review page.
Quarantined postings are stored, not discarded, so a human can review and release them later.

Known, measured gaps (details in `docs/0001`):
- A short attack inside a long chunk is diluted: one attack sentence scored 1.0 alone and
  ~0.00001 inside a 512-token chunk. Smaller chunks catch more but raise false alarms
  (line by line flagged 14 of 135 clean real postings, 512 tokens flagged none).
- The current model misses the plain German override fixture.
- Text hidden with CSS on the careers page reaches the guard as ordinary text, because
  HTML-to-text drops styling.
- Recruiter "if you are an AI…" lines are likely missed; both candidate models target
  explicit instruction overrides.

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

`tests/` mirrors `src/jobfit/` (e.g. `tests/ingest/test_anonymize.py` tests
`src/jobfit/ingest/anonymize.py`). Shared fixtures (`tests/fixtures/`) stay flat since they're
used across multiple modules' tests, not tied to one.

## Development log (`docs/`)

This is a portfolio project, so the reasoning behind it matters as much as the code.
`docs/` holds a numbered log of what was discussed, found and decided, written so the
user can explain the project later (interviews, write-ups). It is not code documentation.

**One entry per iteration:** everything between two commits, or one AI/data task (an
eval, a tuning run, a model or threshold decision). Draft it at the end of the iteration
and show it to the user for review before it's committed; don't wait to be asked.

**File naming:** `docs/NNNN-short-slug.md`, four digits, in order (`0001-guard-eval.md`).
Never renumber.

**Committed entries are never edited.** If a later finding changes an earlier one, say
so in a new entry and reference the old one by number ("revises 0003, topic 2").

**Structure:** an iteration usually covers several unrelated things, so an entry is a
list of topics, one section each. Per topic, only what applies:
- **Intention:** what we wanted and why
- **Spec changes:** what the system now does differently (behaviour, rules, thresholds,
  data, scope), not which files changed
- **Findings:** what we measured or learned, with numbers and their uncertainty;
  include what didn't work
- **Decisions:** what was decided and the reasoning; mark the user's own calls as such
- **Open questions**

Plain language a non-specialist could follow. Don't overclaim.
