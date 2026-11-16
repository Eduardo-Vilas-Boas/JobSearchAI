from __future__ import annotations

from jobfit.config import load_companies
from jobfit.ingest.pipeline import run_ingest


def main() -> None:
    companies = load_companies()
    stats = run_ingest(companies)

    print(f"Fetched:          {stats.fetched}")
    print(f"Stored:           {stats.stored}")
    print(f"Exact duplicates: {stats.exact_duplicates}")
    print(f"Near duplicates:  {stats.near_duplicates}")
    print(f"Quarantined:      {stats.quarantined}")
    if stats.errors:
        print("Errors:")
        for error in stats.errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
