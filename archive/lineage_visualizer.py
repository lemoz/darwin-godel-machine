"""Archive lineage visualization helpers."""

from collections import defaultdict
from html import escape
from typing import Dict, Iterable, List, Tuple

from .agent_archive import ArchivedAgent


def _short_id(agent_id: str) -> str:
    return agent_id[:8]


def _score_label(score: float) -> str:
    return f"{score:.3f}"


def _sorted_agents(agents: Iterable[ArchivedAgent]) -> List[ArchivedAgent]:
    return sorted(agents, key=lambda agent: (agent.generation, agent.created_at, agent.agent_id))


def render_archive_lineage_svg(agents: Iterable[ArchivedAgent]) -> str:
    """Render archived agents as a simple SVG family tree."""
    sorted_agents = _sorted_agents(agents)
    if not sorted_agents:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="160" '
            'viewBox="0 0 480 160" role="img" aria-label="Empty archive lineage">'
            '<rect width="480" height="160" fill="#ffffff"/>'
            '<text x="240" y="82" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="18" fill="#475569">No archived agents yet</text>'
            "</svg>"
        )

    levels: Dict[int, List[ArchivedAgent]] = defaultdict(list)
    for agent in sorted_agents:
        levels[agent.generation].append(agent)

    node_width = 150
    node_height = 72
    x_gap = 40
    y_gap = 70
    margin = 40
    max_nodes = max(len(level) for level in levels.values())
    max_generation = max(levels)
    width = max(520, margin * 2 + max_nodes * node_width + (max_nodes - 1) * x_gap)
    height = margin * 2 + (max_generation + 1) * node_height + max_generation * y_gap

    positions: Dict[str, Tuple[int, int]] = {}
    for generation, level_agents in levels.items():
        row_width = len(level_agents) * node_width + (len(level_agents) - 1) * x_gap
        start_x = (width - row_width) // 2
        y = margin + generation * (node_height + y_gap)
        for index, agent in enumerate(level_agents):
            x = start_x + index * (node_width + x_gap)
            positions[agent.agent_id] = (x, y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="DGM archive lineage">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>'
        '.node-label{font-family:Arial,sans-serif;font-size:13px;fill:#0f172a}'
        '.node-meta{font-family:Arial,sans-serif;font-size:11px;fill:#475569}'
        '.edge{stroke:#94a3b8;stroke-width:2;fill:none}'
        "</style>",
    ]

    for agent in sorted_agents:
        if not agent.parent_id or agent.parent_id not in positions:
            continue
        parent_x, parent_y = positions[agent.parent_id]
        child_x, child_y = positions[agent.agent_id]
        x1 = parent_x + node_width // 2
        y1 = parent_y + node_height
        x2 = child_x + node_width // 2
        y2 = child_y
        mid_y = (y1 + y2) // 2
        parts.append(
            f'<path class="edge" d="M{x1},{y1} C{x1},{mid_y} {x2},{mid_y} {x2},{y2}"/>'
        )

    for agent in sorted_agents:
        x, y = positions[agent.agent_id]
        fill = "#ecfdf5" if agent.is_valid else "#fef2f2"
        stroke = "#10b981" if agent.is_valid else "#ef4444"
        label = escape(_short_id(agent.agent_id))
        score = escape(_score_label(agent.average_score))
        parent = escape(_short_id(agent.parent_id)) if agent.parent_id else "root"
        parts.extend([
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
            f'rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
            f'<text class="node-label" x="{x + 12}" y="{y + 24}">agent {label}</text>',
            f'<text class="node-meta" x="{x + 12}" y="{y + 43}">gen {agent.generation} '
            f'| score {score}</text>',
            f'<text class="node-meta" x="{x + 12}" y="{y + 60}">parent {parent}</text>',
        ])

    parts.append("</svg>")
    return "\n".join(parts)


def render_archive_lineage_html(agents: Iterable[ArchivedAgent]) -> str:
    """Render archived agents as a standalone HTML lineage report."""
    sorted_agents = _sorted_agents(agents)
    svg = render_archive_lineage_svg(sorted_agents)
    rows = []
    for agent in sorted_agents:
        rows.append(
            "<tr>"
            f"<td>{escape(agent.agent_id)}</td>"
            f"<td>{escape(agent.parent_id or '')}</td>"
            f"<td>{agent.generation}</td>"
            f"<td>{escape(_score_label(agent.average_score))}</td>"
            f"<td>{'yes' if agent.is_valid else 'no'}</td>"
            f"<td>{escape(agent.created_at)}</td>"
            "</tr>"
        )

    table_body = "\n".join(rows) or '<tr><td colspan="6">No archived agents yet</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>DGM Archive Lineage</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 24px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }}
    th {{ background: #f8fafc; }}
  </style>
</head>
<body>
  <h1>DGM Archive Lineage</h1>
  {svg}
  <table>
    <thead>
      <tr>
        <th>Agent</th>
        <th>Parent</th>
        <th>Generation</th>
        <th>Average score</th>
        <th>Valid</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody>
      {table_body}
    </tbody>
  </table>
</body>
</html>
"""
