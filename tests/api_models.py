# api_models.py — data models for FastAPI.
#
# Pydantic automatically:
#   - validates input data,
#   - documents the API,
#   - serializes responses to JSON.

from pydantic import BaseModel, Field
from typing import Optional


# ============================================================
# INCOMING REQUESTS
# ============================================================

class InvestigateRequest(BaseModel):
    """Investigation request."""
    input_type: str = Field(
        ...,
        description="Тип входных данных: username | email | domain",
        pattern="^(username|email|domain)$",
    )
    value: str = Field(
        ...,
        description="Значение для поиска (ник, email или домен)",
        min_length=1,
        max_length=200,
    )
    language: str = Field(
        default="ru",
        description="Язык отчёта: ru | en",
        pattern="^(ru|en)$",
    )
    use_ai: bool = Field(
        default=True,
        description="False — Raw Mode: без фильтрации и анализа через LLM",
    )


# ============================================================
# OUTGOING RESPONSES
# ============================================================

class HealthResponse(BaseModel):
    """Response to /api/health."""
    status: str
    ollama_model: str
    ollama_available: bool
    llm_provider: str = "ollama"
    llm_model: str = ""
    llm_available: bool = False
    use_ai: bool = True


class InvestigateResponse(BaseModel):
    """Investigation result."""
    input: str
    input_type: str
    collected_at: str
    language: str
    raw_data: dict
    filtered: dict
    analysis: dict
    report_path: Optional[str] = None
    error: Optional[str] = None
    ai_used: bool = True
    mode: Optional[str] = None
    llm_provider: str = "ollama"
    llm_model: str = ""


# ============================================================
# INVESTIGATIONS (a graph assembled manually)
# ============================================================

class InvestigationCreate(BaseModel):
    """Creating an empty investigation."""
    title: Optional[str] = Field(default=None, max_length=200)


class InvestigationUpdate(BaseModel):
    """Renaming an investigation."""
    title: str = Field(..., min_length=1, max_length=200)


class NodeCreate(BaseModel):
    """A new graph node (created manually)."""
    label: str = Field(..., min_length=1, max_length=500)
    type: str = Field(default="custom", max_length=32)
    url: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=20000)
    x: Optional[float] = None
    y: Optional[float] = None


class NodeUpdate(BaseModel):
    """Partial update of a node."""
    label: Optional[str] = Field(default=None, min_length=1, max_length=500)
    type: Optional[str] = Field(default=None, max_length=32)
    url: Optional[str] = Field(default=None, max_length=2000)
    description: Optional[str] = Field(default=None, max_length=4000)
    notes: Optional[str] = Field(default=None, max_length=20000)
    x: Optional[float] = None
    y: Optional[float] = None


class EdgeCreate(BaseModel):
    """A new edge between nodes."""
    source: str = Field(..., min_length=1, max_length=80)
    target: str = Field(..., min_length=1, max_length=80)
    label: str = Field(default="связь", max_length=200)
    confidence: str = Field(default="medium", pattern="^(high|medium|low)$")
    evidence: str = Field(default="", max_length=4000)
    reasoning: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=20000)


class EdgeUpdate(BaseModel):
    """Partial update of an edge."""
    label: Optional[str] = Field(default=None, max_length=200)
    confidence: Optional[str] = Field(default=None, pattern="^(high|medium|low)$")
    evidence: Optional[str] = Field(default=None, max_length=4000)
    reasoning: Optional[str] = Field(default=None, max_length=4000)
    notes: Optional[str] = Field(default=None, max_length=20000)


class PositionsUpdate(BaseModel):
    """Card coordinates after dragging."""
    positions: dict[str, dict]


class ImportSearchRequest(BaseModel):
    """Importing a search result into an investigation."""
    result: dict = Field(..., description="Ответ /api/investigate")
    link_to: Optional[str] = Field(
        default=None,
        description="id существующего звена, к которому нужно привязать новый запрос",
    )


class ImportReportRequest(BaseModel):
    """Importing an old JSON report from output/."""
    filename: str = Field(..., min_length=1, max_length=300)
    link_to: Optional[str] = None


class SavePageRequest(BaseModel):
    """Saving an HTML snapshot of the analysis page."""
    html: str = Field(..., min_length=1)
    title: Optional[str] = Field(default=None, max_length=200)


# ============================================================
# LLM SETTINGS FROM THE WEB
# ============================================================

class LLMSettingsUpdate(BaseModel):
    """Changing the provider/key/URL/model without editing files."""
    provider: Optional[str] = Field(
        default=None,
        pattern="^(ollama|openai|openrouter)$",
    )
    model: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)
    clear_api_key: bool = False
