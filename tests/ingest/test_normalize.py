from jobfit.ingest.normalize import html_to_text


def test_html_to_text_handles_double_escaped_greenhouse_content():
    # Greenhouse's job board API returns `content` with entities escaped twice:
    # literal text "&lt;p&gt;", not an actual <p> tag.
    double_escaped = "&lt;p&gt;&lt;strong&gt;Senior ML Engineer&lt;/strong&gt;&lt;/p&gt;"
    text = html_to_text(double_escaped)
    assert text == "Senior ML Engineer"
    assert "&lt;" not in text
    assert "<" not in text
