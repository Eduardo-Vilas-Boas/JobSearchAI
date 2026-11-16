from __future__ import annotations

import html
import unicodedata

from bs4 import BeautifulSoup
from lingua import Language, LanguageDetectorBuilder

_DETECTOR = (
    LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.FRENCH, Language.GERMAN)
    .with_low_accuracy_mode()
    .build()
)

_LANGUAGE_CODES = {
    Language.ENGLISH: "en",
    Language.FRENCH: "fr",
    Language.GERMAN: "de",
}


def html_to_text(raw_html: str) -> str:
    """Strips HTML markup, collapsing whitespace left behind by block tags.

    Unescapes entities first: Greenhouse's job board API returns `content`
    double-escaped (literal "&lt;p&gt;" text, not a real `<p>` tag), so without
    this the tags never parse and the output is full of stray "&lt;"/"&gt;".
    Unescaping already-normal HTML (e.g. Lever's) is a harmless no-op.
    """
    text = BeautifulSoup(html.unescape(raw_html), "lxml").get_text(separator="\n")
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def detect_language(text: str) -> str | None:
    """Returns 'en', 'fr' or 'de', or None if confidence is too low to call it."""
    language = _DETECTOR.detect_language_of(text)
    return _LANGUAGE_CODES.get(language)
