"""Linux, Windows and macOS must run the same code, not three copies of it.

A feature that exists on one platform exists on the others unless the
difference is deliberate and named in a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clipster import i18n


# ----------------------------------------------------------------------
# The update button
# ----------------------------------------------------------------------
def test_the_unknown_version_wording_exists_in_every_language() -> None:
    """Both languages must be able to say it, or the About page shows a raw key."""
    for language in i18n.available_languages():
        messages = i18n.load(language)
        text = messages.format("update_unversioned", commit="abc1234")
        assert text and "update_unversioned" not in text
        assert "abc1234" in text


# ----------------------------------------------------------------------
# The settings page
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_the_desktop_settings_show_where_files_land(gui, downloads: Path) -> None:
    """An empty field or a link target is easy to misread, so the real folder is shown."""
    gui.view.select_page("settings")
    gui.view._vars["download_dir"].set(str(downloads))
    gui.view.window.update_idletasks()
    shown = str(gui.view._download_dir_resolved.cget("text"))
    assert shown
    assert str(downloads) in shown


@pytest.mark.gui
def test_an_empty_download_dir_still_names_a_folder(gui) -> None:
    """"Empty means the system folder" is not obvious - so name it."""
    gui.view.select_page("settings")
    gui.view._vars["download_dir"].set("")
    gui.view.window.update_idletasks()
    assert str(gui.view._download_dir_resolved.cget("text")).strip()


@pytest.mark.gui
def test_the_resolved_folder_follows_what_is_typed(gui, tmp_path: Path) -> None:
    gui.view.select_page("settings")
    first = tmp_path / "one"
    second = tmp_path / "two"
    gui.view._vars["download_dir"].set(str(first))
    gui.view.window.update_idletasks()
    before = str(gui.view._download_dir_resolved.cget("text"))
    gui.view._vars["download_dir"].set(str(second))
    gui.view.window.update_idletasks()
    assert str(gui.view._download_dir_resolved.cget("text")) != before


@pytest.mark.gui
def test_nonsense_in_the_folder_field_does_not_crash_the_page(gui) -> None:
    gui.view.select_page("settings")
    for text in ("\x00", "~" * 500, "  ", "://"):
        gui.view._vars["download_dir"].set(text)
        gui.view.window.update_idletasks()


# ----------------------------------------------------------------------
# Shared code, not parallel code
# ----------------------------------------------------------------------
def test_both_platforms_use_one_download_folder_resolver(config) -> None:
    """The resolver returns an absolute path whatever the platform."""
    resolved = config.resolved_download_dir()
    assert isinstance(resolved, Path)
    assert resolved.is_absolute()


def test_the_update_words_exist_in_every_language() -> None:
    from clipster import i18n

    for language in ("en", "de"):
        messages = i18n.load(language)
        for key in ("update_check", "update_install",
                    "update_available", "update_current", "update_failed", "update_error"):
            assert messages[key].strip(), "{0} missing in {1}".format(key, language)


def test_the_403_explanation_exists_in_every_language() -> None:
    from clipster import i18n

    for language in ("en", "de"):
        assert i18n.load(language)["error_forbidden"].strip()
        assert i18n.load(language)["error_drm"].strip()
