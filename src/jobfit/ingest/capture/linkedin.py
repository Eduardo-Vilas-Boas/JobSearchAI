"""Reads one job posting from a logged-in LinkedIn page, as the browser
rendered it.

LinkedIn's class names are hashed and change between releases, so nothing
here uses them. What the parser relies on instead (checked on a real page,
2026-11-22):
- the posting's id: `currentJobId` in the search view's URL, or
  /jobs/view/<id>/ in a job page's URL;
- the description: the first `data-testid="expandable-text-box"` on the
  page ("About the job"; the next one is "About the company"), without the
  "… more" button inside it;
- the title: the last link to /jobs/view/<id>/ before the description. In
  the newer search layout (/jobs/search-results/) the job list also links
  to the selected job, earlier in the page, with "Company • Location" on one
  line and no date; the top card's link is the one nearest the description;
- the company: the /company/ link just before it;
- location and date: the first two "·"-separated pieces of the paragraph
  after the title ("Zurich, Switzerland · 2 weeks ago · 100 applicants").
The field selection is adapted from Prepify's LinkedIn scraper
(github.com/igagandeep/Prepify, MIT), whose class-name selectors no longer
match LinkedIn's pages.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from dateparser.search import search_dates

from jobfit.ingest.fetchers.base import RawPosting

_VIEW_PATH = re.compile(r"/jobs/view/(\d+)")
_SEPARATOR = "·"


class NotAJobPosting(ValueError):
    """The captured page shows no job posting the parser can find."""


def parse_linkedin(html: str, url: str, captured_at: datetime) -> RawPosting:
    """`captured_at` anchors LinkedIn's relative dates ("6 days ago")."""
    soup = BeautifulSoup(html, "lxml")
    job_id = _job_id_from_url(url)
    description = soup.find(attrs={"data-testid": "expandable-text-box"})
    title_link = _title_link(soup, job_id, description)
    if title_link is None:
        raise NotAJobPosting(f"no job posting found on {url}")
    job_id = job_id or _VIEW_PATH.search(title_link["href"]).group(1)

    company_link = title_link.find_previous("a", href=re.compile(r"/company/"))
    pieces = _top_card_pieces(title_link)
    if description is not None:
        for button in description.find_all("button"):
            button.decompose()
        _collapse_whitespace(description)

    return RawPosting(
        source="linkedin",
        external_id=job_id,
        company=_text(company_link) if company_link else "",
        title=_text(title_link),
        location=pieces[0] if pieces else None,
        description_html=description.decode_contents() if description else "",
        raw_payload={"url": url, "html": html},
        posted_at=_posted_at(pieces[1:], captured_at),
        url=f"https://www.linkedin.com/jobs/view/{job_id}/",
    )


def _job_id_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    if match := _VIEW_PATH.search(parts.path):
        return match.group(1)
    current = parse_qs(parts.query).get("currentJobId")
    return current[0] if current else None


def _title_link(soup: BeautifulSoup, job_id: str | None, description: Tag | None) -> Tag | None:
    """The top card's link to the job: the nearest one before the description,
    or without a description, the last one on the page."""
    links = description.find_all_previous("a", href=_VIEW_PATH) if description else []
    links = links or reversed(soup.find_all("a", href=_VIEW_PATH))
    for link in links:
        if job_id is None or _VIEW_PATH.search(link["href"]).group(1) == job_id:
            if _text(link):
                return link
    return None


def _top_card_pieces(title_link: Tag) -> list[str]:
    """The "·"-separated pieces of the line after the title."""
    line = title_link.find_next("p")
    if line is None:
        return []
    text = " ".join(line.get_text(" ").split())
    return [piece.strip() for piece in text.split(_SEPARATOR) if piece.strip()]


def _posted_at(pieces: list[str], captured_at: datetime) -> datetime | None:
    settings = {
        "RELATIVE_BASE": captured_at,
        "PREFER_DATES_FROM": "past",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }
    for piece in pieces:
        if found := search_dates(piece, settings=settings):
            return found[0][1]
    return None


def _collapse_whitespace(element: Tag) -> None:
    """Whitespace runs in HTML text render as one space; the page source
    breaks lines mid-sentence, which html_to_text would keep as new lines."""
    for node in element.find_all(string=True):
        if isinstance(node, NavigableString) and node.strip():
            node.replace_with(" ".join(node.split()))


def _text(element: Tag) -> str:
    return " ".join(element.get_text(" ").split())
