"""Curated top-level import surface for external adapter authors (issue #149).

External subjects implement ``Adapter``, ``ConstraintPorts``, and
``DirectApplication`` today by importing from module paths. These tests pin the
curated top-level re-export surface: every adapter-author contract name is
importable from ``termverify`` itself and is identical to its module-path
definition, so both import styles stay interchangeable.

Issue #198 extended the surface with the two things an adapter author
otherwise had to reach for behind an underscore or a module path: the
authoritative transcript codec and the closed ``termverify.key/v1`` and
``termverify.key-encoding/v1`` registries.
"""

from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

import termverify
import termverify._key_encoding_v1
import termverify._key_v1
import termverify.adapter
import termverify.direct
import termverify.transcript

_FIXTURES = Path(__file__).parent / "fixtures" / "transcripts" / "v1"

_HEADLINE_NAMES = (
    "Adapter",
    "ConstraintPorts",
    "DirectAdapter",
    "DirectApplication",
)

#: Codec names re-exported from ``termverify.transcript``.
_CODEC_NAMES = (
    "TranscriptValidationError",
    "parse_transcript",
    "serialize_transcript",
)

#: Registry names promoted out of private modules by issue #198, mapped to
#: the module that defines them.
_REGISTRY_SOURCES = {
    "KEY_NAMES": termverify._key_v1,
    "is_key_chord": termverify._key_v1,
    "encode_key_chord": termverify._key_encoding_v1,
}


def test_headline_contract_names_are_importable_from_the_top_level() -> None:
    for name in _HEADLINE_NAMES:
        assert hasattr(termverify, name), name
        assert name in termverify.__all__, name


def test_every_adapter_contract_name_is_reexported_identically() -> None:
    for name in termverify.adapter.__all__:
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(termverify.adapter, name), name


def test_every_direct_runtime_name_is_reexported_identically() -> None:
    for name in termverify.direct.__all__:
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(termverify.direct, name), name


def test_every_codec_name_is_reexported_identically() -> None:
    for name in _CODEC_NAMES:
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(termverify.transcript, name), name


def test_every_registry_name_is_reexported_identically() -> None:
    for name, module in _REGISTRY_SOURCES.items():
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(module, name), name


def test_the_promoted_registries_need_no_private_import() -> None:
    """The point of the promotion: chord validation and encoding from the top."""
    assert "Control" in termverify.KEY_NAMES
    assert "ArrowUp" in termverify.KEY_NAMES
    assert "Ctrl" not in termverify.KEY_NAMES
    assert termverify.is_key_chord(["Control", "c"])
    assert not termverify.is_key_chord(["Ctrl", "c"])
    assert termverify.encode_key_chord(["Control", "c"]) == "\x03"


class _Chord(NamedTuple):
    """A plausible adapter-author modelling of a chord — and not one."""

    modifier: str
    base: str


def test_the_promoted_encoder_rejects_a_chord_by_exact_container_type() -> None:
    """The documented strictness: a NamedTuple of key names is not a chord.

    The adapter-author guide promises the container rejection is
    indistinguishable from an invalid-chord rejection, and that a type
    checker cannot warn about it — both are pinned here, since the guide
    tells authors to model chords as plain tuples because of it.
    """
    assert termverify.is_key_chord(list(_Chord("Control", "c")))
    assert not termverify.is_key_chord(_Chord("Control", "c"))

    valid_names = _Chord("Control", "c")
    container = _message_of(lambda: termverify.encode_key_chord(valid_names))
    invalid = _message_of(lambda: termverify.encode_key_chord(["Ctrl", "c"]))
    assert container == invalid == "keys must be one canonical termverify.key/v1 chord"


def _message_of(call: Callable[[], object]) -> str:
    with pytest.raises(ValueError) as raised:
        call()
    return str(raised.value)


def test_the_promoted_codec_round_trips_from_the_top_level() -> None:
    """Both codec halves, exercised without a module-path import."""
    data = (_FIXTURES / "valid" / "basic.jsonl").read_bytes()
    assert termverify.serialize_transcript(termverify.parse_transcript(data)) == data


def test_the_promoted_codec_rejects_a_non_transcript_from_the_top_level() -> None:
    """The exported error type is the one the exported codec actually raises."""
    with pytest.raises(termverify.TranscriptValidationError):
        termverify.parse_transcript(b"not a transcript\n")
    with pytest.raises(termverify.TranscriptValidationError):
        termverify.serialize_transcript([])


def test_dunder_all_is_exactly_the_curated_surface() -> None:
    curated = (
        set(termverify.adapter.__all__)
        | set(termverify.direct.__all__)
        | set(_CODEC_NAMES)
        | set(_REGISTRY_SOURCES)
        | {
            "TRANSCRIPT_SCHEMA_V1_ID",
            "__version__",
            "persist_transcript_evidence",
            "transcript_schema_v1_bytes",
            "transcript_schema_v1_json",
        }
    )
    assert set(termverify.__all__) == curated


def test_dunder_all_is_sorted_deduplicated_and_resolvable() -> None:
    assert list(termverify.__all__) == sorted(set(termverify.__all__))
    for name in termverify.__all__:
        getattr(termverify, name)
