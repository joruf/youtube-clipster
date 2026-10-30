"""Platform detection and all filesystem locations used by YouTube Clipster.

Everything the application writes lives below :func:`install_dir` so that the
checkout itself stays clean and the same code works on Linux, Windows and macOS.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

#: ``True`` inside the single-file executable that ``build-exe.py`` produces.
IS_FROZEN = bool(getattr(sys, "frozen", False))

#: Folder below ``sys._MEIPASS`` the executable carries the sources in.  It has
#: the name a checkout has.
FROZEN_SOURCE_DIR = "youtube-clipster"


def _project_root() -> Path:
    """Return the directory that holds ``run.py`` and the ``clipster`` package.

    The executable unpacks itself into a temporary directory on every start;
    the sources travel there as data, so the icons and the locale files are found
    exactly where a checkout has them.

    :return: The project root.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / FROZEN_SOURCE_DIR
    return Path(__file__).resolve().parent.parent


#: Root of the checkout (the directory containing ``run.py``).
PROJECT_ROOT = _project_root()

#: Environment variable that relocates the whole application data directory.
HOME_ENV_VAR = "YOUTUBE_CLIPSTER_HOME"


def install_dir() -> Path:
    """Return the writable application data directory for the current user."""
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "YoutubeClipster"
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / "YoutubeClipster"
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "YoutubeClipster"


def venv_dir() -> Path:
    """Return the directory of the managed virtual environment."""
    return install_dir() / "venv"


def venv_python(gui: bool = False) -> Path:
    """Return the interpreter of the managed virtual environment.

    ``gui=True`` returns ``pythonw.exe`` on Windows, which starts without a
    console window; on every other platform both variants are identical.
    """
    if IS_WINDOWS:
        return venv_dir() / "Scripts" / ("pythonw.exe" if gui else "python.exe")
    return venv_dir() / "bin" / "python"


def running_in_managed_venv() -> bool:
    """Return ``True`` when the current interpreter is the managed venv."""
    try:
        return Path(sys.prefix).resolve() == venv_dir().resolve()
    except OSError:
        return False


def ffmpeg_dir() -> Path:
    """Return the directory of the privately installed FFmpeg build."""
    return install_dir() / "ffmpeg"


def bundled_ffmpeg_bin() -> Path:
    """Return the ``bin`` directory of the privately installed FFmpeg build."""
    return ffmpeg_dir() / "bin"


def bundled_ffmpeg_exe() -> Path:
    """Return the path the privately installed ``ffmpeg`` executable would have."""
    return bundled_ffmpeg_bin() / ("ffmpeg.exe" if IS_WINDOWS else "ffmpeg")


def bundled_ffplay_exe() -> Path:
    """Return the path the privately installed ``ffplay`` executable would have."""
    return bundled_ffmpeg_bin() / ("ffplay.exe" if IS_WINDOWS else "ffplay")


def deno_dir() -> Path:
    """Return the directory of the privately installed Deno runtime."""
    return install_dir() / "deno"


def bundled_deno_exe() -> Path:
    """Return the path the privately installed ``deno`` executable would have.

    yt-dlp needs a JavaScript engine to solve YouTube's signature and ``n``
    challenges.  Distributions rarely ship a new enough one - Ubuntu's
    ``quickjs`` predates the minimum by years - so Clipster keeps its own next
    to the FFmpeg it already downloads.
    """
    return deno_dir() / ("deno.exe" if IS_WINDOWS else "deno")


def bootstrap_script() -> Path:
    """Return the path of the bootstrap launcher ``run.py``."""
    return PROJECT_ROOT / "run.py"


def executable() -> Path:
    """Return the single-file executable this process was started from.

    Only meaningful when :data:`IS_FROZEN` is set; otherwise it is the Python
    interpreter.
    """
    return Path(sys.executable).resolve()


