"""One posting in full, at /job?id=<posting id>: its details, status
(editable), lifecycle dates, guard verdict, other stored copies, and the
stored text (after PII redaction and the guard)."""

from __future__ import annotations

import html
import uuid

import streamlit as st

from jobfit.db.models import JobStatus
from jobfit.db.session import get_session
from jobfit.db.store import set_status
from jobfit.ui.data import (
    SCANNER_NAMES,
    date_or,
    job_page_link,
    load_job,
    load_postings,
    status_label,
)


def _posting_id() -> uuid.UUID | None:
    try:
        return uuid.UUID(st.query_params.get("id", ""))
    except ValueError:
        return None


posting_id = _posting_id()
job = load_job(posting_id) if posting_id else None
if job is None:
    st.title("Posting not found")
    st.write("This link doesn't point to a stored posting.")
    st.page_link("postings.py", label="All postings", icon=":material/arrow_back:")
    st.stop()

st.title(job.title)
st.markdown(
    f"{f'**{job.company}**' if job.company else 'company unknown'} · "
    f"{job.location or 'location unknown'} · "
    f"[original posting on {job.source}]({job.url})"
)
if job.duplicate_of:
    st.info(
        "This is a duplicate copy; status is tracked on the "
        f"[original posting]({job_page_link(str(job.duplicate_of), job.title)})."
    )

status_column, dates_column, guard_column = st.columns([1, 2, 2])
with status_column:
    status = st.selectbox(
        "Status",
        list(JobStatus),
        index=list(JobStatus).index(JobStatus(job.status)),
        format_func=status_label,
        disabled=job.duplicate_of is not None,
    )
    st.caption(f"Changed {date_or(job.status_changed_at, 'never')}")
    if status != job.status:
        with get_session() as session:
            set_status(session, job.id, status)
        load_postings.clear()  # the table's cached copy
        st.rerun()

with dates_column:
    st.markdown(
        f"**Posted:** {date_or(job.posted_at, 'unknown')}  \n"
        f"**First seen:** {date_or(job.first_seen, 'unknown')}  \n"
        f"**Last seen:** {date_or(job.last_seen, 'unknown')}  \n"
        f"**Closed:** {date_or(job.closed_at, 'still open')}"
    )

with guard_column:
    verdict = "quarantined" if job.quarantined else "allowed"
    flagged = f" (flagged by {', '.join(job.flagged_by)})" if job.flagged_by else ""
    scores = " · ".join(
        f"{name}: {job.scores[name]:.2f}" if name in job.scores else f"{name}: n/a"
        for name in SCANNER_NAMES
    )
    st.markdown(f"**Guard verdict:** {verdict}{flagged}  \n{scores}")
    st.caption(f"Language: {job.language or 'unknown'}")

if job.copies:
    links = ", ".join(f"[{copy.source}]({copy.url})" for copy in job.copies)
    st.markdown(f"**Also posted on:** {links}")

st.divider()
st.caption("Stored text, after PII redaction and the guard")
# Plain text with its line breaks kept; escaped, so nothing in a posting is
# rendered as markup.
st.html(
    '<div style="white-space: pre-wrap; line-height: 1.6; max-width: 80ch">'
    f"{html.escape(job.text)}</div>"
)
