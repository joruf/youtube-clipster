"""Cross-platform contract tests for YouTube Clipster (no GUI required)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipster import dependencies, paths
from clipster.cli import build_parser
from clipster.dependencies import LEVEL_REQUIRED


class TestPathsContract(unittest.TestCase):
    """Filesystem layout must stay consistent across platforms."""

    def test_home_override_relocates_install_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {paths.HOME_ENV_VAR: tmp}):
                self.assertEqual(paths.install_dir(), Path(tmp))
                self.assertEqual(paths.venv_dir(), Path(tmp) / "venv")

    def test_project_root_contains_run_py(self) -> None:
        self.assertTrue((paths.PROJECT_ROOT / "run.py").is_file())
        self.assertTrue((paths.PROJECT_ROOT / "clipster").is_dir())

    def test_venv_python_name_matches_platform(self) -> None:
        name = paths.venv_python().name
        if paths.IS_WINDOWS:
            self.assertEqual(name, "python.exe")
            self.assertEqual(paths.venv_python(gui=True).name, "pythonw.exe")
        else:
            self.assertEqual(name, "python")


class TestDependenciesContract(unittest.TestCase):
    """Dependency table drives installers and requirements.txt."""

    def test_ytdlp_is_required_everywhere(self) -> None:
        required = [
            dep
            for dep in dependencies.PIP_DEPENDENCIES
            if dep.package == "yt-dlp" and dep.level == LEVEL_REQUIRED
        ]
        self.assertTrue(required)
        for platform in ("linux", "windows", "macos"):
            self.assertTrue(any(dep.applies_to(platform) for dep in required))

    def test_requirements_text_lists_ytdlp(self) -> None:
        text = dependencies.requirements_text()
        self.assertIn("yt-dlp", text)

    def test_python_xlib_is_linux_only(self) -> None:
        xlib = [dep for dep in dependencies.PIP_DEPENDENCIES if dep.package == "python-xlib"]
        self.assertTrue(xlib)
        self.assertTrue(xlib[0].applies_to("linux"))
        self.assertFalse(xlib[0].applies_to("windows"))


class TestCliContract(unittest.TestCase):
    """Bootstrap CLI flags used by installers and matrix runs."""

    def test_check_flag_parses(self) -> None:
        ns = build_parser().parse_args(["--check", "--no-auto-install"])
        self.assertTrue(ns.check)
        self.assertTrue(ns.no_auto_install)

    def test_help_mentions_clipster(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("YouTube", help_text)


class TestModuleImports(unittest.TestCase):
    """Core modules import without a display server."""

    def test_import_core_modules(self) -> None:
        import clipster.config  # noqa: F401
        import clipster.history  # noqa: F401
        import clipster.i18n  # noqa: F401
        import clipster.logging_setup  # noqa: F401
        import clipster.setup_ui  # noqa: F401
        import clipster.singleinstance  # noqa: F401


class TestDownloadRetryContract(unittest.TestCase):
    """A refused transfer must be retried the same way on every platform."""

    def test_a_403_is_its_own_kind_of_error(self) -> None:
        from clipster.downloader import classify_error

        self.assertEqual(classify_error("HTTP Error 403: Forbidden"), "forbidden")
        self.assertEqual(
            classify_error("ERROR: unable to download video, data: HTTP Error 403 Forbidden"),
            "forbidden",
        )

    def test_a_bot_check_is_not_mistaken_for_a_plain_403(self) -> None:
        from clipster.downloader import classify_error

        self.assertEqual(
            classify_error("HTTP Error 403: Forbidden. Sign in to confirm you're not a bot"),
            "bot",
        )

    def test_the_retry_prefers_the_format_that_plays(self) -> None:
        from clipster.downloader import _M4A_FIRST, _RETRY_PLAYER_CLIENTS

        self.assertIn("m4a", _M4A_FIRST)
        self.assertTrue(_RETRY_PLAYER_CLIENTS)
        self.assertNotIn("tv", _RETRY_PLAYER_CLIENTS)
        self.assertNotIn("ios", _RETRY_PLAYER_CLIENTS)

    def test_a_drm_wall_is_its_own_kind_of_error(self) -> None:
        from clipster.downloader import classify_error

        self.assertEqual(
            classify_error("ERROR: [youtube] abc: This video is DRM protected"),
            "drm",
        )


class TestUpdateContract(unittest.TestCase):
    """The update path has to work the same on Linux, Windows and macOS."""

    def test_the_restart_replays_the_startup_arguments(self) -> None:
        from clipster import cli, updater

        original = list(cli.STARTUP_ARGUMENTS)
        cli.STARTUP_ARGUMENTS[:] = ["--no-window", "--skip-checks"]
        try:
            command = updater.restart_command()
        finally:
            cli.STARTUP_ARGUMENTS[:] = original
        self.assertEqual(command[2:], ["--no-window"])
        self.assertNotIn("--skip-checks", command)
        self.assertNotIn("--show-window", command)

    def test_the_desktop_restart_comes_back_on_screen(self) -> None:
        from clipster import cli, updater

        original = list(cli.STARTUP_ARGUMENTS)
        cli.STARTUP_ARGUMENTS[:] = ["--skip-checks"]
        try:
            command = updater.restart_command()
        finally:
            cli.STARTUP_ARGUMENTS[:] = original
        self.assertEqual(command[2:], ["--show-window"])

    def test_shutdown_does_not_restart_while_the_lock_is_held(self) -> None:
        import inspect

        from clipster.app import ClipsterApp

        source = inspect.getsource(ClipsterApp._shutdown)
        self.assertNotIn("updater.restart", source)


if __name__ == "__main__":
    unittest.main()
