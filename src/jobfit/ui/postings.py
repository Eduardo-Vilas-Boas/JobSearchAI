"""The postings table: every stored posting (duplicates hidden) with its
job status, which the user edits in the table, its lifecycle dates, and the
guard's per-scanner scores and allowed/quarantined verdict. Clicking a title
opens that posting's own page (job.py) in a new tab.
"""

from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from jobfit.db.models import JobStatus
from jobfit.db.session import get_session
from jobfit.db.store import set_status
from jobfit.ui.data import JOB_LINK_TITLE, SCANNER_NAMES, load_postings, status_label

st.title("Job postings")
st.caption(
    "Every stored posting except duplicates, newest first. Click a title to open "
    "the full posting in a new tab. Change a job's status in the Status column; "
    "it's saved straight away. Last seen and Closed come from ingest runs: when "
    "the posting was last on the company's board, and when it left it. Then the "
    "current checks' scores (PromptInjection: attack probability, flagged above "
    "0.5; InvisibleText: 1 = hidden characters found), and the verdict stored at "
    "ingest, with the scanners that flagged it. Postings are scanned once, when "
    "first ingested, so verdicts from removed scanners stay until re-scanned."
)

df = load_postings()

if df.empty:
    st.warning("No postings stored yet — run `uv run python -m jobfit.ingest.cli` first.")
    st.stop()

ALL = "All"
status_filter = st.selectbox(
    "Status", [ALL, *JobStatus], format_func=lambda s: s if s == ALL else status_label(s)
)
if status_filter != ALL:
    df = df[df["status"] == status_filter]

verdict_filter = st.radio("Show", ["All", "Quarantined only", "Allowed only"], horizontal=True)
if verdict_filter == "Quarantined only":
    df = df[df["verdict"] == "quarantined"]
elif verdict_filter == "Allowed only":
    df = df[df["verdict"] == "allowed"]

POSTED_WITHIN_DAYS = {"Any time": None, "Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}
posted_filter = st.radio("Posted", list(POSTED_WITHIN_DAYS), horizontal=True)
days = POSTED_WITHIN_DAYS[posted_filter]
if days is not None:
    # Postings without a posting date are left out of any time window.
    posted = pd.to_datetime(df["posted"], utc=True)
    df = df[posted >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)]

st.caption(f"{len(df)} postings")

table_columns = [
    "job_page",
    "status",
    "company",
    "location",
    "posted",
    "last_seen",
    "closed_at",
    "verdict",
    "flagged_by",
    *SCANNER_NAMES,
    "url",
]


def date_column(label: str, help_text: str | None = None):
    return st.column_config.DatetimeColumn(label, format="YYYY-MM-DD", width=110, help=help_text)


# Fixed column widths: when they add up to more than the page is wide, the
# table scrolls left/right, with title and status pinned on the left.
# A new key after each save gives a fresh editor: its pending edits are keyed
# by row position, which would point at other rows once the data reloads
# (e.g. the edited job leaving the status filter).
st.session_state.setdefault("editor_version", 0)
edited = st.data_editor(
    df[table_columns],
    column_config={
        "job_page": st.column_config.LinkColumn(
            "Title", display_text=JOB_LINK_TITLE, width=320, pinned=True
        ),
        "status": st.column_config.SelectboxColumn(
            "Status",
            options=list(JobStatus),
            format_func=status_label,
            required=True,
            width=130,
            pinned=True,
        ),
        "company": st.column_config.TextColumn("Company", width=130),
        "location": st.column_config.TextColumn("Location", width=220),
        "posted": date_column("Posted"),
        "last_seen": date_column("Last seen", "Last ingest run that found it on the board"),
        "closed_at": date_column("Closed", "When it left the company's board"),
        "verdict": st.column_config.TextColumn("Verdict", width=110),
        "flagged_by": st.column_config.TextColumn("Flagged by", width=130),
        **{
            name: st.column_config.NumberColumn(name, format="%.2f", width=130)
            for name in SCANNER_NAMES
        },
        "url": st.column_config.LinkColumn("Original posting", display_text="Open", width=110),
    },
    disabled=[column for column in table_columns if column != "status"],
    hide_index=True,
    width="stretch",
    key=f"jobs_table_{st.session_state.editor_version}",
)

changed = edited["status"] != df["status"]
if changed.any():
    with get_session() as session:
        for posting_id, status in edited.loc[changed, "status"].items():
            set_status(session, uuid.UUID(posting_id), status)
    load_postings.clear()
    st.session_state.editor_version += 1
    st.rerun()
