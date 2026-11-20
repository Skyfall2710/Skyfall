# main.py — the main Skyfall CLI script.
#
# What it does:
#   1. Shows the banner.
#   2. Asks for the data TYPE (nick / email / domain).
#   3. Runs the corresponding tools.
#   4. Normalizes and filters the data.
#   5. Sends it to the configured LLM (Ollama or cloud).
#   6. Prints the report + saves JSON.
#   7. Offers to continue the investigation along the found entities (pivot).
#
# Interface language: --lang ru|en, or OSINT_LANG, or auto-detection.

import argparse
import datetime
import json
import os
import re
import textwrap
import time

import requests

import config
from config import (
    OLLAMA_URL, OLLAMA_MODEL,
    build_filter_prompt, build_analyze_prompt,
    OUTPUT_DIR,
)
from site_weights import get_site_weight

from tools.sherlock import run_sherlock
from tools.maigret import run_maigret
from tools.holehe import run_holehe
from tools.diablinda import run_diablinda
from tools.theharvester import run_theharvester
from tools.threatfox import check_many

import i18n
from banner import clear_console, print_banner
from logger import get_logger


logger = get_logger("main")


# Maximum depth of the investigation chain (the original report — depth=0).
MAX_PIVOT_DEPTH = 3

# How many new entities to offer per step (to avoid going on forever).
MAX_PIVOT_CANDIDATES = 5

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9\-])"
)

_TELEGRAM_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t|telegram)\.me/"
    r"([A-Za-z0-9_]{4,32})\b",
    re.IGNORECASE,
)

_PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "domain.com",
    "email.com",
    "test.com",
}

_TELEGRAM_RESERVED = {
    "joinchat",
    "addstickers",
    "addemoji",
    "share",
    "proxy",
    "socks",
    "iv",
    "login",
}


# ============================================================
# HELPERS
# ============================================================

