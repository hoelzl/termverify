from __future__ import annotations

import pytest

from termverify.adapter import Cursor, Frame
from termverify.vt import (
    NORMALIZER_ID,
    NORMALIZER_VERSION,
    ScreenSnapshot,
    TerminalOutputNormalizer,
    VtNormalizationError,
    VtScreenNormalizer,
)

ESC = "\x1b"
ST = "\x1b\\"


def _normalizer(*, rows: int = 4, columns: int = 8) -> VtScreenNormalizer:
    return VtScreenNormalizer(rows=rows, columns=columns)


def _lines(normalizer: VtScreenNormalizer) -> tuple[str, ...]:
    return normalizer.snapshot().frame.lines


def test_identity_constants() -> None:
    assert NORMALIZER_ID == "termverify.vt"
    assert NORMALIZER_VERSION == "1"


def test_satisfies_port_protocol() -> None:
    normalizer: TerminalOutputNormalizer = _normalizer()
    assert isinstance(normalizer, TerminalOutputNormalizer)


def test_initial_snapshot_is_blank_home_visible_normal() -> None:
    snapshot = _normalizer(rows=2, columns=3).snapshot()
    assert snapshot == ScreenSnapshot(
        frame=Frame(lines=("   ", "   "), columns=3, rows=2),
        cursor=Cursor(column=0, row=0, visible=True),
        mode="normal",
    )


def test_construction_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError):
        VtScreenNormalizer(rows=0, columns=8)
    with pytest.raises(ValueError):
        VtScreenNormalizer(rows=4, columns=0)
    with pytest.raises(TypeError):
        VtScreenNormalizer(rows=True, columns=8)


def test_printable_text_advances_cursor() -> None:
    normalizer = _normalizer()
    normalizer.feed("hi")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines[0] == "hi      "
    assert snapshot.cursor == Cursor(column=2, row=0, visible=True)


def test_crlf_moves_to_next_line() -> None:
    normalizer = _normalizer()
    normalizer.feed("ab\r\ncd")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines[:2] == ("ab      ", "cd      ")
    assert snapshot.cursor == Cursor(column=2, row=1, visible=True)


def test_lf_keeps_column() -> None:
    normalizer = _normalizer()
    normalizer.feed("ab\ncd")
    assert _lines(normalizer)[:2] == ("ab      ", "  cd    ")


def test_backspace_moves_left_and_clamps() -> None:
    normalizer = _normalizer()
    normalizer.feed("ab\b\b\bX")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines[0] == "Xb      "
    assert snapshot.cursor.column == 1


def test_bel_is_consumed_without_effect() -> None:
    normalizer = _normalizer()
    normalizer.feed("a\x07b")
    assert _lines(normalizer)[0] == "ab      "


def test_deferred_wrap_at_last_column() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("abcd")
    snapshot = normalizer.snapshot()
    assert snapshot.cursor == Cursor(column=3, row=0, visible=True)
    normalizer.feed("e")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines == ("abcd", "e   ")
    assert snapshot.cursor == Cursor(column=1, row=1, visible=True)


def test_cr_clears_pending_wrap() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("abcd\rX")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines == ("Xbcd", "    ")
    assert snapshot.cursor == Cursor(column=1, row=0, visible=True)


def test_lf_at_bottom_scrolls_and_top_line_is_lost() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("aa\r\nbb\r\ncc")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines == ("bb  ", "cc  ")
    assert snapshot.cursor.row == 1


def test_wrap_at_bottom_scrolls() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("abcdefghi")
    assert _lines(normalizer) == ("efgh", "i   ")


def test_tab_moves_to_next_default_stop_and_last_column() -> None:
    normalizer = _normalizer(rows=2, columns=20)
    normalizer.feed("a\tb")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines[0].startswith("a       b")
    normalizer.feed("\t\t\t")
    assert normalizer.snapshot().cursor.column == 19


