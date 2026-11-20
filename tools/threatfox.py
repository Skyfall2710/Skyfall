# tools/threatfox.py — checks domains/IPs against the ThreatFox (abuse.ch) database.
#
# ThreatFox is a public database of indicators of compromise (IOC):
# C2 servers, malware domains, payload delivery, etc.
#
# Documentation: https://threatfox.abuse.ch/api/
#
# A free Auth-Key is required (https://auth.abuse.ch/).
# The key is taken from the THREATFOX_KEY environment variable and is NOT hardcoded.
#
# Example:
#   export THREATFOX_KEY="your-key"
#   python3 -c "from tools.threatfox import check_ioc; print(check_ioc('example.com'))"

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from logger import get_logger


logger = get_logger("tools.threatfox")

THREATFOX_URL = os.environ.get(
    "THREATFOX_URL",
    "https://threatfox-api.abuse.ch/api/v1/",
)


def _get_key() -> str:
    return os.environ.get("THREATFOX_KEY", "").strip()


def _confidence(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def check_ioc(domain_or_ip: str, timeout: int = 15) -> dict:
    """
    Checks a single IOC (domain or IP) in ThreatFox.

    Returns:
      {
        "ioc": "...",
        "found": True,
        "malware": "Emotet",
        "confidence": 100,
        "threat_type": "botnet_cc",
        "matches": [...]
      }
    or:
      {"ioc": "...", "found": False, "error": "..."}
    """
    ioc = (domain_or_ip or "").strip().lower()
    if not ioc:
        return {"ioc": "", "found": False, "error": "Пустой IOC"}

    key = _get_key()
    if not key:
        return {
            "ioc": ioc,
            "found": False,
            "error": "THREATFOX_KEY не задан (получи ключ на https://auth.abuse.ch/)",
        }

    logger.debug("ThreatFox: проверка %s", ioc)

    body = {
        "query": "search_ioc",
        "search_term": ioc,
        "exact_match": True,
    }
    headers = {
        "Auth-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            THREATFOX_URL,
            json=body,
            headers=headers,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        logger.warning("ThreatFox timeout: %s", ioc)
        return {"ioc": ioc, "found": False, "error": "ThreatFox timeout"}
    except requests.exceptions.RequestException as exc:
        logger.warning("ThreatFox request error (%s): %s", ioc, exc)
        return {"ioc": ioc, "found": False, "error": f"ThreatFox request error: {exc}"}

    if response.status_code in (401, 403):
        return {"ioc": ioc, "found": False, "error": "ThreatFox: неверный Auth-Key"}
    if response.status_code == 429:
        return {"ioc": ioc, "found": False, "error": "ThreatFox: rate limit (429)"}
    if response.status_code != 200:
        return {
            "ioc": ioc,
            "found": False,
            "error": f"ThreatFox HTTP {response.status_code}",
        }

    try:
        payload = response.json()
    except ValueError:
        return {"ioc": ioc, "found": False, "error": "ThreatFox: ответ не JSON"}

    if not isinstance(payload, dict):
        return {"ioc": ioc, "found": False, "error": "ThreatFox: неожиданный формат ответа"}

    status = payload.get("query_status")
    data = payload.get("data") or []

    if status != "ok" or not isinstance(data, list) or not data:
        return {
            "ioc": ioc,
            "found": False,
            "query_status": status or "no_result",
        }

    matches = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        confidence = _confidence(entry.get("confidence_level"))
        matches.append({
            "ioc": entry.get("ioc") or ioc,
            "malware": (
                entry.get("malware_printable")
                or entry.get("malware")
                or "Unknown"
            ),
            "malware_id": entry.get("malware") or "",
            "confidence": confidence,
            "threat_type": entry.get("threat_type") or "",
            "first_seen": entry.get("first_seen") or "",
            "reference": entry.get("reference") or "",
        })

    if not matches:
        return {"ioc": ioc, "found": False, "query_status": status or "no_result"}

    best = max(matches, key=lambda item: item["confidence"])

    return {
        "ioc": ioc,
        "found": True,
        "malware": best["malware"],
        "confidence": best["confidence"],
        "threat_type": best["threat_type"],
        "matches": matches,
    }


def check_many(iocs, timeout: int = 15, max_workers: int = 4) -> list:
    """
    Checks a batch of IOCs in parallel (gently: 4 threads by default).

    Duplicates are removed, the order of results is preserved.
    """
    unique = []
    seen = set()
    for ioc in iocs or []:
        value = str(ioc or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)

    if not unique:
        return []

    logger.info("ThreatFox: старт проверки %s IOC", len(unique))

    # Without a key we spend no threads or requests — fail fast with a clear error.
    if not _get_key():
        logger.warning("ThreatFox: THREATFOX_KEY не задан, проверка пропущена")
        return [
            {
                "ioc": value.lower(),
                "found": False,
                "error": "THREATFOX_KEY не задан (получи ключ на https://auth.abuse.ch/)",
            }
            for value in unique
        ]

    results = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(unique))) as pool:
        futures = {
            pool.submit(check_ioc, value, timeout): value
            for value in unique
        }
        for future in as_completed(futures):
            results.append(future.result())

    order = {value.lower(): index for index, value in enumerate(unique)}
    results.sort(key=lambda item: order.get(item.get("ioc", ""), 10 ** 9))
    return results
