"""RFC 5646 language-tag validation shared by v1 protocol boundaries."""

from __future__ import annotations

_GRANDFATHERED_LANGUAGE_TAGS = frozenset(
    {
        "art-lojban",
        "cel-gaulish",
        "en-gb-oed",
        "i-ami",
        "i-bnn",
        "i-default",
        "i-enochian",
        "i-hak",
        "i-klingon",
        "i-lux",
        "i-mingo",
        "i-navajo",
        "i-pwn",
        "i-tao",
        "i-tay",
        "i-tsu",
        "no-bok",
        "no-nyn",
        "sgn-be-fr",
        "sgn-be-nl",
        "sgn-ch-de",
        "zh-guoyu",
        "zh-hakka",
        "zh-min",
        "zh-min-nan",
        "zh-xiang",
    }
)


def is_well_formed_language_tag(value: str) -> bool:
    """Return whether *value* is a supported well-formed RFC 5646 language tag."""
    if value == "C":
        return True
    if value.lower() in _GRANDFATHERED_LANGUAGE_TAGS:
        return True

    subtags = value.split("-")
    if any(
        not 1 <= len(subtag) <= 8 or not subtag.isascii() or not subtag.isalnum()
        for subtag in subtags
    ):
        return False
    if subtags[0].lower() == "x":
        return len(subtags) > 1

    primary = subtags[0]
    if not primary.isalpha() or not 2 <= len(primary) <= 8:
        return False
    index = 1
    if len(primary) <= 3:
        extlang_count = 0
        while (
            index < len(subtags)
            and len(subtags[index]) == 3
            and subtags[index].isalpha()
            and extlang_count < 3
        ):
            index += 1
            extlang_count += 1
    if index < len(subtags) and len(subtags[index]) == 4 and subtags[index].isalpha():
        index += 1
    if index < len(subtags) and (
        (len(subtags[index]) == 2 and subtags[index].isalpha())
        or (len(subtags[index]) == 3 and subtags[index].isdigit())
    ):
        index += 1

    variants: set[str] = set()
    while index < len(subtags) and (
        5 <= len(subtags[index]) <= 8
        or (len(subtags[index]) == 4 and subtags[index][0].isdigit())
    ):
        variant = subtags[index].lower()
        if variant in variants:
            return False
        variants.add(variant)
        index += 1

    extension_singletons: set[str] = set()
    while (
        index < len(subtags)
        and len(subtags[index]) == 1
        and subtags[index].lower() != "x"
    ):
        singleton = subtags[index].lower()
        if singleton in extension_singletons:
            return False
        extension_singletons.add(singleton)
        index += 1
        extension_start = index
        while index < len(subtags) and len(subtags[index]) >= 2:
            index += 1
        if index == extension_start:
            return False

    if index < len(subtags) and subtags[index].lower() == "x":
        index += 1
        if index == len(subtags):
            return False
        index = len(subtags)
    return index == len(subtags)