def test_hts_and_tbc_manage_tab_stops() -> None:
    normalizer = _normalizer(rows=2, columns=20)
    normalizer.feed(f"{ESC}[1;4H{ESC}H\r\t")
    assert normalizer.snapshot().cursor.column == 3
    normalizer.feed(f"{ESC}[0g\r\t")
    assert normalizer.snapshot().cursor.column == 8
    normalizer.feed(f"{ESC}[3g\r\t")
    assert normalizer.snapshot().cursor.column == 19


def test_cup_is_one_based_and_clamped() -> None:
    normalizer = _normalizer(rows=4, columns=8)
    normalizer.feed(f"{ESC}[2;3HX")
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines[1] == "  X     "
    normalizer.feed(f"{ESC}[99;99H")
    assert normalizer.snapshot().cursor == Cursor(column=7, row=3, visible=True)
    normalizer.feed(f"{ESC}[H")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=0, visible=True)


def test_hvp_matches_cup() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[2;2fY")
    assert _lines(normalizer)[1] == " Y      "


def test_relative_cursor_moves_clamp() -> None:
    normalizer = _normalizer(rows=4, columns=8)
    normalizer.feed(f"{ESC}[2;3H{ESC}[9A")
    assert normalizer.snapshot().cursor.row == 0
    normalizer.feed(f"{ESC}[9B{ESC}[9C")
    assert normalizer.snapshot().cursor == Cursor(column=7, row=3, visible=True)
    normalizer.feed(f"{ESC}[2D{ESC}[1A")
    assert normalizer.snapshot().cursor == Cursor(column=5, row=2, visible=True)


def test_cnl_cpl_cha_vpa() -> None:
    normalizer = _normalizer(rows=4, columns=8)
    normalizer.feed(f"{ESC}[2;5H{ESC}[1E")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=2, visible=True)
    normalizer.feed(f"{ESC}[4;5H{ESC}[2F")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=1, visible=True)
    normalizer.feed(f"{ESC}[6G")
    assert normalizer.snapshot().cursor.column == 5
    normalizer.feed(f"{ESC}[3d")
    assert normalizer.snapshot().cursor.row == 2


def test_erase_display_to_end() -> None:
    normalizer = _normalizer(rows=3, columns=4)
    normalizer.feed("aaaa\r\nbbbb\r\ncccc")
    normalizer.feed(f"{ESC}[2;3H{ESC}[0J")
    assert _lines(normalizer) == ("aaaa", "bb  ", "    ")


def test_erase_display_from_start_and_all() -> None:
    normalizer = _normalizer(rows=3, columns=4)
    normalizer.feed("aaaa\r\nbbbb\r\ncccc")
    normalizer.feed(f"{ESC}[2;2H{ESC}[1J")
    assert _lines(normalizer) == ("    ", "  bb", "cccc")
    normalizer.feed(f"{ESC}[2J")
    assert _lines(normalizer) == ("    ", "    ", "    ")


def test_erase_line_variants() -> None:
    normalizer = _normalizer(rows=1, columns=6)
    normalizer.feed("abcdef" + f"{ESC}[1;3H{ESC}[K")
    assert _lines(normalizer) == ("ab    ",)
    normalizer.feed("cdef" + f"{ESC}[1;4H{ESC}[1K")
    assert _lines(normalizer) == ("    ef",)
    normalizer.feed(f"{ESC}[2K")
    assert _lines(normalizer) == ("      ",)


def test_insert_delete_erase_characters() -> None:
    normalizer = _normalizer(rows=1, columns=6)
    normalizer.feed("abcdef" + f"{ESC}[1;2H{ESC}[2@")
    assert _lines(normalizer) == ("a  bcd",)
    normalizer.feed(f"{ESC}[1;2H{ESC}[2P")
    assert _lines(normalizer) == ("abcd  ",)
    normalizer.feed(f"{ESC}[1;1H{ESC}[3X")
    assert _lines(normalizer) == ("   d  ",)


def test_insert_delete_lines_within_region() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc")
    normalizer.feed(f"{ESC}[1;1H{ESC}[1L")
    assert _lines(normalizer) == ("  ", "aa", "bb")
    normalizer.feed(f"{ESC}[1M")
    assert _lines(normalizer) == ("aa", "bb", "  ")


