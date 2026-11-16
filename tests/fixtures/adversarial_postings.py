"""Loads the adversarial/benign posting set for guard testing.

Section 1's "done when" criteria calls for 30 hand-written adversarial
postings; the 8 in adversarial_postings.json cover the main attack shapes
and unblock guard development now. Growing this set to 30 (with the
catch-rate / false-positive eval from Section 4) is a follow-up, not done
here. Each entry has a descriptive key (not a list index) so test failures
and parametrize IDs name the attack, not "posting3".
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "adversarial_postings.json").read_text())

ADVERSARIAL_POSTINGS: dict[str, str] = _DATA["adversarial"]
BENIGN_POSTINGS: dict[str, str] = _DATA["benign"]
