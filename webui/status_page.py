"""Generate a read-only local DGM status page."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from archive.agent_archive import ArchivedAgent
from archive.lineage_visualizer import render_archive_lineage_svg


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ArtifactStatus:
    """Status for an artifact surfaced by the local WebUI."""

    label: str
    path: str
    exists: bool
    detail: str = ""


@dataclass(frozen=True)
class ScoreMovementStatus:
    """Checked-in no-network score movement evidence."""

    exists: bool
    benchmark: str = ""
    baseline_score: float | None = None
    candidate_score: float | None = None
    delta: float | None = None
    detail: str = ""


@dataclass(frozen=True)
class WebUIStatusModel:
    """Data needed to render the local status page."""

    project_root: Path
    archive_dir: Path
    generated_at: str
    agents: list[ArchivedAgent]
    archive_warning: str | None
    artifacts: list[ArtifactStatus]
    score_movement: ScoreMovementStatus
    live_runs: list[str]
    commands: list[str]


def _relative_label(path: Path, project_root: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_archived_agents(archive_dir: Path) -> tuple[list[ArchivedAgent], str | None]:
    """Load archive metadata without creating or modifying archive directories."""
    metadata_path = archive_dir / "archive_metadata.json"
    if not metadata_path.exists():
        return [], f"No archive metadata found at {metadata_path}"

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        agents = [
            ArchivedAgent.from_dict(agent_data)
            for agent_data in data.get("agents", {}).values()
        ]
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return [], f"Could not load archive metadata: {exc}"

    return agents, None


def _artifact(path: Path, project_root: Path, label: str, detail: str = "") -> ArtifactStatus:
    return ArtifactStatus(
        label=label,
        path=_relative_label(path, project_root),
        exists=path.is_file(),
        detail=detail,
    )


def _load_score_movement(project_root: Path) -> ScoreMovementStatus:
    score_path = project_root / "docs" / "demo" / "humaneval_score_movement.json"
    if not score_path.exists():
        return ScoreMovementStatus(False, detail="Missing checked-in score movement JSON")

    try:
        data = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ScoreMovementStatus(False, detail=f"Could not read score movement JSON: {exc}")

    baseline = data.get("baseline", {}).get("score")
    candidate = data.get("candidate", {}).get("score")
    delta = data.get("delta")
    return ScoreMovementStatus(
        exists=True,
        benchmark=str(data.get("benchmark", "")),
        baseline_score=baseline if isinstance(baseline, (int, float)) else None,
        candidate_score=candidate if isinstance(candidate, (int, float)) else None,
        delta=delta if isinstance(delta, (int, float)) else None,
        detail=_relative_label(score_path, project_root),
    )


def _live_run_labels(project_root: Path) -> list[str]:
    live_runs_dir = project_root / "docs" / "live-runs"
    if not live_runs_dir.exists():
        return []
    return [
        _relative_label(path, project_root)
        for path in sorted(live_runs_dir.iterdir())
        if path.is_dir()
    ]


def build_status_model(
    project_root: Path = PROJECT_ROOT,
    archive_dir: Path | None = None,
) -> WebUIStatusModel:
    """Collect read-only status for the local WebUI page."""
    project_root = project_root.resolve()
    archive_dir = (archive_dir or project_root / "archive" / "agents").resolve()
    agents, archive_warning = _load_archived_agents(archive_dir)
    live_runs = _live_run_labels(project_root)

    artifacts = [
        _artifact(project_root / "README.md", project_root, "README"),
        _artifact(project_root / "config" / "dgm_config.yaml", project_root, "Default DGM config"),
        _artifact(project_root / "scripts" / "verify_demo_path.py", project_root, "No-network verifier"),
        _artifact(project_root / "scripts" / "run_dgm_in_sandbox.py", project_root, "Sandboxed DGM runner"),
        _artifact(project_root / "docs" / "demo" / "humaneval_score_movement.json", project_root, "Score movement evidence"),
        _artifact(project_root / "docs" / "archive-lineage-example.svg", project_root, "Archive lineage example"),
        _artifact(
            project_root / "docs" / "live-runs" / "2026-06-12-proof" / "README.md",
            project_root,
            "Live-run proof notes",
        ),
        _artifact(
            project_root / "docs" / "live-runs" / "2026-06-12-proof" / "transcript.txt",
            project_root,
            "Live-run proof transcript",
        ),
    ]

    commands = [
        "python scripts/verify_demo_path.py",
        "python scripts/generate_webui_status.py --output docs/webui-status.html",
        "python scripts/run_dgm_in_sandbox.py --help",
    ]

    return WebUIStatusModel(
        project_root=project_root,
        archive_dir=archive_dir,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        agents=agents,
        archive_warning=archive_warning,
        artifacts=artifacts,
        score_movement=_load_score_movement(project_root),
        live_runs=live_runs,
        commands=commands,
    )


def _format_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    return f"{score:.3f}"


def _archive_stats(model: WebUIStatusModel) -> dict[str, str]:
    valid_agents = [agent for agent in model.agents if agent.is_valid]
    scores = [agent.average_score for agent in valid_agents]
    return {
        "Total agents": str(len(model.agents)),
        "Valid agents": str(len(valid_agents)),
        "Best score": _format_score(max(scores) if scores else None),
        "Max generation": str(max((agent.generation for agent in model.agents), default=0)),
    }


def _render_metric_cards(model: WebUIStatusModel) -> str:
    stats = _archive_stats(model)
    cards = []
    for label, value in stats.items():
        cards.append(
            '<section class="metric">'
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</section>"
        )
    return "\n".join(cards)


def _render_artifacts(model: WebUIStatusModel) -> str:
    rows = []
    for artifact in model.artifacts:
        status = "present" if artifact.exists else "missing"
        rows.append(
            "<tr>"
            f"<td>{escape(artifact.label)}</td>"
            f"<td><code>{escape(artifact.path)}</code></td>"
            f'<td><span class="status {status}">{status}</span></td>'
            f"<td>{escape(artifact.detail)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_agent_rows(model: WebUIStatusModel) -> str:
    sorted_agents = sorted(
        model.agents,
        key=lambda agent: (agent.generation, agent.created_at, agent.agent_id),
    )
    if not sorted_agents:
        return '<tr><td colspan="6">No archived agents found.</td></tr>'

    rows = []
    for agent in sorted_agents:
        rows.append(
            "<tr>"
            f"<td><code>{escape(agent.agent_id)}</code></td>"
            f"<td><code>{escape(agent.parent_id or 'root')}</code></td>"
            f"<td>{agent.generation}</td>"
            f"<td>{escape(_format_score(agent.average_score))}</td>"
            f'<td><span class="status {"present" if agent.is_valid else "missing"}">'
            f"{'valid' if agent.is_valid else 'invalid'}</span></td>"
            f"<td>{escape(agent.created_at)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_live_runs(model: WebUIStatusModel) -> str:
    if not model.live_runs:
        return "<li>No live-run proof directories found.</li>"
    return "\n".join(f"<li><code>{escape(label)}</code></li>" for label in model.live_runs)


def _render_commands(model: WebUIStatusModel) -> str:
    return "\n".join(f"<li><code>{escape(command)}</code></li>" for command in model.commands)


def render_status_page(model: WebUIStatusModel) -> str:
    """Render a standalone HTML status page."""
    lineage_svg = render_archive_lineage_svg(model.agents)
    score = model.score_movement
    archive_warning = (
        f'<p class="notice">{escape(model.archive_warning)}</p>'
        if model.archive_warning
        else ""
    )
    score_detail = (
        f"{escape(score.benchmark)}: {_format_score(score.baseline_score)} to "
        f"{_format_score(score.candidate_score)} ({_format_score(score.delta)} delta)"
        if score.exists
        else escape(score.detail)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DGM Local Status</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #5f6b7a;
      --line: #d8dee8;
      --ok-bg: #e7f7ed;
      --ok: #146c43;
      --warn-bg: #fff3d8;
      --warn: #8a5a00;
      --accent: #1f6feb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      margin-bottom: 24px;
    }}
    h1, h2 {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 34px; }}
    h2 {{ font-size: 20px; margin-bottom: 14px; }}
    p {{ margin: 6px 0 0; color: var(--muted); }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      overflow-wrap: anywhere;
    }}
    .section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .status {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 600;
    }}
    .present {{
      background: var(--ok-bg);
      color: var(--ok);
    }}
    .missing {{
      background: var(--warn-bg);
      color: var(--warn);
    }}
    .notice {{
      color: var(--warn);
      background: var(--warn-bg);
      border-radius: 6px;
      padding: 10px 12px;
      margin: 12px 0 0;
    }}
    .lineage {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .lineage svg {{
      max-width: 100%;
      height: auto;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 18px;
    }}
    ul {{
      margin: 10px 0 0;
      padding-left: 20px;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 18px; }}
      header, .two-col {{ display: block; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>DGM Local Status</h1>
        <p>Read-only view of archive, demo evidence, and safe local commands.</p>
      </div>
      <p><code>{escape(_relative_label(model.project_root, model.project_root)) or "."}</code><br>
      generated {escape(model.generated_at)}</p>
    </header>

    <div class="metrics">
      {_render_metric_cards(model)}
    </div>

    <section class="section">
      <h2>Score Movement Evidence</h2>
      <p>{score_detail}</p>
    </section>

    <section class="section">
      <h2>Archive Lineage</h2>
      {archive_warning}
      <div class="lineage">{lineage_svg}</div>
    </section>

    <section class="section">
      <h2>Archived Agents</h2>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Parent</th>
            <th>Generation</th>
            <th>Score</th>
            <th>State</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {_render_agent_rows(model)}
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>Artifacts</h2>
      <table>
        <thead>
          <tr>
            <th>Artifact</th>
            <th>Path</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {_render_artifacts(model)}
        </tbody>
      </table>
    </section>

    <div class="two-col">
      <section class="section">
        <h2>Live Runs</h2>
        <ul>
          {_render_live_runs(model)}
        </ul>
      </section>
      <section class="section">
        <h2>Exact Commands</h2>
        <ul>
          {_render_commands(model)}
        </ul>
      </section>
    </div>
  </main>
</body>
</html>
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Repository root to inspect.",
    )
    parser.add_argument(
        "--archive-dir",
        help="Archive directory containing archive_metadata.json. Defaults to archive/agents.",
    )
    parser.add_argument(
        "--output",
        default="docs/webui-status.html",
        help="HTML output path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    archive_dir = Path(args.archive_dir) if args.archive_dir else None
    if archive_dir is not None and not archive_dir.is_absolute():
        archive_dir = project_root / archive_dir
    model = build_status_model(project_root=project_root, archive_dir=archive_dir)
    html = render_status_page(model)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote local WebUI status page to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
