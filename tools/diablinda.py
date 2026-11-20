# tools/diablinda.py — wrapper around Diablinda.
#
# Diablinda — a JS alternative to Holehe (Node.js, ESM).
# Checks an email on 50+ platforms and pulls metadata:
# nicknames, avatars, bio, names, profile links.
#
# Run:
#   npx diablinda <email> --json
#
# JSON format (Diablinda 1.x):
#   {
#     "email": "...",
#     "totalModules": 55,
#     "hits": 4,
#     "results": [
#       {
#         "id": "github",
#         "service": "GitHub",
#         "category": "tech",
#         "exists": true,
#         "metadata": {
#           "username": "octocat",
#           "avatarUrl": "https://...",
#           "profileUrl": "https://github.com/octocat",
#           "name": "...",
#           "bio": "..."
#         }
#       }
#     ],
#     "dossier": {
#       "names": [...], "usernames": [...], "avatars": [...], ...
#     }
#   }

import json
import os
import re
import subprocess

from logger import get_logger


logger = get_logger("tools.diablinda")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _extract_json(raw: str):
    """
    Extracts a JSON object/array from stdout.

    npx may print npm warnings before the JSON, so
    we look for the first '{' and the last '}', then — the first '[' and the last ']'.
    """
    text = _strip_ansi(raw or "")

    candidates = []

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    return []


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_diablinda_json(payload) -> dict:
    """
    Normalizes Diablinda JSON to the internal format.

    Returns:
      {
        "email": "...",
        "found": [
          {
            "service": "GitHub",
            "username": "octocat",
            "avatar": "https://...",
            "profile_url": "https://github.com/octocat",
            "url": "https://github.com/octocat",
            "name": "...",
            "bio": "...",
            "category": "tech",
            "verified_by_email": true
          }
        ],
        "dossier": {
          "names": [...], "usernames": [...], "avatars": [...],
          "bios": [...], "locations": [...], "companies": [...],
          "external_links": [...]
        }
      }
    """
    result = {
        "email": "",
        "found": [],
        "dossier": {
            "names": [],
            "usernames": [],
            "avatars": [],
            "bios": [],
            "locations": [],
            "companies": [],
            "external_links": [],
        },
    }

    if isinstance(payload, list):
        results = payload
        dossier_raw = {}
        email = ""
    elif isinstance(payload, dict):
        email = _clean(payload.get("email") or payload.get("targetEmail"))
        results = (
            _as_list(payload.get("results"))
            or _as_list(payload.get("found"))
            or _as_list(payload.get("data"))
        )
        # If this is a single ServiceResult rather than a summary.
        if not results and (payload.get("service") or payload.get("id")):
            results = [payload]
        dossier_raw = payload.get("dossier") or {}
    else:
        results = []
        dossier_raw = {}
        email = ""

    result["email"] = email

    seen = set()
    for item in results:
        if not isinstance(item, dict):
            continue

        # exists=False — the site was checked, there is no account.
        if item.get("exists") is False:
            continue

        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        service = (
            _clean(item.get("service"))
            or _clean(item.get("name"))
            or _clean(item.get("id"))
            or "?"
        )
        username = (
            _clean(metadata.get("username"))
            or _clean(item.get("username"))
            or _clean(item.get("nickname"))
        )
        avatar = (
            _clean(metadata.get("avatarUrl"))
            or _clean(metadata.get("avatar"))
            or _clean(item.get("avatarUrl"))
            or _clean(item.get("avatar"))
        )
        profile_url = (
            _clean(metadata.get("profileUrl"))
            or _clean(item.get("profileUrl"))
            or _clean(item.get("url"))
        )
        name = _clean(metadata.get("name"))
        bio = _clean(metadata.get("bio"))
        category = _clean(item.get("category"))
        extra = metadata.get("extra") if isinstance(metadata.get("extra"), dict) else {}
        verified = bool(extra.get("verifiedByEmail"))

        key = (service.lower(), username.lower(), profile_url.lower())
        if key in seen:
            continue
        seen.add(key)

        result["found"].append({
            "service": service,
            "username": username,
            "avatar": avatar,
            "profile_url": profile_url,
            "url": profile_url,
            "name": name,
            "bio": bio,
            "category": category,
            "verified_by_email": verified,
        })

    # Dossier — aggregated data across all found accounts.
    if isinstance(dossier_raw, dict):
        result["dossier"]["names"] = [
            _clean(x) for x in _as_list(dossier_raw.get("names")) if _clean(x)
        ]
        result["dossier"]["usernames"] = [
            _clean(x) for x in _as_list(dossier_raw.get("usernames")) if _clean(x)
        ]
        result["dossier"]["avatars"] = [
            _clean(x) for x in _as_list(dossier_raw.get("avatars")) if _clean(x)
        ]
        result["dossier"]["bios"] = [
            _clean(x) for x in _as_list(dossier_raw.get("bios")) if _clean(x)
        ]
        result["dossier"]["locations"] = [
            _clean(x) for x in _as_list(dossier_raw.get("locations")) if _clean(x)
        ]
        result["dossier"]["companies"] = [
            _clean(x) for x in _as_list(dossier_raw.get("companies")) if _clean(x)
        ]

        links = []
        for link in _as_list(dossier_raw.get("externalLinks")):
            if not isinstance(link, dict):
                continue
            url = _clean(link.get("url"))
            if url:
                links.append({
                    "platform": _clean(link.get("platform")) or "?",
                    "url": url,
                })
        result["dossier"]["external_links"] = links

    if not result["email"] and isinstance(dossier_raw, dict):
        result["email"] = _clean(dossier_raw.get("targetEmail"))

    return result


