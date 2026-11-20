# graph.py — draws a connection graph from a JSON report.
#
# Usage:
#   python3 graph.py output/report_xxx.json
#   python3 graph.py output/report_xxx.json --output graph.png
#
# The style mirrors the Skyfall web graph:
#   - link cards with a number, a title and a caption;
#   - colour by entity type;
#   - curved edges: turquoise (high), grey (medium/low);
#   - a very dark background.
#
# The graph is built from analysis.entities and analysis.connections.

import argparse
import json
import math
import os
import tempfile

# By default Matplotlib tries to write its cache to ~/.config/matplotlib,
# which is not always available. We redirect the cache to a temporary folder.
os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(tempfile.gettempdir(), "skyfall-matplotlib"),
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import FancyBboxPatch, PathPatch
from matplotlib.path import Path


BG = "#05070a"
CARD_BG = "#10151d"
TEXT = "#e6edf3"
DIM = "#8b949e"
FAINT = "#5d6672"

NODE_STYLES = {
    "center":   ("#6b1d1d", "#c53a3a"),
    "nick":     ("#15233b", "#3f6ea8"),
    "email":    ("#24331f", "#6f9a3f"),
    "domain":   ("#2a2344", "#7c5cd6"),
    "url":      ("#0e3836", "#1fb8a6"),
    "telegram": ("#0b2c3c", "#38bdf8"),
    "custom":   ("#232b38", "#8b9bb4"),
    "unknown":  ("#1a212c", "#475569"),
}

EDGE_COLORS = {
    "high": "#2dd4bf",
    "medium": "#7d8798",
    "low": "#454f5e",
}

EDGE_WIDTHS = {
    "high": 2.4,
    "medium": 1.4,
    "low": 0.9,
}

TYPE_ALIASES = {
    "username": "nick",
    "nick": "nick",
    "email": "email",
    "domain": "domain",
    "url": "url",
    "telegram": "telegram",
}


def _style(node_type: str):
    return NODE_STYLES.get(TYPE_ALIASES.get(node_type, node_type), NODE_STYLES["unknown"])


def _node_width(label: str, description: str) -> float:
    estimated = max(len(label) * 0.115, len(description) * 0.075) + 1.15
    return max(2.0, min(5.2, estimated))


def _trim(cx, cy, width, height, tx, ty):
    """Point on the card border in the direction of (tx, ty)."""
    dx = tx - cx
    dy = ty - cy
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    scale = min(
        (width / 2) / (abs(ux) or 1e-6),
        (height / 2) / (abs(uy) or 1e-6),
    )
    return cx + ux * scale, cy + uy * scale


def _extract(report: dict) -> tuple:
    analysis = report.get("analysis") or {}
    entities = analysis.get("entities") or []
    connections = analysis.get("connections") or []

    nodes = {}   # label -> {"type", "description", "num"}
    edges = []   # {"a", "b", "confidence"}

    # Site names from filtering: such nodes are coloured as "links".
    site_names = set()
    for item in (report.get("filtered") or {}).get("kept") or []:
        if isinstance(item, dict):
            site = str(item.get("site") or "").strip().lower()
            if site:
                site_names.add(site)

    root = report.get("input") or analysis.get("input_value")
    if root:
        nodes[str(root)] = {
            "type": "center",
            "description": "субъект анализа",
        }

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        value = str(entity.get("value") or "").strip()
        if not value:
            continue
        node_type = str(entity.get("type") or "unknown").lower()
        found_in = entity.get("found_in")
        description = ""
        if isinstance(found_in, list) and found_in:
            description = "найдено в: " + ", ".join(str(item) for item in found_in)
        nodes.setdefault(value, {"type": node_type, "description": description})

    if root and str(root) in nodes:
        nodes[str(root)]["type"] = "center"
        nodes[str(root)]["description"] = "субъект анализа"

    def ensure(value, node_type="unknown"):
        value = str(value or "").strip()
        if not value:
            return None
        if value not in nodes:
            guessed = "url" if value.lower() in site_names else node_type
            nodes[value] = {"type": guessed, "description": ""}
        return value

    for connection in connections:
        if not isinstance(connection, dict):
            continue
        a = ensure(connection.get("entity_a"))
        b = ensure(connection.get("entity_b"))
        if not a or not b or a == b:
            continue
        confidence = str(connection.get("confidence") or "low").lower()
        if confidence not in EDGE_COLORS:
            confidence = "low"
        edges.append({"a": a, "b": b, "confidence": confidence})

        reasoning = connection.get("reasoning")
        evidence = connection.get("evidence")
        for value in (a, b):
            if not nodes[value].get("description") and (reasoning or evidence):
                nodes[value]["description"] = str(reasoning or evidence)

    # Link the central node to the entities if the report provided no connections.
    if root:
        connected = set()
        for edge in edges:
            connected.add(edge["a"])
            connected.add(edge["b"])
        for value in list(nodes):
            if value != root and value not in connected:
                edges.append({"a": str(root), "b": value, "confidence": "medium"})
                connected.add(value)

    return nodes, edges


