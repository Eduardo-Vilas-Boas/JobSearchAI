"""Streamlit page for the stored postings: job status and guard decisions.

Run with: uv run streamlit run src/jobfit/ui/guard_review.py

Shows every posting (duplicates hidden) with its job status, which the user
edits in the table, its lifecycle dates, and the guard's per-scanner scores
and allowed/quarantined verdict, so a human can track applications and
spot-check what the guard quarantined (or missed) against real postings.
"""

from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st
from sqlalchemy import select

from jobfit.db.models import Company, GuardResult, JobStatus, Posting
from jobfit.db.session import get_session
from jobfit.db.store import set_status

# The current guard's scanners, as in guard.default_scanners(); keep in step
# with it. PII redaction is a separate step, not shown here. Postings stored
# before a scanner existed have no score for it (shown blank).
SCANNER_NAMES = ["InvisibleText", "PromptInjection"]


@st.cache_data(ttl=30)
def load_postings() -> pd.DataFrame:
    with get_session() as session:
        rows = session.execute(
            select(Posting, Company.name)
            .join(Company)
            # Status lives on the canonical posting; duplicates would only
            # repeat it.
            .where(Posting.is_duplicate_of.is_(None))
            .order_by(Posting.posted_at.desc().nulls_last())
        ).all()
        guard_rows = session.execute(
            select(
                GuardResult.posting_id, GuardResult.scanner, GuardResult.score, GuardResult.flagged
            ).order_by(GuardResult.scanner)
        ).all()

    scores_by_posting: dict = {}
    flagged_by_posting: dict = {}
    for posting_id, scanner, score, flagged in guard_rows:
        scores_by_posting.setdefault(posting_id, {})[scanner] = score
        if flagged:
            flagged_by_posting.setdefault(posting_id, []).append(scanner)

    records = []
    for posting, company_name in rows:
        record = {
            "id": str(posting.id),
            "title": posting.title,
            "status": posting.status,
            "company": company_name,
            "location": posting.location_raw,
            # From the ATS: Greenhouse's first_published, Lever's createdAt
            # (when the job was created in Lever, possibly before it went public).
            "posted": posting.posted_at,
            "last_seen": posting.last_seen,
            "closed_at": posting.closed_at,
            "status_changed_at": posting.status_changed_at,
            "url": posting.url,
            "verdict": "quarantined" if posting.is_quarantined else "allowed",
            # The verdict was decided at ingest and isn't recomputed, so it
            # can come from a scanner since removed (e.g. Anonymize or
            # Language); this column shows which ones decided it.
            "flagged_by": ", ".join(flagged_by_posting.get(posting.id, [])),
            "content": posting.normalized_text,
        }
        scanner_scores = scores_by_posting.get(posting.id, {})
        for name in SCANNER_NAMES:
            record[name] = scanner_scores.get(name)
        records.append(record)

    return pd.DataFrame.from_records(records, index="id")


def status_label(status: str) -> str:
    return status.replace("_", " ")


def date_or(value, missing: str) -> str:
    return f"{value:%Y-%m-%d}" if pd.notna(value) else missing


st.set_page_config(page_title="Job postings", layout="wide")
st.title("Job postings")
st.caption(
    "Every stored posting except duplicates, newest first. Change a job's status "
    "in the Status column; it's saved straight away. Last seen and Closed come "
    "from ingest runs: when the posting was last on the company's board, and "
    "when it left it. Also its text after PII redaction and the guard, the "
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
    "title",
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
        "title": st.column_config.TextColumn("Title", width=320, pinned=True),
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

st.divider()
st.subheader("Inspect one posting")
selected_title = st.selectbox("Posting", df["title"] + " — " + df["company"])
if selected_title:
    row = df[df["title"] + " — " + df["company"] == selected_title].iloc[0]
    flagged_by = f" (flagged by {row['flagged_by']})" if row["flagged_by"] else ""
    st.markdown(
        f"**Status:** {status_label(row['status'])} "
        f"(changed {date_or(row['status_changed_at'], 'never')}) · "
        f"**Posted:** {date_or(row['posted'], 'unknown')} · "
        f"**Last seen:** {date_or(row['last_seen'], 'unknown')} · "
        f"**Closed:** {date_or(row['closed_at'], 'still on the board')}"
    )
    st.markdown(f"**Verdict:** {row['verdict']}{flagged_by} · [original posting]({row['url']})")
    scanner_summary = ", ".join(
        f"{name}: {row[name]:.2f}" if pd.notna(row[name]) else f"{name}: n/a"
        for name in SCANNER_NAMES
    )
    st.caption(scanner_summary)
    st.text_area("Stored text (after PII redaction and the guard)", row["content"], height=300)
