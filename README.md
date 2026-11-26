# JobSearchAI

[![CI](https://github.com/Eduardo-Vilas-Boas/JobSearchAI/actions/workflows/ci.yml/badge.svg)](https://github.com/Eduardo-Vilas-Boas/JobSearchAI/actions/workflows/ci.yml)

A job-fit ranking system for the Swiss AI job market. This repository holds the first stage,
"Data in": a plain, testable pipeline that fetches job postings from public ATS job boards
(Greenhouse, Lever) and LinkedIn captures, cleans them, redacts contact details, screens them
for prompt injection, removes duplicates and stores them in Postgres.

The reasoning behind each decision is logged in [`docs/`](docs/).

## Quick start

```
uv sync
docker compose up -d
uv run alembic upgrade head
uv run python -m jobfit.ingest.cli   # fetch from live job boards
uv run pytest                        # tests (needs the Postgres container)
```

The postings page is then at http://localhost:8501.
