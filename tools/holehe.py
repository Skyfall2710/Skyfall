# tools/holehe.py — wrapper around Holehe.
#
# Holehe checks where an email is registered.
# It does NOT notify the owner.
#
# IMPORTANT: Holehe output format (see holehe/core.py):
#   [+] site.com                    — the email IS FOUND on this site
#   [+] site.com recovery@mail.com  — found + service metadata
#   [-] site.com                    — the email is NOT found
#   [x] site.com                    — rate limit (could not check)
#   [+] Email used                  — LEGEND (not a site!)
#   [-] Email not used              — LEGEND (not a site!)
#   [x] Rate limit                  — LEGEND (not a site!)
#   [+] Twitter : @...              — service line
#
# We catch ONLY "[+] <site>" lines, where <site> is a valid domain.
# Everything that follows the domain (email recovery / phone / FullName)
# is stored in the "details" field, but is not treated as a site.
# We drop the legend and service lines.

import re
import subprocess

from logger import get_logger


logger = get_logger("tools.holehe")

# ANSI sequences (in case --no-color did not work)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Strict domain: at least one dot, TLD — letters only (2+).
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$",
    re.IGNORECASE,
)

# Legend lines that Holehe prints at the end of the report
_LEGEND_LABELS = {
    "email",
    "email used",
    "email not used",
    "rate limit",
    "twitter",
    "github",
    "for btc donations",
}

# [+] site.com [metadata]
_USED_RE = re.compile(r"^\s*\[\+\]\s+(\S+)(.*)$")
# [x] site.com [metadata]
_RATE_RE = re.compile(r"^\s*\[x\]\s+(\S+)(.*)$")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _is_valid_domain(text: str) -> bool:
    """
    True only if text is a real domain like site.com.

    Rejects:
      • "Email", "Email used", "Rate limit", "Twitter" (no dot);
      • "user@example.com" (does not match the regex);
      • "http://site.com" (does not match the regex);
      • "site" (no dot).
    """
    text = (text or "").strip().lower()
    if not text:
        return False
    if text in _LEGEND_LABELS:
        return False
    return bool(_DOMAIN_RE.fullmatch(text))


def _clean_details(rest: str) -> str:
    """Removes extra separators from the tail of a Holehe line."""
    rest = _strip_ansi(rest).strip()
    return rest.strip(" /|-—\t")


def parse_holehe_output(raw: str) -> dict:
    """
    Parses Holehe stdout.

    Returns:
      {
        "found": [{"site": "github.com", "url": "https://github.com",
                   "details": "..."}],
        "rate_limited": ["site.com", ...]
      }
    """
    raw = _strip_ansi(raw or "")
    found = []
    rate_limited = []
    seen_found = set()
    seen_rate = set()

    for line in raw.splitlines():
        # [+] site.com — FOUND
        m = _USED_RE.match(line)
        if m:
            candidate = m.group(1).strip().strip(".,;:")
            if _is_valid_domain(candidate):
                domain = candidate.lower()
                if domain not in seen_found:
                    seen_found.add(domain)
                    item = {
                        "site": domain,
                        "url": f"https://{domain}",
                    }
                    details = _clean_details(m.group(2))
                    if details:
                        item["details"] = details
                    found.append(item)
            continue

        # [x] site.com — RATE LIMIT
        m = _RATE_RE.match(line)
        if m:
            candidate = m.group(1).strip().strip(".,;:")
            if _is_valid_domain(candidate):
                domain = candidate.lower()
                if domain not in seen_rate:
                    seen_rate.add(domain)
                    rate_limited.append(domain)

    return {"found": found, "rate_limited": rate_limited}


def run_holehe(email: str) -> dict:
    """
    Runs Holehe for an email.
    Returns:
    {
      "email": "...",
      "found": [{"site": "...", "url": "...", "details": "..."}],
      "rate_limited": [...],   # sites that could not be checked
      "raw": "..."
    }
    """
    logger.info("Запуск Holehe: %s", email)
    cmd = [
        "holehe", email,
        "--only-used",     # show only found ones
        "--no-color",
        "--no-clear",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        raw = result.stdout or ""
    except FileNotFoundError:
        logger.warning("Holehe не найден")
        return {"email": email, "found": [], "rate_limited": [],
                "error": "Holehe не найден"}
    except subprocess.TimeoutExpired:
        logger.warning("Holehe timeout (180 сек)")
        return {"email": email, "found": [], "rate_limited": [],
                "error": "Holehe не успел за 3 минуты"}
    except Exception as exc:
        logger.error("Ошибка Holehe: %s", exc, exc_info=True)
        return {"email": email, "found": [], "rate_limited": [],
                "error": f"Holehe: {exc}"}

    parsed = parse_holehe_output(raw)

    response = {
        "email": email,
        "found": parsed["found"],
        "rate_limited": parsed["rate_limited"],
        "raw": raw[:5000],   # truncate so the JSON does not bloat
    }

    # If Holehe failed but printed something — keep stderr for diagnostics.
    logger.info(
        "Holehe завершен: найдено %s сайтов, rate-limit %s",
        len(parsed["found"]), len(parsed["rate_limited"]),
    )

    if result.returncode != 0 and not parsed["found"]:
        stderr = (result.stderr or "").strip()
        if stderr:
            response["error"] = stderr[:500]
            logger.warning("Holehe код %s, stderr: %s", result.returncode, stderr[:300])

    return response
