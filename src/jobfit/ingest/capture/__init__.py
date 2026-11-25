"""Postings captured from a page open in the browser (the Chrome extension
in `extension/`), for sites without a public job-board API, such as LinkedIn."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from jobfit.ingest.capture.linkedin import NotAJobPosting, parse_linkedin
from jobfit.ingest.fetchers.base import RawPosting

__all__ = ["NotAJobPosting", "UnsupportedSite", "parse_capture"]


class UnsupportedSite(ValueError):
    """No parser for the captured page's site."""


def parse_capture(html: str, url: str, captured_at: datetime) -> RawPosting:
    host = urlsplit(url).hostname or ""
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return parse_linkedin(html, url, captured_at)
    raise UnsupportedSite(f"no parser for {host or url!r} yet; only LinkedIn is supported")
