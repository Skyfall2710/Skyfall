# logger.py — Skyfall end-to-end logging.
#
# Logs are written to ~/osint_helper/logs/skyfall_YYYYMMDD_HHMMSS.log.
# The file rotates: at most 5 files (current + 4 backups) of 10 MB each.
#
# If the home directory is unavailable (e.g. the process runs in a sandbox),
# a temporary directory is used — the app must not crash because of logging.
#
# Usage:
#   from logger import get_logger
#   logger = get_logger("main")
#   logger.info("Starting")

import logging
import os
import tempfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 4          # current + 4 = max 5 files
_LOGGER_ROOT = "skyfall"

_configured = False
_log_file = None
_handler = None
_module_loggers = set()
_module_logger_names = set()


def _log_level() -> int:
    name = os.environ.get("OSINT_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _preferred_dir() -> Path:
    raw = os.environ.get("OSINT_LOG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    try:
        home = Path.home()
    except RuntimeError:
        home = Path(tempfile.gettempdir())
    return home / "osint_helper" / "logs"


def _ensure_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _resolve_dir() -> Path:
    preferred = _preferred_dir()
    if _ensure_writable(preferred):
        return preferred

    fallback = Path(tempfile.gettempdir()) / "osint_helper" / "logs"
    if _ensure_writable(fallback):
        return fallback

    # Absolute last resort: the logger will work without a file.
    return preferred


def _configure() -> None:
    global _configured, _log_file, _handler
    if _configured:
        return
    _configured = True

    log_dir = _resolve_dir()
    _log_file = log_dir / f"skyfall_{datetime.now():%Y%m%d_%H%M%S}.log"

    try:
        handler = RotatingFileHandler(
            _log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        _handler = handler
    except OSError:
        # Do not crash the app just because the log cannot be opened.
        _handler = logging.NullHandler()


def get_logger(name: str) -> logging.Logger:
    """
    Returns a module logger: main, api, tools.sherlock, ...

    One shared RotatingFileHandler is attached to every named
    logger; propagate=False protects against duplicated records.
    """
    global _handler
    _configure()

    clean = str(name or "app").strip().strip(".") or "app"
    if clean.startswith(_LOGGER_ROOT + "."):
        clean = clean[len(_LOGGER_ROOT) + 1:]

    module_logger = logging.getLogger(clean)
    module_logger.setLevel(_log_level())
    module_logger.propagate = False

    if _handler is not None and _handler not in module_logger.handlers:
        module_logger.addHandler(_handler)
    _module_loggers.add(module_logger)
    _module_logger_names.add(clean)

    return module_logger


def log_file():
    """Path to the current log file (or None if it is unavailable)."""
    _configure()
    if _log_file and _log_file.exists():
        return _log_file
    return None


def log_dir() -> Path:
    _configure()
    return _log_file.parent if _log_file else _preferred_dir()


def latest_log_file():
    """The freshest skyfall_*.log (for GET /api/logs)."""
    _configure()
    directory = log_dir()
    try:
        files = sorted(
            directory.glob("skyfall_*.log"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    return files[0] if files else None


def reset_for_tests() -> None:
    """Resets the global state (used in tests)."""
    global _configured, _log_file, _handler
    names = set(_module_logger_names)
    for module_logger in list(_module_loggers):
        if _handler is not None:
            try:
                module_logger.removeHandler(_handler)
            except Exception:
                pass
    if _handler is not None:
        try:
            _handler.close()
        except Exception:
            pass
    _module_loggers.clear()
    _module_logger_names.clear()
    _handler = None
    _configured = False
    _log_file = None

    # Recreate the logger in the current environment and attach the handler
    # back to the already-created module loggers, so logging does not go to stderr.
    _configure()
    for name in names:
        module_logger = logging.getLogger(name)
        module_logger.setLevel(_log_level())
        module_logger.propagate = False
        if _handler is not None and _handler not in module_logger.handlers:
            module_logger.addHandler(_handler)
        _module_loggers.add(module_logger)
        _module_logger_names.add(name)