def _layout(nodes: dict, edges: list) -> dict:
    graph = nx.Graph()
    for value in nodes:
        graph.add_node(value)
    for edge in edges:
        graph.add_edge(edge["a"], edge["b"])

    if graph.number_of_nodes() == 0:
        return {}

    if graph.number_of_nodes() == 1:
        return {next(iter(graph.nodes)): (0.0, 0.0)}

    positions = nx.spring_layout(
        graph,
        k=2.6 / math.sqrt(graph.number_of_nodes()),
        iterations=260,
        seed=42,
        scale=7.0,
    )

    # Spread the cards apart so they do not overlap.
    sizes = {
        value: (_node_width(value, nodes[value].get("description", "")), 0.82)
        for value in nodes
    }
    points = {value: list(float(coord) for coord in positions[value]) for value in positions}

    for _ in range(90):
        moved = False
        values = list(points)
        for i, first in enumerate(values):
            for second in values[i + 1:]:
                wx, wy = sizes[first][0] + sizes[second][0], 1.6
                dx = points[second][0] - points[first][0]
                dy = points[second][1] - points[first][1]
                overlap_x = wx / 2 + 0.35 - abs(dx)
                overlap_y = wy / 2 + 0.25 - abs(dy)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                moved = True
                if overlap_x < overlap_y:
                    push = ((1 if dx >= 0 else -1) * overlap_x) / 2
                    points[second][0] += push
                    points[first][0] -= push
                else:
                    push = ((1 if dy >= 0 else -1) * overlap_y) / 2
                    points[second][1] += push
                    points[first][1] -= push
        if not moved:
            break

    return {value: (point[0], point[1]) for value, point in points.items()}


