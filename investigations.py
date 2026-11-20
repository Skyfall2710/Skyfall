# investigations.py — storage for "live" investigations.
#
# How it differs from a report in output/:
#   output/report_*.json — a snapshot of a single search (what the tools + LLM returned).
#   investigations/*.json — a graph the user assembles by hand:
#       several consecutive searches, own nodes,
#       manual edges, notes on nodes and edges, card coordinates.
#
# The module deliberately does not depend on FastAPI: it can be used from the CLI and tests.
#
# Investigation file structure:
# {
#   "id": "inv_...",
#   "title": "Investigation: octocat",
#   "created_at": "ISO",
#   "updated_at": "ISO",
#   "nodes": [
#     {"id": "n_...", "num": 1, "label": "...", "type": "center|nick|email|domain|url|telegram|custom|unknown",
#      "url": "https://...", "description": "...", "notes": "...", "origin": "Search: ...",
#      "role": "input|entity|manual", "x": 0, "y": 0, "created_at": "ISO", "updated_at": "ISO"}
#   ],
#   "edges": [
#     {"id": "e_...", "source": "n_...", "target": "n_...", "label": "link",
#      "confidence": "high|medium|low", "evidence": "...", "reasoning": "...",
#      "notes": "...", "origin": "...", "created_at": "ISO", "updated_at": "ISO"}
#   ],
#   "searches": [
#     {"input": "...", "input_type": "username", "report_path": "...", "at": "ISO",
#      "nodes_added": 12, "edges_added": 5}
#   ]
# }

import datetime
import json
import math
import os
import re
import secrets

from config import OUTPUT_DIR
import i18n


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _ui(ru: str, en: str) -> str:
    return en if i18n.current_lang() == "en" else ru

# The folders can be overridden via the environment (handy for tests).
INVESTIGATIONS_DIR = os.environ.get(
    "OSINT_INVESTIGATIONS_DIR",
    os.path.join(BASE_DIR, "investigations"),
)
SAVED_PAGES_DIR = os.environ.get(
    "OSINT_SAVED_PAGES_DIR",
    os.path.join(BASE_DIR, "saved_pages"),
)

os.makedirs(INVESTIGATIONS_DIR, exist_ok=True)
os.makedirs(SAVED_PAGES_DIR, exist_ok=True)

# Maximum size of a saved HTML page (25 MB).
MAX_PAGE_BYTES = 25 * 1024 * 1024

_INV_ID_RE = re.compile(r"^inv_[A-Za-z0-9_]+$")
_NODE_TYPES = {
    "center", "nick", "email", "domain", "url", "telegram", "custom", "unknown",
}

_TYPE_ALIASES = {
    "username": "nick",
    "ник": "nick",
    "nickname": "nick",
    "e-mail": "email",
    "почта": "email",
    "site": "url",
    "website": "url",
    "profile": "url",
    "ссылка": "url",
    "tg": "telegram",
    "телеграм": "telegram",
    "своё": "custom",
    "own": "custom",
}

_INPUT_TYPE_TO_NODE = {
    "username": "nick",
    "email": "email",
    "domain": "domain",
}

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE)


# ============================================================
# HELPERS
# ============================================================

