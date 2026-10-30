#!/usr/bin/env python3
"""Capture anonymized Clipster UI screenshots for docs.

Uses the real Tk GUI with fixture data (no network, no personal paths).
Run under a display, e.g.::

    xvfb-run -a .venv/bin/python tools/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "docs" / "images"


def _grab_widget(widget, dest: Path) -> None:
    """Save a PNG of ``widget`` (a mapped Tk toplevel)."""
    widget.update_idletasks()
    widget.update()
    time.sleep(0.35)
    widget.update_idletasks()
    widget.update()

    x = int(widget.winfo_rootx())
    y = int(widget.winfo_rooty())
    w = max(1, int(widget.winfo_width()))
    h = max(1, int(widget.winfo_height()))
    print("grab", dest.name, "at", (x, y, w, h), flush=True)

    from PIL import ImageGrab

    image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    print("wrote", dest, "({0}x{1})".format(image.width, image.height), flush=True)


def _fake_history():
    from clipster.history import STATUS_CANCELED, STATUS_FAILED, STATUS_OK, HistoryEntry

    anon = "/home/user/Downloads"
    return [
        HistoryEntry(
            name="Sample Track One.mp3",
            path="{0}/Sample Track One.mp3".format(anon),
            title="Sample Track One",
            url="https://www.example.com/watch?v=ExAmPle0001",
            media_format="mp3",
            duration=214,
            size=7_120_000,
            status=STATUS_OK,
            finished_at="2026-07-31T11:20:05",
        ),
        HistoryEntry(
            name="Sample Track Two.mp3",
            path="{0}/Sample Track Two.mp3".format(anon),
            title="Sample Track Two (Lyrics)",
            url="https://www.example.com/watch?v=ExAmPle0002",
            media_format="mp3",
            duration=187,
            size=6_240_000,
            status=STATUS_OK,
            finished_at="2026-07-30T18:05:11",
        ),
        HistoryEntry(
            name="Coastline Melody.mp4",
            path="{0}/Coastline Melody.mp4".format(anon),
            title="Coastline Melody",
            url="https://www.example.com/watch?v=ExAmPle0004",
            media_format="mp4",
            duration=198,
            size=28_500_000,
            status=STATUS_OK,
            finished_at="2026-07-29T21:44:30",
        ),
        HistoryEntry(
            name="Unavailable Demo.mp4",
            path="",
            title="Unavailable Demo",
            url="https://www.example.com/watch?v=ExAmPle9999",
            media_format="mp4",
            status=STATUS_FAILED,
            error="Video unavailable",
            error_kind="unavailable",
            finished_at="2026-07-28T09:00:00",
        ),
        HistoryEntry(
            name="Canceled Demo.mp4",
            path="",
            title="Canceled Demo",
            url="https://www.example.com/watch?v=ExAmPle8888",
            media_format="mp4",
            status=STATUS_CANCELED,
            finished_at="2026-07-27T16:12:00",
        ),
    ]


def main() -> int:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No DISPLAY; aborting.", file=sys.stderr)
        return 1

    home = Path(tempfile.mkdtemp(prefix="clipster-shots-"))
    downloads = home / "Downloads"
    downloads.mkdir()
    os.environ["YOUTUBE_CLIPSTER_HOME"] = str(home)

    from clipster import i18n, paths
    from clipster.config import Config
    from clipster.gui import Gui
    from clipster.terms import TERMS_APP_VERSION

    # Avoid portable config.json next to the sources winning over the temp home.
    paths.PROJECT_ROOT = home  # type: ignore[misc]

    config = Config()
    config.path = home / "config.json"
    config.download_dir = "/home/user/Downloads"
    config.use_tray = False
    config.ask_desktop_shortcut = False
    config.show_startup_notification = False
    config.open_folder_after_download = False
    config.clear_clipboard_after_download = False
    config.autostart = False
    config.language = "en"
    config.terms_app_version = TERMS_APP_VERSION
    config.save()

    messages = i18n.load("en")

    # Pretend anonymized download files exist so the list shows Ready rows cleanly.
    from clipster.history import STATUS_OK, HistoryEntry

    def _fake_file_path(self):
        if self.status == STATUS_OK and self.path:
            return Path(self.path)
        if not self.path:
            return None
        candidate = Path(self.path)
        return candidate if candidate.exists() else None

    HistoryEntry.file_path = _fake_file_path  # type: ignore[method-assign]

    gui = Gui(messages, config, Path("/home/user/Downloads"))
    gui.build_windows()
    gui.render_history(_fake_history())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    print("building downloads shot…", flush=True)
    gui.show_view("downloads")
    gui.view.window.geometry("1120x720+40+40")
    gui.root.update_idletasks()
    gui.root.update()
    dest = OUT_DIR / "downloads.png"
    _grab_widget(gui.view.window, dest)
    written.append(dest)

    print("building settings shot…", flush=True)
    gui.view.select_page("settings")
    gui.root.update_idletasks()
    gui.root.update()
    dest = OUT_DIR / "settings.png"
    _grab_widget(gui.view.window, dest)
    written.append(dest)

    print("building about shot…", flush=True)
    gui.view.select_page("about")
    gui.root.update_idletasks()
    gui.root.update()
    dest = OUT_DIR / "about.png"
    _grab_widget(gui.view.window, dest)
    written.append(dest)

    print("building terms shot…", flush=True)
    terms_dest = OUT_DIR / "terms.png"
    attempts = {"n": 0}

    def _iter_toplevels():
        stack = [gui.root]
        seen = set()
        while stack:
            node = stack.pop()
            try:
                wid = str(node)
            except Exception:
                continue
            if wid in seen:
                continue
            seen.add(wid)
            try:
                children = list(node.winfo_children())
            except Exception:
                continue
            for child in children:
                stack.append(child)
                try:
                    if child.winfo_class() == "Toplevel":
                        yield child
                except Exception:
                    continue

    def _capture_terms() -> None:
        attempts["n"] += 1
        win = None
        view_win = getattr(gui.view, "window", None)
        for child in _iter_toplevels():
            try:
                if child is view_win:
                    continue
                if int(child.winfo_viewable()):
                    win = child
                    break
            except Exception:
                continue
        if win is None:
            if attempts["n"] < 50:
                gui.root.after(100, _capture_terms)
            else:
                print("terms dialog not found", flush=True)
                # Unblock wait_window so the script can exit.
                for child in list(_iter_toplevels()):
                    if child is not view_win:
                        try:
                            child.destroy()
                        except Exception:
                            pass
            return
        _grab_widget(win, terms_dest)
        written.append(terms_dest)
        win.destroy()

    gui.root.after(300, _capture_terms)
    gui.show_terms_document(
        "terms_app_title",
        ("terms_app_body",),
    )

    gui.destroy()
    print("done:", ", ".join(str(p.relative_to(ROOT)) for p in written), flush=True)
    return 0 if len(written) >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())
