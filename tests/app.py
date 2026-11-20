# app.py — FastAPI server for Skyfall.
#
# What it does:
#   1. Starts an HTTP server on http://127.0.0.1:8000
#   2. Provides endpoints:
#        GET  /                — HTML page (form)
#        GET  /api/health      — check that everything works
#        POST /api/investigate — start a search
#        GET  /api/logs       — the latest log file (plain text)
#        GET  /api/investigations… — "live" investigations (graph, nodes, edges)
#        GET  /pages/…         — saved HTML analysis pages
#        GET  /docs            — automatic documentation
#   3. Serves static files from /static
#
# Run: python3 app.py

import datetime
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Logic from the CLI version
from main import (
    collect_by_username,
    collect_by_email,
    collect_by_domain,
    normalize,
    has_usable_data,
    filter_sites,
    analyze_filtered,
    raw_filtered,
    raw_analysis,
    save_report,
)
import config
from api_models import (
    InvestigateRequest,
    InvestigateResponse,
    HealthResponse,
    InvestigationCreate,
    InvestigationUpdate,
    NodeCreate,
    NodeUpdate,
    EdgeCreate,
    EdgeUpdate,
    PositionsUpdate,
    ImportSearchRequest,
    ImportReportRequest,
    SavePageRequest,
    LLMSettingsUpdate,
)

import investigations
import requests
import i18n
import web_i18n
from logger import get_logger, latest_log_file


# Server-wide interface language: `python app.py --lang en`, OSINT_LANG=en,
# or Russian by default even when the app is imported by uvicorn.
i18n.setup(i18n.parse_lang_arg())

logger = get_logger("api")
logger.info(
    "API старт: provider=%s model=%s use_ai=%s",
    config.LLM_PROVIDER, config.active_model(), config.USE_AI,
)


# Paths to templates and static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
SAVED_PAGES_DIR = investigations.SAVED_PAGES_DIR


app = FastAPI(
    title="Skyfall OSINT Helper API",
    description="Локальный OSINT-анализ через Sherlock, Maigret, Holehe, Diablinda, theHarvester, ThreatFox и LLM (Ollama / OpenAI / OpenRouter).",
    version="0.3.0",
)

# Mount the static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def wt(text: str) -> str:
    """Translates a static web UI string for the active language."""
    return web_i18n.translate(text, i18n.current_lang())


def _web_msg(ru: str, en: str) -> str:
    return en if i18n.current_lang() == "en" else ru


templates.env.globals["wt"] = wt


# ============================================================
# MAIN HTML PAGE
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Returns the HTML page with the form in the server's language."""
    lang = i18n.current_lang()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "lang": lang,
            "web_i18n": web_i18n.translations_for(lang),
        },
    )


# ============================================================
# API ENDPOINTS
# ============================================================

def _llm_status() -> dict:
    """Checks the availability of the selected LLM provider."""
    provider = config.LLM_PROVIDER
    model = config.active_model()
    ollama_ok = False
    llm_ok = False
    error = None

    if provider == "ollama":
        try:
            base = config.OLLAMA_URL.split("/api/")[0]
            r = requests.get(base, timeout=3)
            ollama_ok = r.status_code == 200
            if not ollama_ok:
                error = f"Ollama HTTP {r.status_code}"
        except Exception as exc:
            error = _web_msg(f"Ollama недоступна: {exc}", f"Ollama unavailable: {exc}")
        llm_ok = ollama_ok
    else:
        if not config.OPENAI_API_KEY:
            error = _web_msg(
                "Не задан API-ключ облачного провайдера",
                "Cloud provider API key is not set",
            )
        else:
            try:
                r = requests.get(
                    config.OPENAI_BASE_URL + "/models",
                    headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                    timeout=5,
                )
                llm_ok = r.status_code < 400
                if not llm_ok:
                    error = f"{config.active_provider()} HTTP {r.status_code}"
            except Exception as exc:
                error = _web_msg(
                    f"{config.active_provider()} недоступен: {exc}",
                    f"{config.active_provider()} unavailable: {exc}",
                )
            llm_ok = bool(llm_ok)

    return {
        "ok": bool(llm_ok),
        "provider": provider,
        "provider_label": config.active_provider(),
        "model": model,
        "ollama_available": bool(ollama_ok),
        "error": error,
    }


@app.get("/api/health", response_model=HealthResponse)
async def health():
    status = _llm_status()
    return HealthResponse(
        status="ok",
        ollama_model=config.OLLAMA_MODEL,
        ollama_available=status["ollama_available"],
        llm_provider=status["provider"],
        llm_model=status["model"],
        llm_available=status["ok"],
        use_ai=config.USE_AI,
    )