def _to_text(value) -> str:
    """Converts any value to a string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_to_text(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _add_unique(target: list, value) -> None:
    """Adds a value to the list if it is not there yet."""
    if value is None:
        return
    value = str(value).strip()
    if value and value not in target:
        target.append(value)


def _add_site(normalized: dict, site_entry: dict) -> dict:
    """
    Adds a site to normalized["sites"] without creating duplicate URLs.

    If such a URL already exists (e.g. Sherlock found github.com/user
    and Maigret — the same profile with bio/fullname), we merge data:
    Maigret/Diablinda metadata is not lost.
    """
    url = site_entry.get("url")
    if url:
        for existing in normalized["sites"]:
            if existing.get("url") != url:
                continue
            if site_entry.get("data"):
                merged = dict(existing.get("data") or {})
                merged.update(site_entry["data"])
                existing["data"] = merged
            if not existing.get("weight") and site_entry.get("weight"):
                existing["weight"] = site_entry["weight"]
            if not existing.get("reason") and site_entry.get("reason"):
                existing["reason"] = site_entry["reason"]
            return existing

    normalized["sites"].append(site_entry)
    return site_entry


def _entity_key(entity: dict) -> str:
    """Key for deduplicating entities in the pivot chain."""
    return f"{entity.get('type', '?')}:{str(entity.get('value', '')).lower()}"


# ============================================================
# DATA COLLECTION
# ============================================================

def collect_by_username(username: str) -> dict:
    data = {}
    logger.info("Сбор по нику: %s", username)

    print(i18n.t("collect.sherlock", value=username))
    data["sherlock"] = run_sherlock(username)
    sherlock_count = len(data["sherlock"].get("found", []))
    print(i18n.t("collect.found_sites", count=sherlock_count))
    logger.info("Sherlock: найдено %s сайтов", sherlock_count)

    print(i18n.t("collect.maigret", value=username))
    data["maigret"] = run_maigret(username, top_sites=100)
    maigret_count = len(data["maigret"].get("found", []))
    print(i18n.t("collect.found_sites", count=maigret_count))
    logger.info("Maigret: найдено %s профилей", maigret_count)

    return data


def collect_by_email(email: str) -> dict:
    """
    Holehe — the primary tool.

    If Holehe returned 0 results (rate limit / sites did not respond),
    we run Diablinda as a fallback and merge the results.
    """
    data = {}

    logger.info("Сбор по email: %s", email)
    print(i18n.t("collect.holehe", value=email))
    data["holehe"] = run_holehe(email)
    holehe_found = data["holehe"].get("found", [])
    print(i18n.t("collect.found_sites", count=len(holehe_found)))
    logger.info("Holehe: найдено %s сайтов", len(holehe_found))

    if not holehe_found:
        print(i18n.t("collect.diablinda_fallback", value=email))
        data["diablinda"] = run_diablinda(email)
        diablinda_found = data["diablinda"].get("found", [])
        print(i18n.t("collect.found_sites", count=len(diablinda_found)))
        logger.info("Diablinda: найдено %s профилей", len(diablinda_found))

        error = data["diablinda"].get("error")
        if error:
            print(i18n.t("collect.diablinda_error", error=error))
            logger.warning("Diablinda: %s", error)

    return data


def collect_by_domain(domain: str) -> dict:
    data = {}

    logger.info("Сбор по домену: %s", domain)
    print(i18n.t("collect.theharvester", value=domain))
    data["theharvester"] = run_theharvester(domain, limit=100)
    th = data["theharvester"]

    print(i18n.t("collect.found_emails", count=len(th.get("emails", []))))
    print(i18n.t("collect.found_subdomains", count=len(th.get("subdomains", []))))
    logger.info(
        "theHarvester: emails=%s subdomains=%s ips=%s",
        len(th.get("emails", [])), len(th.get("subdomains", [])),
        len(th.get("ips", [])),
    )

    if th.get("error"):
        print(i18n.t("collect.theharvester_error", error=th["error"]))
        logger.warning("theHarvester: %s", th["error"])

    # --- ThreatFox: the domain + all subdomains + all IPs ---
    iocs = [domain]
    iocs.extend(th.get("subdomains", []))
    iocs.extend(th.get("ips", []))
    for host in th.get("hosts", []):
        if isinstance(host, dict) and host.get("ip"):
            iocs.append(host["ip"])

    # Deduplication preserving order.
    unique_iocs = list(dict.fromkeys(
        str(ioc).strip() for ioc in iocs if str(ioc or "").strip()
    ))

    print(i18n.t("collect.threatfox", count=len(unique_iocs)))
    logger.info("ThreatFox: проверка %s IOC", len(unique_iocs))
    threatfox_results = check_many(unique_iocs)
    data["threatfox"] = threatfox_results
    logger.info("ThreatFox: найдено %s совпадений",
                sum(1 for item in threatfox_results if item.get("found")))

    for result in threatfox_results:
        if result.get("found"):
            print(i18n.t(
                "collect.threatfox_hit",
                ioc=result.get("ioc", "?"),
                malware=result.get("malware", "?"),
                confidence=result.get("confidence", "?"),
            ))

    errors = [r for r in threatfox_results if r.get("error")]
    if errors:
        print(i18n.t("collect.threatfox_error", error=errors[0]["error"]))

    return data


# ============================================================
# NORMALIZATION
# ============================================================

def normalize(data: dict, input_type: str, value: str) -> dict:
    normalized = {
        "input_type": input_type,
        "input_value": value,
        "nicks": [],
        "emails": [],
        "urls": [],
        "sites": [],
        "observations": [],
        "raw_data": data,     # <-- keep everything for pivots
    }

    # --- Sherlock ---
    sherlock = data.get("sherlock")
    if sherlock:
        _add_unique(normalized["nicks"], sherlock.get("username"))
        seen_domains = set()   # deduplication by domain
        for item in sherlock.get("found", []):
            url = item.get("url", "")
            if not url:
                continue
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            domain = domain_match.group(1) if domain_match else url

            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            _add_unique(normalized["urls"], url)
            _add_site(normalized, {"site": item.get("site", "?"), "url": url})
            normalized["observations"].append(
                f"Ник найден на {item.get('site', '?')}: {url}"
            )

    # --- Maigret (with metadata!) ---
    maigret = data.get("maigret")
    if maigret:
        for item in maigret.get("found", []):
            url = item.get("url")
            if not url:
                continue

            _add_unique(normalized["urls"], url)

            # Attach metadata (bio, fullname, followers).
            # _add_site() will merge them with the Sherlock entry for the same URL.
            site_entry = {"site": item.get("site", "?"), "url": url}
            if item.get("data"):
                site_entry["data"] = item["data"]
            _add_site(normalized, site_entry)

            # Human-readable observation for the LLM
            obs = f"Maigret: профиль на {item.get('site', '?')} — {url}"
            data_fields = item.get("data", {})
            if data_fields:
                interesting = []
                for key in ["fullname", "bio", "created_at",
                            "follower_count", "following_count"]:
                    if key in data_fields and data_fields[key]:
                        interesting.append(f"{key}={data_fields[key]}")
                if interesting:
                    obs += " | " + " | ".join(interesting)
            normalized["observations"].append(obs)

    # --- Holehe ---
    holehe = data.get("holehe")
    if holehe:
        email = holehe.get("email", "")
        # The target email itself is not a "found entity". We add it
        # only if Holehe actually found something.
        if holehe.get("found"):
            _add_unique(normalized["emails"], email)
        for item in holehe.get("found", []):
            site = item.get("site", "?")
            url = item.get("url") or f"https://{site}"
            details = item.get("details", "")

            _add_unique(normalized["urls"], url)

            site_entry = {
                "site": site,
                "url": url,
                "weight": "medium",
                "reason": _ui(
                    f"email {email} зарегистрирован",
                    f"email {email} is registered",
                ),
            }
            if details:
                site_entry["data"] = {"details": details}
            _add_site(normalized, site_entry)

            obs = f"Email {email} зарегистрирован на {site}"
            if details:
                obs += f" | {details}"
            normalized["observations"].append(obs)

    # --- Diablinda (fallback for email: nicks, avatars, bio) ---
    diablinda = data.get("diablinda")
    if diablinda:
        email = diablinda.get("email", "")
        # Do not add the target email if Diablinda found nothing.
        if diablinda.get("found"):
            _add_unique(normalized["emails"], email)

        dossier = diablinda.get("dossier") or {}
        for nick in dossier.get("usernames", []):
            _add_unique(normalized["nicks"], nick)

        for item in diablinda.get("found", []):
            if not isinstance(item, dict):
                continue

            service = item.get("service") or "?"
            username = item.get("username") or ""
            avatar = item.get("avatar") or ""
            profile_url = item.get("profile_url") or item.get("url") or ""
            name = item.get("name") or ""
            bio = item.get("bio") or ""
            category = item.get("category") or ""

            if username:
                _add_unique(normalized["nicks"], username)
            if profile_url:
                _add_unique(normalized["urls"], profile_url)

            data_fields = {}
            if username:
                data_fields["username"] = username
            if name:
                data_fields["name"] = name
            if avatar:
                data_fields["avatar"] = avatar
            if bio:
                data_fields["bio"] = bio
            if category:
                data_fields["category"] = category

            site_entry = {
                "site": service,
                "url": profile_url,
                "weight": "medium",
                "reason": _ui(
                    "профиль найден через Diablinda",
                    "profile found via Diablinda",
                ),
            }
            if data_fields:
                site_entry["data"] = data_fields
            _add_site(normalized, site_entry)

            obs = f"Diablinda: {service}"
            if username:
                obs += f" — ник @{username}"
            if name:
                obs += f", имя: {name}"
            if avatar:
                obs += f", аватар: {avatar}"
            if bio:
                obs += f", bio: {bio}"
            normalized["observations"].append(obs)

        # Dossier summary — sent to the LLM as separate observations.
        summary_parts = []
        if dossier.get("names"):
            summary_parts.append("имена: " + ", ".join(dossier["names"][:5]))
        if dossier.get("usernames"):
            summary_parts.append("ники: " + ", ".join(
                f"@{nick}" for nick in dossier["usernames"][:5]
            ))
        if dossier.get("avatars"):
            summary_parts.append("аватары: " + ", ".join(dossier["avatars"][:3]))
        if dossier.get("bios"):
            summary_parts.append("bio: " + " | ".join(dossier["bios"][:3]))
        if summary_parts:
            normalized["observations"].append(
                "Diablinda (сводка): " + " | ".join(summary_parts)
            )

    # --- theHarvester ---
    th = data.get("theharvester")
    if th:
        # Emails
        for email in th.get("emails", []):
            if email not in normalized["emails"]:
                normalized["emails"].append(email)
                normalized["observations"].append(f"Email найден: {email}")

        # Subdomains
        for sub in th.get("subdomains", []):
            url = f"https://{sub}"
            _add_unique(normalized["urls"], url)
            _add_site(normalized, {
                "site": sub,
                "url": url,
                "weight": "medium",
                "reason": _ui("субдомен", "subdomain"),
            })
            normalized["observations"].append(f"Субдомен: {sub}")

        # Hosts that are not in subdomains (just in case)
        known_subdomains = {str(sub).lower() for sub in th.get("subdomains", [])}
        for host_entry in th.get("hosts", []):
            if not isinstance(host_entry, dict):
                continue
            host = str(host_entry.get("host") or "").strip().lower()
            ip = str(host_entry.get("ip") or "").strip()
            if host and host not in known_subdomains:
                known_subdomains.add(host)
                url = f"https://{host}"
                _add_unique(normalized["urls"], url)
                _add_site(normalized, {
                    "site": host,
                    "url": url,
                    "weight": "medium",
                    "reason": _ui("хост", "host"),
                })
                normalized["observations"].append(f"Хост: {host}")
            if host and ip:
                normalized["observations"].append(f"Хост {host} → IP {ip}")

        # IP addresses
        for ip in th.get("ips", []):
            normalized["observations"].append(f"IP-адрес: {ip}")

    # --- ThreatFox ---
    threatfox = data.get("threatfox")
    if threatfox:
        for item in threatfox:
            if not isinstance(item, dict) or not item.get("found"):
                continue

            malware = item.get("malware") or "Unknown"
            ioc = item.get("ioc") or "?"
            confidence = item.get("confidence", "?")
            threat_type = item.get("threat_type") or ""

            obs = f"⚠️ Домен связан с малварью: {malware}"
            details = [f"IOC: {ioc}", f"уверенность: {confidence}%"]
            if threat_type:
                details.append(f"тип: {threat_type}")
            obs += f" ({', '.join(details)})"

            normalized["observations"].append(obs)

    return normalized


# ============================================================
# LLM REQUEST (Ollama / OpenAI / OpenRouter)
# ============================================================

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*")


def _strip_markdown_fences(raw: str) -> str:
    """Strips the markdown wrapper and extraneous junk around the JSON."""
    text = (raw or "").strip().lstrip("\ufeff")
    text = _FENCE_RE.sub("", text)
    text = text.replace("```", "")
    return text.strip()


def _balance_json(text: str) -> str:
    """Completes closing quotes/brackets of truncated JSON."""
    text = re.sub(r",\s*([}\]])", r"\1", text)

    stack = []
    in_string = False
    escape = False
    out = []

    for char in text:
        out.append(char)
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char in "[{":
                stack.append(char)
            elif char in "]}":
                if stack and (
                    (char == "}" and stack[-1] == "{")
                    or (char == "]" and stack[-1] == "[")
                ):
                    stack.pop()

    if in_string:
        if out and out[-1] == "\\":
            out.append("\\")
        out.append('"')

    for opener in reversed(stack):
        out.append("}" if opener == "{" else "]")

    return "".join(out)


def _last_comma(text: str) -> int:
    """Index of the last comma outside a string (for trimming the tail)."""
    in_string = False
    escape = False
    last = -1

    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == ",":
                last = index

    return last


def _extract_json(raw: str) -> dict:
    """Extracts a JSON object from the model response, fixing markdown and truncation."""
    if not raw or not str(raw).strip():
        return {"error": "Пустой ответ модели", "raw": ""}

    text = _strip_markdown_fences(str(raw))

    start = text.find("{")
    if start == -1:
        return {"error": "В ответе нет JSON-объекта", "raw": text[:1500]}

    # Do not take all text up to the last '}' — after the JSON the model may
    # append an explanation. Try to find a valid object starting from the first '{'.
    candidate = text[start:]
    end = candidate.rfind("}")
    if end != -1:
        candidate = candidate[: end + 1]

    last_error = ""

    for attempt in range(5):
        variants = [candidate, _balance_json(candidate)]
        for variant in variants:
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
                continue

            if isinstance(parsed, dict):
                return parsed
            last_error = f"JSON не является объектом ({type(parsed).__name__})"

        # The model truncated the response: drop the last incomplete element
        # and complete the brackets.
        trimmed = _last_comma(candidate)
        if trimmed == -1:
            break
        candidate = candidate[:trimmed]

    return {
        "error": f"JSON parse failed: {last_error}",
        "raw": text[:1500],
    }


def _log_llm_exchange(purpose: str, system_prompt: str, user_content: str,
                      response: str, elapsed: float, extra: str = "") -> None:
    """Logs the truncated prompt/response and generation time."""
    prompt_preview = (
        f"SYSTEM: {system_prompt.replace(chr(10), ' ')[:220]} | "
        f"USER: {user_content.replace(chr(10), ' ')[:260]}"
    )
    logger.info(
        "LLM[%s] запрос: %s%s",
        purpose,
        prompt_preview,
        "…" if (len(system_prompt) + len(user_content)) > 480 else "",
    )
    logger.info(
        "LLM[%s] ответ за %.1f сек: %s%s",
        purpose,
        elapsed,
        (response or "").replace("\n", " ")[:500],
        "…" if len(response or "") > 500 else "",
    )
    if extra:
        logger.info("LLM[%s] stats: %s", purpose, extra)


def _call_llm(system_prompt: str, user_content: str, timeout: int = None,
              purpose: str = "llm", max_tokens: int = None) -> dict:
    """
    Single entry point for calling the LLM.

    ollama  — POST /api/generate
    openai  — POST {OPENAI_BASE_URL}/chat/completions (OpenAI-compatible API,
              including OpenRouter).
    """
    provider = config.LLM_PROVIDER
    model = config.active_model()

    if timeout is None:
        timeout = config.filter_timeout() if purpose == "filter" else config.analyze_timeout()
    if max_tokens is None:
        if purpose == "filter":
            max_tokens = config.OLLAMA_FILTER_NUM_PREDICT
        elif purpose == "analyze":
            max_tokens = config.OLLAMA_ANALYZE_NUM_PREDICT
        else:
            max_tokens = config.OLLAMA_NUM_PREDICT

    logger.info(
        "LLM вызов: provider=%s model=%s purpose=%s timeout=%s max_tokens=%s",
        provider, model, purpose, timeout, max_tokens,
    )

    started = time.perf_counter()
    extra = ""

    try:
        if provider == "ollama":
            body = {
                "model": config.OLLAMA_MODEL,
                "system": system_prompt,
                "prompt": user_content,
                "stream": False,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": config.OLLAMA_NUM_CTX,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                },
            }
            response = requests.post(config.OLLAMA_URL, json=body, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            raw = (payload.get("response") or "").strip()
            extra = (
                f"eval_count={payload.get('eval_count', '?')} "
                f"prompt_eval={payload.get('prompt_eval_count', '?')} "
                f"load={round((payload.get('load_duration') or 0) / 1e9, 2)}s"
            )
        else:
            if not config.OPENAI_API_KEY:
                logger.error("LLM: не задан OPENAI_API_KEY/OPENROUTER_API_KEY")
                return {
                    "error": "Не задан OPENAI_API_KEY (или OPENROUTER_API_KEY)",
                    "provider": provider,
                }

            url = config.OPENAI_BASE_URL.rstrip("/") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            if provider == "openrouter":
                headers.setdefault("HTTP-Referer", "http://localhost:8000")
                headers.setdefault("X-Title", "Skyfall OSINT Helper")

            body = {
                "model": config.OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            }
            response = requests.post(url, headers=headers, json=body, timeout=timeout)

            if response.status_code >= 400:
                detail = (response.text or "")[:500]
                try:
                    error_json = response.json()
                    detail = (
                        (error_json.get("error") or {}).get("message")
                        or error_json.get("message")
                        or detail
                    )
                except Exception:
                    pass
                logger.error(
                    "LLM HTTP %s: %s", response.status_code, str(detail)[:500],
                )
                return {
                    "error": f"LLM HTTP {response.status_code}: {detail}",
                    "provider": provider,
                }

            payload = response.json()
            choices = payload.get("choices") or []
            message = (choices[0] or {}).get("message") if choices else {}
            content = (message or {}).get("content", "")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            raw = str(content or "").strip()

            usage = payload.get("usage") or {}
            extra = (
                f"tokens={usage.get('total_tokens', '?')} "
                f"prompt={usage.get('prompt_tokens', '?')} "
                f"completion={usage.get('completion_tokens', '?')}"
            )

    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - started
        logger.error(
            "LLM[%s] timeout через %.1f сек (provider=%s, model=%s)",
            purpose, elapsed, provider, model,
        )
        return {
            "error": f"LLM timeout ({timeout} сек)",
            "provider": provider,
            "timeout": True,
        }
    except requests.exceptions.ConnectionError as exc:
        logger.error("LLM[%s] connection error: %s", purpose, exc)
        return {
            "error": "LLM недоступна (connection error)",
            "provider": provider,
        }
    except Exception as exc:
        logger.error("LLM[%s] ошибка: %s", purpose, exc, exc_info=True)
        return {
            "error": f"LLM request error: {exc}",
            "provider": provider,
        }

    elapsed = time.perf_counter() - started
    _log_llm_exchange(purpose, system_prompt, user_content, raw, elapsed, extra)

    if not raw:
        logger.error("LLM[%s] пустой ответ", purpose)
        return {"error": "Пустой ответ модели", "provider": provider}

    parsed = _extract_json(raw)
    if "error" in parsed:
        logger.warning(
            "LLM[%s] не удалось распарсить JSON: %s",
            purpose, parsed.get("error"),
        )
    return parsed


# Compatibility with the old name (used by external scripts/tests).
_call_ollama = _call_llm


# ============================================================
# STAGES
# ============================================================

def has_usable_data(normalized: dict) -> bool:
    """
    Whether there is at least something to filter and analyze.

    For email/username at least one site/profile is needed: otherwise Holehe
    returned only a rate limit and the LLM would get an empty list.
    For a domain, the found emails are enough (theHarvester may not find
    subdomains, but emails are already a result).
    """
    if normalized.get("sites"):
        return True
    if normalized.get("input_type") == "domain" and (
        normalized.get("emails") or normalized.get("observations")
    ):
        return True
    return False


def _input_entity_type(input_type: str) -> str:
    return {"username": "nick", "email": "email", "domain": "domain"}.get(
        input_type, "unknown"
    )


def _site_name(item: dict) -> str:
    return str(item.get("site") or item.get("url") or "").strip()


def _site_weight(item: dict) -> str:
    weight = str(item.get("weight") or "").strip().lower()
    if weight in {"strong", "medium", "weak", "unknown"}:
        return weight
    return get_site_weight(item.get("site", ""))


def _ui(ru: str, en: str) -> str:
    """Returns a deterministic message in the active interface language."""
    return en if i18n.current_lang() == "en" else ru


def _site_rank(item: dict) -> tuple:
    """Sort sites for the LLM: metadata first, then strong/medium."""
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    weight_rank = {"strong": 3, "medium": 2, "unknown": 1, "weak": 0}.get(
        _site_weight(item), 0
    )
    return (1 if data else 0, weight_rank)


def raw_filtered(normalized: dict) -> dict:
    """
    Raw Mode: no LLM filtering — return all found sites.

    The structure is compatible with regular filtered, so the JSON report and
    the web interface do not break.
    """
    sites = []
    for item in normalized.get("sites") or []:
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        copy["weight"] = _site_weight(copy)
        copy.setdefault(
            "reason",
            _ui("Raw Mode: без AI-фильтрации", "Raw Mode: no AI filtering"),
        )
        sites.append(copy)

    logger.info("Raw Mode: фильтрация пропущена, сайтов=%s", len(sites))
    return {
        "thinking": _ui("Режим без AI (Raw Mode)", "Raw Mode (no AI)"),
        "kept": sites,
        "dropped": [],
        "mode": "raw",
    }


def _local_entities(normalized: dict, sites: list, limit: int = 40) -> list:
    """Deterministic entities from the normalized data."""
    entities = []
    seen = set()

    def add(entity_type: str, value, found_in=None):
        value = str(value or "").strip()
        if not value:
            return
        key = (entity_type, value.lower())
        if key in seen:
            return
        seen.add(key)
        entities.append({
            "type": entity_type,
            "value": value,
            "found_in": [str(x) for x in (found_in or []) if x][:10],
        })

    add(_input_entity_type(normalized.get("input_type", "")),
        normalized.get("input_value"))

    for nick in (normalized.get("nicks") or [])[:20]:
        add("nick", nick)
    for email in (normalized.get("emails") or [])[:20]:
        add("email", email)
    if not sites:
        for url in (normalized.get("urls") or [])[:20]:
            add("url", url)

    for item in sites:
        if not isinstance(item, dict):
            continue
        name = _site_name(item)
        if not name:
            continue
        add("url" if item.get("url") else "unknown", name, [name])

    return entities[:limit]


def _local_connections(normalized: dict, sites: list, limit: int = 15) -> list:
    """Simple connections "query → found site" without the LLM."""
    root = str(normalized.get("input_value") or "").strip()
    connections = []
    seen = set()

    for item in sites:
        if not isinstance(item, dict):
            continue
        target = _site_name(item)
        if not target or target.lower() == root.lower():
            continue
        key = (root.lower(), target.lower())
        if key in seen:
            continue
        seen.add(key)
        connections.append({
            "entity_a": root,
            "entity_b": target,
            "confidence": "medium",
            "evidence": str(item.get("url") or "")[:500],
            "reasoning": _ui(
                "найдено при сборе данных (без AI-анализа)",
                "found during collection (no AI analysis)",
            ),
        })
        if len(connections) >= limit:
            break

    return connections


def _local_tree(normalized: dict, sites: list) -> dict:
    children = []
    for item in sites:
        if not isinstance(item, dict):
            continue
        name = _site_name(item)
        if name and name not in children:
            children.append(name)
        if len(children) >= 8:
            break
    return {
        "root": str(normalized.get("input_value") or "?"),
        "children": children,
    }


def raw_analysis(normalized: dict, filtered: dict,
                 summary: str = None, mode: str = "raw",
                 reason: str = None) -> dict:
    """
    Local analysis without the LLM.

    For explicit Raw Mode, summary is set to the raw-mode UI message.
    For an emergency fallback — a clear explanation of why AI did not work.
    """
    sites = [item for item in (filtered.get("kept") or []) if isinstance(item, dict)]
    input_value = str(normalized.get("input_value") or "?")
    input_type = str(normalized.get("input_type") or "unknown")

    if summary is None:
        summary = _ui("Режим без AI (Raw Mode)", "Raw Mode (no AI)")

    analysis = {
        "thinking": reason or _ui(
            "Данные получены без использования LLM.",
            "Data was collected without using an LLM.",
        ),
        "summary": summary,
        "entities": _local_entities(normalized, sites, limit=80),
        "connections": _local_connections(normalized, sites, limit=60),
        "contradictions": [],
        "uncertainties": [],
        "tree": _local_tree(normalized, sites),
        "input_type": input_type,
        "input_value": input_value,
        "mode": mode,
    }
    if reason:
        analysis["notice"] = reason

    logger.info(
        "Локальный анализ: mode=%s, entities=%s, connections=%s",
        mode, len(analysis["entities"]), len(analysis["connections"]),
    )
    return analysis


def _compact_site(item: dict, max_value: int = 80) -> dict:
    """Short version of a site for the prompt (fewer tokens — faster response)."""
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    interesting_keys = (
        "username", "fullname", "name", "bio", "created_at",
        "follower_count", "following_count", "category", "details",
    )
    short_data = {}
    for key in interesting_keys:
        if key in data and data[key] not in (None, ""):
            short_data[key] = str(data[key])[:max_value]
    for key, value in data.items():
        if len(short_data) >= 3:
            break
        if key not in short_data and value not in (None, ""):
            short_data[str(key)] = str(value)[:max_value]

    return {
        "site": _site_name(item),
        "url": str(item.get("url") or "")[:500],
        "weight": _site_weight(item),
        "reason": str(item.get("reason") or "")[:160],
        "data": short_data,
    }


def _parse_keep_indices(result: dict, site_count: int) -> list:
    """Extracts site numbers from the model's compact response."""
    raw_keep = result.get("keep")
    indices = []

    def add_index(value):
        try:
            index = int(value)
        except (TypeError, ValueError):
            return
        if 1 <= index <= site_count and index not in indices:
            indices.append(index)

    if isinstance(raw_keep, list):
        for item in raw_keep:
            if isinstance(item, dict):
                for key in ("i", "index", "num", "n", "id"):
                    if key in item:
                        add_index(item[key])
                        break
            else:
                add_index(item)

    return indices


