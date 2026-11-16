from jobfit.ingest.normalize import detect_language, html_to_text, normalize_unicode


def test_html_to_text_strips_markup_and_collapses_whitespace():
    html = "<p>We need a <strong>Machine Learning</strong> Engineer.</p>\n<ul><li>Python</li></ul>"
    text = html_to_text(html)
    assert "<" not in text
    assert "Machine Learning" in text
    assert "Python" in text


def test_normalize_unicode_applies_nfkc():
    text = normalize_unicode("café")  # composed form already NFKC-stable
    assert text == "café"
    assert normalize_unicode("ﬁ") == "fi"  # ligature decomposes under NFKC


def test_detect_language_english():
    assert (
        detect_language("We are looking for a senior machine learning engineer in Zurich.") == "en"
    )


def test_detect_language_french():
    assert (
        detect_language("Nous recherchons un ingénieur en apprentissage automatique à Genève.")
        == "fr"
    )


def test_detect_language_german():
    assert (
        detect_language("Wir suchen einen erfahrenen Machine-Learning-Ingenieur in Zürich.") == "de"
    )


def test_html_to_text_handles_double_escaped_greenhouse_content():
    # Greenhouse's job board API returns `content` with entities escaped twice:
    # literal text "&lt;p&gt;", not an actual <p> tag.
    double_escaped = "&lt;p&gt;&lt;strong&gt;Senior ML Engineer&lt;/strong&gt;&lt;/p&gt;"
    text = html_to_text(double_escaped)
    assert text == "Senior ML Engineer"
    assert "&lt;" not in text
    assert "<" not in text
