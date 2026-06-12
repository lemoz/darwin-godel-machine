#!/usr/bin/env python3
"""Generate an SVG or HTML archive lineage report."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from archive import AgentArchive
from archive.lineage_visualizer import (
    render_archive_lineage_html,
    render_archive_lineage_svg,
)


def _infer_format(output_path: Path) -> str:
    suffix = output_path.suffix.lower()
    if suffix == ".svg":
        return "svg"
    if suffix in {".html", ".htm"}:
        return "html"
    raise ValueError("Cannot infer format: output must end in .svg, .html, or .htm")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-dir",
        default="archive/agents",
        help="Directory containing archive_metadata.json",
    )
    parser.add_argument(
        "--output",
        default="docs/archive-lineage.html",
        help="Output path ending in .svg or .html",
    )
    parser.add_argument(
        "--format",
        choices=["svg", "html"],
        help="Output format. Defaults to the output file extension.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_format = args.format or _infer_format(output_path)
    archive = AgentArchive(archive_dir=args.archive_dir)
    agents = archive.get_all_agents()

    if output_format == "svg":
        rendered = render_archive_lineage_svg(agents)
    else:
        rendered = render_archive_lineage_html(agents)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_format} lineage report to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
