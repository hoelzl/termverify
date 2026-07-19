"""Exact `termverify.transcript/v1` comparison and its deterministic report.

The comparator is a pure consumer of the frozen v1 protocol: both inputs
must pass the strict codec's `parse_transcript` (an invalid side is a
structured input error, never a comparison result), and records compare by
canonical semantic equality of envelope and payload over the full record
sequence. The v1 equivalence rule is closed with exactly one disclosed
identity exclusion: the envelope ``run_id``, which names a run rather than
its behavior. There are no normalizers, predicates, tolerances, or
per-scenario configuration; extending the exclusion set requires an
owner-accepted amendment of the Phase 2 boundary design.

The report is a rendering of the structured verdict — never a second
comparison implementation — and it is not a golden master: no test may
assert stored report bytes as behavioral truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import rfc8785

from termverify._json import JsonValue
from termverify.transcript import (
    Record,
    TranscriptValidationError,
    parse_transcript,
)

__all__ = [
    "ComparisonVerdict",
    "MemberDifference",
    "RecordDivergence",
    "TranscriptInputError",
    "compare_transcripts",
    "render_report",
]

#: The closed v1 identity exclusion: envelope members never compared.
_EXCLUDED_ENVELOPE_MEMBERS = frozenset({"run_id"})

_REPORT_VALUE_LIMIT = 120


class TranscriptInputError(ValueError):
    """One comparison input failed the strict codec.

    An invalid side is a structured input error, not a comparison result:
    the comparator never states a verdict about bytes the codec rejects.
    """

    def __init__(self, side: Literal["left", "right"], message: str) -> None:
        super().__init__(f"{side} transcript is invalid: {message}")
        self.side = side
        self.message = message


@dataclass(frozen=True, slots=True)
class MemberDifference:
    """One differing member, located by its dotted path from the record root.

    ``left`` and ``right`` are the canonical RFC 8785 JSON encodings of the
    differing values; ``None`` means the member is absent on that side. The
    path is a rendering aid: a member name that itself contains ``.`` or
    ``[`` (for example a delivered-tier environment-variable name) is not
    escaped, so such a path can read like deeper nesting — the comparison
    itself is unaffected.
    """

    path: str
    left: str | None
    right: str | None


@dataclass(frozen=True, slots=True)
class RecordDivergence:
    """One differing record position in the compared sequences.

    A ``None`` kind means that side has no record at this sequence (the
    transcripts have different lengths); ``differences`` is then empty
    because there is nothing member-level to compare against.
    """

    sequence: int
    left_kind: str | None
    right_kind: str | None
    differences: tuple[MemberDifference, ...]


@dataclass(frozen=True, slots=True)
class ComparisonVerdict:
    """The structured outcome of one exact v1 transcript comparison."""

    equivalent: bool
    left_record_count: int
    right_record_count: int
    divergences: tuple[RecordDivergence, ...]

    @property
    def first_divergence_sequence(self) -> int | None:
        """The sequence number of the first divergence, or None."""
        if not self.divergences:
            return None
        return self.divergences[0].sequence


def _canonical(value: JsonValue) -> str:
    return rfc8785.dumps(value).decode("utf-8")


def _collect_differences(
    path: str,
    left: JsonValue,
    right: JsonValue,
    differences: list[MemberDifference],
) -> None:
    if type(left) is not type(right):
        differences.append(MemberDifference(path, _canonical(left), _canonical(right)))
        return
    if isinstance(left, dict):
        right_object = cast(dict[str, JsonValue], right)
        for key in sorted(left.keys() | right_object.keys()):
            child_path = f"{path}.{key}" if path else key
            if key not in left:
                differences.append(
                    MemberDifference(child_path, None, _canonical(right_object[key]))
                )
            elif key not in right_object:
                differences.append(
                    MemberDifference(child_path, _canonical(left[key]), None)
                )
            else:
                _collect_differences(
                    child_path, left[key], right_object[key], differences
                )
        return
    if isinstance(left, list):
        right_list = cast(list[JsonValue], right)
        if len(left) != len(right_list):
            differences.append(
                MemberDifference(path, _canonical(left), _canonical(right))
            )
            return
        for index, (left_item, right_item) in enumerate(
            zip(left, right_list, strict=True)
        ):
            _collect_differences(f"{path}[{index}]", left_item, right_item, differences)
        return
    if left != right:
        differences.append(MemberDifference(path, _canonical(left), _canonical(right)))


def _compare_records(
    sequence: int, left: Record, right: Record
) -> RecordDivergence | None:
    differences: list[MemberDifference] = []
    for key in sorted(left.keys() | right.keys()):
        if key in _EXCLUDED_ENVELOPE_MEMBERS:
            continue
        if key not in left:
            differences.append(MemberDifference(key, None, _canonical(right[key])))
        elif key not in right:
            differences.append(MemberDifference(key, _canonical(left[key]), None))
        else:
            _collect_differences(key, left[key], right[key], differences)
    if not differences:
        return None
    return RecordDivergence(
        sequence=sequence,
        left_kind=cast(str, left["kind"]),
        right_kind=cast(str, right["kind"]),
        differences=tuple(differences),
    )


def _parse_side(side: Literal["left", "right"], data: bytes) -> list[Record]:
    if type(data) is not bytes:
        raise TranscriptInputError(side, "transcript input must be bytes")
    try:
        return parse_transcript(data)
    except TranscriptValidationError as error:
        raise TranscriptInputError(side, str(error)) from error


def compare_transcripts(left: bytes, right: bytes) -> ComparisonVerdict:
    """Compare two v1 transcripts under the exact, closed equivalence rule.

    Both inputs must pass `parse_transcript`; an invalid side raises
    :class:`TranscriptInputError`. Records compare position by position by
    canonical semantic equality of envelope and payload, excluding only the
    envelope ``run_id``. The verdict lists every divergent record with its
    exact differing members in deterministic order.
    """
    left_records = _parse_side("left", left)
    right_records = _parse_side("right", right)
    divergences: list[RecordDivergence] = []
    for sequence in range(max(len(left_records), len(right_records))):
        if sequence >= len(left_records):
            divergences.append(
                RecordDivergence(
                    sequence=sequence,
                    left_kind=None,
                    right_kind=cast(str, right_records[sequence]["kind"]),
                    differences=(),
                )
            )
        elif sequence >= len(right_records):
            divergences.append(
                RecordDivergence(
                    sequence=sequence,
                    left_kind=cast(str, left_records[sequence]["kind"]),
                    right_kind=None,
                    differences=(),
                )
            )
        else:
            divergence = _compare_records(
                sequence, left_records[sequence], right_records[sequence]
            )
            if divergence is not None:
                divergences.append(divergence)
    return ComparisonVerdict(
        equivalent=not divergences,
        left_record_count=len(left_records),
        right_record_count=len(right_records),
        divergences=tuple(divergences),
    )


def _bounded(rendered: str | None) -> str:
    if rendered is None:
        return "absent"
    encoded = rendered.encode("utf-8")
    if len(encoded) <= _REPORT_VALUE_LIMIT:
        return rendered
    prefix = encoded[:_REPORT_VALUE_LIMIT].decode("utf-8", errors="ignore")
    hidden = len(encoded) - len(prefix.encode("utf-8"))
    return f"{prefix}... (+{hidden} bytes)"


def render_report(verdict: ComparisonVerdict) -> str:
    """Render a verdict as deterministic plain text.

    Identical verdicts produce identical report text. The report is a
    rendering of the structured verdict only; it performs no comparison of
    its own, and long member values are truncated with a disclosed byte
    count so the member-level diff stays bounded and human-readable.
    """
    if type(verdict) is not ComparisonVerdict:
        raise TypeError("render_report requires a ComparisonVerdict")
    lines = [
        "termverify.transcript/v1 comparison",
        f"left records: {verdict.left_record_count}",
        f"right records: {verdict.right_record_count}",
    ]
    if verdict.equivalent:
        lines.append("verdict: equivalent (run_id excluded by rule)")
    else:
        lines.append(
            "verdict: divergent"
            f" ({len(verdict.divergences)} divergent records,"
            f" first at seq {verdict.first_divergence_sequence})"
        )
    for divergence in verdict.divergences:
        if divergence.left_kind is None:
            lines.append(
                f"seq {divergence.sequence}: missing on the left side"
                f" (right kind: {divergence.right_kind})"
            )
            continue
        if divergence.right_kind is None:
            lines.append(
                f"seq {divergence.sequence}: missing on the right side"
                f" (left kind: {divergence.left_kind})"
            )
            continue
        lines.append(
            f"seq {divergence.sequence}:"
            f" left kind {divergence.left_kind},"
            f" right kind {divergence.right_kind}"
        )
        for difference in divergence.differences:
            lines.append(
                f"  {difference.path}:"
                f" left {_bounded(difference.left)}"
                f" | right {_bounded(difference.right)}"
            )
    return "\n".join(lines) + "\n"
