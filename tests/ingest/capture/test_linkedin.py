"""LinkedIn job pages, as the browser extension captures them (the rendered
page's HTML), parsed into a RawPosting.

The committed fixture is hand-written with the real page's structure and
made-up text. `test_real_sample` also runs the parser on a real captured page
in data/html_samples/linkedin/ (gitignored, so it's skipped on a fresh
checkout); its expected values were copied from the page by hand.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobfit.config import REPO_ROOT
from jobfit.ingest.capture.linkedin import NotAJobPosting, parse_linkedin
from jobfit.ingest.normalize import html_to_text

FIXTURES = Path(__file__).parents[2] / "fixtures"
FIXTURE = FIXTURES / "linkedin_job_search.html"
# LinkedIn's newer search layout, where the job list links to the job too.
RESULTS_FIXTURE = FIXTURES / "linkedin_job_search_results.html"
RESULTS_URL = "https://www.linkedin.com/jobs/search-results/?currentJobId=4000000001"
SAMPLES = REPO_ROOT / "data" / "html_samples" / "linkedin"
REAL_SAMPLE = SAMPLES / "sample01.html"
REAL_RESULTS_SAMPLE = SAMPLES / "sample02.html"
NO_SAMPLE = "real LinkedIn sample not on this machine"

SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords=robotics&currentJobId=4000000001"
CAPTURED_AT = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _parse(url: str = SEARCH_URL, html: str | None = None):
    return parse_linkedin(html or FIXTURE.read_text(), url, CAPTURED_AT)


def test_reads_the_top_card():
    posting = _parse()

    assert posting.source == "linkedin"
    assert posting.external_id == "4000000001"
    assert posting.title == "Perception Engineer"
    assert posting.company == "Example Robotics"
    assert posting.location == "Zurich, Switzerland"


def test_url_is_the_postings_own_page_without_tracking():
    assert _parse().url == "https://www.linkedin.com/jobs/view/4000000001/"


def test_relative_posting_date_is_counted_back_from_capture_time():
    # "Reposted 2 weeks ago"
    assert _parse().posted_at == CAPTURED_AT - timedelta(weeks=2)


def test_description_is_the_job_not_the_company_blurb():
    text = html_to_text(_parse().description_html)

    assert text.startswith("About the team")
    assert "Fuse camera and lidar data on the robot." in text
    assert "MSc in computer science" in text
    assert "legged robots for industrial sites" not in text  # "About the company"


def test_postings_in_the_job_list_are_ignored():
    posting = _parse()

    assert "Data Scientist" not in posting.title
    assert posting.company != "Other Corp"


def test_standalone_job_page_url_gives_the_same_id():
    posting = _parse(url="https://www.linkedin.com/jobs/view/4000000001/?refId=xyz")

    assert posting.external_id == "4000000001"


def test_whole_page_is_kept_as_the_raw_payload():
    posting = _parse()

    assert posting.raw_payload["url"] == SEARCH_URL
    assert posting.raw_payload["html"] == FIXTURE.read_text()


def test_newer_layout_reads_the_job_pane_not_the_job_list_card():
    posting = _parse(url=RESULTS_URL, html=RESULTS_FIXTURE.read_text())

    assert posting.title == "Perception Engineer"
    assert posting.company == "Example Robotics"
    assert posting.location == "Zurich, Switzerland"
    assert posting.posted_at == CAPTURED_AT - timedelta(days=3)


def test_the_expand_button_is_not_part_of_the_description():
    posting = _parse(url=RESULTS_URL, html=RESULTS_FIXTURE.read_text())

    text = html_to_text(posting.description_html)
    assert text.endswith("100% · On-site")


def test_page_without_a_job_is_rejected():
    feed = "<html><body><main><h2>Feed</h2><p>Someone shared a post</p></main></body></html>"

    with pytest.raises(NotAJobPosting):
        _parse(url="https://www.linkedin.com/feed/", html=feed)


@pytest.mark.skipif(not REAL_SAMPLE.exists(), reason=NO_SAMPLE)
def test_real_sample():
    posting = parse_linkedin(
        REAL_SAMPLE.read_text(),
        "https://www.linkedin.com/jobs/search/?currentJobId=4489733931",
        CAPTURED_AT,
    )

    assert posting.external_id == "4489733931"
    assert posting.title == "Machine Learning Engineer"
    assert posting.company == "EPFL"
    assert posting.location == "Lausanne Metropolitan Area"
    assert posting.posted_at == CAPTURED_AT - timedelta(days=6)  # "6 days ago"
    text = html_to_text(posting.description_html)
    # Line breaks inside the page's source text are spacing, not new lines.
    assert text.startswith("About The Swiss Data Science Center (SDSC)\nThe Swiss Data")
    assert "(Ecole Polytechnique" not in text  # "About the company"


@pytest.mark.skipif(not REAL_RESULTS_SAMPLE.exists(), reason=NO_SAMPLE)
def test_real_sample_newer_layout():
    posting = parse_linkedin(
        REAL_RESULTS_SAMPLE.read_text(),
        "https://www.linkedin.com/jobs/search-results/?currentJobId=4491610897",
        CAPTURED_AT,
    )

    assert posting.external_id == "4491610897"
    assert posting.title == "Computer Vision and Machine Learning Engineer"
    assert posting.company == "Sunflower Labs"
    assert posting.location == "Stallikon, Zurich, Switzerland"
    assert posting.posted_at == CAPTURED_AT - timedelta(days=3)  # "3 days ago"
    text = html_to_text(posting.description_html)
    assert text.startswith("We are looking for a Computer Vision and Machine Learning")
    assert text.endswith("100% · On-site")
