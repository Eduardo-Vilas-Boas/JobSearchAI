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

SCANNER_NAMES = ["Anonymize", "InvisibleText", "PromptInjection", "Regex"]


@st.cache_data(ttl=30)
def load_postings() -> pd.DataFrame:
    with get_session() as session:
        rows = session.execute(
            select(Posting, Company.name).join(Company).order_by(Posting.first_seen)
        ).all()
        guard_rows = session.execute(
            select(GuardResult.posting_id, GuardResult.scanner, GuardResult.score)
        ).all()

    scores_by_posting: dict = {}
    for posting_id, scanner, score in guard_rows:
        scores_by_posting.setdefault(posting_id, {})[scanner] = score

    records = []
    for posting, company_name in rows:
        record = {
            "title": posting.title,
            "company": company_name,
            "location": posting.location_raw,
            "url": posting.url,
            "verdict": "flagged" if posting.is_quarantined else "allowed",
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
    "Every stored posting, the content fed to LLM Guard's scanners, their "
    "per-scanner scores (-1 = clean, 0-1 = risk), and the final verdict."
)

df = load_postings()

if df.empty:
    st.warning("No postings stored yet — run `uv run python -m jobfit.ingest.cli` first.")
    st.stop()

verdict_filter = st.radio("Show", ["All", "Flagged only", "Allowed only"], horizontal=True)
if verdict_filter == "Flagged only":
    df = df[df["verdict"] == "flagged"]
elif verdict_filter == "Allowed only":
    df = df[df["verdict"] == "allowed"]

st.caption(f"{len(df)} postings")

table_columns = ["title", "company", "location", "verdict", *SCANNER_NAMES, "url"]
st.dataframe(
    df[table_columns],
    column_config={
        "url": st.column_config.LinkColumn("Original posting", display_text="Open"),
        "verdict": st.column_config.TextColumn("Verdict"),
        **{name: st.column_config.NumberColumn(name, format="%.2f") for name in SCANNER_NAMES},
    },
    hide_index=True,
    use_container_width=True,
)

st.divider()
st.subheader("Inspect one posting")
selected_title = st.selectbox("Posting", df["title"] + " — " + df["company"])
if selected_title:
    row = df[df["title"] + " — " + df["company"] == selected_title].iloc[0]
    st.markdown(f"**Verdict:** {row['verdict']} · [original posting]({row['url']})")
    scanner_summary = ", ".join(f"{name}: {row[name]:.2f}" for name in SCANNER_NAMES)
    st.caption(scanner_summary)
    st.text_area("Content fed to the guard (post-redaction)", row["content"], height=300)