def executable_name(version: str = "", build: int = 0) -> str:
    """Return the file name of the executable for this platform and version.

    ``build-exe.py`` writes the executable under this name and the updater
    looks for a release asset with it, so both always agree.  The version is
    part of it so a downloaded file says which one it is.

    :param version: ``major.minor.patch``; defaults to this program's.
    :param build: The build number; defaults to this program's.
    :return: e.g. ``youtube-clipster-linux-x86_64-2.4.1-build9`` or
        ``youtube-clipster-windows-x86_64-2.4.1-build9.exe``.
    """
    if not version:
        from . import APP_BUILD, APP_VERSION

        version, build = APP_VERSION, APP_BUILD
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    system = "windows" if IS_WINDOWS else ("macos" if IS_MACOS else "linux")
    return "youtube-clipster-{0}-{1}-{2}-build{3}{4}".format(
        system, machine, version, build, ".exe" if IS_WINDOWS else "")


def child_environment(env: "dict | None" = None) -> dict:
    """Return the environment a child process should get.

    The executable runs with ``LD_LIBRARY_PATH`` - and, through PyInstaller's
    GTK hooks, ``GI_TYPELIB_PATH``, ``GTK_PATH`` and friends - pointing into its
    unpacked files.  Inherited, they make FFmpeg, mpv, the file manager or the
    package manager load the program's libraries instead of their own, which
    ends anywhere between odd warnings and crashes.  Every entry that points
    into the unpacked files is removed; ``LD_LIBRARY_PATH`` gets the value it
    had before the program started.

    :param env: The environment to clean; defaults to this process's.
    :return: A new dict; a plain copy outside the executable.
    """
    source = os.environ if env is None else env
    bundle = getattr(sys, "_MEIPASS", "")
    if not IS_FROZEN or not bundle:
        return dict(source)
    clean = {}
    for key, value in source.items():
        if key.startswith("_PYI_") or key == "LD_LIBRARY_PATH_ORIG":
            continue
        if bundle in value:
            kept = [part for part in value.split(os.pathsep) if part and bundle not in part]
            if not kept:
                continue
            value = os.pathsep.join(kept)
        clean[key] = value
    original = source.get("LD_LIBRARY_PATH_ORIG")
    if original:
        clean["LD_LIBRARY_PATH"] = original
    return clean


def use_system_environment_for_children() -> None:
    """Start every child process with :func:`child_environment`.

    One place instead of every ``subprocess`` call: the program starts dozens
    of tools, and a single forgotten ``env=`` would bring the problem back.
    Does nothing outside the executable.

    :return: None
    """
    import subprocess

    if not IS_FROZEN or getattr(subprocess.Popen, "_clipster_clean_env", False):
        return

    class _SystemPopen(subprocess.Popen):  # type: ignore[misc, valid-type]
        """``Popen`` that never hands the bundled libraries to a child."""

        _clipster_clean_env = True

        def __init__(self, *args, **kwargs) -> None:
            kwargs["env"] = child_environment(kwargs.get("env"))
            super().__init__(*args, **kwargs)

    subprocess.Popen = _SystemPopen  # type: ignore[misc]


def ytdlp_zipapp() -> Path:
    """Return the yt-dlp release the executable downloads and imports from.

    yt-dlp is deliberately not baked into the executable: YouTube changes
    often, and a fresh yt-dlp must not have to wait for a new build.
    """
    return install_dir() / "yt-dlp.pyz"


def use_external_ytdlp() -> None:
    """Make the downloaded yt-dlp importable; does nothing outside the executable."""
    if not IS_FROZEN:
        return
    archive = str(ytdlp_zipapp())
    if archive not in sys.path and os.path.isfile(archive):
        sys.path.insert(0, archive)


def lock_file() -> Path:
    """Return the single-instance lock file."""
    return install_dir() / "youtube-clipster.lock"


def log_file() -> Path:
    """Return the rotating log file."""
    return install_dir() / "youtube-clipster.log"


def state_file() -> Path:
    """Return the machine-managed state file (update timestamps, ...)."""
    return install_dir() / "state.json"


def config_file() -> Path:
    """Return the active configuration file.

    A ``config.json`` next to the sources wins (portable / per-checkout setup),
    otherwise the per-user file inside :func:`install_dir` is used.
    """
    portable = PROJECT_ROOT / "config.json"
    if portable.is_file():
        return portable
    return install_dir() / "config.json"


