"""Streamlit page for reviewing injection-guard decisions on stored postings.

Run with: uv run streamlit run src/jobfit/ui/guard_review.py

Shows every posting's link, guard-formatted content, per-scanner scores and
the final allowed/flagged verdict, so a human can spot-check what the guard
quarantined (or missed) against the real postings, not just the adversarial
test set.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from jobfit.db.models import Company, GuardResult, Posting
from jobfit.db.session import get_session

# The current guard's scanners, as in guard.default_scanners(); keep in step
# with it. PII redaction is a separate step, not shown here. Postings stored
# before a scanner existed have no score for it (shown blank).
SCANNER_NAMES = ["InvisibleText", "PromptInjection"]


@st.cache_data(ttl=30)
def load_postings() -> pd.DataFrame:
    with get_session() as session:
        rows = session.execute(
            select(Posting, Company.name).join(Company).order_by(Posting.first_seen)
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
            "title": posting.title,
            "company": company_name,
            "location": posting.location_raw,
            # From the ATS: Greenhouse's first_published, Lever's createdAt
            # (when the job was created in Lever, possibly before it went public).
            "posted": posting.posted_at,
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

    return pd.DataFrame.from_records(records)


st.set_page_config(page_title="Guard review", layout="wide")
st.title("Injection guard review")
st.caption(
    "Every stored posting, its text after PII redaction and the guard, the "
    "current checks' scores (PromptInjection: attack probability, flagged above "
    "0.5; InvisibleText: 1 = hidden characters found), and the verdict stored at "
    "ingest, with the scanners that flagged it. Postings are scanned once, when "
    "first ingested, so verdicts from removed scanners stay until re-scanned."
)

df = load_postings()

if df.empty:
    st.warning("No postings stored yet — run `uv run python -m jobfit.ingest.cli` first.")
    st.stop()

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
    "company",
    "location",
    "posted",
    "verdict",
    "flagged_by",
    *SCANNER_NAMES,
    "url",
]
st.dataframe(
    df[table_columns],
    column_config={
        "url": st.column_config.LinkColumn("Original posting", display_text="Open"),
        "posted": st.column_config.DatetimeColumn("Posted", format="YYYY-MM-DD"),
        "verdict": st.column_config.TextColumn("Verdict"),
        "flagged_by": st.column_config.TextColumn("Flagged by"),
        **{name: st.column_config.NumberColumn(name, format="%.2f") for name in SCANNER_NAMES},
    },
    hide_index=True,
    width="stretch",
)

st.divider()
st.subheader("Inspect one posting")
selected_title = st.selectbox("Posting", df["title"] + " — " + df["company"])
if selected_title:
    row = df[df["title"] + " — " + df["company"] == selected_title].iloc[0]
    flagged_by = f" (flagged by {row['flagged_by']})" if row["flagged_by"] else ""
    posted = f"{row['posted']:%Y-%m-%d}" if pd.notna(row["posted"]) else "unknown"
    st.markdown(
        f"**Verdict:** {row['verdict']}{flagged_by} · **Posted:** {posted} · "
        f"[original posting]({row['url']})"
    )
    scanner_summary = ", ".join(
        f"{name}: {row[name]:.2f}" if pd.notna(row[name]) else f"{name}: n/a"
        for name in SCANNER_NAMES
    )
    st.caption(scanner_summary)
    st.text_area("Stored text (after PII redaction and the guard)", row["content"], height=300)
