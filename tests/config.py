# config.py — settings and prompts.

import datetime
import json
import os

from site_weights import build_site_dictionary


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = (
    os.environ.get("OSINT_SETTINGS_FILE")
    or os.path.join(BASE_DIR, "llm_settings.json")
)


def _env_bool(name: str, default: bool = True) -> bool:
    """Reads a boolean environment variable (0/false/no/off are False)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ---------- Operating mode ----------
# USE_AI=False — Raw Mode: no filtering or analysis via the LLM.
USE_AI = _env_bool("OSINT_USE_AI", True)

# ---------- Ollama ----------
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# 4096 instead of 8192: on machines with 8 GB of RAM this noticeably reduces the KV-cache
# and prevents the model from going into swap. For large lists the data is truncated.
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 4096)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 1200)
OLLAMA_FILTER_NUM_PREDICT = _env_int("OLLAMA_FILTER_NUM_PREDICT", 200)
OLLAMA_ANALYZE_NUM_PREDICT = _env_int("OLLAMA_ANALYZE_NUM_PREDICT", 450)
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "15m")

# Timeouts (seconds). Better to return raw data than to wait 10+ minutes.
OLLAMA_FILTER_TIMEOUT = _env_int("OLLAMA_FILTER_TIMEOUT", 300)
OLLAMA_ANALYZE_TIMEOUT = _env_int("OLLAMA_ANALYZE_TIMEOUT", 420)

# ---------- Cloud LLMs ----------
# LLM_PROVIDER: ollama | openai | openrouter
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
if LLM_PROVIDER not in {"ollama", "openai", "openrouter"}:
    LLM_PROVIDER = "ollama"

OPENAI_API_KEY = (
    os.environ.get("OPENAI_API_KEY")
    or os.environ.get("OPENROUTER_API_KEY")
    or ""
).strip()

_DEFAULT_OPENAI_BASE = (
    "https://openrouter.ai/api/v1"
    if LLM_PROVIDER == "openrouter"
    else "https://api.openai.com/v1"
)
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", _DEFAULT_OPENAI_BASE).rstrip("/")

_DEFAULT_OPENAI_MODEL = (
    "anthropic/claude-3.5-sonnet"
    if LLM_PROVIDER == "openrouter"
    else "gpt-4o-mini"
)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)

OPENAI_FILTER_TIMEOUT = _env_int("OPENAI_FILTER_TIMEOUT", 120)
OPENAI_ANALYZE_TIMEOUT = _env_int("OPENAI_ANALYZE_TIMEOUT", 180)

# Limits on the amount of data sent to the LLM.
MAX_FILTER_SITES = _env_int("OSINT_MAX_FILTER_SITES", 20)
MAX_ANALYZE_SITES = _env_int("OSINT_MAX_ANALYZE_SITES", 15)
MAX_OBSERVATIONS = _env_int("OSINT_MAX_OBSERVATIONS", 15)

# ---------- Paths ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get(
    "OSINT_OUTPUT_DIR",
    os.path.join(BASE_DIR, "output"),
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# ACTIVE MODEL
# ============================================================

def active_model() -> str:
    """Active provider's model."""
    if LLM_PROVIDER == "ollama":
        return OLLAMA_MODEL
    return OPENAI_MODEL


def active_provider() -> str:
    """Human-readable provider name."""
    return {
        "ollama": "Ollama",
        "openai": "OpenAI",
        "openrouter": "OpenRouter",
    }.get(LLM_PROVIDER, LLM_PROVIDER)


def llm_configured() -> bool:
    """Whether the selected provider is configured (the cloud needs a key)."""
    if LLM_PROVIDER == "ollama":
        return True
    return bool(OPENAI_API_KEY)


def filter_timeout() -> int:
    if LLM_PROVIDER == "ollama":
        return OLLAMA_FILTER_TIMEOUT
    return OPENAI_FILTER_TIMEOUT


def analyze_timeout() -> int:
    if LLM_PROVIDER == "ollama":
        return OLLAMA_ANALYZE_TIMEOUT
    return OPENAI_ANALYZE_TIMEOUT


# ============================================================
# LLM SETTINGS MANAGED FROM THE WEB
# ============================================================

def _default_base_url(provider: str) -> str:
    return (
        "https://openrouter.ai/api/v1"
        if provider == "openrouter"
        else "https://api.openai.com/v1"
    )