def history_file() -> Path:
    """Return the JSON file holding the download history.

    It always lives beside the active configuration file, so a portable
    checkout keeps its own history.
    """
    return config_file().with_name("history.json")


#: Locations searched for the application icon, most specific first.
_ICON_CANDIDATES = (
    ("assets", "icons", "youtube-clipster.png"),
    ("assets", "youtube-clipster.png"),
    ("linux", "youtube-clipster-linux.png"),
    ("windows", "youtube-clipster-windows.png"),
)


def icon_file() -> Path:
    """Return the application icon (PNG, readable by Tk 8.6+).

    The first existing candidate wins; when none exists the canonical path is
    returned so callers can report a helpful location.
    """
    canonical = PROJECT_ROOT.joinpath(*_ICON_CANDIDATES[0])
    for parts in _ICON_CANDIDATES:
        candidate = PROJECT_ROOT.joinpath(*parts)
        if candidate.is_file():
            return candidate
    return canonical


def windows_icon_file() -> Path:
    """Return the Windows shortcut icon; may not exist."""
    return PROJECT_ROOT / "assets" / "icons" / "youtube-clipster.ico"


def _xdg_user_dir(key: str) -> Path | None:
    """Resolve a single entry of the freedesktop ``user-dirs.dirs`` file."""
    base = os.environ.get("XDG_CONFIG_HOME")
    config = (Path(base) if base else Path.home() / ".config") / "user-dirs.dirs"
    try:
        content = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for raw in content.splitlines():
        line = raw.strip()
        if not line.startswith(key + "="):
            continue
        value = line.split("=", 1)[1].strip().strip('"')
        value = value.replace("$HOME", str(Path.home()))
        candidate = Path(value)
        if candidate.is_dir():
            return candidate
    return None


def _windows_shell_folder(guid: str) -> Path | None:
    """Resolve a Windows known folder through the registry."""
    try:
        import winreg
    except ImportError:
        return None
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, guid)
    except OSError:
        return None
    expanded = Path(os.path.expandvars(value))
    return expanded if expanded.is_dir() else None


#: Folder created inside the system Downloads directory.  The files dropped
#: straight into ``~/Downloads`` mixed them in with everything a browser ever
#: saved.
DOWNLOAD_SUBFOLDER = "clipster"


def system_download_dir() -> Path:
    """Return the operating system's own Downloads folder.

    The plain folder, without Clipster's subfolder - what a file dialog would
    open at, and the base :func:`default_download_dir` builds on.

    :return: The user's Downloads directory.
    """
    if IS_WINDOWS:
        folder = _windows_shell_folder("{374DE290-123F-4565-9164-39C4925E467B}")
        if folder is not None:
            return folder
    elif IS_LINUX:
        folder = _xdg_user_dir("XDG_DOWNLOAD_DIR")
        if folder is not None:
            return folder
    return Path.home() / "Downloads"


def default_download_dir() -> Path:
    """Return the folder downloads land in when Settings names none.

    Always the system Downloads folder plus :data:`DOWNLOAD_SUBFOLDER`, so the
    files stay together and apart from everything else that folder collects.

    :return: The default download directory.
    """
    return system_download_dir() / DOWNLOAD_SUBFOLDER


def desktop_dir() -> Path:
    """Return the user's desktop folder, falling back to the home directory."""
    if IS_WINDOWS:
        folder = _windows_shell_folder("Desktop")
        if folder is not None:
            return folder
    elif IS_LINUX:
        folder = _xdg_user_dir("XDG_DESKTOP_DIR")
        if folder is not None:
            return folder
    for name in ("Desktop", "Schreibtisch", "Bureau", "Escritorio"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return candidate
    return Path.home()


def autostart_dir() -> Path:
    """Return the freedesktop autostart directory (Linux only)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "autostart"


def ensure_install_dir() -> Path:
    """Create and return :func:`install_dir`."""
    target = install_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target
