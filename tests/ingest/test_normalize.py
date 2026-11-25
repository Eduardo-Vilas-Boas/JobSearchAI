from jobfit.ingest.normalize import detect_language, html_to_text


def test_html_to_text_handles_double_escaped_greenhouse_content():
    # Greenhouse's job board API returns `content` with entities escaped twice:
    # literal text "&lt;p&gt;", not an actual <p> tag.
    double_escaped = "&lt;p&gt;&lt;strong&gt;Senior ML Engineer&lt;/strong&gt;&lt;/p&gt;"
    text = html_to_text(double_escaped)
    assert text == "Senior ML Engineer"
    assert "&lt;" not in text
    assert "<" not in text


def test_english_full_of_product_names_is_english():
    """Tech postings are lists of product names; lingua's low-accuracy mode
    called this German (it did so for 7 of 137 stored English postings)."""
    text = "\n".join(
        [
            "IT Operations Engineer",
            "Experience with PyTorch or TensorFlow, ONNX, TensorRT, CUDA",
            "Strong programming skills in Python and C++",
            "Manage Microsoft 365, Intune, Jamf and Okta for our Zurich office",
            "Support onboarding and offboarding, hardware inventory and SaaS licences",
            "Work permit in Switzerland required",
            "100% · On-site",
        ]
    )

    assert detect_language(text) == "en"


def test_german_and_french_postings_are_recognised():
    german = "Wir suchen eine erfahrene Ingenieurin für maschinelles Lernen in Zürich."
    french = "Nous recherchons un ingénieur en apprentissage automatique à Lausanne."

    assert (detect_language(german), detect_language(french)) == ("de", "fr")