def test_scroll_up_and_down() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc")
    normalizer.feed(f"{ESC}[1S")
    assert _lines(normalizer) == ("bb", "cc", "  ")
    normalizer.feed(f"{ESC}[2T")
    assert _lines(normalizer) == ("  ", "  ", "bb")


def test_scroll_margins_confine_lf_scrolling() -> None:
    normalizer = _normalizer(rows=4, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc\r\ndd")
    normalizer.feed(f"{ESC}[2;3r")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=0, visible=True)
    normalizer.feed(f"{ESC}[3;1H\n")
    assert _lines(normalizer) == ("aa", "cc", "  ", "dd")


def test_invalid_margins_are_ignored() -> None:
    normalizer = _normalizer(rows=4, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc\r\ndd")
    normalizer.feed(f"{ESC}[3;2r{ESC}[4;1H\n")
    assert _lines(normalizer) == ("bb", "cc", "dd", "  ")


def test_reverse_index_scrolls_down_at_top_margin() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc" + f"{ESC}[1;1H{ESC}M")
    assert _lines(normalizer) == ("  ", "aa", "bb")


def test_ind_and_nel() -> None:
    normalizer = _normalizer(rows=3, columns=4)
    normalizer.feed("ab" + f"{ESC}D")
    assert normalizer.snapshot().cursor == Cursor(column=2, row=1, visible=True)
    normalizer.feed(f"{ESC}E")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=2, visible=True)


def test_save_restore_cursor_esc7_esc8() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[2;3H{ESC}7{ESC}[4;5H{ESC}8")
    assert normalizer.snapshot().cursor == Cursor(column=2, row=1, visible=True)


def test_restore_without_save_goes_home() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[2;3H{ESC}8")
    assert normalizer.snapshot().cursor == Cursor(column=0, row=0, visible=True)


def test_ris_resets_everything() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed(f"ab{ESC}[?25l{ESC}[?1049h" + "xy" + f"{ESC}c")
    snapshot = normalizer.snapshot()
    assert snapshot == ScreenSnapshot(
        frame=Frame(lines=("    ", "    "), columns=4, rows=2),
        cursor=Cursor(column=0, row=0, visible=True),
        mode="normal",
    )


def test_charset_and_keypad_sequences_are_consumed() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}(B{ESC})0{ESC}*A{ESC}+B{ESC}={ESC}>ok")
    assert _lines(normalizer)[0].startswith("ok")


def test_sgr_is_consumed_and_not_rendered() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[1;31;40mred{ESC}[0m")
    assert _lines(normalizer)[0] == "red     "


def test_cursor_visibility_dectcem() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[?25l")
    assert normalizer.snapshot().cursor.visible is False
    normalizer.feed(f"{ESC}[?25h")
    assert normalizer.snapshot().cursor.visible is True


def test_cursor_blink_mode_is_consumed() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[?12h{ESC}[?12l")
    assert normalizer.snapshot().cursor.visible is True


def test_combined_private_modes_apply_each() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}[?25;12l")
    assert normalizer.snapshot().cursor.visible is False


def test_alternate_buffer_1049_switch_and_restore() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("ab" + f"{ESC}[?1049h")
    snapshot = normalizer.snapshot()
    assert snapshot.mode == "alternate"
    assert snapshot.frame.lines == ("    ", "    ")
    normalizer.feed("zz")
    normalizer.feed(f"{ESC}[?1049l")
    snapshot = normalizer.snapshot()
    assert snapshot.mode == "normal"
    assert snapshot.frame.lines == ("ab  ", "    ")
    assert snapshot.cursor == Cursor(column=2, row=0, visible=True)


def test_alternate_buffer_1047_and_1048() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed(f"{ESC}[2;2H{ESC}[?1048h{ESC}[?1047h")
    assert normalizer.snapshot().mode == "alternate"
    normalizer.feed("q")
    normalizer.feed(f"{ESC}[?1047l")
    snapshot = normalizer.snapshot()
    assert snapshot.mode == "normal"
    normalizer.feed(f"{ESC}[?1047h")
    assert normalizer.snapshot().frame.lines == ("    ", "    ")
    normalizer.feed(f"{ESC}[?1047l{ESC}[?1048l")
    assert normalizer.snapshot().cursor == Cursor(column=1, row=1, visible=True)


def test_osc_with_bel_terminator_is_consumed() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}]0;window title\x07ok")
    assert _lines(normalizer)[0] == "ok      "


def test_osc_readiness_marker_with_st_never_renders() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}]7791;ready{ST}done")
    assert _lines(normalizer)[0] == "done    "


def test_dcs_sos_pm_apc_are_consumed() -> None:
    normalizer = _normalizer()
    normalizer.feed(f"{ESC}Pdata{ST}a{ESC}Xs{ST}b{ESC}^p{ST}c{ESC}_q{ST}d")
    assert _lines(normalizer)[0] == "abcd    "


def test_sequences_split_across_chunks_parse_identically() -> None:
    unsplit = _normalizer()
    unsplit.feed(f"{ESC}[2;3HX{ESC}]0;t\x07Y")
    split = _normalizer()
    for character in f"{ESC}[2;3HX{ESC}]0;t\x07Y":
        split.feed(character)
    assert unsplit.snapshot() == split.snapshot()


def test_snapshot_is_pure_and_repeatable() -> None:
    normalizer = _normalizer()
    normalizer.feed("abc")
    first = normalizer.snapshot()
    second = normalizer.snapshot()
    assert first == second
    other = _normalizer()
    other.feed("abc")
    assert other.snapshot() == first


def test_feed_rejects_non_string() -> None:
    normalizer = _normalizer()
    with pytest.raises(TypeError):
        normalizer.feed(b"abc")  # type: ignore[arg-type]


def test_unknown_c0_control_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed("\x01")


def test_delete_character_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed("\x7f")


def test_unknown_escape_final_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError) as excinfo:
        normalizer.feed(f"{ESC}#8")
    assert "#" in str(excinfo.value) or "8" in str(excinfo.value)


def test_unknown_csi_final_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[5i")


def test_unknown_private_mode_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[?2004h")


def test_unknown_erase_selector_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[3J")


def test_stray_string_terminator_in_osc_requires_backslash() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}]0;t{ESC}Z")


def test_resize_pads_and_crops_preserving_top_left() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("abcd\r\nefgh")
    normalizer.notify_resize(rows=3, columns=2)
    snapshot = normalizer.snapshot()
    assert snapshot.frame.lines == ("ab", "ef", "  ")
    assert snapshot.frame.columns == 2
    normalizer.notify_resize(rows=1, columns=6)
    assert normalizer.snapshot().frame.lines == ("ab    ",)


def test_resize_clamps_cursor_and_resets_margins() -> None:
    normalizer = _normalizer(rows=4, columns=8)
    normalizer.feed(f"{ESC}[2;3r{ESC}[4;8H")
    normalizer.notify_resize(rows=2, columns=4)
    assert normalizer.snapshot().cursor == Cursor(column=3, row=1, visible=True)
    normalizer.feed(f"{ESC}[2;1H\n")
    assert normalizer.snapshot().cursor.row == 1


def test_resize_rejects_invalid_dimensions() -> None:
    normalizer = _normalizer()
    with pytest.raises(ValueError):
        normalizer.notify_resize(rows=0, columns=4)
    with pytest.raises(TypeError):
        normalizer.notify_resize(rows=2, columns="4")  # type: ignore[arg-type]


def test_resize_applies_to_both_buffers() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("ab" + f"{ESC}[?1049h{ESC}[H" + "cd")
    normalizer.notify_resize(rows=2, columns=2)
    assert normalizer.snapshot().frame.lines == ("cd", "  ")
    normalizer.feed(f"{ESC}[?1049l")
    assert normalizer.snapshot().frame.lines == ("ab", "  ")


def test_frame_lines_are_exact_width() -> None:
    normalizer = _normalizer(rows=3, columns=5)
    normalizer.feed("ab")
    for line in _lines(normalizer):
        assert len(line) == 5


def test_snapshot_aggregate_validates_fields() -> None:
    frame = Frame(lines=("  ",), columns=2, rows=1)
    cursor = Cursor(column=0, row=0, visible=True)
    with pytest.raises(TypeError):
        ScreenSnapshot(frame="frame", cursor=cursor, mode="normal")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ScreenSnapshot(frame=frame, cursor="cursor", mode="normal")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ScreenSnapshot(frame=frame, cursor=cursor, mode="fullscreen")


def test_malformed_csi_byte_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[2\x01H")


def test_non_hl_private_mode_final_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[?25q")


def test_colon_parameter_outside_sgr_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[1:2H")


def test_unknown_erase_line_selector_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[4K")


def test_unknown_tab_clear_selector_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[1g")


def test_lf_below_bottom_margin_at_last_row_stays_put() -> None:
    normalizer = _normalizer(rows=4, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc\r\ndd" + f"{ESC}[1;2r{ESC}[4;1H\n")
    assert normalizer.snapshot().cursor.row == 3
    assert _lines(normalizer) == ("aa", "bb", "cc", "dd")


def test_reverse_index_above_top_margin_moves_up() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed(f"{ESC}[2;3r{ESC}[3;1H{ESC}M{ESC}M")
    assert normalizer.snapshot().cursor.row == 1


def test_reverse_index_at_first_row_above_top_margin_stays_put() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed("aa" + f"{ESC}[2;3r{ESC}[1;1H{ESC}M")
    assert normalizer.snapshot().cursor.row == 0
    assert _lines(normalizer)[0] == "aa"


def test_reentering_alternate_buffer_is_idempotent() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed(f"{ESC}[?1049h" + "ab" + f"{ESC}[?1049h")
    snapshot = normalizer.snapshot()
    assert snapshot.mode == "alternate"
    assert snapshot.frame.lines[0] == "ab  "
    normalizer.feed(f"{ESC}[?1049l{ESC}[?1049l")
    assert normalizer.snapshot().mode == "normal"


def test_insert_delete_lines_outside_margins_are_ignored() -> None:
    normalizer = _normalizer(rows=3, columns=2)
    normalizer.feed("aa\r\nbb\r\ncc" + f"{ESC}[1;2r{ESC}[3;1H{ESC}[1L{ESC}[1M")
    assert _lines(normalizer) == ("aa", "bb", "cc")


def test_c1_control_characters_fail_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed("\x9b31mred")


def test_private_mode_with_sgr_final_fails_closed() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[?1049m")


def test_intermediate_bytes_fail_closed_as_unsupported() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError) as excinfo:
        normalizer.feed(f"{ESC}[1 q")
    assert "unsupported control sequence" in str(excinfo.value)
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[1 m")


def test_parser_returns_to_ground_after_error() -> None:
    normalizer = _normalizer()
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}[2\x01H")
    normalizer.feed("A")
    assert _lines(normalizer)[0].startswith("A")
    with pytest.raises(VtNormalizationError):
        normalizer.feed(f"{ESC}]0;t{ESC}Z")
    normalizer.feed("B")
    assert _lines(normalizer)[0].startswith("AB")


def test_save_restore_preserves_pending_wrap() -> None:
    normalizer = _normalizer(rows=2, columns=4)
    normalizer.feed("abcd" + f"{ESC}7{ESC}8" + "e")
    assert _lines(normalizer) == ("abcd", "e   ")


def test_vertical_moves_stop_at_scroll_margins() -> None:
    normalizer = _normalizer(rows=4, columns=2)
    normalizer.feed(f"{ESC}[2;3r{ESC}[3;1H{ESC}[9A")
    assert normalizer.snapshot().cursor.row == 1
    normalizer.feed(f"{ESC}[9B")
    assert normalizer.snapshot().cursor.row == 2
    normalizer.feed(f"{ESC}[1;1H{ESC}[9B")
    assert normalizer.snapshot().cursor.row == 2
    normalizer.feed(f"{ESC}[4;1H{ESC}[9A")
    assert normalizer.snapshot().cursor.row == 1
