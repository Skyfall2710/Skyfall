# tools/sherlock.py — wrapper around Sherlock.

import subprocess
import re

from logger import get_logger


logger = get_logger("tools.sherlock")


def run_sherlock(username: str) -> dict:
    logger.info("Запуск Sherlock: %s", username)
    cmd = [
        "sherlock", username,
        "--print-found", "--no-color",
        "--timeout", "10",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        raw = result.stdout or ""
    except FileNotFoundError:
        logger.warning("Sherlock не найден")
        return {"username": username, "found": [], "error": "Sherlock не найден"}
    except subprocess.TimeoutExpired:
        logger.warning("Sherlock timeout (300 сек)")
        return {"username": username, "found": [], "error": "Sherlock не успел"}
    except Exception as exc:
        logger.error("Ошибка Sherlock: %s", exc, exc_info=True)
        return {"username": username, "found": [], "error": f"Sherlock: {exc}"}

    found = []
    pattern = re.compile(r"\[\+\]\s+([^:]+):\s+(https?://\S+)")
    for line in raw.splitlines():
        m = pattern.search(line)
        if m:
            found.append({"site": m.group(1).strip(), "url": m.group(2).strip()})

    logger.info("Sherlock завершен, найдено %s сайтов", len(found))
    if result.returncode != 0 and not found:
        logger.warning("Sherlock код %s, stderr: %s", result.returncode,
                       (result.stderr or "").strip()[:300])
    return {"username": username, "found": found}
