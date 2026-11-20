# i18n.py — localization (internationalization).
#
# How it works:
#   - Loads the dictionary from locales/<lang>.json
#   - The t("key") function returns the translation
#   - The t("key", count=5) function substitutes parameters into {count}
#
# How to choose the language:
#   1. Command-line flag: python3 main.py --lang en
#   2. Environment variable: OSINT_LANG=en python3 main.py
#   3. Auto-detection from LANG (the system one)
#   4. Default — ru

import os
import json
import argparse
from pathlib import Path


# Where the translations live
LOCALES_DIR = Path(__file__).parent / "locales"

# Available languages
AVAILABLE_LANGS = ["ru", "en"]
DEFAULT_LANG = "en"

# Global state (filled in by setup())
_current_lang = DEFAULT_LANG
_translations = {}


def _load_translations(lang: str) -> dict:
    """Reads locales/<lang>.json."""
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        print(f"[i18n] Warning: locale file not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[i18n] Error loading {path}: {e}")
        return {}


def _detect_lang() -> str:
    """
    Detects the language from:
      1. The OSINT_LANG environment variable
      2. The system LANG variable (e.g. ru_RU.UTF-8 → ru)
      3. DEFAULT_LANG
    """
    # 1. OSINT_LANG
    env_lang = os.environ.get("OSINT_LANG", "").lower()
    if env_lang in AVAILABLE_LANGS:
        return env_lang

    # 2. System LANG (ru_RU.UTF-8 → ru)
    sys_lang = os.environ.get("LANG", "").lower()[:2]
    if sys_lang in AVAILABLE_LANGS:
        return sys_lang

    # 3. Fallback
    return DEFAULT_LANG


def parse_lang_arg() -> str:
    """
    Reads --lang from the command-line arguments.
    If not given — detects it automatically.
    Called once in main().
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", choices=AVAILABLE_LANGS, default=None)
    args, _ = parser.parse_known_args()

    if args.lang:
        return args.lang
    return _detect_lang()


def setup(lang: str = None):
    """
    Initializes localization. Call once at the start of main().
    """
    global _current_lang, _translations
    _current_lang = lang or _detect_lang()
    _translations = _load_translations(_current_lang)


def t(key: str, **kwargs) -> str:
    """
    Returns the translation for a key.
    If the key is not found — returns the key itself (so a missing one is visible).
    Parameters are substituted into {placeholder}.
    """
    text = _translations.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def current_lang() -> str:
    """Returns the current language."""
    return _current_lang
