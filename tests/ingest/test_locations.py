"""Location matching for dedup: two postings are only the same job if their
locations name the same set of places, however each spells or orders them."""

import pytest

from jobfit.ingest.locations import locations_conflict


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Zürich", "Zurich"),
        ("Genève", "Geneva"),
        ("Geneva, Barcelona", "Barcelona; Geneva"),
        ("London; ", "London"),
        ("Geneva, Switzerland", "Geneva"),
        ("San Mateo, CA", "San Mateo"),
        ("Austin, Texas, London", "London, Austin, Texas"),
    ],
)
def test_the_same_places_written_differently_do_not_conflict(a, b):
    assert not locations_conflict(a, b)
    assert not locations_conflict(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("London", "Bochum"),
        ("Geneva, Barcelona", "Tampere"),
        ("Geneva, Switzerland", "Paris, France"),
        ("Remote USA", "Remote DEU"),
        ("Remote USA", "Austin, Texas"),
    ],
)
def test_places_with_nothing_in_common_conflict(a, b):
    assert locations_conflict(a, b)
    assert locations_conflict(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Geneva, Barcelona", "Geneva"),
        ("Geneva, Switzerland, Paris, France", "Paris"),
        ("Austin, Texas, London", "London"),
        ("San Mateo, CA, Remote USA", "Remote USA"),
    ],
)
def test_overlapping_but_different_places_conflict(a, b):
    """The same role in an extra city can be a different team: only the same
    set of places makes it the same job."""
    assert locations_conflict(a, b)
    assert locations_conflict(b, a)


@pytest.mark.parametrize("missing", [None, "", "  ", ";"])
def test_a_missing_location_conflicts_with_any_known_one(missing):
    assert locations_conflict(missing, "London")
    assert locations_conflict("London", missing)


@pytest.mark.parametrize(("a", "b"), [(None, None), (None, ""), ("  ", ";")])
def test_two_missing_locations_do_not_conflict(a, b):
    assert not locations_conflict(a, b)


def test_unrecognised_places_are_compared_as_text():
    assert not locations_conflict("Atlantis  HQ", "atlantis hq")
    assert locations_conflict("Atlantis HQ", "Bochum")
