"""One version, visible everywhere, and never out of step with itself.

A build number is only worth having if every surface reports the same one.  The
windows carry it in their title bars and the About page shows it, so they are
checked against :mod:`clipster` here.
"""

from __future__ import annotations

import re

import pytest

import clipster


def test_the_version_is_a_three_part_number() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", clipster.APP_VERSION), clipster.APP_VERSION


def test_the_build_number_counts_up() -> None:
    assert isinstance(clipster.APP_BUILD, int)
    assert clipster.APP_BUILD > 0


def test_the_full_version_names_both_parts() -> None:
    """``2.1.0 (4)`` - the format Fundus uses, so the projects read alike."""
    assert clipster.APP_VERSION_FULL == "{0} ({1})".format(
        clipster.APP_VERSION, clipster.APP_BUILD
    )


def test_every_title_carries_the_build() -> None:
    """A screenshot of any window has to say which build it came from."""
    for title in (clipster.APP_TITLE, clipster.APP_WINDOW_TITLE):
        assert clipster.APP_VERSION_FULL in title, title


@pytest.mark.gui
def test_every_window_title_shows_the_version(gui) -> None:
    titles = [gui.root.title(), gui.view.window.title()]
    if gui.nav is not None:
        titles.append(gui.nav.window.title())
    for title in titles:
        assert clipster.APP_VERSION_FULL in title, title


@pytest.mark.gui
def test_the_about_page_shows_the_full_version(gui) -> None:
    gui.show_view("about")
    gui.root.update_idletasks()
    page = gui.view._pages["about"]
    texts = []

    def walk(widget) -> None:
        for child in widget.winfo_children():
            if child.winfo_class() in ("TLabel", "Label"):
                try:
                    texts.append(str(child.cget("text")))
                except Exception:  # pragma: no cover - defensive
                    pass
            walk(child)

    walk(page)
    assert any(clipster.APP_VERSION_FULL in text for text in texts), texts


def test_the_command_line_prints_the_version_once(capsys) -> None:
    from clipster.cli import print_version

    print_version()
    printed = capsys.readouterr().out.strip()
    assert printed.count(clipster.APP_VERSION) == 1, printed
    assert clipster.APP_VERSION_FULL in printed
