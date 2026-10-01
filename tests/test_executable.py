"""The single-file executable: its paths, its yt-dlp, its updates, its build.

The executable itself is never started here - ``build-exe.py`` does that after
every build.  These tests pretend to be frozen and check that nothing in that
mode reaches for a venv, pip or a Python interpreter that is not there.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from clipster import APP_BUILD, APP_VERSION_FULL, installer, paths, shortcuts, updater

ROOT = Path(__file__).resolve().parent.parent


class _Response(io.BytesIO):
    """Minimal stand-in for what urlopen returns."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


@pytest.fixture()
def frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pretend to run as the executable; return its (fake) file."""
    executable = tmp_path / "bin" / "youtube-clipster-linux-x86_64"
    executable.parent.mkdir()
    executable.write_bytes(b"old")
    monkeypatch.setattr(paths, "IS_FROZEN", True)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setenv(paths.HOME_ENV_VAR, str(tmp_path / "home"))
    return executable


def _release(build: int, asset: str = "") -> dict:
    """Return a fake GitHub release answer."""
    name = asset or paths.executable_name("9.9.9", build)
    return {
        "tag_name": "v9.9.9-build{0}".format(build),
        "name": "YouTube Clipster 9.9.9 ({0})".format(build),
        "assets": [{"name": name, "browser_download_url": "https://example.invalid/" + name}],
    }


def _fake_ytdlp(target: Path, version: str = "2026.08.19", solver: bool = True) -> Path:
    """Write a file shaped like yt-dlp's release."""
    with zipfile.ZipFile(str(target), "w") as bundle:
        bundle.writestr("yt_dlp/__init__.py", "")
        bundle.writestr("yt_dlp/version.py", "__version__ = '{0}'\n".format(version))
        if solver:
            bundle.writestr("yt_dlp_ejs/__init__.py", "")
    return target


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
def test_the_executable_finds_its_sources_in_the_unpacked_data(monkeypatch: pytest.MonkeyPatch,
                                                               tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths._project_root() == tmp_path / paths.FROZEN_SOURCE_DIR


def test_a_checkout_finds_its_sources_next_to_the_package() -> None:
    assert paths._project_root() == ROOT
    assert paths.web_root() == ROOT / "clipster" / "web"


@pytest.mark.parametrize("windows, machine, expected", [
    (False, "x86_64", "youtube-clipster-linux-x86_64-2.4.1-build9"),
    (False, "aarch64", "youtube-clipster-linux-aarch64-2.4.1-build9"),
    (True, "AMD64", "youtube-clipster-windows-x86_64-2.4.1-build9.exe"),
    (True, "ARM64", "youtube-clipster-windows-aarch64-2.4.1-build9.exe"),
])
def test_the_executable_is_named_after_its_platform_and_version(monkeypatch: pytest.MonkeyPatch,
                                                                windows: bool, machine: str,
                                                                expected: str) -> None:
    monkeypatch.setattr(paths, "IS_WINDOWS", windows)
    monkeypatch.setattr(paths, "IS_MACOS", False)
    monkeypatch.setattr(paths.platform, "machine", lambda: machine)
    assert paths.executable_name("2.4.1", 9) == expected


def test_the_executable_name_defaults_to_this_version() -> None:
    from clipster import APP_VERSION

    assert paths.executable_name().split("-", 4)[-1].startswith(
        "{0}-build{1}".format(APP_VERSION, APP_BUILD))


def test_the_downloaded_ytdlp_is_only_put_on_the_path_when_frozen(frozen: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    archive = paths.ytdlp_zipapp()
    archive.parent.mkdir(parents=True)
    _fake_ytdlp(archive)
    monkeypatch.setattr(sys, "path", list(sys.path))
    paths.use_external_ytdlp()
    assert sys.path[0] == str(archive)
    paths.use_external_ytdlp()
    assert sys.path.count(str(archive)) == 1

    monkeypatch.setattr(paths, "IS_FROZEN", False)
    monkeypatch.setattr(sys, "path", [item for item in sys.path if item != str(archive)])
    paths.use_external_ytdlp()
    assert str(archive) not in sys.path


# ----------------------------------------------------------------------
# yt-dlp as a download
# ----------------------------------------------------------------------
def test_the_ytdlp_version_is_read_without_importing(tmp_path: Path) -> None:
    assert installer.zipapp_ytdlp_version(_fake_ytdlp(tmp_path / "yt-dlp")) == "2026.08.19"


def test_a_release_without_the_challenge_solver_is_rejected(tmp_path: Path) -> None:
    """Without yt-dlp-ejs every YouTube download ends in HTTP 403."""
    assert installer.zipapp_ytdlp_version(_fake_ytdlp(tmp_path / "yt-dlp", solver=False)) is None


def test_a_missing_or_broken_file_has_no_version(tmp_path: Path) -> None:
    assert installer.zipapp_ytdlp_version(tmp_path / "missing") is None
    broken = tmp_path / "broken"
    broken.write_bytes(b"not a zip")
    assert installer.zipapp_ytdlp_version(broken) is None


def test_ytdlp_is_downloaded_on_the_first_start(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def download(url: str, target: Path):
        assert url == installer.YTDLP_ZIPAPP_URL
        _fake_ytdlp(target)
        return None

    monkeypatch.setattr(installer, "_download", download)
    step = installer.ensure_ytdlp_zipapp()
    assert step.ok and step.changed
    assert installer.zipapp_ytdlp_version(paths.ytdlp_zipapp()) == "2026.08.19"
    assert not paths.ytdlp_zipapp().with_name("yt-dlp.pyz.part").exists()


def test_a_bad_download_never_replaces_a_working_ytdlp(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = paths.ytdlp_zipapp()
    target.parent.mkdir(parents=True)
    _fake_ytdlp(target, version="2026.01.01")

    def download(url: str, target: Path):
        target.write_bytes(b"<html>rate limited</html>")
        return None

    monkeypatch.setattr(installer, "_download", download)
    step = installer.ensure_ytdlp_zipapp(force_update=True)
    assert step.ok and "update failed" in step.detail
    assert installer.zipapp_ytdlp_version(target) == "2026.01.01"


def test_without_ytdlp_and_without_network_the_setup_fails(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "_download", lambda url, target: "offline")
    step = installer.ensure_ytdlp_zipapp()
    assert not step.ok
    assert installer.YTDLP_ZIPAPP_URL in step.hint


def test_no_auto_install_only_reports(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "_download", lambda url, target: pytest.fail("must not download"))
    assert not installer.ensure_ytdlp_zipapp(auto_install=False).ok


def test_the_frozen_setup_never_starts_an_interpreter(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``sys.executable`` is the program itself: ``-m pip`` would start Clipster."""
    def run_command(command, *args, **kwargs):
        assert str(command[0]) != sys.executable, command
        return installer.CommandResult(returncode=0, output="")

    monkeypatch.setattr(installer, "run_command", run_command)
    monkeypatch.setattr(installer, "ensure_venv", lambda **kwargs: pytest.fail("no venv when frozen"))
    monkeypatch.setattr(installer, "ensure_ytdlp", lambda **kwargs: pytest.fail("no pip when frozen"))
    monkeypatch.setattr(installer, "ensure_ytdlp_zipapp",
                        lambda **kwargs: installer.Step(name="yt-dlp", ok=True, detail="fake"))
    monkeypatch.setattr(installer, "ensure_ffmpeg", lambda **kwargs: installer.Step(name="FFmpeg", ok=True))
    monkeypatch.setattr(installer, "ensure_mpv", lambda **kwargs: installer.Step(name="mpv", ok=True))
    monkeypatch.setattr(installer, "ensure_clipboard_tool", lambda **kwargs: installer.Step(name="c", ok=True))
    monkeypatch.setattr(installer, "ensure_js_runtime", lambda **kwargs: installer.Step(name="js", ok=True))
    report = installer.bootstrap(need_gui=True)
    assert report.ok
    names = [step.name for step in report.steps]
    assert "System tray" in names and "Phone QR code" in names


def test_a_bundled_package_is_found_in_this_process() -> None:
    assert installer._bundled_step("x", "json", "nothing").detail == "json (bundled)"
    step = installer._bundled_step("x", "clipster_no_such_module", "the feature")
    assert step.ok and "the feature" in step.detail


# ----------------------------------------------------------------------
# Updates from GitHub releases
# ----------------------------------------------------------------------
def test_the_release_tag_carries_the_build_number() -> None:
    assert updater.release_build("v2.4.0-build8") == 8
    assert updater.release_build("v2.4.0") is None
    assert updater.release_build("nightly") is None


def test_the_workflow_tags_releases_the_way_the_updater_reads_them() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release-exe.yml").read_text(encoding="utf-8")
    assert 'TAG="v${VERSION}-build${BUILD}"' in workflow
    assert updater.RELEASE_TAG.match("v{0}-build{1}".format("2.4.0", 8))


def _serve(monkeypatch: pytest.MonkeyPatch, release: dict, payload: bytes = b"") -> None:
    """Answer the release API with ``release`` and the download with ``payload``."""
    def urlopen(request, timeout=None):
        if "api.github.com" in request.full_url:
            return _Response(json.dumps(release).encode("utf-8"))
        return _Response(payload)

    monkeypatch.setattr(updater.urllib.request, "urlopen", urlopen)


def test_a_higher_build_is_an_update(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _release(APP_BUILD + 1))
    info = updater.check()
    assert info.available and info.known
    assert info.local == APP_VERSION_FULL
    assert info.remote == "9.9.9 ({0})".format(APP_BUILD + 1)


def test_the_same_build_is_current(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _release(APP_BUILD))
    info = updater.check()
    assert not info.available and info.known


def test_a_release_without_this_platform_is_an_error(frozen: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _release(APP_BUILD + 1, asset="youtube-clipster-plan9-mips"))
    info = updater.check()
    assert info.error and not info.available


@pytest.fixture()
def no_launchers(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record shortcut work instead of touching the desktop."""
    calls: list = []
    monkeypatch.setattr(shortcuts, "desktop_shortcut_exists", lambda: True)
    monkeypatch.setattr(shortcuts, "create_desktop_shortcut", lambda: calls.append("shortcut"))
    monkeypatch.setattr(shortcuts, "autostart_enabled", lambda: True)
    monkeypatch.setattr(shortcuts, "set_autostart", lambda enabled: calls.append(("autostart", enabled)))
    monkeypatch.setattr(updater, "_updated_executable", None)
    return calls


@pytest.mark.parametrize("windows", [False, True])
def test_the_update_arrives_under_its_own_versioned_name(frozen: Path, monkeypatch: pytest.MonkeyPatch,
                                                        no_launchers: list, windows: bool) -> None:
    monkeypatch.setattr(paths, "IS_WINDOWS", windows)
    new = b"N" * (2 * 1024 * 1024)
    _serve(monkeypatch, _release(APP_BUILD + 1), new)
    ok, message = updater.apply()
    assert ok, message
    target = frozen.with_name(paths.executable_name("9.9.9", APP_BUILD + 1))
    assert target.read_bytes() == new
    assert frozen.read_bytes() == b"old", "the running file is left alone"
    if not windows:
        assert target.stat().st_mode & 0o111
    from clipster import cli

    monkeypatch.setattr(cli, "STARTUP_ARGUMENTS", ["--skip-checks"])
    assert updater.restart_command() == [str(target), "--show-window"]


def test_the_new_program_removes_the_old_one_and_moves_the_launchers(
        frozen: Path, monkeypatch: pytest.MonkeyPatch, no_launchers: list) -> None:
    _serve(monkeypatch, _release(APP_BUILD + 1), b"N" * (2 * 1024 * 1024))
    assert updater.apply()[0]
    target = frozen.with_name(paths.executable_name("9.9.9", APP_BUILD + 1))

    monkeypatch.setattr(sys, "executable", str(target))
    updater.finish_executable_update()
    assert not frozen.exists()
    assert no_launchers == ["shortcut", ("autostart", True)]
    updater.finish_executable_update()
    assert no_launchers == ["shortcut", ("autostart", True)], "done once, not on every start"


def test_the_old_program_started_again_never_deletes_itself(
        frozen: Path, monkeypatch: pytest.MonkeyPatch, no_launchers: list) -> None:
    _serve(monkeypatch, _release(APP_BUILD + 1), b"N" * (2 * 1024 * 1024))
    assert updater.apply()[0]
    updater.finish_executable_update()
    assert frozen.exists()
    assert no_launchers == []


def test_a_truncated_download_leaves_the_program_alone(frozen: Path, monkeypatch: pytest.MonkeyPatch,
                                                       no_launchers: list) -> None:
    _serve(monkeypatch, _release(APP_BUILD + 1), b"<html>error</html>")
    ok, _message = updater.apply()
    assert not ok
    assert frozen.read_bytes() == b"old"
    assert list(frozen.parent.iterdir()) == [frozen]


def test_the_restart_starts_the_executable_itself(frozen: Path, monkeypatch: pytest.MonkeyPatch,
                                                  no_launchers: list) -> None:
    from clipster import cli

    monkeypatch.setattr(cli, "STARTUP_ARGUMENTS", ["--skip-checks"])
    assert updater.restart_command() == [str(frozen.resolve()), "--show-window"]


# ----------------------------------------------------------------------
# Shortcuts
# ----------------------------------------------------------------------
def test_shortcuts_start_the_executable(frozen: Path) -> None:
    assert shortcuts.launch_command() == [str(frozen.resolve())]
    text = shortcuts._desktop_entry_text()
    assert 'Exec="{0}"'.format(frozen.resolve()) in text


def test_the_launcher_icon_outlives_the_unpacked_files(frozen: Path) -> None:
    icon = shortcuts._launcher_icon()
    assert icon.parent == paths.install_dir()
    assert icon.is_file()


# ----------------------------------------------------------------------
# The build script
# ----------------------------------------------------------------------
def _build_script():
    """Import ``build-exe.py`` (its name is not a module name)."""
    spec = importlib.util.spec_from_file_location("build_exe", str(ROOT / "build-exe.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_build_leaves_ytdlp_out_but_carries_its_helpers() -> None:
    build = _build_script()
    packages = build.bundled_packages()
    assert not any(item.lower().startswith("yt-dlp") for item in packages)
    assert "certifi" in packages and "pystray" in packages
    assert "yt_dlp" in build.EXCLUDED_MODULES


@pytest.mark.skipif(not hasattr(sys, "stdlib_module_names"), reason="building needs Python 3.10+")
def test_the_build_carries_the_standard_library_ytdlp_needs() -> None:
    modules = set(_build_script().stdlib_modules())
    for needed in ("sqlite3", "http.cookiejar", "xml.etree.ElementTree", "hmac", "ctypes"):
        assert needed in modules
    assert not any(name == "test" or name.startswith("test.") for name in modules)


def test_the_spec_file_limits_gtk_and_names_the_platform(tmp_path: Path) -> None:
    build = _build_script()
    text = build.spec_text(tmp_path / paths.FROZEN_SOURCE_DIR)
    compile(text, "youtube-clipster.spec", "exec")
    assert "'icons': []" in text and "'themes': []" in text
    expected = paths.executable_name()
    if expected.endswith(".exe"):
        expected = expected[:-4]
    assert "name={0!r}".format(expected) in text


def test_the_phone_bundle_never_carries_build_output() -> None:
    from clipster import android

    assert {"build", "dist"} <= android._SKIP_DIRS
