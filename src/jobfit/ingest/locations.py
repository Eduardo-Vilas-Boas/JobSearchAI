"""Turns a posting's free-text location into a set of places, for dedup.

ATS location fields are free text: "Geneva, Barcelona", "Barcelona; Geneva",
"Geneva, Switzerland, Paris, France", "San Mateo, CA, Remote USA". Commas
separate both one city from the next and a city from its country or state,
so each piece is looked up instead: cities become their GeoNames id
(spelling-independent: Zurich, Zürich), countries and US states are dropped
as qualifiers, "Remote ..." stays its own place, and anything unrecognised is
kept as normalized text.
"""

from __future__ import annotations

import re
from functools import cache

import geonamescache

_SEPARATORS = re.compile(r"[,;/|]")


def locations_conflict(location_a: str | None, location_b: str | None) -> bool:
    """True unless both locations name the same set of places (the user's rule).

    Overlap isn't enough: the same role in Geneva, and in Geneva and Barcelona,
    can be two teams hiring separately, so both postings are kept. A missing
    location is the empty set: it matches only another missing location.
    """
    return places(location_a) != places(location_b)


def places(location: str | None) -> frozenset[str]:
    """The places a location names, as comparable keys."""
    found: set[str] = set()
    qualifiers: set[str] = set()
    for piece in _SEPARATORS.split(location or ""):
        name = " ".join(piece.lower().split())
        if not name:
            continue
        if name.startswith("remote"):
            found.add(name)
        elif name in _city_ids():
            found.add(f"city:{_city_ids()[name]}")
        elif name in _regions():
            qualifiers.add(f"region:{name}")
        else:
            found.add(name)
    # A location that is only a country ("Switzerland") still names a place.
    return frozenset(found or qualifiers)


@cache
def _city_ids() -> dict[str, int]:
    """Lowercased city name or alternate name -> GeoNames id. An ambiguous
    name ("London", "Paris") goes to its most populous city."""
    ids: dict[str, int] = {}
    cities = sorted(
        geonamescache.GeonamesCache().get_cities().values(), key=lambda c: c["population"]
    )
    for city in cities:  # least populous first, so bigger cities overwrite
        for name in [city["name"], *city["alternatenames"]]:
            ids[name.lower()] = city["geonameid"]
    # Country and state codes ("CA", "USA") are qualifiers, even where some
    # city lists them as an alternate name. Full names that are also cities
    # (Singapore, Luxembourg) stay cities.
    for code in _region_codes():
        ids.pop(code, None)
    return ids


@cache
def _regions() -> frozenset[str]:
    """Lowercased country names and ISO codes, and US state names and codes."""
    gc = geonamescache.GeonamesCache()
    names: set[str] = set()
    for country in gc.get_countries().values():
        names.update((country["name"], country["iso"], country["iso3"]))
    for state in gc.get_us_states().values():
        names.update((state["name"], state["code"]))
    return frozenset(name.lower() for name in names)


@cache
def _region_codes() -> frozenset[str]:
    gc = geonamescache.GeonamesCache()
    codes: set[str] = set()
    for country in gc.get_countries().values():
        codes.update((country["iso"], country["iso3"]))
    codes.update(state["code"] for state in gc.get_us_states().values())
    return frozenset(code.lower() for code in codes)
