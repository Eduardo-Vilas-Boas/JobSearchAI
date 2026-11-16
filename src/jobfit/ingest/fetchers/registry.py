from __future__ import annotations

from jobfit.ingest.fetchers.base import Fetcher
from jobfit.ingest.fetchers.greenhouse import GreenhouseFetcher
from jobfit.ingest.fetchers.lever import LeverFetcher

FETCHERS: dict[str, type[Fetcher]] = {
    "greenhouse": GreenhouseFetcher,
    "lever": LeverFetcher,
}


def get_fetcher(ats: str) -> Fetcher:
    try:
        return FETCHERS[ats]()
    except KeyError:
        raise ValueError(f"No fetcher registered for ATS type '{ats}'") from None