def _merge_analysis(result: dict, normalized: dict, filtered: dict) -> dict:
    """Augments the LLM response with local entities/connections/tree."""
    sites = [item for item in (filtered.get("kept") or []) if isinstance(item, dict)]
    local_entities = _local_entities(normalized, sites)
    local_connections = _local_connections(normalized, sites, limit=40)
    local_summary = _ui(
        f"Найдено {len(sites)} сайтов/профилей. "
        "LLM не дала развёрнутого вывода, показаны сырые связи.",
        f"Found {len(sites)} sites/profiles. "
        "The LLM did not produce a detailed conclusion; raw connections are shown.",
    )

    analysis = dict(result)
    analysis.pop("error", None)

    llm_entities = analysis.get("entities")
    merged = []
    seen = set()
    for entity in (llm_entities if isinstance(llm_entities, list) else []) + local_entities:
        if not isinstance(entity, dict):
            continue
        value = str(entity.get("value") or "").strip()
        if not value:
            continue
        key = (str(entity.get("type") or "unknown"), value.lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(entity)
    analysis["entities"] = merged[:40]

    llm_connections = analysis.get("connections")
    if not isinstance(llm_connections, list):
        llm_connections = []

    merged_connections = []
    seen_pairs = set()
    for item in list(llm_connections) + list(local_connections):
        if not isinstance(item, dict):
            continue
        a = str(item.get("entity_a") or "").strip().lower()
        b = str(item.get("entity_b") or "").strip().lower()
        if not a or not b or a == b:
            continue
        pair = frozenset((a, b))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        merged_connections.append(item)
        if len(merged_connections) >= 60:
            break
    analysis["connections"] = merged_connections

    summary = analysis.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        analysis["summary"] = local_summary

    if not isinstance(analysis.get("thinking"), str) or not analysis["thinking"].strip():
        analysis["thinking"] = _ui(
            "Краткий анализ на основе отфильтрованных данных.",
            "Brief analysis based on the filtered data.",
        )

    for key in ("contradictions", "uncertainties"):
        if not isinstance(analysis.get(key), list):
            analysis[key] = []

    if not isinstance(analysis.get("tree"), dict):
        analysis["tree"] = _local_tree(normalized, sites)

    analysis["input_type"] = normalized.get("input_type")
    analysis["input_value"] = normalized.get("input_value")
    analysis["mode"] = "ai"
    return analysis


def filter_sites(normalized: dict) -> dict:
    """
    Compact filtering via the LLM.

    The model returns only the numbers of the kept sites:
        {"keep": [1, 2, 5], "thinking": "..."}
    This is many times shorter than full JSON and does not push CPU inference
    into a 10-minute timeout. Full site objects are reconstructed here.
    """
    sites = [item for item in (normalized.get("sites") or []) if isinstance(item, dict)]
    if not sites:
        return {"kept": [], "dropped": [], "thinking": "No sites to filter"}

    limit = max(1, config.MAX_FILTER_SITES)
    ordered = sorted(sites, key=_site_rank, reverse=True)
    candidates = ordered[:limit]
    overflow = ordered[limit:]

    lines = []
    for index, item in enumerate(candidates, start=1):
        weight = _site_weight(item)
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if data:
            preview = "; ".join(
                f"{key}={str(value)[:60]}"
                for key, value in list(data.items())[:4]
            )
        else:
            preview = "no"
        # We do not put the URL in the prompt: the model only picks numbers, and the URL
        # is restored from candidates. This noticeably saves tokens.
        lines.append(
            f"{index}. {_site_name(item)} | weight={weight} | data={preview}"
        )

    observations = []
    if normalized.get("input_type") != "username":
        observations = [
            str(item)[:140]
            for item in (normalized.get("observations") or [])[
                : min(10, config.MAX_OBSERVATIONS)
            ]
        ]

    user_content = (
        f"Input type: {normalized.get('input_type')}\n"
        f"Value: {normalized.get('input_value')}\n\n"
        f"Sites ({len(candidates)}):\n"
        + "\n".join(lines)
    )
    if observations:
        user_content += "\n\nObservations:\n" + "\n".join(observations)
    user_content += "\n\nReturn only JSON with keep indices."

    prompt = config.build_filter_compact_prompt(
        normalized.get("input_type", ""), i18n.current_lang()
    )
    started = time.perf_counter()
    result = _call_llm(
        prompt,
        user_content,
        timeout=config.filter_timeout(),
        purpose="filter",
        max_tokens=config.OLLAMA_FILTER_NUM_PREDICT,
    )
    elapsed = time.perf_counter() - started

    if "error" in result:
        logger.warning(
            "Фильтрация LLM не удалась за %.1f сек: %s",
            elapsed, result.get("error"),
        )
        return result

    thinking = str(result.get("thinking") or "").strip()
    keep_indices = _parse_keep_indices(result, len(candidates))

    kept = []
    explicit_kept = []

    # Old/full format: the model returned ready-made objects.
    legacy_kept = result.get("kept")
    if isinstance(legacy_kept, list):
        for item in legacy_kept:
            if isinstance(item, dict) and (item.get("site") or item.get("url")):
                explicit_kept.append(dict(item))
    if isinstance(result.get("keep"), list):
        for item in result.get("keep"):
            if isinstance(item, dict) and (item.get("site") or item.get("url")):
                explicit_kept.append(dict(item))

    if explicit_kept:
        for item in explicit_kept:
            item["weight"] = _site_weight(item)
            item.setdefault(
                "reason",
                _ui(
                    f"оставлено фильтром ({item['weight']})",
                    f"kept by the filter ({item['weight']})",
                ),
            )
            if isinstance(item.get("data"), dict):
                pass
            kept.append(item)
    else:
        for index in sorted(keep_indices):
            item = dict(candidates[index - 1])
            item["weight"] = _site_weight(item)
            item.setdefault(
                "reason",
                _ui(
                    f"оставлено фильтром ({item['weight']})",
                    f"kept by the filter ({item['weight']})",
                ),
            )
            kept.append(item)

    # Safety net: STRONG/MEDIUM and sites with metadata must not be lost
    # because of a model error. We add them locally.
    kept_keys = {
        (_site_name(item).lower(), str(item.get("url") or "").lower())
        for item in kept
    }
    local_added = 0
    for item in candidates:
        weight = _site_weight(item)
        if not item.get("data") and weight not in {"strong", "medium"}:
            continue
        key = (_site_name(item).lower(), str(item.get("url") or "").lower())
        if key in kept_keys:
            continue
        copy = dict(item)
        copy["weight"] = weight
        copy.setdefault(
            "reason",
            _ui(
                "оставлено локально: strong/medium/metadata",
                "kept locally: strong/medium/metadata",
            ),
        )
        kept.append(copy)
        kept_keys.add(key)
        local_added += 1
    if local_added:
        thinking = (thinking + " " if thinking else "") + (
            _ui(
                f"Локально добавлено важных сайтов: {local_added}.",
                f"Important sites added locally: {local_added}.",
            )
        )

    # If the model dropped everything at all — we do not lose the result.
    if not kept:
        strong_or_medium = [
            dict(item) for item in candidates
            if _site_weight(item) in {"strong", "medium"}
        ]
        kept = strong_or_medium or [dict(item) for item in candidates[:10]]
        for item in kept:
            item["weight"] = _site_weight(item)
            item.setdefault(
                "reason",
                _ui(
                    "оставлено локально: LLM не выбрала сайты",
                    "kept locally: the LLM selected no sites",
                ),
            )
        thinking = (thinking + " " if thinking else "") + _ui(
            "LLM не выбрала сайты — оставлены кандидаты локально.",
            "The LLM selected no sites; local candidates were kept.",
        )
        logger.warning("Фильтр вернул пустой keep — использую локальный fallback")

    kept_keys = {
        (_site_name(item).lower(), str(item.get("url") or "").lower())
        for item in kept
    }

    candidate_ids = {id(item) for item in candidates}
    dropped = []
    for item in list(candidates) + list(overflow):
        key = (_site_name(item).lower(), str(item.get("url") or "").lower())
        if key in kept_keys:
            continue
        dropped.append({
            "site": _site_name(item),
            "url": item.get("url", ""),
            "reason": (
                _ui("отброшено LLM-фильтром", "dropped by the LLM filter")
                if id(item) in candidate_ids
                else _ui("лимит LLM-фильтра", "LLM filter limit")
            ),
        })

    if overflow:
        thinking = (thinking + " " if thinking else "") + (
            _ui(
                f"Ещё {len(overflow)} сайтов не отправлены в LLM (лимит {limit}).",
                f"{len(overflow)} more sites were not sent to the LLM (limit {limit}).",
            )
        )

    logger.info(
        "Фильтрация завершена за %.1f сек: оставлено=%s, отброшено=%s, всего=%s",
        elapsed, len(kept), len(dropped), len(sites),
    )

    return {
        "thinking": thinking or _ui("Фильтрация выполнена.", "Filtering completed."),
        "kept": kept,
        "dropped": dropped,
    }


def analyze_filtered(normalized: dict, filtered: dict) -> dict:
    """
    Compact analysis via the LLM.

    We ask for summary/connections/notes, and restore entities locally when
    needed — the response is shorter, the graph is still complete.
    """
    kept = [item for item in (filtered.get("kept") or []) if isinstance(item, dict)]
    if not kept:
        if normalized.get("input_type") == "domain" and (
            normalized.get("emails") or normalized.get("observations")
        ):
            kept = []
        else:
            return {"error": "No data left after filtering"}

    limit = max(1, config.MAX_ANALYZE_SITES)

    priority = sorted(kept, key=_site_rank, reverse=True)[:limit]
    compact_kept = [_compact_site(item) for item in priority]

    kept_names = {
        _site_name(item).lower() for item in kept if _site_name(item)
    }
    observations = []
    for line in normalized.get("observations") or []:
        text = str(line)
        low = text.lower()
        if low.startswith("⚠️") or any(name in low for name in kept_names):
            observations.append(text[:120])
        if len(observations) >= min(8, config.MAX_OBSERVATIONS):
            break

    clean_input = {
        "input_type": normalized.get("input_type"),
        "input_value": normalized.get("input_value"),
        "nicks": (normalized.get("nicks") or [])[:20],
        "emails": (normalized.get("emails") or [])[:20],
        "observations": observations,
        "kept_sites": compact_kept,
    }

    user_content = (
        "Analyze the data according to the methodology.\n\n"
        "DATA:\n"
        + json.dumps(clean_input, ensure_ascii=False, indent=2)
        + "\n\nReturn JSON."
    )
    prompt = config.build_analyze_compact_prompt(
        normalized.get("input_type", ""), i18n.current_lang()
    )
    started = time.perf_counter()
    result = _call_llm(
        prompt,
        user_content,
        timeout=config.analyze_timeout(),
        purpose="analyze",
        max_tokens=config.OLLAMA_ANALYZE_NUM_PREDICT,
    )
    elapsed = time.perf_counter() - started

    if "error" in result:
        logger.warning(
            "Анализ LLM не удался за %.1f сек: %s",
            elapsed, result.get("error"),
        )
        return result

    analysis = _merge_analysis(result, normalized, filtered)
    logger.info(
        "Анализ завершён за %.1f сек: entities=%s, connections=%s",
        elapsed, len(analysis.get("entities") or []),
        len(analysis.get("connections") or []),
    )
    return analysis


# ============================================================
# RECURSIVE PIVOT
# ============================================================

def _iter_strings(value):
    """Recursively iterates over all strings in a JSON-like structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _is_pivot_email(email: str) -> bool:
    email = (email or "").strip()
    if not email or email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if domain.lower() in _PLACEHOLDER_DOMAINS:
        return False
    return len(email) <= 254


def extract_pivot_candidates(analysis: dict) -> list:
    """
    Looks for new entities in the analysis results to continue with:
      • email addresses;
      • Telegram channels/profiles (t.me/<handle>).

    Returns a list of {"type": "email"|"username", "value": ..., "label": ...}.
    """
    if not isinstance(analysis, dict):
        return []

    seen = set()
    candidates = []

    for text in _iter_strings(analysis):
        for email in _EMAIL_RE.findall(text):
            email = email.strip().strip(".,;:()[]<>\"'")
            if not _is_pivot_email(email):
                continue
            key = f"email:{email.lower()}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "type": "email",
                "value": email,
                "label": email,
            })

        for handle in _TELEGRAM_RE.findall(text):
            handle = handle.strip()
            if not handle or handle.lower() in _TELEGRAM_RESERVED:
                continue
            key = f"username:{handle.lower()}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "type": "username",
                "value": handle,
                "label": f"Telegram: @{handle}",
            })

    # Emails first, then Telegram — this is clearer for the user.
    candidates.sort(key=lambda item: 0 if item["type"] == "email" else 1)
    return candidates


def _ask_yes_no(prompt: str) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "д", "да"}


def run_recursive_pivot(analysis: dict, depth: int, parent_report: str,
                        visited: set) -> None:
    """
    After the report, offers to continue the investigation along the found entities.

    depth — the depth of the current report (the original = 0).
    Maximum MAX_PIVOT_DEPTH. parent_report — path to the previous JSON.
    """
    logger.info("Pivot: depth=%s parent=%s", depth, parent_report)
    if depth >= MAX_PIVOT_DEPTH:
        print(i18n.t("pivot.max_depth", depth=MAX_PIVOT_DEPTH))
        return

    candidates = [
        item for item in extract_pivot_candidates(analysis)
        if _entity_key(item) not in visited
    ][:MAX_PIVOT_CANDIDATES]

    if not candidates:
        return

    print("\n" + "=" * 60)
    print(i18n.t("pivot.title"))
    for index, item in enumerate(candidates, 1):
        print(f"   {index}. {item['label']}")
    print("=" * 60)

    if not _ask_yes_no(i18n.t("pivot.prompt")):
        return

    for item in candidates:
        key = _entity_key(item)
        if key in visited:
            continue
        visited.add(key)

        print(f"\n{i18n.t('pivot.running', type=item['type'], value=item['value'])}")
        result = run_cycle(
            item["type"],
            item["value"],
            parent_report=parent_report,
            depth=depth + 1,
        )
        if result:
            run_recursive_pivot(
                result["analysis"],
                depth + 1,
                result["path"],
                visited,
            )


# ============================================================
# PRINTING
# ============================================================

def print_tree(node, prefix: str = "", is_last: bool = True):
    if not isinstance(node, dict):
        connector = "└── " if is_last else "├── "
        print(prefix + connector + _to_text(node))
        return
    connector = "└── " if is_last else "├── "
    label = _to_text(node.get("node", "?"))
    if node.get("confidence"):
        label += f"  [{node['confidence']}]"
    print(prefix + connector + label)
    child_prefix = prefix + ("    " if is_last else "│   ")
    children = node.get("children") or []
    if not isinstance(children, list):
        children = []
    for i, child in enumerate(children):
        print_tree(child, child_prefix, is_last=(i == len(children) - 1))


def print_filter_report(filtered: dict):
    print("\n" + "=" * 60)
    print(i18n.t("report.stage_filter"))
    print("=" * 60)

    if "error" in filtered:
        print(f"\n{i18n.t('error.filter', error=filtered['error'])}")
        if "raw" in filtered:
            print(f"\n{i18n.t('error.raw_response')}")
            print(_to_text(filtered["raw"])[:1500])
        return

    thinking = _to_text(filtered.get("thinking"))
    if thinking.strip():
        print(f"\n{i18n.t('report.thinking')}")
        print(textwrap.indent(thinking, "   "))

    kept = filtered.get("kept", [])
    dropped = filtered.get("dropped", [])

    print(f"\n{i18n.t('report.kept', count=len(kept) if isinstance(kept, list) else 0)}")
    if isinstance(kept, list):
        for item in kept:
            if isinstance(item, dict):
                weight = item.get("weight", "?")
                site = item.get("site", "?")
                url = item.get("url", "")
                print(f"   • [{weight}] {site}: {url}")
                # Show metadata if present
                if item.get("data"):
                    for k, v in list(item["data"].items())[:3]:
                        print(f"     {k}: {_to_text(v)[:80]}")

    print(f"\n{i18n.t('report.dropped', count=len(dropped) if isinstance(dropped, list) else 0)}")
    if isinstance(dropped, list):
        for item in dropped[:10]:
            if isinstance(item, dict):
                site = item.get("site", "?")
                reason = _to_text(item.get("reason", ""))
                print(f"   • {site}: {reason}")
        if len(dropped) > 10:
            print(f"   {i18n.t('report.more', count=len(dropped) - 10)}")


def _print_entity(e):
    if isinstance(e, dict):
        etype = e.get("type", "?")
        value = e.get("value", "?")
        found_in = e.get("found_in", [])
        if isinstance(found_in, list):
            found_in = ", ".join(_to_text(x) for x in found_in)
        print(f"   • [{etype}] {value}")
        if found_in:
            print(f"     {i18n.t('report.found_in')} {found_in}")
    else:
        print(f"   • {_to_text(e)}")


def _print_connection(c):
    if isinstance(c, dict):
        a = c.get("entity_a", "?")
        b = c.get("entity_b", "?")
        conf = c.get("confidence", "?")
        print(f"   • {a} ↔ {b}  [{conf}]")
        if c.get("evidence"):
            print(f"     {i18n.t('report.evidence')} {_to_text(c['evidence'])}")
        if c.get("reasoning"):
            print(f"     {i18n.t('report.reason')} {_to_text(c['reasoning'])}")
    else:
        print(f"   • {_to_text(c)}")


def print_analysis_report(analysis: dict, report_path: str):
    print("\n" + "=" * 60)
    print(i18n.t("report.stage_analysis"))
    print("=" * 60)

    if "error" in analysis:
        print(f"\n{i18n.t('error.analysis', error=analysis['error'])}")
        if "raw" in analysis:
            print(f"\n{i18n.t('error.raw_response')}")
            print(_to_text(analysis["raw"])[:1500])
        return

    thinking = _to_text(analysis.get("thinking"))
    if thinking.strip():
        print(f"\n{i18n.t('report.thinking')}")
        print(textwrap.indent(thinking, "   "))

    summary = _to_text(analysis.get("summary"))
    if summary.strip():
        print(f"\n{i18n.t('report.summary')}\n   {summary}")

    entities = analysis.get("entities", [])
    if isinstance(entities, list) and entities:
        print(f"\n{i18n.t('report.entities')}")
        for e in entities:
            _print_entity(e)

    connections = analysis.get("connections", [])
    if isinstance(connections, list) and connections:
        print(f"\n{i18n.t('report.connections')}")
        for c in connections:
            _print_connection(c)
    else:
        print(f"\n{i18n.t('report.no_connections')}")

    contradictions = analysis.get("contradictions", [])
    if isinstance(contradictions, list) and contradictions:
        print(f"\n{i18n.t('report.contradictions')}")
        for c in contradictions:
            print(f"   • {_to_text(c)}")

    uncertainties = analysis.get("uncertainties", [])
    if isinstance(uncertainties, list) and uncertainties:
        print(f"\n{i18n.t('report.uncertainties')}")
        for u in uncertainties:
            print(f"   • {_to_text(u)}")

    tree = analysis.get("tree")
    if isinstance(tree, dict) and tree:
        print(f"\n{i18n.t('report.tree')}")
        print(f"   {_to_text(tree.get('root', '?'))}")
        children = tree.get("children") or []
        if isinstance(children, list):
            for i, child in enumerate(children):
                print_tree(child, prefix="   ", is_last=(i == len(children) - 1))

    print(f"\n{i18n.t('report.json_saved', path=report_path)}")


# ============================================================
# SAVING
# ============================================================

def save_report(value: str, data: dict, filtered: dict, analysis: dict,
                parent_report: str = None, depth: int = 0) -> str:
    """
    Saves the JSON report.

    parent_report — path to the previous report in the chain (or None).
    depth — the investigation depth (the original report = 0, maximum 3).
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_value = re.sub(r"[^\w\-.]", "_", value)
    path = os.path.join(OUTPUT_DIR, f"report_{safe_value}_{ts}.json")
    safe_depth = max(0, min(int(depth), MAX_PIVOT_DEPTH))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "input": value,
            "input_type": analysis.get("input_type") if isinstance(analysis, dict) else None,
            "collected_at": ts,
            "language": i18n.current_lang(),
            "depth": safe_depth,
            "parent_report": parent_report,
            "mode": analysis.get("mode") if isinstance(analysis, dict) else None,
            "llm_provider": config.LLM_PROVIDER,
            "raw_data": data,
            "filtered": filtered,
            "analysis": analysis,
        }, f, ensure_ascii=False, indent=2)
    logger.info("Отчёт сохранён: %s", path)
    return path


