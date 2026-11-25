"""Entry point of the Streamlit app: routes to its two pages.

Run with: uv run streamlit run src/jobfit/ui/guard_review.py

- postings.py: the table of stored postings (the default page, at /).
- job.py: one posting in full, at /job?id=<posting id>; opened in a new tab
  by clicking a title in the table. Hidden from the navigation menu.
"""

import streamlit as st

st.set_page_config(page_title="Job postings", layout="wide")
st.navigation(
    [
        st.Page("postings.py", title="Job postings", default=True),
        st.Page("job.py", title="Job", url_path="job"),
    ],
    position="hidden",
).run()