# ============================================================
# LLM SETTINGS (WITHOUT EDITING FILES)
# ============================================================

@app.get("/api/settings/llm")
async def get_llm_settings():
    """Current LLM settings; the API key is returned only in masked form."""
    return config.get_llm_settings()


@app.post("/api/settings/llm")
async def save_llm_settings(req: LLMSettingsUpdate):
    """Saves the provider/key/URL/model to llm_settings.json."""
    try:
        settings = config.update_llm_settings(req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "LLM настройки обновлены: provider=%s model=%s base=%s has_key=%s",
        settings.get("provider"), settings.get("model"),
        settings.get("openai_base_url"), settings.get("has_api_key"),
    )
    return {"settings": settings, "status": _llm_status()}


@app.post("/api/settings/llm/test")
async def test_llm_settings():
    """Checks the availability of the current provider (for the "Check" button)."""
    return _llm_status()


@app.post("/api/investigate", response_model=InvestigateResponse)
async def investigate(req: InvestigateRequest):
    """
    Runs the full cycle:
      1. Data collection via the appropriate tool.
      2. Normalization.
      3. Filtering via the LLM (if AI is enabled).
      4. Analysis via the LLM (if AI is enabled).
      5. Saving JSON to output/.
    Returns the full report.

    Raw Mode (use_ai=false or USE_AI=false) skips the LLM.
    If the LLM failed/did not finish within the timeout — automatic fallback
    to raw data so that the investigation is not lost.
    """
    value = req.value.strip()
    input_type = req.input_type
    use_ai = bool(req.use_ai and config.USE_AI)
    started = time.perf_counter()

    logger.info(
        "API расследование: type=%s value=%s use_ai=%s provider=%s model=%s",
        input_type, value, use_ai, config.LLM_PROVIDER, config.active_model(),
    )

    if not value:
        logger.warning("API: пустое значение запроса")
        raise HTTPException(status_code=400, detail="Пустое значение")

    # --- 1. Data collection ---
    try:
        logger.info("Сбор данных: type=%s value=%s", input_type, value)
        if input_type == "username":
            data = collect_by_username(value)
        elif input_type == "email":
            data = collect_by_email(value)
        elif input_type == "domain":
            data = collect_by_domain(value)
        else:
            raise HTTPException(status_code=400, detail="Неверный тип входа")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ошибка сбора данных: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сбора: {e}")

    # --- 2. Normalization ---
    try:
        normalized = normalize(data, input_type, value)
    except Exception as e:
        logger.error("Ошибка нормализации: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка нормализации: {e}")

    logger.info(
        "Нормализация: sites=%s nicks=%s emails=%s observations=%s",
        len(normalized.get("sites") or []),
        len(normalized.get("nicks") or []),
        len(normalized.get("emails") or []),
        len(normalized.get("observations") or []),
    )

    # --- 2.1. Protection against an empty result ---
    if not has_usable_data(normalized):
        logger.warning("Нет пригодных данных для %s", value)
        return InvestigateResponse(
            input=value,
            input_type=input_type,
            collected_at=datetime.datetime.now().isoformat(),
            language=req.language,
            raw_data=data,
            filtered={},
            analysis={},
            error=i18n.t("error.no_data", value=value),
            ai_used=False,
            mode="no_data",
            llm_provider=config.LLM_PROVIDER,
            llm_model=config.active_model(),
        )

    # --- 3-4. Filtering and analysis ---
    fallback_reason = ""
    mode = "ai"
    ai_used = False

    if not use_ai:
        mode = "raw"
        logger.info("Raw Mode: LLM-фильтрация и анализ пропущены")
        filtered = raw_filtered(normalized)
        analysis = raw_analysis(normalized, filtered)
    else:
        # --- 3. Filtering ---
        try:
            filtered = filter_sites(normalized)
        except Exception as e:
            logger.error("Ошибка фильтрации: %s", e, exc_info=True)
            filtered = {"error": str(e)}

        if "error" in filtered:
            fallback_reason = str(filtered.get("error"))
            logger.warning("Фильтрация LLM недоступна, Raw fallback: %s", fallback_reason)
            filtered = raw_filtered(normalized)
            analysis = raw_analysis(
                normalized,
                filtered,
                summary=_web_msg(
                    "LLM недоступна — показаны данные без AI-анализа",
                    "The LLM is unavailable; data is shown without AI analysis",
                ),
                mode="raw_fallback",
                reason=_web_msg(
                    f"Фильтрация LLM: {fallback_reason}",
                    f"LLM filtering: {fallback_reason}",
                ),
            )
            mode = "raw_fallback"
        else:
            # --- 4. Analysis ---
            try:
                analysis = analyze_filtered(normalized, filtered)
            except Exception as e:
                logger.error("Ошибка анализа: %s", e, exc_info=True)
                analysis = {"error": str(e)}

            if not isinstance(analysis, dict) or "error" in analysis:
                fallback_reason = str(
                    analysis.get("error") if isinstance(analysis, dict) else "empty analysis"
                )
                logger.warning("Анализ LLM недоступен, Raw fallback: %s", fallback_reason)
                analysis = raw_analysis(
                    normalized,
                    filtered,
                    summary=_web_msg(
                        "LLM недоступна — показаны данные без AI-анализа",
                        "The LLM is unavailable; data is shown without AI analysis",
                    ),
                    mode="raw_fallback",
                    reason=_web_msg(
                        f"Анализ LLM: {fallback_reason}",
                        f"LLM analysis: {fallback_reason}",
                    ),
                )
                mode = "raw_fallback"
            else:
                ai_used = True
                mode = "ai"

    if not isinstance(analysis, dict):
        analysis = raw_analysis(normalized, filtered)

    analysis.setdefault("input_type", input_type)
    analysis.setdefault("input_value", value)
    analysis.setdefault("mode", mode)
    if fallback_reason:
        analysis.setdefault("notice", fallback_reason)

    # --- 5. Saving ---
    try:
        path = save_report(value, data, filtered, analysis)
        logger.info("Отчёт сохранён: %s", path)
    except Exception as e:
        path = None
        logger.error("Не удалось сохранить отчёт: %s", e, exc_info=True)

    elapsed = time.perf_counter() - started
    logger.info(
        "API расследование завершено за %.1f сек: mode=%s, filtered=%s, report=%s",
        elapsed, mode, len(filtered.get("kept") or []), path,
    )

    return InvestigateResponse(
        input=value,
        input_type=input_type,
        collected_at=datetime.datetime.now().isoformat(),
        language=req.language,
        raw_data=data,
        filtered=filtered,
        analysis=analysis,
        report_path=path,
        ai_used=ai_used,
        mode=mode,
        llm_provider=config.LLM_PROVIDER,
        llm_model=config.active_model(),
    )