# ============================================================
# ONE INVESTIGATION CYCLE
# ============================================================

def run_cycle(input_type: str, value: str, parent_report: str = None,
              depth: int = 0) -> dict | None:
    """
    Full cycle: collection → normalization → filtering → analysis → saving.

    If config.USE_AI == False — Raw Mode: the LLM is not called.
    If the LLM failed/did not finish within the timeout — automatic fallback
    to raw data so that the investigation is not lost.

    Returns {"path", "analysis", "data", "filtered", "ai_used"} or None
    if there is no data / an error occurred.
    """
    use_ai = bool(config.USE_AI)
    started = time.perf_counter()

    logger.info(
        "Старт расследования: type=%s value=%s depth=%s use_ai=%s provider=%s model=%s",
        input_type, value, depth, use_ai, config.LLM_PROVIDER, config.active_model(),
    )

    if depth > 0:
        print("\n" + "=" * 60)
        print(i18n.t("pivot.cycle_header", depth=depth, type=input_type, value=value))
        print("=" * 60)

    try:
        if input_type == "username":
            data = collect_by_username(value)
        elif input_type == "email":
            data = collect_by_email(value)
        elif input_type == "domain":
            data = collect_by_domain(value)
        else:
            print(i18n.t("menu.invalid"))
            logger.warning("Неверный тип входа: %s", input_type)
            return None
    except Exception as exc:
        print(i18n.t("error.collect", error=exc))
        logger.error("Ошибка сбора данных: %s", exc, exc_info=True)
        return None

    print(f"\n{i18n.t('step.normalize')}")
    try:
        normalized = normalize(data, input_type, value)
    except Exception as exc:
        print(i18n.t("error.collect", error=exc))
        logger.error("Ошибка нормализации: %s", exc, exc_info=True)
        return None

    logger.info(
        "Нормализация: sites=%s nicks=%s emails=%s observations=%s",
        len(normalized.get("sites") or []),
        len(normalized.get("nicks") or []),
        len(normalized.get("emails") or []),
        len(normalized.get("observations") or []),
    )

    # --- Protection against "No data left after filtering" ---
    if not has_usable_data(normalized):
        print(i18n.t("error.no_data", value=value))
        logger.warning("Нет пригодных данных для %s", value)
        return None

    ai_used = False
    fallback_reason = ""

    if use_ai:
        print(f"\n{i18n.t('step.filter', count=len(normalized['sites']))}")
        try:
            filtered = filter_sites(normalized)
        except Exception as exc:
            logger.error("Исключение при фильтрации: %s", exc, exc_info=True)
            filtered = {"error": str(exc)}

        if "error" in filtered:
            fallback_reason = str(filtered.get("error"))
            print(i18n.t("mode.fallback", error=fallback_reason))
            logger.warning("Fallback на Raw Mode: %s", fallback_reason)
            filtered = raw_filtered(normalized)
            analysis = raw_analysis(
                normalized,
                filtered,
                summary=_ui(
                    "LLM недоступна — показаны данные без AI-анализа",
                    "The LLM is unavailable; data is shown without AI analysis",
                ),
                mode="raw_fallback",
                reason=_ui(
                    f"Фильтрация LLM: {fallback_reason}",
                    f"LLM filtering: {fallback_reason}",
                ),
            )
        else:
            print_filter_report(filtered)
            print(f"\n{i18n.t('step.analyze')}")
            try:
                analysis = analyze_filtered(normalized, filtered)
            except Exception as exc:
                logger.error("Исключение при анализе: %s", exc, exc_info=True)
                analysis = {"error": str(exc)}

            if not isinstance(analysis, dict) or "error" in analysis:
                fallback_reason = str(
                    analysis.get("error") if isinstance(analysis, dict) else "empty analysis"
                )
                print(i18n.t("mode.fallback", error=fallback_reason))
                logger.warning("Fallback анализа на Raw Mode: %s", fallback_reason)
                analysis = raw_analysis(
                    normalized,
                    filtered,
                    summary=_ui(
                        "LLM недоступна — показаны данные без AI-анализа",
                        "The LLM is unavailable; data is shown without AI analysis",
                    ),
                    mode="raw_fallback",
                    reason=_ui(
                        f"Анализ LLM: {fallback_reason}",
                        f"LLM analysis: {fallback_reason}",
                    ),
                )
            else:
                ai_used = True
    else:
        print(f"\n{i18n.t('mode.raw')}")
        filtered = raw_filtered(normalized)
        analysis = raw_analysis(normalized, filtered)
        print_filter_report(filtered)

    if isinstance(analysis, dict):
        analysis.setdefault("input_type", input_type)
        analysis.setdefault("input_value", value)
        analysis.setdefault("mode", "ai" if ai_used else "raw")
        if fallback_reason:
            analysis.setdefault("notice", fallback_reason)

    path = save_report(
        value,
        data,
        filtered,
        analysis,
        parent_report=parent_report,
        depth=depth,
    )
    print_analysis_report(analysis, path)

    elapsed = time.perf_counter() - started
    logger.info(
        "Расследование завершено за %.1f сек: ai_used=%s, filtered=%s, report=%s",
        elapsed, ai_used, len(filtered.get("kept") or []), path,
    )

    return {
        "path": path,
        "analysis": analysis,
        "data": data,
        "filtered": filtered,
        "ai_used": ai_used,
    }