def _default_cloud_model(provider: str) -> str:
    return (
        "anthropic/claude-3.5-sonnet"
        if provider == "openrouter"
        else "gpt-4o-mini"
    )


def _mask_key(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return "••••••" + value[-4:]


def _load_saved_settings() -> None:
    """
    Picks up llm_settings.json (if it exists).

    The file takes priority over environment variables — this way changes
    made via the web persist after a restart.
    """
    global LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OLLAMA_MODEL

    if not SETTINGS_FILE or not os.path.isfile(SETTINGS_FILE):
        return

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[config] Не удалось прочитать {SETTINGS_FILE}: {exc}")
        return

    if not isinstance(data, dict):
        return

    provider = str(data.get("provider") or "").strip().lower()
    if provider in {"ollama", "openai", "openrouter"}:
        LLM_PROVIDER = provider

    if "openai_api_key" in data:
        OPENAI_API_KEY = str(data.get("openai_api_key") or "").strip()
    if data.get("openai_base_url"):
        OPENAI_BASE_URL = str(data["openai_base_url"]).strip().rstrip("/")
    if data.get("openai_model"):
        OPENAI_MODEL = str(data["openai_model"]).strip()
    if data.get("ollama_model"):
        OLLAMA_MODEL = str(data["ollama_model"]).strip()

    if provider == "openrouter" and not data.get("openai_base_url"):
        OPENAI_BASE_URL = _default_base_url("openrouter")
    if provider in {"openai", "openrouter"} and not data.get("openai_model"):
        OPENAI_MODEL = _default_cloud_model(provider)


def _write_saved_settings() -> None:
    payload = {
        "provider": LLM_PROVIDER,
        "openai_api_key": OPENAI_API_KEY,
        "openai_base_url": OPENAI_BASE_URL,
        "openai_model": OPENAI_MODEL,
        "ollama_model": OLLAMA_MODEL,
        "updated_at": datetime.datetime.now().replace(microsecond=0).isoformat(),
    }
    directory = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    os.makedirs(directory, exist_ok=True)
    tmp_path = SETTINGS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        pass
    os.replace(tmp_path, SETTINGS_FILE)


def get_llm_settings(mask_key: bool = True) -> dict:
    """Public LLM settings (the key is never returned in full)."""
    return {
        "provider": LLM_PROVIDER,
        "provider_label": active_provider(),
        "model": active_model(),
        "ollama_model": OLLAMA_MODEL,
        "openai_model": OPENAI_MODEL,
        "openai_base_url": OPENAI_BASE_URL,
        "has_api_key": bool(OPENAI_API_KEY),
        "api_key_masked": _mask_key(OPENAI_API_KEY) if mask_key else "",
        "configured": llm_configured(),
        "settings_file": SETTINGS_FILE,
        "use_ai": USE_AI,
        "limits": {
            "max_filter_sites": MAX_FILTER_SITES,
            "max_analyze_sites": MAX_ANALYZE_SITES,
            "max_observations": MAX_OBSERVATIONS,
            "ollama_num_ctx": OLLAMA_NUM_CTX,
            "ollama_filter_num_predict": OLLAMA_FILTER_NUM_PREDICT,
            "ollama_analyze_num_predict": OLLAMA_ANALYZE_NUM_PREDICT,
            "ollama_filter_timeout": OLLAMA_FILTER_TIMEOUT,
            "ollama_analyze_timeout": OLLAMA_ANALYZE_TIMEOUT,
        },
    }


def update_llm_settings(data: dict) -> dict:
    """
    Changes the provider/key/URL/model and saves llm_settings.json.

    An empty api_key means "keep the current key".
    Set clear_api_key=True to delete the key.
    """
    global LLM_PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OLLAMA_MODEL

    if not isinstance(data, dict):
        raise ValueError("Некорректные настройки LLM")

    previous_provider = LLM_PROVIDER
    provider = str(data.get("provider") or LLM_PROVIDER).strip().lower()
    if provider not in {"ollama", "openai", "openrouter"}:
        raise ValueError("Провайдер должен быть ollama, openai или openrouter")

    new_key = data.get("api_key")
    if data.get("clear_api_key"):
        OPENAI_API_KEY = ""
    elif new_key is not None and str(new_key).strip() not in {"", "__KEEP__"}:
        OPENAI_API_KEY = str(new_key).strip()

    model = str(data.get("model") or "").strip()
    base_url = str(data.get("base_url") or "").strip().rstrip("/")

    if provider == "ollama":
        if model:
            OLLAMA_MODEL = model
        if not base_url:
            base_url = OPENAI_BASE_URL or _default_base_url("openai")
    else:
        if not base_url:
            base_url = _default_base_url(provider)
        if not base_url.lower().startswith(("http://", "https://")):
            raise ValueError("Base URL должен начинаться с http:// или https://")
        if model:
            OPENAI_MODEL = model
        elif provider != previous_provider:
            OPENAI_MODEL = _default_cloud_model(provider)
        if not OPENAI_API_KEY and not data.get("clear_api_key"):
            raise ValueError("Для облачного провайдера нужен API-ключ")

    LLM_PROVIDER = provider
    if base_url:
        OPENAI_BASE_URL = base_url
    if provider == "openrouter" and not OPENAI_MODEL:
        OPENAI_MODEL = _default_cloud_model(provider)

    _write_saved_settings()
    return get_llm_settings()


# Apply the saved settings after all constants are declared.
_load_saved_settings()


# ============================================================
# PROMPT 1: FILTERING
# ============================================================

def build_filter_prompt(input_type: str) -> str:
    base = """Ты — OSINT-аналитик на этапе фильтрации данных.
Твоя задача — убрать мусор из списка найденных данных.

""" + build_site_dictionary() + """

ПРАВИЛА ФИЛЬТРАЦИИ:
1. Сайты STRONG — оставляй всегда.
2. Сайты MEDIUM — оставляй.
3. Сайты WEAK — отбрасывай, если нет метаданных.
4. Дубликаты — оставляй один.
5. Если у сайта есть "data" (bio, fullname) — оставляй, копируй data.
6. Если "data" нет — не выдумывай.
7. Учитывай observations: предупреждения ThreatFox о малвари — сильный сигнал.

"""

    if input_type == "username":
        base += """
ТИП: НИК (username).
Данные: список сайтов, где найден ник.
У некоторых может быть "data" (bio, fullname, followers).
Оставляй сайты с метаданными и STRONG. Остальные — отбрасывай.
"""
    elif input_type == "email":
        base += """
ТИП: EMAIL.
Данные: сайты, где зарегистрирован email (Holehe), и/или метаданные
от Diablinda (fallback, если Holehe дал 0 результатов).
Diablinda может дать: service, username/никнейм, avatar/аватарку,
name/имя, bio, ссылку на профиль.
Правила:
  • Holehe: сайт найден — оставляй, weight="medium".
  • Diablinda: если есть username/avatar/bio — это метаданные, копируй их
    в "data" и оставляй сайт.
  • Оставляй ВСЕ найденные сайты. НЕ отбрасывай их за "отсутствие метаданных".
  • Пометь: weight="medium", reason="email найден на этом сайте"
    (или "профиль найден через Diablinda").
"""
    elif input_type == "domain":
        base += """
ТИП: ДОМЕН.
Данные: emails, субдомены, хосты (theHarvester).
Оставляй все email и субдомены.
Отбрасывай только очевидный мусор (postmaster@, abuse@, noreply@).
"""
    else:
        base += "\nТИП: неизвестный. Используй общие правила.\n"

    base += """
ФОРМАТ ОТВЕТА (строго JSON):
{
  "thinking": "рассуждения, 3-5 предложений",
  "kept": [
    {"site": "...", "url": "...", "weight": "strong|medium|weak|unknown", "reason": "...", "data": {...}}
  ],
  "dropped": [
    {"site": "...", "url": "...", "reason": "..."}
  ]
}
ВАЖНО: твой ответ — ТОЛЬКО JSON. Начни с { и закончи }.
"""
    return base


def build_analyze_prompt(input_type: str) -> str:
    base = """Ты — OSINT-аналитик. Твоя работа — сделать обоснованные выводы.

Данные уже прошли фильтрацию.
В поле observations могут быть предупреждения ThreatFox о малвари,
найденные email/никообразующие строки и метаданные Diablinda.

====================================================
МЕТОДОЛОГИЯ
====================================================
ШАГ 1. Сильные сигналы: точное совпадение email, редкого URL, редкого ника.
ШАГ 2. Правило трёх: 3+ раза — сильный сигнал.
ШАГ 3. Иерархия: high (прямая ссылка), medium (косвенная), low (спекулятивно).
ШАГ 4. Противоречия важнее согласованности.
ШАГ 5. Честность о незнании: мало данных — пиши в "uncertainties".

ЖЁСТКИЕ ЗАПРЕТЫ:
- НЕ выдумывай сущности.
- НЕ выдумывай связи.
- Отвечай ТОЛЬКО JSON.

"""

    if input_type == "username":
        base += """
ТИП: НИК.
Ищи связи: ник ↔ bio-ссылка, ник ↔ email в bio, ник ↔ другой ник.
Если в data есть bio с t.me/... — это связь с Telegram-каналом.
"""
    elif input_type == "email":
        base += """
ТИП: EMAIL.
Данные: сайты, где email зарегистрирован (Holehe), и метаданные Diablinda.
Diablinda — fallback-инструмент: он может вернуть никнеймы (@username),
ссылки на аватарки, имена, bio и ссылки на профили. Это ЦЕННЫЕ сигналы:
  • одинаковый никнейм на нескольких сервисах — сильная связь;
  • аватарка/имя/bio помогают связать email с публичной личностью;
  • ссылка на профиль — подтверждение аккаунта.
ГЛАВНОЕ: email найден на N сайтах. Это уже вывод.
Ищи паттерны: какие категории сайтов (соцсети, форумы, сервисы).
Если email найден на github.com + stackoverflow.com — вероятно, программист.
Если email найден только на 1 сайте — weak signal.
НЕ выдумывай bio, ники, телефоны — используй ТОЛЬКО то, что есть в data
или observations от Diablinda.
Связи: между email, никнеймами и категориями сайтов.
"""
    elif input_type == "domain":
        base += """
ТИП: ДОМЕН.
Данные: emails и субдомены, связанные с доменом.
ГЛАВНОЕ: собрать общую картину инфраструктуры.
Ищи:
  • Паттерны email (john@, admin@, hr@ — разные отделы).
  • Субдомены (mail., api., dev. — инфраструктура).
  • Утечки (если email совпадают с известными breaches).
НЕ выдумывай связи между конкретными email и людьми — их в данных НЕТ.
"""
    else:
        base += "\nТИП: неизвестный.\n"

    base += """
ФОРМАТ ОТВЕТА (строго JSON):
{
  "thinking": "...",
  "summary": "...",
  "entities": [
    {"type": "email|nick|url|domain", "value": "...", "found_in": ["..."]}
  ],
  "connections": [
    {"entity_a": "...", "entity_b": "...", "confidence": "high|medium|low", "evidence": "...", "reasoning": "..."}
  ],
  "contradictions": [],
  "uncertainties": [],
  "tree": {"root": "...", "children": [...]}
}

КРИТИЧНО: Отвечай ИСКЛЮЧИТЕЛЬНО на русском языке.
ВАЖНО: твой ответ — ТОЛЬКО JSON.
"""
    return base


# ============================================================
# ENGLISH COMPACT PROMPTS (used by the English web UI)
# ============================================================

def _build_filter_compact_prompt_en(input_type: str) -> str:
    type_hint = {
        "username": "We are searching for a username. STRONG/MEDIUM sites matter; WEAK sites without metadata are noise.",
        "email": "We are searching for an email. Keep every site where the email is found, especially ones with metadata (username/avatar/bio).",
        "domain": "We are searching for a domain. Keep emails and subdomains; drop only postmaster@/abuse@/noreply@.",
    }.get(input_type, "Keep meaningful sites and drop obvious noise.")

    return f"""You are an OSINT filter. You receive a numbered list of sites.
{type_hint}

RULES:
1. Keep STRONG and MEDIUM sites.
2. Drop WEAK sites without metadata.
3. Keep sites with data (bio, fullname, username, followers).
4. Do not rewrite sites or URLs. Return only numbers.
5. If unsure, keep the site.

RESPONSE FORMAT (strict JSON, no markdown):
{{"keep": [1, 2, 5], "thinking": "one short sentence"}}

IMPORTANT: JSON only. No text around it.
"""


def _build_analyze_compact_prompt_en(input_type: str) -> str:
    type_hint = {
        "username": "Link the username to sites, bio links, emails, and Telegram.",
        "email": "Link the email to sites and discovered usernames; an email on many sites is already a finding.",
        "domain": "Describe the infrastructure: emails, subdomains, hosts; do not invent people.",
    }.get(input_type, "Make only evidence-based conclusions.")

    return f"""You are an OSINT analyst. The data has already been filtered.
{type_hint}

HARD RULES:
- Do not invent entities or connections. Use only DATA.
- Be concise: summary 1-2 sentences, thinking at most 1 sentence (optional).
- connections: at most 10, only real connections from the data.
- entities may be omitted - they are already extracted by the program.
- contradictions and uncertainties: at most 2 items each.

RESPONSE FORMAT (strict JSON, no markdown):
{{
  "thinking": "one sentence or omit",
  "summary": "1-2 sentences",
  "connections": [
    {{"entity_a": "...", "entity_b": "...", "confidence": "high|medium|low", "evidence": "...", "reasoning": "..."}}
  ],
  "contradictions": [],
  "uncertainties": []
}}

CRITICAL: answer in English. JSON only.
"""


# ============================================================
# COMPACT PROMPTS (fast CPU-friendly mode)
# ============================================================
# The full prompts above are good for powerful models, but on a 7B/CPU model
# generation produces too much text: filtering 16 sites can take
# 10+ minutes. The compact protocol asks only for site numbers and short
# conclusions — the response is many times shorter, and the data is restored on the Python side.

def build_filter_compact_prompt(input_type: str, lang: str = "ru") -> str:
    if str(lang).lower().startswith("en"):
        return _build_filter_compact_prompt_en(input_type)

    type_hint = {
        "username": "Ищем ник. STRONG/MEDIUM сайты важны, WEAK без метаданных — мусор.",
        "email": "Ищем email. Оставляй все сайты, где email найден, особенно с metadata (username/avatar/bio).",
        "domain": "Ищем домен. Оставляй email и субдомены; отбрасывай только postmaster@/abuse@/noreply@.",
    }.get(input_type, "Оставляй значимые сайты, отбрасывай явный мусор.")

    return f"""Ты — OSINT-фильтр. Тебе дан пронумерованный список сайтов.
{type_hint}

ПРАВИЛА:
1. Номера STRONG и MEDIUM — оставляй.
2. WEAK без metadata — отбрасывай.
3. Сайт с data (bio, fullname, username, followers) — оставляй.
4. Не переписывай сайты и URL. Только номера.
5. Если сомневаешься — оставь сайт.

ФОРМАТ ОТВЕТА (строго JSON, без markdown):
{{"keep": [1, 2, 5], "thinking": "одно короткое предложение"}}

ВАЖНО: только JSON. Никаких пояснений вокруг.
"""


def build_analyze_compact_prompt(input_type: str, lang: str = "ru") -> str:
    if str(lang).lower().startswith("en"):
        return _build_analyze_compact_prompt_en(input_type)

    type_hint = {
        "username": "Связывай ник с сайтами, bio-ссылками, email и Telegram.",
        "email": "Связывай email с сайтами и найденными никнеймами; email на многих сайтах — уже вывод.",
        "domain": "Опиши инфраструктуру: email, субдомены, хосты; не выдумывай людей.",
    }.get(input_type, "Делай только обоснованные выводы.")

    return f"""Ты — OSINT-аналитик. Данные уже отфильтрованы.
{type_hint}

ЖЁСТКИЕ ПРАВИЛА:
- Не выдумывай сущности и связи. Используй только DATA.
- Пиши кратко: summary 1–2 предложения, thinking — максимум 1 предложение (можно пропустить).
- connections: максимум 10, только реальные связи из данных.
- entities можно не перечислять — они уже извлечены программой.
- contradictions и uncertainties: максимум по 2 пункта.

ФОРМАТ ОТВЕТА (строго JSON, без markdown):
{{
  "thinking": "1 предложение или пропусти",
  "summary": "1–2 предложения",
  "connections": [
    {{"entity_a": "...", "entity_b": "...", "confidence": "high|medium|low", "evidence": "...", "reasoning": "..."}}
  ],
  "contradictions": [],
  "uncertainties": []
}}

КРИТИЧНО: отвечай по-русски. Только JSON.
"""