# ============================================================
# LOGS (for debugging via the browser)
# ============================================================

@app.get("/api/logs", response_class=PlainTextResponse)
async def get_logs():
    """Returns the contents of the latest log file as plain text."""
    path = latest_log_file()
    if not path:
        return PlainTextResponse("Лог-файл не найден.", status_code=404)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("Не удалось прочитать лог %s: %s", path, e, exc_info=True)
        return PlainTextResponse(f"Не удалось прочитать лог: {e}", status_code=500)
    return PlainTextResponse(content)


# ============================================================
# INVESTIGATIONS (a graph the user assembles by hand)
# ============================================================

def _get_investigation_or_404(inv_id: str) -> dict:
    try:
        inv = investigations.load_investigation(inv_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not inv:
        raise HTTPException(status_code=404, detail="Расследование не найдено")
    return inv


def _save(inv: dict):
    try:
        return investigations.save_investigation(inv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/investigations")
async def list_investigations():
    """List of saved investigations."""
    return {"items": investigations.list_investigations()}


@app.post("/api/investigations", status_code=201)
async def create_investigation(req: InvestigationCreate):
    """Creates an empty investigation."""
    return investigations.create_investigation(req.title)


@app.get("/api/investigations/{inv_id}")
async def get_investigation(inv_id: str):
    """Full investigation: nodes, edges, searches."""
    return _get_investigation_or_404(inv_id)


@app.patch("/api/investigations/{inv_id}")
async def rename_investigation(inv_id: str, req: InvestigationUpdate):
    _get_investigation_or_404(inv_id)
    try:
        return investigations.update_investigation(inv_id, req.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/investigations/{inv_id}")
async def remove_investigation(inv_id: str):
    try:
        removed = investigations.delete_investigation(inv_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Расследование не найдено")
    return {"ok": True}


# ---------- Nodes ----------

@app.post("/api/investigations/{inv_id}/nodes", status_code=201)
async def create_node(inv_id: str, req: NodeCreate):
    inv = _get_investigation_or_404(inv_id)
    try:
        node, created = investigations.add_node(
            inv,
            label=req.label,
            type=req.type,
            url=req.url,
            description=req.description,
            notes=req.notes,
            origin=_web_msg("Добавлено вручную", "Added manually"),
            role="manual",
            x=req.x,
            y=req.y,
        )
        _save(inv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"node": node, "created": created, "investigation": inv}


@app.patch("/api/investigations/{inv_id}/nodes/{node_id}")
async def patch_node(inv_id: str, node_id: str, req: NodeUpdate):
    inv = _get_investigation_or_404(inv_id)
    try:
        investigations.update_node(inv, node_id, req.model_dump(exclude_unset=True))
        _save(inv)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "investigation": inv}


@app.delete("/api/investigations/{inv_id}/nodes/{node_id}")
async def remove_node(inv_id: str, node_id: str):
    inv = _get_investigation_or_404(inv_id)
    if not investigations.delete_node(inv, node_id):
        raise HTTPException(status_code=404, detail="Звено не найдено")
    _save(inv)
    return {"ok": True, "investigation": inv}


# ---------- Edges ----------

@app.post("/api/investigations/{inv_id}/edges", status_code=201)
async def create_edge(inv_id: str, req: EdgeCreate):
    inv = _get_investigation_or_404(inv_id)
    try:
        edge, created = investigations.add_edge(
            inv,
            source=req.source,
            target=req.target,
            label=req.label,
            confidence=req.confidence,
            evidence=req.evidence,
            reasoning=req.reasoning,
            notes=req.notes,
            origin=_web_msg("Добавлено вручную", "Added manually"),
        )
        _save(inv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"edge": edge, "created": created, "investigation": inv}


@app.patch("/api/investigations/{inv_id}/edges/{edge_id}")
async def patch_edge(inv_id: str, edge_id: str, req: EdgeUpdate):
    inv = _get_investigation_or_404(inv_id)
    try:
        investigations.update_edge(inv, edge_id, req.model_dump(exclude_unset=True))
        _save(inv)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "investigation": inv}


@app.delete("/api/investigations/{inv_id}/edges/{edge_id}")
async def remove_edge(inv_id: str, edge_id: str):
    inv = _get_investigation_or_404(inv_id)
    if not investigations.delete_edge(inv, edge_id):
        raise HTTPException(status_code=404, detail="Связь не найдена")
    _save(inv)
    return {"ok": True, "investigation": inv}


@app.post("/api/investigations/{inv_id}/positions")
async def save_positions(inv_id: str, req: PositionsUpdate):
    inv = _get_investigation_or_404(inv_id)
    updated = investigations.set_positions(inv, req.positions)
    _save(inv)
    return {"ok": True, "updated": updated}


# ---------- Import a search into the current graph ----------

@app.post("/api/investigations/{inv_id}/import")
async def import_search(inv_id: str, req: ImportSearchRequest):
    inv = _get_investigation_or_404(inv_id)
    try:
        return investigations.import_search(inv, req.result, link_to=req.link_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reports")
async def list_reports():
    """Old JSON reports from output/ — can be imported into an investigation."""
    return {"items": investigations.reports_available()}


@app.post("/api/investigations/{inv_id}/import-report")
async def import_report(inv_id: str, req: ImportReportRequest):
    inv = _get_investigation_or_404(inv_id)
    try:
        return investigations.import_report_file(inv, req.filename, link_to=req.link_to)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------- Saving an HTML page ----------

@app.post("/api/investigations/{inv_id}/save-page")
async def save_page(inv_id: str, req: SavePageRequest):
    inv = _get_investigation_or_404(inv_id)
    try:
        saved = investigations.save_page(inv, req.html, title=req.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return saved


@app.get("/api/pages")
async def list_pages():
    return {"items": investigations.list_saved_pages()}


@app.get("/pages/{filename}")
async def serve_saved_page(filename: str):
    try:
        path = investigations.saved_page_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="text/html; charset=utf-8")


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Skyfall web server")
    parser.add_argument(
        "--lang",
        choices=i18n.AVAILABLE_LANGS,
        default=i18n.current_lang(),
        help="Web interface language (ru or en)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    i18n.setup(args.lang)

    print("=" * 60)
    print("Skyfall OSINT Helper API")
    print("=" * 60)
    print(f"Language: {i18n.current_lang()}")
    print(f"URL:    http://{args.host}:{args.port}")
    print(f"Docs:   http://{args.host}:{args.port}/docs")
    print(f"Health: http://{args.host}:{args.port}/api/health")
    print("=" * 60)
    print("Stop:   Ctrl+C")
    print("=" * 60)
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
