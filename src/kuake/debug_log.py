"""Optional structured debug log to a file.

Activated by setting environment variable `KUAKE_DEBUG_LOG=/path/to/file`.
When set, every CLI command writes a detailed timeline to that file:
- info/ok/warn/err lines mirrored from the rich console output
- each panel_api request URL + body + response code + body snippet
- exceptions with full traceback
- timing markers (per-stage push, sign_in latency, etc.)

This makes diagnosing real-world issues across machines straightforward —
hand the log file to the dev, they see the entire timeline.
"""
from __future__ import annotations
import os
import logging
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOG_PATH: Optional[Path] = None
_root_logger: Optional[logging.Logger] = None


def _setup_once() -> Optional[logging.Logger]:
    global _LOG_PATH, _root_logger
    if _root_logger is not None:
        return _root_logger
    path_str = os.environ.get("KUAKE_DEBUG_LOG")
    if not path_str:
        return None
    path = Path(path_str).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = path

    logger = logging.getLogger("kuake")
    logger.setLevel(logging.DEBUG)
    # Avoid duplicate handlers on reimport
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.propagate = False

    # Write run header
    from kuake import __version__
    logger.info("======== kuake debug log ========")
    logger.info(f"kuake-pipe version: {__version__}")
    logger.info(f"python: {sys.version.split()[0]} {platform.platform()}")
    logger.info(f"argv: {sys.argv}")
    logger.info(f"cwd: {os.getcwd()}")
    logger.info(f"KUAKE_HOME: {os.environ.get('KUAKE_HOME', '<unset>')}")
    logger.info(f"started at: {datetime.now().isoformat()}")
    logger.info("---------------------------------")
    _root_logger = logger
    return logger


def get_logger(name: str = "kuake"):
    """Return a logger under the kuake hierarchy. No-op if debug log not enabled."""
    _setup_once()
    return logging.getLogger(name)


def log_path() -> Optional[Path]:
    """Path of the active debug log, or None if disabled."""
    _setup_once()
    return _LOG_PATH


def dbg(msg: str, name: str = "kuake.dbg") -> None:
    """Log a debug-level message (only goes to file, not console)."""
    get_logger(name).debug(msg)


def log_event(level: str, msg: str, name: str = "kuake.event") -> None:
    """Log an event mirrored from the console output."""
    lg = get_logger(name)
    if level == "info":
        lg.info(msg)
    elif level == "ok":
        lg.info(f"OK: {msg}")
    elif level == "warn":
        lg.warning(msg)
    elif level == "err":
        lg.error(msg)
    else:
        lg.info(msg)


def log_exception(exc: BaseException, where: str = "<unknown>") -> None:
    """Log full traceback of an exception."""
    lg = get_logger("kuake.exc")
    lg.exception(f"Exception at {where}: {type(exc).__name__}: {exc}")