def run_diablinda(email: str) -> dict:
    """
    Runs Diablinda and returns the normalized result.

    Returns:
      {
        "email": "...",
        "found": [{"service": ..., "username": ..., "avatar": ..., ...}],
        "dossier": {...},
        "raw": "...",
        "error": "..."   # only on failure
      }
    """
    logger.info("Запуск Diablinda: %s", email)
    binary = os.environ.get("DIABLINDA_BIN", "").strip()
    if binary:
        cmd = [binary, email, "--json"]
    else:
        # --yes: do not ask for confirmation when installing the package via npx.
        cmd = ["npx", "--yes", "diablinda", email, "--json"]

    env = os.environ.copy()
    env.setdefault("npm_config_yes", "true")
    env.setdefault("NPM_CONFIG_YES", "true")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        raw = result.stdout or ""
    except FileNotFoundError:
        logger.warning("Diablinda/npx не найден")
        return {"email": email, "found": [], "error": "npx/Diablinda не найден"}
    except subprocess.TimeoutExpired:
        logger.warning("Diablinda timeout (300 сек)")
        return {"email": email, "found": [], "error": "Diablinda не успел за 5 минут"}
    except Exception as exc:
        logger.error("Ошибка Diablinda: %s", exc, exc_info=True)
        return {"email": email, "found": [], "error": f"Diablinda: {exc}"}

    payload = _extract_json(raw)

    if payload is None:
        stderr = _strip_ansi(result.stderr or "").strip()
        logger.warning("Diablinda: не удалось распарсить JSON, stderr=%s", stderr[:300])
        return {
            "email": email,
            "found": [],
            "error": "Не удалось распарсить JSON Diablinda",
            "raw": (raw or stderr)[:2000],
        }

    parsed = parse_diablinda_json(payload)
    if not parsed["email"]:
        parsed["email"] = email

    parsed["raw"] = raw[:5000]

    logger.info("Diablinda завершен: найдено %s профилей", len(parsed["found"]))

    if result.returncode != 0 and not parsed["found"]:
        stderr = _strip_ansi(result.stderr or "").strip()
        if stderr:
            parsed["error"] = stderr[:500]
            logger.warning("Diablinda код %s, stderr: %s", result.returncode, stderr[:300])

    return parsed
