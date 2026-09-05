"""Shared loaders and chart helpers for the Term 4 artefact builders."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DOCS = Path(__file__).resolve().parents[1]
RESULTS = DOCS / "results"
FIGS = RESULTS / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

INK = "#14181d"
MUTED = "#5b6472"
SIGNAL = "#0f9e8e"
WARN = "#a67a00"
INFO = "#4a6690"
CRIT = "#c8291b"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def pct(x, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def num(x, d: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{d}f}"


def style(ax, title: str | None = None):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#c9ccc7")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_color(MUTED)
    ax.grid(axis="y", color="#e6e9e3", linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="600", pad=10)


def fig_forecast(f: dict) -> Path:
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=160)
    hist = f["history"][-72:]
    fc = f["forecast"]
    x_h = list(range(len(hist)))
    x_f = list(range(len(hist), len(hist) + len(fc)))
    ax.fill_between(x_h, [h["value"] for h in hist], color=MUTED, alpha=0.15, linewidth=0)
    ax.plot(x_h, [h["value"] for h in hist], color=MUTED, linewidth=1.2, label="Last 3 days")
    ax.plot(x_f, [p["value"] for p in fc], color=SIGNAL, linewidth=2, label="GBR forecast")
    ax.plot(x_f, [p["baseline"] if p["baseline"] is not None else float("nan") for p in fc], color=INFO, linewidth=1.2, linestyle="--", label="Seasonal naive")
    ax.axvline(len(hist) - 0.5, color=MUTED, linewidth=0.8, linestyle=":")
    ax.set_ylabel("customers / hour")
    ax.set_xticks(list(range(0, len(hist) + len(fc), 12)))
    ax.set_xticklabels([(hist + fc)[i]["ts"][11:16] for i in range(0, len(hist) + len(fc), 12)], rotation=0)
    style(ax, f"Footfall forecast: MAE {f['mae']} vs seasonal naive {f['mae_naive']} ({f['improvement_pct']}% better)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    p = FIGS / "forecast.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_queue_model(k: dict) -> Path:
    slots = k["queue_model"][-24:]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=160)
    x = list(range(len(slots)))
    ax.bar(x, [s["rho"] for s in slots], color=SIGNAL, alpha=0.2, width=0.8, label="ρ utilisation")
    ax2 = ax.twinx()
    ax2.plot(x, [s["wq_model_min"] if s["wq_model_min"] is not None else float("nan") for s in slots], color=SIGNAL, linewidth=2, label="W_q model (min)")
    obs = [s["wq_observed_min"] if s["wq_observed_min"] is not None else float("nan") for s in slots]
    ax2.plot(x, obs, color=WARN, linewidth=1.4, linestyle="--", marker="o", markersize=3, label="W_q observed (min)")
    ax.axhline(0.85, color=CRIT, linewidth=0.8, linestyle=":")
    ax.set_ylim(0, max(1.05, max(s["rho"] for s in slots) * 1.1))
    ax.set_xticks(x[::4])
    ax.set_xticklabels([s["slot_start"][11:16] for s in slots][::4])
    ax.set_ylabel("ρ")
    ax2.set_ylabel("minutes", color=MUTED)
    ax2.spines[["top"]].set_visible(False)
    ax2.tick_params(colors=MUTED, labelsize=9)
    style(ax, "Queue model vs observed, last 24 slots (μ estimated from video)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper left")
    p = FIGS / "queue_model.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_workforce(w: dict) -> Path:
    fig, ax = plt.subplots(figsize=(8, 3.0), dpi=160)
    x = list(range(len(w["tills"])))
    ax.bar(x, w["tills"], color=SIGNAL, width=0.85, label="planned tills")
    ax.axhline(w["observed_tills"], color=MUTED, linewidth=1, linestyle="--", label=f"today: {w['observed_tills']} tills")
    ax.set_xticks(x[::8])
    ax.set_xticklabels([s[11:16] for s in w["slots"]][::8])
    ax.set_ylabel("tills")
    style(ax, f"Staffing plan (ρ ≤ 0.85): {w['staff_hours']} staff-hours vs {w['baseline_staff_hours']} flat, saving {w['savings_hours']} h")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    p = FIGS / "workforce.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def fig_latency(e: dict) -> Path:
    d = e["detectors"]
    names = [n for n in ("yolo", "rtdetr") if n in d and "latency_ms_p50" in d[n]]
    fig, ax = plt.subplots(figsize=(6, 2.6), dpi=160)
    vals = [d[n]["latency_ms_p50"] for n in names]
    ax.barh([{"yolo": "YOLO26n (AGPL)", "rtdetr": "RT-DETR-L"}[n] for n in names], vals, color=[SIGNAL, INFO][: len(names)])
    for i, v in enumerate(vals):
        ax.text(v + 2, i, f"{v} ms · {d[names[i]]['fps_detect_only']} fps", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, max(vals) * 1.6)
    ax.set_xlabel("median latency per frame (ms), Apple M4 Pro, MPS")
    style(ax, f"Detector adapter: same pipeline, two backends · end-to-end {e['pipeline']['fps_end_to_end']} fps")
    p = FIGS / "latency.png"
    fig.tight_layout()
    fig.savefig(p)
    plt.close(fig)
    return p


def all_figures() -> dict[str, Path]:
    return {
        "forecast": fig_forecast(load("forecast_retail.json")),
        "queue": fig_queue_model(load("kpis_retail.json")),
        "workforce": fig_workforce(load("workforce_retail.json")),
        "latency": fig_latency(load("edge_eval.json")),
    }
