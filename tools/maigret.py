# tools/maigret.py — wrapper around Maigret.
#
# Maigret is more powerful than Sherlock: 3000+ sites, profile parsing,
# it pulls bio, dates, links. It writes a Markdown report,
# while stdout carries metadata that is not in the report.
#
# Strategy:
#   1. Run Maigret with --md (Markdown) and --json simple.
#   2. Parse stdout — it has [+] Site: URL + metadata (bio, followers).
#   3. Parse Markdown — it has the summary and the list of accounts.
#   4. If nothing — return an empty list.

import subprocess
import os
import re
from config import OUTPUT_DIR
from logger import get_logger


logger = get_logger("tools.maigret")


def _parse_stdout(raw: str) -> list:
    """
    Parses Maigret stdout.
    Lines look like:
      [+] TikTok: https://www.tiktok.com/@octocat    | ▅▇▇ 10/108 ...
      [+] Twitch: https://twitchtracker.com/octocat  | ▂▂▄ 27/108 ...
      ├─fullname: pomoica
      ├─bio: tg - https://t.me/example
      ├─follower_count: 282
    """
    found = []
    current = None

    # Regex for the main account line
    # ^\[\+\]\s+(.+?):\s+(https?://[^\s|]+)
    account_re = re.compile(r"^\[\+\]\s+(.+?):\s+(https?://[^\s|]+)")

    # Regex for metadata (├─key: value or └─key: value)
    meta_re = re.compile(r"^[├└]─(\w+):\s*(.*)$")

    for line in raw.splitlines():
        acc = account_re.search(line)
        if acc:
            # Save the previous account
            if current:
                found.append(current)
            current = {
                "site": acc.group(1).strip(),
                "url": acc.group(2).strip(),
                "data": {},
            }
            continue

        # Metadata of the current account
        if current:
            meta = meta_re.search(line.strip())
            if meta:
                key = meta.group(1).strip()
                value = meta.group(2).strip()
                if value:
                    current["data"][key] = value

    if current:
        found.append(current)

    return found


def _parse_markdown(md_text: str) -> list:
    """
    Parses the Maigret Markdown report.
    Format:
      ## Accounts found
      | Site | URL | ... |
      |------|-----|-----|
      | TikTok | https://... | ... |
    """
    found = []
    in_accounts = False

    for line in md_text.splitlines():
        if line.strip().startswith("## Accounts found"):
            in_accounts = True
            continue
        if in_accounts:
            if line.strip().startswith("##") and "Accounts" not in line:
                break
            # Table rows: | TikTok | https://... | ... |
            if line.strip().startswith("|") and "http" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    site = parts[0]
                    url = parts[1]
                    if url.startswith("http"):
                        found.append({"site": site, "url": url, "data": {}})
    return found


def run_maigret(username: str, top_sites: int = 100) -> dict:
    """
    Runs Maigret for a username.
    Returns:
    {
      "username": "octocat",
      "found": [
        {
          "site": "TikTok",
          "url": "https://www.tiktok.com/@octocat",
          "data": {"fullname": "pomoica", "bio": "...", "follower_count": "282"}
        },
        ...
      ],
      "raw_stdout": "...",
      "raw_markdown": "..."
    }
    """
    logger.info("Запуск Maigret: %s (top_sites=%s)", username, top_sites)
    reports_dir = os.path.join(OUTPUT_DIR, f"maigret_{username}")
    os.makedirs(reports_dir, exist_ok=True)

    cmd = [
        "maigret", username,
        "--top-sites", str(top_sites),
        "--timeout", "30",
        "--no-recursion",
        "--no-color",
        "--md",                    # Markdown report
        "-fo", reports_dir,        # directory for reports
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        raw = result.stdout or ""
    except FileNotFoundError:
        logger.warning("Maigret не найден")
        return {"username": username, "found": [], "error": "Maigret не найден"}
    except subprocess.TimeoutExpired:
        logger.warning("Maigret timeout (600 сек)")
        return {"username": username, "found": [], "error": "Maigret не успел за 10 минут"}
    except Exception as exc:
        logger.error("Ошибка Maigret: %s", exc, exc_info=True)
        return {"username": username, "found": [], "error": f"Maigret: {exc}"}

    # 1. Parse stdout — metadata lives there
    found = _parse_stdout(raw)

    # 2. If stdout is empty — try Markdown
    md_text = ""
    if os.path.isdir(reports_dir):
        for fname in os.listdir(reports_dir):
            if fname.endswith(".md"):
                try:
                    with open(os.path.join(reports_dir, fname), "r", encoding="utf-8") as f:
                        md_text = f.read()
                    break
                except OSError:
                    pass

    if not found and md_text:
        found = _parse_markdown(md_text)

    logger.info("Maigret завершен, найдено %s профилей", len(found))
    if result.returncode != 0 and not found:
        logger.warning("Maigret код %s, stderr: %s", result.returncode,
                       (result.stderr or "").strip()[:300])

    return {
        "username": username,
        "found": found,
        "raw_stdout": raw[:5000],
        "raw_markdown": md_text[:5000],
    }
