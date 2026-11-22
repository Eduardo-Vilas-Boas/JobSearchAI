"""Test doubles shared across test modules.

Plain duck-typed classes, not subclasses of the real ones. There's no fake
guard: tests use a real InjectionGuard over fake scanners, which loads no
models and still runs the guard's own logic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jobfit.ingest.fetchers.base import RawPosting


def raw_posting(
    external_id: str,
    title: str = "Machine Learning Engineer",
    company: str = "Acme",
    location: str | None = "Zurich",
    description_html: str = "<p>Build production ML systems with Python and PyTorch.</p>",
    source: str = "greenhouse",
    raw_payload: dict | None = None,
) -> RawPosting:
    return RawPosting(
        source=source,
        external_id=external_id,
        company=company,
        title=title,
        location=location,
        description_html=description_html,
        raw_payload=raw_payload or {},
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        url=f"https://example.com/jobs/{external_id}",
    )


class FakeFetcher:
    """Returns canned postings per board token; raises for unknown boards,
    the way a real fetcher raises on a 404."""

    def __init__(self, boards: dict[str, list[RawPosting]]) -> None:
        self.boards = boards

    def fetch(self, board_token: str, company: str) -> list[RawPosting]:
        if board_token not in self.boards:
            raise LookupError(f"no board {board_token!r}")
        return self.boards[board_token]


class FakeAnonymizer:
    """Passes text through unchanged; anonymize.py has its own tests."""

    def anonymize(self, text: str) -> str:
        return text


class FakeScanner:
    """A guard check with a fixed score, or one that flags only text
    containing `flag_on`.

    A score above 0 means the text is flagged. Records every text it received.
    """

    def __init__(
        self, score: float = -1.0, rewrite: str | None = None, flag_on: str | None = None
    ) -> None:
        self.score = score
        self.rewrite = rewrite
        self.flag_on = flag_on
        self.seen: list[str] = []

    @property
    def received(self) -> str | None:
        """The last text scanned."""
        return self.seen[-1] if self.seen else None

    def scan(self, prompt: str) -> tuple[str, bool, float]:
        self.seen.append(prompt)
        score = self.score if self.flag_on is None else (1.0 if self.flag_on in prompt else -1.0)
        sanitized = prompt if self.rewrite is None else self.rewrite
        return sanitized, score <= 0, score


def fake_scanner(
    name: str, score: float = -1.0, rewrite: str | None = None, flag_on: str | None = None
) -> FakeScanner:
    """The guard names each result after type(scanner).__name__, so each fake
    gets its own class name, the way the real checks are named."""
    return type(name, (FakeScanner,), {})(score, rewrite, flag_on)
