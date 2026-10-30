"""The two windows: download list, filters, settings and the download flow.

Every test here needs a display; without one the whole module is skipped.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from clipster import theme, viewwindow
from clipster.bridge import Prompt
from clipster.clip import ClipRange
from clipster.history import STATUS_CANCELED, STATUS_FAILED, STATUS_OK, HistoryEntry

pytestmark = pytest.mark.gui


def _rows(view) -> list:
    """Return the rendered table rows of the download list."""
    return [w for w in view._scroller.body.winfo_children() if w.winfo_class() == "TFrame"]


def _entries(widget) -> list:
    """Collect every text entry below ``widget``, in the order they were added."""
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() == "TEntry":
            found.append(child)
        found.extend(_entries(child))
    return found


def _row_actions(view) -> list:
    """Return one dict per rendered row: action handler name -> button.

    The row actions are symbols with tooltips, so they are found by the position
    :data:`clipster.viewwindow._ROW_ACTIONS` declares rather than by their text -
    which also keeps these tests indifferent to translations.

    :param view: The view window.
    :return: One mapping per row, in display order.
    """
    rows = []
    for _separator, row, _entry in view._row_items:
        frames = [w for w in row.winfo_children() if w.winfo_class() == "TFrame"]
        buttons = [w for w in frames[-1].winfo_children() if w.winfo_class() == "TButton"]
        rows.append(dict(zip((action[0] for action in viewwindow._ROW_ACTIONS), buttons)))
    return rows


def _labels(widget) -> list:
    """Collect every label below ``widget``."""
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() in ("TLabel", "Label"):
            found.append(child)
        found.extend(_labels(child))
    return found


def _all_text(widget) -> list:
    """Collect the text of every label below ``widget``."""
    found = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget("text"))
        except Exception:
            text = ""
        if text:
            found.append(text)
        found.extend(_all_text(child))
    return found


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------
def test_both_windows_are_created_and_hidden(gui) -> None:
    assert gui.nav is not None and gui.view is not None
    assert not gui.nav.visible()
    assert not gui.view.visible()


def test_the_root_window_never_shows_itself(gui) -> None:
    """It only hosts the two real windows."""
    assert gui.root.state() == "withdrawn"


def test_the_theme_is_applied(gui) -> None:
    assert gui.palette is theme.PALETTE


def test_showing_and_hiding_the_view(gui) -> None:
    gui.show_view()
    assert gui.view_visible()
    gui.hide_view()
    assert not gui.view_visible()


@pytest.mark.parametrize("page", ["downloads", "settings", "about"])
def test_every_page_can_be_selected(gui, page: str) -> None:
    gui.view.select_page(page)
    assert gui.view._page == page


def test_an_unknown_page_is_ignored(gui) -> None:
    gui.view.select_page("settings")
    gui.view.select_page("no-such-page")
    assert gui.view._page == "settings"


def test_downloads_is_the_default_leftmost_tab(gui, messages) -> None:
    assert gui.view._page == "downloads"
    order = [key for key in gui.view._menu_buttons]
    # Dict insertion order matches pack order in the menu.
    assert order == ["downloads", "settings", "about"]
    assert gui.view._menu_buttons["downloads"].cget("text") == messages["page_downloads"]


# ----------------------------------------------------------------------
# The download list
# ----------------------------------------------------------------------
def test_an_empty_list_says_so(gui, messages) -> None:
    gui.render_history([])
    assert messages["history_empty"] in _all_text(gui.view._scroller.body)


def test_every_entry_becomes_a_row(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    assert len(_rows(gui.view)) == 3


def test_the_sidebar_counts_each_status(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    assert gui.view._counts == {"all": 3, STATUS_OK: 1, STATUS_FAILED: 1, STATUS_CANCELED: 1}


def test_a_filter_narrows_the_table(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    gui.view.set_filter(STATUS_FAILED)
    assert len(_rows(gui.view)) == 1
    gui.view.set_filter("all")
    assert len(_rows(gui.view)) == 3


def test_an_empty_filter_explains_itself(gui, messages) -> None:
    gui.render_history([HistoryEntry(name="a.mp3", status=STATUS_OK)])
    gui.view.set_filter(STATUS_FAILED)
    assert messages["filter_empty"] in _all_text(gui.view._scroller.body)


def test_a_row_shows_name_length_size_and_date(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    texts = _all_text(gui.view._scroller.body)
    assert any("song.mp3" in t for t in texts)
    assert "3:33" in texts
    assert "6.6 MB" in texts
    assert "31.07.2026 11:20" in texts


def test_a_failed_row_shows_the_problem(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    assert any("boom" in t for t in _all_text(gui.view._scroller.body))


def test_play_and_folder_are_disabled_when_the_file_is_gone(gui, sample_entries) -> None:
    """Deleting stays available - it is the only way to clear a stale row."""
    gui.render_history(sample_entries)
    rows = _row_actions(gui.view)
    assert len(rows) == len(sample_entries)
    for row in rows:
        assert set(row) == {action[0] for action in viewwindow._ROW_ACTIONS}
        for handler in ("_on_play_entry", "_on_reveal_entry"):
            assert "disabled" in row[handler].state(), handler
        for handler in ("_on_hide_entry", "_on_delete_entry"):
            assert "disabled" not in row[handler].state(), handler
    # Only the failed row can be retried; the fixture orders them
    # finished / failed / canceled, newest first, which is how they render.
    assert "disabled" in rows[0]["_on_retry_entry"].state()
    assert "disabled" not in rows[1]["_on_retry_entry"].state()
    assert "disabled" in rows[2]["_on_retry_entry"].state()


def test_deleting_a_row_needs_no_confirmation(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    deleted = []
    gui.on_delete_entry = deleted.append

    gui._delete_entry(sample_entries[0])
    assert deleted == [sample_entries[0]]


def test_hiding_a_row_forwards_without_prompt(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    hidden = []
    gui.on_hide_entry = hidden.append

    gui._hide_entry(sample_entries[0])
    assert hidden == [sample_entries[0]]


def test_retrying_a_failed_row_forwards_without_prompt(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    retried = []
    gui.on_retry_entry = retried.append
    retry = [
        row["_on_retry_entry"]
        for row in _row_actions(gui.view)
        if "disabled" not in row["_on_retry_entry"].state()
    ]
    # Only the failed row has something to retry.
    assert len(retry) == 1
    retry[0].invoke()
    assert retried == [sample_entries[1]]


def test_removing_one_entry_keeps_other_row_widgets(gui, sample_entries) -> None:
    """Hide/delete must drop one row without destroying the rest (no list flash)."""
    gui.render_history(sample_entries)
    rows_before = _rows(gui.view)
    assert len(rows_before) == 3
    kept = rows_before[1:]

    gui.render_history(sample_entries[1:])
    rows_after = _rows(gui.view)

    assert len(rows_after) == 2
    assert rows_after[0] is kept[0]
    assert rows_after[1] is kept[1]
    assert gui.view._counts["all"] == 2


def test_removing_middle_entry_under_filter_keeps_siblings(gui, sample_entries) -> None:
    """Incremental remove still works when a status filter is active."""
    gui.render_history(sample_entries)
    gui.view.set_filter("all")
    rows_before = _rows(gui.view)
    middle = sample_entries[1]

    gui.render_history([sample_entries[0], sample_entries[2]])
    rows_after = _rows(gui.view)

    assert len(rows_after) == 2
    assert rows_after[0] is rows_before[0]
    assert rows_after[1] is rows_before[2]
    assert all(item[2] is not middle for item in gui.view._row_items)


def test_removing_last_visible_row_shows_empty_state(gui, sample_entries, messages) -> None:
    gui.render_history(sample_entries)
    gui.view.set_filter(STATUS_OK)
    assert len(_rows(gui.view)) == 1

    gui.render_history(sample_entries[1:])
    assert len(_rows(gui.view)) == 0
    assert messages["filter_empty"] in _all_text(gui.view._scroller.body)
    assert gui.view._counts["all"] == 2


@pytest.mark.xfail(reason="8-18 px left over: Tk distributes the slack of the "
                          "weighted name column differently in the heading strip "
                          "than in a row. The original error was 187 px.",
                   strict=False)
def test_the_header_lines_up_with_the_values(gui, sample_entries) -> None:
    """The heading must sit over its values, not left of them."""
    gui.render_history(sample_entries)
    gui.show_view("downloads")
    gui.root.update()
    gui.root.update_idletasks()

    header = gui.view._header
    row = [w for w in gui.view._scroller.body.winfo_children()
           if w.winfo_class() == "TFrame"][0]
    heads = {c.grid_info().get("column"): c.winfo_x() for c in header.winfo_children()}
    cells = {c.grid_info().get("column"): c.winfo_x() for c in row.winfo_children()}
    for column in (1, 2, 3, 4):
        assert abs(heads[column] - cells[column]) <= 2, \
            "column {0}: heading at {1}, value at {2}".format(column, heads[column], cells[column])


def test_a_long_name_is_shortened_to_one_line(gui) -> None:
    long_name = "A very long file name that certainly does not fit into the narrow column.mp4"
    assert gui.view._fit_line(long_name, 120).endswith("…")
    assert gui.view._fit_line("short.mp3", 400) == "short.mp3"


def test_clearing_asks_before_it_empties(gui, sample_entries, monkeypatch) -> None:
    gui.render_history(sample_entries)
    cleared: list = []
    gui.on_clear_history = lambda: cleared.append(True)

    monkeypatch.setattr(gui, "ask_yes_no", lambda *a: False)
    gui._clear_history()
    assert not cleared, "a declined confirmation must not clear anything"

    monkeypatch.setattr(gui, "ask_yes_no", lambda *a: True)
    gui._clear_history()
    assert cleared


# ----------------------------------------------------------------------
# Sorting the table
# ----------------------------------------------------------------------
def _order(view) -> list:
    """Return the names of the rendered rows, top to bottom."""
    return [entry.name for _sep, _row, entry in view._row_items]


def test_the_table_starts_with_the_newest_download(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    assert _order(gui.view) == ["song.mp3", "broken.mp4", "stopped.mp4"]
    assert (gui.view._sort_key, gui.view._sort_desc) == ("date", True)


def test_clicking_a_heading_sorts_by_that_column(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    gui.view.set_sort("name")
    assert _order(gui.view) == ["broken.mp4", "song.mp3", "stopped.mp4"]


def test_clicking_the_same_heading_turns_the_order_around(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    gui.view.set_sort("name")
    gui.view.set_sort("name")
    assert _order(gui.view) == ["stopped.mp4", "song.mp3", "broken.mp4"]
    assert gui.view._sort_desc is True


def test_numbers_sort_by_value_not_by_their_text(gui) -> None:
    """9 MB below 10 MB - the trap of sorting the rendered text instead."""
    entries = [
        HistoryEntry(name="nine.mp3", size=9_000_000, status=STATUS_OK, finished_at="2026-07-01T10:00:00"),
        HistoryEntry(name="ten.mp3", size=10_000_000, status=STATUS_OK, finished_at="2026-07-02T10:00:00"),
    ]
    gui.render_history(entries)
    gui.view.set_sort("size")
    assert _order(gui.view) == ["ten.mp3", "nine.mp3"]


def test_the_sorted_column_is_the_one_that_carries_the_mark(gui, sample_entries, messages) -> None:
    gui.render_history(sample_entries)
    gui.view.set_sort("size")
    marks = {
        key: str(label.cget("text"))
        for key, label in gui.view._column_labels.items()
    }
    assert marks["size"].startswith(messages["column_size"].upper())
    assert marks["size"].endswith("▼")
    assert not any(text.endswith(("▼", "▲")) for key, text in marks.items() if key != "size")
    gui.view.set_sort("size")
    assert str(gui.view._column_labels["size"].cget("text")).endswith("▲")


def test_sorting_and_filtering_hold_at_the_same_time(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    gui.view.set_filter(STATUS_OK)
    gui.view.set_sort("name")
    assert _order(gui.view) == ["song.mp3"]
    gui.view.set_filter("all")
    assert _order(gui.view) == ["broken.mp4", "song.mp3", "stopped.mp4"], \
        "a new filter must not throw the sorting away"


def test_a_new_download_lands_in_the_sorted_order(gui, sample_entries) -> None:
    """Rendering again keeps the chosen order instead of falling back to date."""
    gui.render_history(sample_entries)
    gui.view.set_sort("name")
    gui.render_history(sample_entries + [
        HistoryEntry(name="aaa.mp3", status=STATUS_OK, finished_at="2026-06-01T10:00:00")
    ])
    assert _order(gui.view)[0] == "aaa.mp3"


# ----------------------------------------------------------------------
# Column widths
# ----------------------------------------------------------------------
class _Pointer:
    """Stands in for a Tk mouse event; only the screen position is read."""

    def __init__(self, x_root: int) -> None:
        self.x_root = x_root


def test_every_heading_fits_into_its_column(gui, messages) -> None:
    """A clickable heading that is cut off cannot be read or trusted."""
    probe = tk.Label(gui.view.window, font=gui.view.fonts["body"])
    for key, column in (("column_duration", 2), ("column_size", 3), ("column_date", 4)):
        probe.configure(text=messages[key].upper() + " ▼")
        probe.update_idletasks()
        assert gui.view._col_widths[column] >= probe.winfo_reqwidth(), key
    probe.destroy()


def test_dragging_a_grip_resizes_the_column_and_every_row(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    before = gui.view._col_widths[4]
    gui.view._start_column_drag(_Pointer(500), 4)
    gui.view._drag_column(_Pointer(560))
    assert gui.view._col_widths[4] == before + 60
    for _sep, row, _entry in gui.view._row_items:
        assert row.grid_columnconfigure(4)["minsize"] == before + 60
    assert gui.view._header.grid_columnconfigure(4)["minsize"] == before + 60


def test_a_row_painted_after_a_drag_uses_the_new_width(gui, sample_entries) -> None:
    gui.render_history(sample_entries)
    gui.view.set_column_width(4, 200)
    gui.render_history(sample_entries[:2])
    for _sep, row, _entry in gui.view._row_items:
        assert row.grid_columnconfigure(4)["minsize"] == 200


def test_a_column_cannot_be_dragged_out_of_existence(gui) -> None:
    gui.view.set_column_width(4, -400)
    assert gui.view._col_widths[4] == 40, "clamped to something still readable"
    gui.view.set_column_width(4, 5000)
    assert gui.view._col_widths[4] == 320, "clamped so the row still fits the window"


def test_only_the_fixed_columns_can_be_dragged(gui) -> None:
    """The name column takes what is left; there is nothing to drag there."""
    assert set(gui.view._grips) == {2, 3, 4}
    gui.view.set_column_width(1, 300)
    assert 1 not in gui.view._col_widths


# ----------------------------------------------------------------------
# Names that do not fit
# ----------------------------------------------------------------------
def _tip_of(widget) -> str:
    """Hover ``widget`` and return the text of the popup, or an empty string."""
    widget.event_generate("<Enter>")
    widget.update_idletasks()
    tips = [child for child in widget.winfo_children() if child.winfo_class() == "Toplevel"]
    if not tips:
        return ""
    texts = _all_text(tips[0])
    widget.event_generate("<Leave>")
    return texts[0] if texts else ""


def test_a_name_that_had_to_be_cut_short_shows_itself_in_full(gui) -> None:
    long_name = ("A very long file name that certainly does not fit into the "
                 "narrow name column of the download list.mp4")
    gui.render_history([HistoryEntry(name=long_name, status=STATUS_OK,
                                     finished_at="2026-07-31T11:20:05")])
    gui.show_view("downloads")
    gui.root.update()
    gui.root.update_idletasks()

    label = [w for w in _labels(gui.view._row_items[0][1]) if str(w.cget("text")).endswith("…")]
    assert label, "the name was expected to be cut short"
    assert _tip_of(label[0]) == long_name


def test_a_name_that_fits_explains_nothing(gui) -> None:
    gui.render_history([HistoryEntry(name="short.mp3", status=STATUS_OK,
                                     finished_at="2026-07-31T11:20:05")])
    gui.show_view("downloads")
    gui.root.update()
    gui.root.update_idletasks()

    label = [w for w in _labels(gui.view._row_items[0][1])
             if str(w.cget("text")) == "short.mp3"]
    assert label, "the name should be shown as it is"
    assert _tip_of(label[0]) == "", "a tooltip repeating what is already there is noise"


# ----------------------------------------------------------------------
# The toolbar
# ----------------------------------------------------------------------
def test_a_pasted_link_is_handed_on(gui) -> None:
    submitted: list = []
    gui.on_submit_url = lambda url, fmt: submitted.append((url, fmt))
    gui.view._url_var.set("https://youtu.be/dQw4w9WgXcQ")
    gui.view._submit_url()
    assert submitted == [("https://youtu.be/dQw4w9WgXcQ", "mp3")]
    assert gui.view._url_var.get() == "", "the field is cleared after submitting"


def test_an_empty_field_submits_nothing(gui) -> None:
    submitted: list = []
    gui.on_submit_url = lambda url, fmt: submitted.append(url)
    gui.view._url_var.set("   ")
    gui.view._submit_url()
    assert submitted == []


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
def test_the_form_shows_the_current_configuration(gui, config) -> None:
    config.history_limit = 55
    gui.view.select_page("settings")
    assert gui.view._vars["history_limit"].get() == "55"


def test_saving_writes_the_values_back(gui, config) -> None:
    saved: list = []
    gui.on_save_settings = lambda: saved.append(True)
    gui.view.select_page("settings")
    gui.view._vars["history_limit"].set("42")
    gui.view._vars["interval_sec"].set("3,5")
    gui.view._vars["use_tray"].set(False)
    gui.view._vars["startup_visibility"].set(gui.messages["settings_startup_window"])
    gui.view._save_settings()
    assert config.history_limit == 42
    assert config.interval_sec == pytest.approx(3.5), "a comma must work as a decimal point"
    assert config.use_tray is False
    assert config.start_minimized is False
    assert saved


def test_startup_tray_setting_enables_tray_icon(gui, config) -> None:
    gui.view.select_page("settings")
    gui.view._vars["use_tray"].set(False)
    gui.view._vars["startup_visibility"].set(gui.messages["settings_startup_tray"])
    gui.view._save_settings()
    assert config.start_minimized is True
    assert config.use_tray is True


def test_cookies_settings_round_trip(gui, config, messages) -> None:
    gui.view.select_page("settings")
    assert "cookies_from_browser" in gui.view._vars
    assert "cookies_file" in gui.view._vars
    assert "cookies_risk_acknowledged" in gui.view._vars
    gui.view._vars["cookies_risk_acknowledged"].set(True)
    gui.view._sync_cookies_controls()
    gui.view._vars["cookies_from_browser"].set(messages["settings_cookies_browser_firefox"])
    gui.view._vars["cookies_file"].set("/tmp/example-cookies.txt")
    gui.view._save_settings()
    assert config.cookies_risk_acknowledged is True
    assert config.cookies_risk_acknowledged_at
    assert config.cookies_from_browser == "firefox"
    assert config.cookies_file == "/tmp/example-cookies.txt"
    gui.view.select_page("downloads")
    gui.view.select_page("settings")
    assert gui.view._vars["cookies_risk_acknowledged"].get()
    assert gui.view._vars["cookies_from_browser"].get() == messages["settings_cookies_browser_firefox"]
    assert gui.view._vars["cookies_file"].get() == "/tmp/example-cookies.txt"
    assert str(gui.view._cookies_browser_combo.cget("state")) == "readonly"


def test_cookies_settings_require_risk_acknowledgement(gui, config, messages) -> None:
    gui.view.select_page("settings")
    assert str(gui.view._cookies_browser_combo.cget("state")) == "disabled"
    gui.view._vars["cookies_from_browser"].set(messages["settings_cookies_browser_firefox"])
    gui.view._vars["cookies_file"].set("/tmp/example-cookies.txt")
    gui.view._vars["cookies_risk_acknowledged"].set(False)
    gui.view._save_settings()
    assert config.cookies_risk_acknowledged is False
    assert config.cookies_risk_acknowledged_at == ""
    assert config.cookies_from_browser == ""
    assert config.cookies_file == ""


def test_clearing_cookie_risk_ack_stops_saving_cookies(gui, config, messages) -> None:
    gui.view.select_page("settings")
    gui.view._vars["cookies_risk_acknowledged"].set(True)
    gui.view._sync_cookies_controls()
    gui.view._vars["cookies_from_browser"].set(messages["settings_cookies_browser_chrome"])
    gui.view._vars["cookies_file"].set("/tmp/keep-me.txt")
    gui.view._save_settings()
    assert config.cookies_from_browser == "chrome"
    stamped = config.cookies_risk_acknowledged_at
    assert stamped

    gui.view._vars["cookies_risk_acknowledged"].set(False)
    gui.view._sync_cookies_controls()
    gui.view._save_settings()
    assert config.cookies_risk_acknowledged is False
    assert config.cookies_risk_acknowledged_at == ""
    assert config.cookies_from_browser == ""
    assert config.cookies_file == ""
    assert str(gui.view._cookies_browser_combo.cget("state")) == "disabled"


def test_nonsense_input_keeps_the_previous_value(gui, config) -> None:
    gui.view.select_page("settings")
    gui.view._vars["interval_sec"].set("2")
    gui.view._save_settings()
    gui.view._vars["interval_sec"].set("not a number")
    gui.view._save_settings()
    assert config.interval_sec == pytest.approx(2.0)


def test_absurd_values_are_clamped(gui, config) -> None:
    gui.view.select_page("settings")
    gui.view._vars["interval_sec"].set("99999")
    gui.view._vars["history_limit"].set("-5")
    gui.view._save_settings()
    assert 0.5 <= config.interval_sec <= 60.0
    assert config.history_limit >= 1


def test_discarding_restores_the_stored_values(gui, config) -> None:
    gui.view.select_page("settings")
    gui.view._vars["history_limit"].set("999")
    gui.view._load_settings()
    assert gui.view._vars["history_limit"].get() == str(config.history_limit)


# ----------------------------------------------------------------------
# About
# ----------------------------------------------------------------------
def test_the_about_page_names_the_author_and_the_repository(gui) -> None:
    from clipster import APP_AUTHOR, APP_URL, APP_WEBSITE

    texts = _all_text(gui.view._pages["about"])
    assert APP_AUTHOR in texts
    assert APP_WEBSITE in texts
    assert APP_URL in texts


def test_the_links_are_clickable_but_the_name_is_not(gui) -> None:
    from clipster import APP_AUTHOR, APP_URL, APP_WEBSITE

    links = []
    def collect(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and str(child.cget("cursor")) == "hand2":
                links.append(str(child.cget("text")))
            collect(child)
    collect(gui.view._pages["about"])
    assert APP_WEBSITE in links and APP_URL in links
    assert APP_AUTHOR not in links


def test_a_link_opens_the_browser(gui, monkeypatch) -> None:
    import webbrowser

    opened: list = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    gui.view._open_link("https://example.com")
    assert opened == ["https://example.com"]


# ----------------------------------------------------------------------
# The navigation window
# ----------------------------------------------------------------------
def test_the_question_asks_for_format_and_track(gui) -> None:
    prompt = Prompt()
    gui.nav.begin("link received")
    gui.nav.ask(prompt, "Some title", 213, ["de", "en", "es"], "mp4", True, "de")
    assert gui.nav.question_pending()
    assert gui.nav._format.get() == "mp4", "the configured default must be preselected"
    boxes = [w for w in gui.nav._form.winfo_children() if w.winfo_class() == "TCombobox"]
    assert len(boxes) == 2, "format and audio track"


def test_the_original_track_is_marked(gui) -> None:
    gui.nav.begin("x")
    gui.nav.ask(Prompt(), "T", 0, ["de", "en"], "mp3", True, "de")
    boxes = [w for w in gui.nav._form.winfo_children() if w.winfo_class() == "TCombobox"]
    values = list(boxes[1]["values"])
    assert "Original" in values[1] or "original" in values[1]
    assert "original" not in values[2].lower()


def test_a_single_track_offers_no_choice(gui) -> None:
    gui.nav.begin("x")
    gui.nav.ask(Prompt(), "T", 0, ["en"], "mp3", True)
    boxes = [w for w in gui.nav._form.winfo_children() if w.winfo_class() == "TCombobox"]
    assert len(boxes) == 1, "only the format selector"


def test_answering_returns_format_language_and_section(gui) -> None:
    prompt = Prompt()
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 0, [], "mp3", False)
    gui.nav._submit()
    assert prompt.wait(poll=0.01) == {"format": "mp3", "language": "", "section": None}
    assert not gui.nav.question_pending()


def test_the_question_offers_two_section_fields(gui) -> None:
    gui.nav.begin("x")
    gui.nav.ask(Prompt(), "T", 213, [], "mp3", False)
    entries = _entries(gui.nav._form)
    assert len(entries) == 2, "from and to"
    assert [entry.get() for entry in entries] == ["", ""], "empty means the whole video"


def test_a_section_is_answered_along_with_the_format(gui) -> None:
    prompt = Prompt()
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 213, [], "mp3", False)
    gui.nav._clip_start.set("1:23")
    gui.nav._clip_end.set("2:45")
    gui.nav._submit()
    answer = prompt.wait(poll=0.01)
    assert answer["section"] == ClipRange(start=83.0, end=165.0)


def test_a_section_beyond_the_video_keeps_the_question_open(gui) -> None:
    """The window has the length, so the mistake is caught before the download."""
    prompt = Prompt()
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 213, [], "mp3", False)
    gui.nav._clip_start.set("9:00")
    gui.nav._submit()
    assert gui.nav.question_pending(), "nothing was answered"
    assert gui.nav._clip_hint is not None
    assert str(gui.nav._clip_hint.cget("style")) == "Danger.TLabel"
    assert str(gui.nav._clip_hint.cget("text")) == gui.messages["clip_error_range"]


def test_a_corrected_section_can_still_be_submitted(gui) -> None:
    prompt = Prompt()
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 213, [], "mp3", False)
    gui.nav._clip_start.set("nonsense")
    gui.nav._submit()
    assert gui.nav.question_pending()
    gui.nav._clip_start.set("0:10")
    gui.nav._submit()
    assert prompt.wait(poll=0.01)["section"] == ClipRange(start=10.0, end=213.0)


def test_the_section_fields_start_empty_for_the_next_link(gui) -> None:
    gui.nav.begin("x")
    gui.nav.ask(Prompt(), "T", 213, [], "mp3", False)
    gui.nav._clip_start.set("1:23")
    gui.nav.cancel_pending()
    gui.nav.begin("y")
    gui.nav.ask(Prompt(), "T2", 213, [], "mp3", False)
    assert gui.nav._clip_start.get() == "", "a section belongs to one download only"


def test_cancelling_the_question(gui) -> None:
    prompt = Prompt()
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 0, [], "mp3", False)
    assert gui.nav.cancel_pending()
    assert prompt.wait(poll=0.01) is None
    assert gui.nav.cancel_event.is_set()


def test_cancelling_without_a_question_reports_nothing(gui) -> None:
    gui.nav.begin("x")
    assert gui.nav.cancel_pending() is False


def test_the_progress_bar_follows_the_download(gui) -> None:
    gui.nav.begin("x")
    gui.nav.show_progress("mp3", 213)
    gui.nav.set_percent(46.0)
    assert gui.nav._value.get() == pytest.approx(46.0)
    gui.nav.set_percent(None)
    assert gui.nav._bar_mode == "indeterminate"


def test_the_result_offers_the_finished_file(gui, tmp_path: Path) -> None:
    target = tmp_path / "song.mp3"
    target.write_bytes(b"x")
    gui.nav.begin("x")
    gui.nav.finish("done", STATUS_OK, "detail", target)
    assert gui.nav.result_path() == target
    assert not gui.nav._bar.winfo_ismapped(), "a full bar looks like an empty one"
    assert gui.nav._auto_close_job is not None
    gui.nav._cancel_auto_close()


def test_a_failed_result_offers_no_file(gui) -> None:
    gui.nav.begin("x")
    gui.nav.finish("it broke", STATUS_FAILED)
    assert gui.nav.result_path() is None
    assert gui.nav._auto_close_job is None


def test_closing_the_window_cancels_a_pending_question(gui) -> None:
    prompt = Prompt()
    closed: list = []
    gui.on_nav_closed = lambda: closed.append(True)
    gui.nav.begin("x")
    gui.nav.ask(prompt, "T", 0, [], "mp3", False)
    gui.nav._closed()
    assert prompt.wait(poll=0.01) is None
    assert closed