def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    """Short unique id: inv_lk3j2h_ab12cd."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}_{secrets.token_hex(3)}"


def _normalize_type(value) -> str:
    raw = str(value or "").strip().lower()
    raw = _TYPE_ALIASES.get(raw, raw)
    return raw if raw in _NODE_TYPES else "unknown"


def _clean_text(value, limit: int = 20000) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    return text[:limit]


def _looks_like_url(value: str) -> bool:
    return bool(_URL_RE.match(value or ""))


def _normalize_url(value) -> str:
    """Keeps only safe links (http/https/mailto) or a domain."""
    text = _clean_text(value, 2000)
    if not text:
        return ""
    if re.match(r"^(https?://|mailto:)", text, re.IGNORECASE):
        return text
    # A link like t.me/name or example.com/path — prepend https://.
    if re.match(r"^[\w.-]+\.[A-Za-z]{2,63}(?:[/?#].*)?$", text):
        return "https://" + text
    # Unknown scheme (javascript:, data:, etc.) — do not save.
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text):
        return ""
    return ""


def _looks_like_domain(value: str) -> bool:
    return bool(_DOMAIN_RE.match(value or ""))


def _translit(value: str) -> str:
    return "".join(_TRANSLIT.get(ch.lower(), ch) for ch in value)


def _slugify(value: str, fallback: str = "page", limit: int = 60) -> str:
    text = _translit(str(value or ""))
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return (text[:limit] or fallback)


def _coerce_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 2)


# ============================================================
# READING / WRITING
# ============================================================

def investigation_file(inv_id: str) -> str:
    """Returns a safe path to the investigation file."""
    if not _INV_ID_RE.match(str(inv_id or "")):
        raise ValueError("Некорректный id расследования")
    return os.path.join(INVESTIGATIONS_DIR, f"{inv_id}.json")


def load_investigation(inv_id: str):
    path = investigation_file(inv_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    data.setdefault("searches", [])
    if not isinstance(data["nodes"], list):
        data["nodes"] = []
    if not isinstance(data["edges"], list):
        data["edges"] = []
    if not isinstance(data["searches"], list):
        data["searches"] = []
    return data


def save_investigation(inv: dict) -> dict:
    """Atomically saves the investigation to disk."""
    if not isinstance(inv, dict) or not inv.get("id"):
        raise ValueError("Некорректное расследование")
    path = investigation_file(inv["id"])
    inv["updated_at"] = _now()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(inv, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return inv


def _touch(inv: dict) -> None:
    inv["updated_at"] = _now()


def list_investigations() -> list:
    """List of investigations (brief), newest first."""
    items = []
    try:
        names = os.listdir(INVESTIGATIONS_DIR)
    except OSError:
        return items

    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            inv = load_investigation(name[:-5])
        except ValueError:
            continue
        if not inv:
            continue
        searches = inv.get("searches") or []
        items.append({
            "id": inv.get("id"),
            "title": inv.get("title") or "Без названия",
            "created_at": inv.get("created_at"),
            "updated_at": inv.get("updated_at"),
            "node_count": len(inv.get("nodes") or []),
            "edge_count": len(inv.get("edges") or []),
            "search_count": len(searches),
            "last_input": searches[-1].get("input") if searches else None,
        })

    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def create_investigation(title: str = None) -> dict:
    now = _now()
    default_title = _ui(
        "Расследование " + datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Investigation " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    inv = {
        "id": _new_id("inv"),
        "title": _clean_text(title, 200) or default_title,
        "created_at": now,
        "updated_at": now,
        "nodes": [],
        "edges": [],
        "searches": [],
    }
    return save_investigation(inv)


def update_investigation(inv_id: str, title: str) -> dict:
    inv = _require(inv_id)
    clean = _clean_text(title, 200)
    if not clean:
        raise ValueError("Название не может быть пустым")
    inv["title"] = clean
    _touch(inv)
    return save_investigation(inv)


def delete_investigation(inv_id: str) -> bool:
    path = investigation_file(inv_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def _require(inv_id: str) -> dict:
    inv = load_investigation(inv_id)
    if not inv:
        raise LookupError("Расследование не найдено")
    return inv


# ============================================================
# NODES
# ============================================================

def _find_node(inv: dict, node_id: str):
    for node in inv.get("nodes") or []:
        if node.get("id") == node_id:
            return node
    return None


def find_node_by_label(inv: dict, label: str, node_type: str = None):
    target = _clean_text(label, 500).lower()
    if not target:
        return None
    for node in inv.get("nodes") or []:
        if node.get("label", "").strip().lower() != target:
            continue
        if node_type and node.get("type") != _normalize_type(node_type):
            continue
        return node
    return None


def _next_num(inv: dict) -> int:
    numbers = []
    for node in inv.get("nodes") or []:
        try:
            numbers.append(int(node.get("num")))
        except (TypeError, ValueError):
            continue
    return (max(numbers) + 1) if numbers else 1


def _spot_is_free(inv: dict, x: float, y: float) -> bool:
    """Rough check that the card will not overlap existing ones."""
    for node in inv.get("nodes") or []:
        nx = _coerce_float(node.get("x"))
        ny = _coerce_float(node.get("y"))
        if nx is None or ny is None:
            continue
        if abs(nx - x) < 230 and abs(ny - y) < 78:
            return False
    return True


def _spawn_position(inv: dict, near_id: str = None, dx: float = 340.0):
    """
    Finds a free spot for a new node.

    If near_id is given, tries points on rings around it
    so that several searches attached to the same node do not stick together.
    """
    nodes = inv.get("nodes") or []
    if near_id:
        near = _find_node(inv, near_id)
        nx = _coerce_float(near.get("x")) if near else None
        ny = _coerce_float(near.get("y")) if near else None
        if nx is not None and ny is not None:
            for ring in range(1, 5):
                radius = dx * ring
                for angle in (0, -45, 45, -90, 90, 135, -135, 180):
                    radians = math.radians(angle)
                    x = round(nx + radius * math.cos(radians), 2)
                    y = round(ny + radius * math.sin(radians), 2)
                    if _spot_is_free(inv, x, y):
                        return x, y
            return nx + dx * 5, ny

    xs = [float(n["x"]) for n in nodes if _coerce_float(n.get("x")) is not None]
    ys = [float(n["y"]) for n in nodes if _coerce_float(n.get("y")) is not None]
    if xs:
        x = max(xs) + dx
        y = (sum(ys) / len(ys)) if ys else 0.0
        if _spot_is_free(inv, x, y):
            return x, y
        # Look for a free spot further to the right.
        for offset in range(1, 6):
            cx = max(xs) + dx + offset * 120
            for dy in (0, -180, 180, -360, 360):
                if _spot_is_free(inv, cx, y + dy):
                    return cx, y + dy
        return x, y
    return 0.0, 0.0


def add_node(inv: dict, *, label: str, type: str = "custom", url: str = "",
             description: str = "", notes: str = "", origin: str = "",
             role: str = "manual", x=None, y=None, force_new: bool = False) -> tuple:
    """
    Adds a node. Returns (node, created).

    Identical (type + value) nodes are not duplicated: the existing node
    is filled in with the missing url/description/notes.
    """
    clean_label = _clean_text(label, 500)
    if not clean_label:
        raise ValueError("Название звена не может быть пустым")

    node_type = _normalize_type(type)

    if not force_new:
        existing = find_node_by_label(inv, clean_label, node_type)
        if existing:
            changed = False
            for key, value in (("url", _normalize_url(url)),
                               ("description", _clean_text(description, 4000)),
                               ("notes", _clean_text(notes, 20000))):
                if value and not existing.get(key):
                    existing[key] = value
                    changed = True
            if origin and not existing.get("origin"):
                existing["origin"] = origin
                changed = True
            if changed:
                existing["updated_at"] = _now()
                _touch(inv)
            return existing, False

    x = _coerce_float(x)
    y = _coerce_float(y)
    if x is None or y is None:
        x, y = _spawn_position(inv, near_id=None)

    now = _now()
    node = {
        "id": _new_id("n"),
        "num": _next_num(inv),
        "label": clean_label,
        "type": node_type,
        "url": _normalize_url(url),
        "description": _clean_text(description, 4000),
        "notes": _clean_text(notes, 20000),
        "origin": _clean_text(origin, 300),
        "role": role if role in {"input", "entity", "manual"} else "manual",
        "x": x,
        "y": y,
        "created_at": now,
        "updated_at": now,
    }
    inv.setdefault("nodes", []).append(node)
    _touch(inv)
    return node, True


def update_node(inv: dict, node_id: str, fields: dict) -> dict:
    node = _find_node(inv, node_id)
    if not node:
        raise LookupError("Звено не найдено")

    if "label" in fields and fields["label"] is not None:
        label = _clean_text(fields["label"], 500)
        if not label:
            raise ValueError("Название звена не может быть пустым")
        node["label"] = label
    if "type" in fields and fields["type"] is not None:
        node["type"] = _normalize_type(fields["type"])
    for key, limit in (("url", 2000), ("description", 4000), ("notes", 20000)):
        if key in fields and fields[key] is not None:
            node[key] = _normalize_url(fields[key]) if key == "url" else _clean_text(fields[key], limit)
    for key in ("x", "y"):
        if key in fields and fields[key] is not None:
            value = _coerce_float(fields[key])
            if value is not None:
                node[key] = value

    node["updated_at"] = _now()
    _touch(inv)
    return node


def delete_node(inv: dict, node_id: str) -> bool:
    node = _find_node(inv, node_id)
    if not node:
        return False
    inv["nodes"] = [n for n in inv.get("nodes") or [] if n.get("id") != node_id]
    inv["edges"] = [
        e for e in inv.get("edges") or []
        if e.get("source") != node_id and e.get("target") != node_id
    ]
    _touch(inv)
    return True


# ============================================================
# EDGES
# ============================================================

def _find_edge(inv: dict, edge_id: str):
    for edge in inv.get("edges") or []:
        if edge.get("id") == edge_id:
            return edge
    return None


def _find_edge_between(inv: dict, a: str, b: str):
    key = {a, b}
    for edge in inv.get("edges") or []:
        if {edge.get("source"), edge.get("target")} == key:
            return edge
    return None


def add_edge(inv: dict, *, source: str, target: str, label: str = "связь",
             confidence: str = "medium", evidence: str = "", reasoning: str = "",
             notes: str = "", origin: str = "", force_new: bool = False) -> tuple:
    """Adds an undirected edge. Returns (edge, created)."""
    if not _find_node(inv, source) or not _find_node(inv, target):
        raise ValueError("Оба звена связи должны существовать")
    if source == target:
        raise ValueError("Нельзя связать звено само с собой")

    level = str(confidence or "medium").strip().lower()
    if level not in {"high", "medium", "low"}:
        level = "medium"

    if not force_new:
        existing = _find_edge_between(inv, source, target)
        if existing:
            changed = False
            for key, value in (("label", _clean_text(label, 200)),
                               ("evidence", _clean_text(evidence, 4000)),
                               ("reasoning", _clean_text(reasoning, 4000)),
                               ("notes", _clean_text(notes, 20000)),
                               ("origin", _clean_text(origin, 300))):
                if value and not existing.get(key):
                    existing[key] = value
                    changed = True
            # A manual edge is "stronger" than an automatic one — raise the confidence.
            if level == "high" and existing.get("confidence") != "high":
                existing["confidence"] = "high"
                changed = True
            if changed:
                existing["updated_at"] = _now()
                _touch(inv)
            return existing, False

    now = _now()
    edge = {
        "id": _new_id("e"),
        "source": source,
        "target": target,
        "label": _clean_text(label, 200) or "связь",
        "confidence": level,
        "evidence": _clean_text(evidence, 4000),
        "reasoning": _clean_text(reasoning, 4000),
        "notes": _clean_text(notes, 20000),
        "origin": _clean_text(origin, 300),
        "created_at": now,
        "updated_at": now,
    }
    inv.setdefault("edges", []).append(edge)
    _touch(inv)
    return edge, True


def update_edge(inv: dict, edge_id: str, fields: dict) -> dict:
    edge = _find_edge(inv, edge_id)
    if not edge:
        raise LookupError("Связь не найдена")

    if "label" in fields and fields["label"] is not None:
        edge["label"] = _clean_text(fields["label"], 200) or "связь"
    if "confidence" in fields and fields["confidence"] is not None:
        level = str(fields["confidence"]).strip().lower()
        if level in {"high", "medium", "low"}:
            edge["confidence"] = level
    for key, limit in (("evidence", 4000), ("reasoning", 4000), ("notes", 20000)):
        if key in fields and fields[key] is not None:
            edge[key] = _clean_text(fields[key], limit)

    edge["updated_at"] = _now()
    _touch(inv)
    return edge


def delete_edge(inv: dict, edge_id: str) -> bool:
    edge = _find_edge(inv, edge_id)
    if not edge:
        return False
    inv["edges"] = [e for e in inv.get("edges") or [] if e.get("id") != edge_id]
    _touch(inv)
    return True


def set_positions(inv: dict, positions: dict) -> int:
    """Saves card coordinates: {node_id: {x, y}}."""
    if not isinstance(positions, dict):
        return 0
    updated = 0
    for node in inv.get("nodes") or []:
        pos = positions.get(node.get("id"))
        if not isinstance(pos, dict):
            continue
        x = _coerce_float(pos.get("x"))
        y = _coerce_float(pos.get("y"))
        if x is None or y is None:
            continue
        node["x"] = x
        node["y"] = y
        updated += 1
    if updated:
        _touch(inv)
    return updated


# ============================================================
# IMPORTING A SEARCH RESULT INTO AN INVESTIGATION
# ============================================================

def _infer_type(value: str, site_urls: dict) -> str:
    text = str(value or "").strip()
    low = text.lower()
    if low in site_urls:
        return "url"
    if _looks_like_url(text):
        return "url"
    if "@" in text and "." in text.rsplit("@", 1)[-1]:
        return "email"
    if low.startswith("t.me/") or low.startswith("@") or "telegram" in low:
        return "telegram"
    if _looks_like_domain(text):
        return "domain"
    return "unknown"


def _site_url_map(filtered: dict) -> tuple:
    urls, descriptions = {}, {}
    for item in (filtered or {}).get("kept") or []:
        if not isinstance(item, dict):
            continue
        site = _clean_text(item.get("site"), 300).lower()
        if not site:
            continue
        url = _clean_text(item.get("url"), 2000)
        if url:
            urls.setdefault(site, url)
        reason = _clean_text(item.get("reason"), 300)
        if reason:
            descriptions.setdefault(site, reason)
    return urls, descriptions


def import_search(inv: dict, result: dict, link_to: str = None) -> dict:
    """
    Adds the results of a single search to the investigation.

    - creates/reuses the query node;
    - adds entities from analysis.entities (with URLs from filtered.kept);
    - adds edges from analysis.connections;
    - with link_to — links the new query to the selected node;
    - lays out new nodes in a ring around the query node.
    """
    if not isinstance(result, dict):
        raise ValueError("Некорректный результат поиска")

    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    filtered = result.get("filtered") if isinstance(result.get("filtered"), dict) else {}

    input_value = _clean_text(result.get("input") or analysis.get("input_value"), 500)
    if not input_value:
        raise ValueError("В результате нет значения запроса")
    input_type = _clean_text(result.get("input_type") or analysis.get("input_type"), 40) or "username"
    origin = _ui(f"Поиск: {input_value}", f"Search: {input_value}")

    site_urls, site_desc = _site_url_map(filtered)

    is_first = not (inv.get("nodes") or [])
    root_type = "center" if is_first else _INPUT_TYPE_TO_NODE.get(input_type, "unknown")

    # --- 1. Query node ---
    root = None
    for node in inv.get("nodes") or []:
        if (node.get("role") == "input"
                and str(node.get("label", "")).strip().lower() == input_value.lower()):
            root = node
            break

    root_created = False
    if root is None:
        root_x, root_y = _spawn_position(inv, near_id=link_to)
        root, root_created = add_node(
            inv,
            label=input_value,
            type=root_type,
            url=(input_value if _looks_like_url(input_value) else ""),
            description=_ui(
                f"Исходный запрос ({input_type})",
                f"Initial query ({input_type})",
            ),
            origin=origin,
            role="input",
            x=root_x,
            y=root_y,
        )
        if is_first and root.get("type") != "center":
            root["type"] = "center"

    root_id = root["id"]
    root_x = float(root.get("x") or 0.0)
    root_y = float(root.get("y") or 0.0)

    nodes_added = 1 if root_created else 0
    edges_added = 0
    spawned = [root] if root_created else []

    def ensure_node(label_value, node_type=None):
        nonlocal nodes_added
        label_clean = _clean_text(label_value, 500)
        if not label_clean:
            return None
        found = find_node_by_label(inv, label_clean)
        if found:
            return found
        guessed = node_type or _infer_type(label_clean, site_urls)
        low = label_clean.lower()
        node, created = add_node(
            inv,
            label=label_clean,
            type=guessed,
            url=site_urls.get(low, ""),
            description=site_desc.get(low, ""),
            origin=origin,
            role="entity",
            x=root_x + 330,
            y=root_y,
        )
        if created:
            nodes_added += 1
            spawned.append(node)
        return node

    # --- 2. Entities ---
    entities = analysis.get("entities") if isinstance(analysis.get("entities"), list) else []
    entity_nodes = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        label = entity.get("value")
        if not label:
            continue
        label = _clean_text(label, 500)
        if label.lower() == input_value.lower():
            continue
        etype = _normalize_type(entity.get("type"))
        if etype == "unknown":
            etype = _infer_type(label, site_urls)
        found_in = entity.get("found_in") if isinstance(entity.get("found_in"), list) else []
        description = ""
        if found_in:
            description = "Найдено в: " + ", ".join(_clean_text(x, 120) for x in found_in if x)
        elif label.lower() in site_desc:
            description = site_desc[label.lower()]

        node = find_node_by_label(inv, label, etype)
        if not node:
            node, created = add_node(
                inv,
                label=label,
                type=etype,
                url=site_urls.get(label.lower(), label if _looks_like_url(label) else ""),
                description=description,
                origin=origin,
                role="entity",
                x=root_x + 330,
                y=root_y,
            )
            if created:
                nodes_added += 1
                spawned.append(node)
        elif description and not node.get("description"):
            node["description"] = description
        entity_nodes.append(node)

    # --- 3. Edges from the LLM ---
    connection_pairs = set()
    connections = analysis.get("connections") if isinstance(analysis.get("connections"), list) else []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        a_label = _clean_text(conn.get("entity_a"), 500)
        b_label = _clean_text(conn.get("entity_b"), 500)
        if not a_label or not b_label:
            continue
        node_a = ensure_node(a_label)
        node_b = ensure_node(b_label)
        if not node_a or not node_b or node_a["id"] == node_b["id"]:
            continue

        evidence = _clean_text(conn.get("evidence"), 4000)
        reasoning = _clean_text(conn.get("reasoning"), 4000)
        for node in (node_a, node_b):
            if evidence and _looks_like_url(evidence) and not node.get("url"):
                node["url"] = _normalize_url(evidence)
        edge, created = add_edge(
            inv,
            source=node_a["id"],
            target=node_b["id"],
            label=_ui("связь", "link"),
            confidence=conn.get("confidence") or "medium",
            evidence=evidence,
            reasoning=reasoning,
            origin=origin,
        )
        connection_pairs.add(frozenset((node_a["id"], node_b["id"])))
        if created:
            edges_added += 1

    # --- 4. Auto edges "query → entity" if the LLM did not provide them ---
    for node in entity_nodes:
        pair = frozenset((root_id, node["id"]))
        if pair in connection_pairs or node["id"] == root_id:
            continue
        _, created = add_edge(
            inv,
            source=root_id,
            target=node["id"],
            label=_ui("найдено", "found"),
            confidence="medium",
            evidence=node.get("url", ""),
            origin=origin,
        )
        connection_pairs.add(pair)
        if created:
            edges_added += 1

    # --- 5. Manual attachment to a node from a previous investigation ---
    if link_to:
        target = _find_node(inv, link_to)
        if target and target["id"] != root_id:
            _, created = add_edge(
                inv,
                source=root_id,
                target=target["id"],
                label=_ui("связь", "link"),
                confidence="high",
                origin=_ui(
                    "Связано вручную при импорте",
                    "Linked manually on import",
                ),
            )
            if created:
                edges_added += 1

    # --- 6. Layout of new nodes around the query node ---
    # Move only what appeared in this search: the old graph does not "jump".
    placed = []
    seen_ids = set()
    for node in spawned:
        if node["id"] == root_id or node["id"] in seen_ids:
            continue
        seen_ids.add(node["id"])
        placed.append(node)

    total = max(len(placed), 1)
    # Fan out to the right of the query — this makes the graph look like the reference scheme:
    # the root node on the left, the found entities in columns on the right.
    for index, node in enumerate(placed):
        column = index // 3
        row = index % 3
        rows_in_column = min(3, total - column * 3)
        node["x"] = round(root_x + 340 + column * 280, 2)
        node["y"] = round(root_y + (row - (rows_in_column - 1) / 2) * 132, 2)

    inv.setdefault("searches", []).append({
        "input": input_value,
        "input_type": input_type,
        "report_path": result.get("report_path"),
        "at": _now(),
        "nodes_added": nodes_added,
        "edges_added": edges_added,
    })

    if not inv.get("title") or inv.get("title") == "Без названия":
        inv["title"] = f"Расследование: {input_value}"

    _touch(inv)
    return {
        "investigation": save_investigation(inv),
        "stats": {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "root_id": root_id,
        },
    }


# ============================================================
# SAVING AN HTML PAGE
# ============================================================

def save_page(inv: dict, html: str, title: str = None) -> dict:
    """Saves a finished HTML analysis page to saved_pages/."""
    if not isinstance(html, str) or not html.strip():
        raise ValueError("Пустая HTML-страница")

    raw = html.encode("utf-8")
    if len(raw) > MAX_PAGE_BYTES:
        raise ValueError(
            f"Страница слишком большая ({len(raw) // (1024 * 1024)} МБ, "
            f"лимит {MAX_PAGE_BYTES // (1024 * 1024)} МБ)"
        )

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = _slugify(title or inv.get("title") or inv.get("id") or "analysis")
    filename = f"{base}_{ts}.html"
    counter = 1
    while os.path.exists(os.path.join(SAVED_PAGES_DIR, filename)):
        counter += 1
        filename = f"{base}_{ts}_{counter}.html"

    path = os.path.join(SAVED_PAGES_DIR, filename)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)

    return {
        "filename": filename,
        "path": path,
        "url": f"/pages/{filename}",
        "size": len(raw),
        "saved_at": _now(),
    }


def list_saved_pages(limit: int = 100) -> list:
    items = []
    try:
        names = os.listdir(SAVED_PAGES_DIR)
    except OSError:
        return items

    for name in names:
        if not name.endswith(".html"):
            continue
        path = os.path.join(SAVED_PAGES_DIR, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        items.append({
            "filename": name,
            "url": f"/pages/{name}",
            "size": stat.st_size,
            "modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).replace(
                microsecond=0
            ).isoformat(),
        })

    items.sort(key=lambda item: item["modified_at"], reverse=True)
    return items[:limit]


def saved_page_path(filename: str) -> str:
    """Safe path to a saved page (no directory traversal)."""
    name = os.path.basename(str(filename or ""))
    if name != str(filename or "") or not name.endswith(".html"):
        raise ValueError("Некорректное имя файла")
    path = os.path.join(SAVED_PAGES_DIR, name)
    if not os.path.isfile(path):
        raise LookupError("Страница не найдена")
    return path


# ============================================================
# MISCELLANEOUS
# ============================================================

def reports_available() -> list:
    """List of JSON reports from output/ (for importing old investigations)."""
    items = []
    try:
        names = os.listdir(OUTPUT_DIR)
    except OSError:
        return items

    for name in names:
        if not name.startswith("report_") or not name.endswith(".json"):
            continue
        path = os.path.join(OUTPUT_DIR, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        items.append({
            "name": name,
            "path": path,
            "size": stat.st_size,
            "modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).replace(
                microsecond=0
            ).isoformat(),
        })

    items.sort(key=lambda item: item["modified_at"], reverse=True)
    return items


def import_report_file(inv: dict, filename: str, link_to: str = None) -> dict:
    """Imports a previously saved output/report_*.json."""
    name = os.path.basename(str(filename or ""))
    if name != str(filename or "") or not name.startswith("report_") or not name.endswith(".json"):
        raise ValueError("Некорректное имя отчёта")

    path = os.path.join(OUTPUT_DIR, name)
    if not os.path.isfile(path):
        raise LookupError("Отчёт не найден")

    with open(path, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError("Некорректный отчёт")

    report.setdefault("report_path", path)
    return import_search(inv, report, link_to=link_to)
