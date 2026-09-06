"""raqib-edge CLI.

  raqib-edge run --site sites/retail_demo.yaml --preview
  raqib-edge run --site sites/greenlam_unit1.yaml --source webcam --api http://localhost:8000
  raqib-edge bench --site sites/retail_demo.yaml --frames 200
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .pipeline import REPO_ROOT, run_pipeline

app = typer.Typer(add_completion=False, help="RAQIB / MUSHRIF edge pipeline")
console = Console()


def _site_path(site: str | None) -> Path:
    s = site or os.environ.get("RAQIB_SITE", "edge/sites/retail_demo.yaml")
    p = Path(s)
    if not p.exists():
        p = REPO_ROOT / s
    if not p.exists():
        p = REPO_ROOT / "edge" / s
    if not p.exists():
        raise typer.BadParameter(f"site config not found: {s}")
    return p


@app.command()
def run(
    site: str = typer.Option(None, help="site YAML (default $RAQIB_SITE or sites/retail_demo.yaml)"),
    source: str = typer.Option(None, help="override camera source: webcam | file"),
    detector: str = typer.Option(os.environ.get("RAQIB_DETECTOR", "yolo"), help="yolo | rtdetr"),
    api: str = typer.Option(os.environ.get("RAQIB_API_URL") or None, help="cloud API base URL; omit for offline"),
    preview: bool = typer.Option(False, help="show OpenCV window"),
    max_frames: int = typer.Option(None, help="stop after N frames (tests/benchmarks)"),
    camera: list[str] = typer.Option(None, help="only these cameras"),
    stream: int = typer.Option(None, help="serve the blurred MJPEG stream on this port (e.g. 8554)"),
    stream_host: str = typer.Option("127.0.0.1", help="bind address for --stream; 0.0.0.0 for the LAN"),
    stream_token: str = typer.Option(os.environ.get("RAQIB_STREAM_TOKEN") or None, help="token required on stream requests"),
    detections: float = typer.Option(None, help="post boxes-only detections to the API every N seconds"),
    telemetry: bool = typer.Option(True, help="heartbeat every minute and drift samples every hour to the API"),
    box_id: str = typer.Option(None, help="edge box id in heartbeats (default: hostname)"),
    verbose: bool = typer.Option(True),
) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    stats = run_pipeline(
        _site_path(site),
        max_frames=max_frames,
        detector=detector,
        api=api,
        preview=preview,
        source_override=source,
        cameras=camera or None,
        stream_port=stream,
        stream_host=stream_host,
        stream_token=stream_token,
        detections_every_s=detections,
        telemetry=telemetry,
        box_id=box_id,
    )
    _print_stats(stats)


@app.command()
def bench(
    site: str = typer.Option(None),
    frames: int = typer.Option(200),
    detector: str = typer.Option("yolo"),
    out: str = typer.Option(None, help="write JSON stats here"),
) -> None:
    logging.basicConfig(level=logging.WARNING)
    stats = run_pipeline(_site_path(site), max_frames=frames, detector=detector, api=None)
    _print_stats(stats)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(stats.as_dict(), indent=2))
        console.print(f"wrote {out}")


def _print_stats(stats) -> None:
    t = Table(title="edge run", show_header=False)
    for k, v in stats.as_dict().items():
        t.add_row(k, json.dumps(v) if isinstance(v, dict) else f"{v:.1f}" if isinstance(v, float) else str(v))
    console.print(t)


if __name__ == "__main__":
    app()