def build_graph(report_path: str, output_path: str = None):
    """Builds and saves a PNG graph from a JSON report."""
    if not os.path.exists(report_path):
        print(f"Файл не найден: {report_path}")
        return None

    with open(report_path, "r", encoding="utf-8") as handle:
        report = json.load(handle)

    nodes, edges = _extract(report)
    if not nodes:
        print("Граф пуст.")
        return None

    positions = _layout(nodes, edges)
    sizes = {
        value: (_node_width(value, nodes[value].get("description", "")), 0.82)
        for value in nodes
    }

    # Numbering: the centre goes first.
    ordered = sorted(nodes, key=lambda value: (nodes[value]["type"] != "center", value.lower()))
    numbers = {value: index + 1 for index, value in enumerate(ordered)}

    figure, axes = plt.subplots(figsize=(17, 9.5))
    figure.patch.set_facecolor(BG)
    axes.set_facecolor(BG)
    axes.set_aspect("equal")
    axes.axis("off")

    # --- Edges ---
    for index, edge in enumerate(edges):
        a, b = edge["a"], edge["b"]
        if a not in positions or b not in positions:
            continue
        ax, ay = positions[a]
        bx, by = positions[b]
        aw, ah = sizes[a]
        bw, bh = sizes[b]
        start = _trim(ax, ay, aw, ah, bx, by)
        end = _trim(bx, by, bw, bh, ax, ay)

        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        bend = (1 if index % 2 == 0 else -1) * (0.22 + (index % 4) * 0.07)

        control = (
            (start[0] + end[0]) / 2 - uy * bend,
            (start[1] + end[1]) / 2 + ux * bend,
        )
        curve = Path(
            [start, control, end],
            [Path.MOVETO, Path.CURVE3, Path.CURVE3],
        )
        patch = PathPatch(
            curve,
            facecolor="none",
            edgecolor=EDGE_COLORS[edge["confidence"]],
            linewidth=EDGE_WIDTHS[edge["confidence"]],
            alpha=0.9 if edge["confidence"] == "high" else 0.65,
            zorder=1,
            capstyle="round",
        )
        axes.add_patch(patch)

    # --- Cards ---
    for value in nodes:
        if value not in positions:
            continue
        x, y = positions[value]
        width, height = sizes[value]
        face, border = _style(nodes[value]["type"])

        card = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0,rounding_size=0.16",
            facecolor=face,
            edgecolor=border,
            linewidth=1.1,
            zorder=3,
        )
        axes.add_patch(card)

        # Link number.
        badge_w = 0.42
        badge = FancyBboxPatch(
            (x - width / 2 + 0.12, y - 0.19),
            badge_w,
            0.38,
            boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=(0, 0, 0, 0.28),
            edgecolor=(1, 1, 1, 0.12),
            linewidth=0.7,
            zorder=4,
        )
        axes.add_patch(badge)
        axes.text(
            x - width / 2 + 0.12 + badge_w / 2,
            y + 0.005,
            str(numbers[value]),
            ha="center",
            va="center",
            color="#c3cbd5",
            fontsize=6.2,
            fontweight="bold",
            family="DejaVu Sans Mono",
            zorder=5,
        )

        text_x = x - width / 2 + 0.66
        max_chars = max(10, int((width - 0.9) * 8.2))
        clean_value = " ".join(str(value).split())
        label = clean_value if len(clean_value) <= max_chars else clean_value[: max_chars - 1] + "…"
        axes.text(
            text_x,
            y + 0.16,
            label,
            ha="left",
            va="center",
            color=TEXT,
            fontsize=7.0,
            fontweight="bold",
            family="DejaVu Sans Mono",
            zorder=5,
        )

        description = " ".join(str(nodes[value].get("description") or "").split())
        if description:
            max_desc = max(12, int((width - 0.9) * 9.5))
            if len(description) > max_desc:
                description = description[: max_desc - 1] + "…"
            axes.text(
                text_x,
                y - 0.17,
                description,
                ha="left",
                va="center",
                color=DIM,
                fontsize=5.3,
                family="DejaVu Sans",
                zorder=5,
            )

    # --- Title/legend ---
    axes.text(
        0.012, 0.985,
        "Skyfall — граф связей",
        transform=axes.transAxes,
        color=FAINT,
        fontsize=10,
        family="DejaVu Sans Mono",
        va="top",
    )
    legend_lines = [
        ("high", "сильная связь"),
        ("medium", "средняя"),
        ("low", "слабая"),
    ]
    for index, (level, label) in enumerate(legend_lines):
        y = 0.965 - index * 0.035
        axes.plot(
            [0.87, 0.895], [y, y],
            color=EDGE_COLORS[level],
            linewidth=EDGE_WIDTHS[level] + 0.8,
            transform=axes.transAxes,
            clip_on=False,
        )
        axes.text(
            0.90, y, label,
            transform=axes.transAxes,
            color=FAINT,
            fontsize=7.2,
            va="center",
            family="DejaVu Sans",
        )

    axes.margins(0.04)

    if output_path is None:
        output_path = report_path.replace(".json", ".png")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    figure.savefig(
        output_path,
        bbox_inches="tight",
        dpi=130,
        facecolor=figure.get_facecolor(),
    )
    plt.close(figure)
    print(f"✅ Граф: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Построить граф связей из JSON-отчёта Skyfall.",
    )
    parser.add_argument("report", help="Путь к JSON-отчёту")
    parser.add_argument("--output", "-o", help="Куда сохранить PNG")
    args = parser.parse_args()

    build_graph(args.report, args.output)


if __name__ == "__main__":
    main()