# ============================================================
# MAIN
# ============================================================

def _no_ai_arg() -> bool:
    """Reads --no-ai without interfering with i18n.parse_lang_arg()."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-ai", action="store_true")
    args, _ = parser.parse_known_args()
    return bool(args.no_ai)


def main():
    # 0. Clean start: clear everything that was in the terminal before Skyfall.
    clear_console()

    # 1. Language and mode
    lang = i18n.parse_lang_arg()
    i18n.setup(lang)

    if _no_ai_arg():
        config.USE_AI = False

    provider = config.active_provider()
    model = config.active_model()
    ai_enabled = bool(config.USE_AI)

    # 2. Banner
    print_banner(version="0.3.0")
    print(f"{'=' * 60}")
    print(f"Model: {model}  |  Provider: {provider}  |  Lang: {i18n.current_lang()}")
    raw_label = "Raw Mode (no AI)" if i18n.current_lang() == "en" else "Raw Mode (без AI)"
    print(f"Mode: {'AI' if ai_enabled else raw_label}")
    print(f"{'=' * 60}")

    logger.info(
        "CLI запущен: provider=%s model=%s use_ai=%s lang=%s",
        provider, model, ai_enabled, i18n.current_lang(),
    )
    try:
        from logger import log_file
        path = log_file()
        if path:
            print(f"Logs: {path}")
    except Exception:
        pass

    # 3. Menu
    print(f"\n{i18n.t('menu.title')}")
    print(f"  1 — {i18n.t('menu.option_username')}")
    print(f"  2 — {i18n.t('menu.option_email')}")
    print(f"  3 — {i18n.t('menu.option_domain')}")
    choice = input(i18n.t("menu.prompt")).strip()

    if choice == "1":
        value = input(i18n.t("input.username")).strip()
        if not value:
            print(i18n.t("input.empty"))
            return
        input_type = "username"
    elif choice == "2":
        value = input(i18n.t("input.email")).strip()
        if not value:
            print(i18n.t("input.empty"))
            return
        input_type = "email"
    elif choice == "3":
        value = input(i18n.t("input.domain")).strip()
        if not value:
            print(i18n.t("input.empty"))
            return
        input_type = "domain"
    else:
        print(i18n.t("menu.invalid"))
        return

    # 4. First cycle
    result = run_cycle(input_type, value, parent_report=None, depth=0)
    if not result:
        return

    # 5. Recursive pivot over the found emails/Telegram
    visited = {_entity_key({"type": input_type, "value": value})}
    run_recursive_pivot(
        result["analysis"],
        depth=0,
        parent_report=result["path"],
        visited=visited,
    )


if __name__ == "__main__":
    main()
