"""Загрузка настроек из config.ini."""
import configparser
import sys
from pathlib import Path

BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
_cfg = configparser.ConfigParser()
_cfg.read(BASE_DIR / "config.ini", encoding="utf-8")


def _get(section, key, default):
    try:
        return _cfg.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default


def _db_url() -> str:
    url = _get("database", "url", "sqlite:///data/library.db")
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url[len("sqlite:///"):]
        path = (BASE_DIR / rel).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + path.as_posix()
    return url


import os

DB_URL = os.environ.get("LIBRARYIS_DB") or _db_url()
LOAN_DAYS = int(_get("app", "loan_days", "14"))
MAX_BOOKS = int(_get("app", "max_books", "5"))
IDLE_MINUTES = int(_get("app", "idle_minutes", "30"))
MAX_RENEWALS = 2
MAX_ATTEMPTS = 5
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_KEEP_DAYS = 30
BACKUP_DIR.mkdir(exist_ok=True)

ROLES = {"librarian": "Библиотекарь", "head": "Заведующий", "admin": "Администратор"}
