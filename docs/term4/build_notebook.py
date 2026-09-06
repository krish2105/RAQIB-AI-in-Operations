"""Build docs/term4_raqib.ipynb: forecasting, M/M/c validation, workforce MILP, with plots. Executed on build.

  cd cloud && uv run --no-sync python ../docs/term4/build_notebook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

DOCS = Path(__file__).resolve().parents[1]
OUT = DOCS / "term4_raqib.ipynb"
CLOUD = DOCS.parents[0] / "cloud"


def main() -> None:
    nb = nbf.v4.new_notebook()
    cells = []
    md = lambda s: cells.append(nbf.v4.new_markdown_cell(s))  # noqa: E731
    code = lambda s: cells.append(nbf.v4.new_code_cell(s))  # noqa: E731

    md("# RAQIB — Term 4 operations analytics notebook\n\nAI 218 *AI in Operations*. This notebook reproduces the three analytical results behind the dashboard from the same code the API runs (`cloud/raqib_api`): the M/M/c queue model checked against textbook values, the footfall forecast against a seasonal-naive baseline, and the staffing integer program. Data: the labelled simulator (`payload.simulated = true`) plus the exported results in `docs/results/`.")
    code(f"""import sys, json, math\nsys.path.insert(0, {str(CLOUD)!r})\nfrom pathlib import Path\nimport numpy as np, pandas as pd\nimport matplotlib.pyplot as plt\nfrom datetime import datetime, timezone\nfrom raqib_api.ops_theory import mmc, slot_rates, service_level, tills_for_target_rho\nfrom raqib_api.forecast import hourly_counts, fit_predict, seasonal_naive\nfrom raqib_api.workforce import staffing_plan\nfrom raqib_api.simulate import generate\nRESULTS = Path({str(DOCS / 'results')!r})\nplt.rcParams.update({{'figure.dpi': 110, 'axes.spines.top': False, 'axes.spines.right': False}})\nprint('modules loaded')""")

    md("## 1. Queueing theory: M/M/c validation\n\nErlang-C closed form. Check against the textbook M/M/2 case (λ = 4/h, μ = 3/h): ρ = 0.667, P₀ = 0.2, L_q ≈ 1.067, W_q ≈ 0.267 h. Then sweep the number of tills for the demo store's peak arrival rate.")
    code("""r = mmc(4, 3, 2)\nprint(f"rho={r.rho:.3f} P0={r.p0:.3f} Lq={r.lq:.3f} Wq={r.wq*60:.1f} min")\nassert abs(r.lq - 1.0667) < 1e-3\nk = json.load(open(RESULTS / 'kpis_retail.json'))\nw = json.load(open(RESULTS / 'workforce_retail.json'))\nlam_peak = max(w['lam']); mu = w['mu']\nrows = []\nfor c in range(1, 7):\n    m = mmc(lam_peak, mu, c)\n    rows.append({'tills': c, 'rho': round(m.rho, 3), 'Wq_min': None if not m.stable else round(m.wq*60, 2), 'P(wait)': None if not m.stable else round(1 - m.p0 * sum((lam_peak/mu)**n/math.factorial(n) for n in range(c)), 3)})\npd.DataFrame(rows)""")
    md("At the peak, adding one till when ρ is near 0.9 cuts the expected wait by an order of magnitude; this is the lever the agent's `propose_open_till` pulls, and why the policy requires ρ > 0.85 before it may be proposed.")

    md("## 2. Model vs observed\n\nThe dashboard's 'Queue model vs observed' card. Observed W_q uses Little's law on the measured queue length. μ is estimated from checkout dwell on video and labelled as such.")
    code("""qm = pd.DataFrame(k['queue_model'])\nfig, ax = plt.subplots(figsize=(10, 3.5))\nax.bar(range(len(qm)), qm['rho'], alpha=0.2, label='ρ')\nax2 = ax.twinx()\nax2.plot(qm['wq_model_min'], label='W_q model (min)')\nax2.plot(qm['wq_observed_min'], 'o--', label='W_q observed (min)')\nax.set_xticks(range(0, len(qm), 4)); ax.set_xticklabels([s[11:16] for s in qm['slot_start']][::4])\nax.axhline(0.85, ls=':', c='r'); ax.set_ylabel('ρ'); ax2.set_ylabel('minutes')\nfig.legend(loc='upper left', ncol=3, frameon=False); plt.title('Queue model vs observed, last 24 slots', loc='left'); plt.show()\nprint('service level (queue <= 3):', k['service_level'], ' peak rho:', k['peak_rho'])""")

    md("## 3. Forecasting vs seasonal naive\n\nRegenerate 21 days from the labelled simulator (deterministic seed), fit the same GradientBoosting model the API uses, and compare with same-hour-last-week.")
    code("""from types import SimpleNamespace\nend = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)\nrows = generate('raqib_demo_store', 'retail', days=21, seed=7, end=end, tills=3)\nevents = [SimpleNamespace(ts=datetime.fromisoformat(r['ts']), kind=r['kind'], payload=r['payload']) for r in rows]\nseries = hourly_counts(events, 'footfall_tick', end=end)\nres = fit_predict(series, horizon=24)\nprint(f"sufficient={res.sufficient} MAE={res.mae} MAE_naive={res.mae_naive} improvement={res.improvement_pct}% MAPE={res.mape}%")\nhist = series.iloc[-72:]\nfig, ax = plt.subplots(figsize=(10, 3.5))\nax.plot(hist.index, hist.values, c='gray', label='last 3 days')\nfi = pd.to_datetime([f['ts'] for f in res.forecast])\nax.plot(fi, [f['value'] for f in res.forecast], label='GBR forecast', lw=2)\nax.plot(fi, [f['baseline'] if f['baseline'] is not None else np.nan for f in res.forecast], '--', label='seasonal naive')\nax.legend(frameon=False); ax.set_ylabel('customers / hour'); plt.title('Footfall: next 24 h', loc='left'); plt.show()""")
    md("The simulator is generated from smooth daily and weekly curves plus Poisson noise, which is close to what seasonal naive assumes, so the margin here is a floor. The pilot target (≥ 20% better) is set for real data with promotions, weather, and school holidays.")

    md("## 4. Workforce optimisation (MILP)\n\nMinimise Σ tills subject to ρ ≤ 0.85 per 15-minute slot, integer tills. Toy check first (hand solution [1, 2, 4]), then the demo day.")
    code("""toy = staffing_plan([2, 5, 8], mu=3, max_rho=0.85, max_tills=6, slot_minutes=60)\nprint('toy tills', toy.tills, 'staff-hours', toy.staff_hours)\nassert toy.tills == [1, 2, 4]\nplan = staffing_plan(w['lam'], w['mu'], max_rho=0.85, max_tills=max(3, tills_for_target_rho(max(w['lam']), w['mu'])), baseline_tills=3)\nprint(f"staff-hours {plan.staff_hours} vs baseline {plan.baseline_staff_hours} (saves {plan.savings_hours} h); peak tills {max(plan.tills)}")\nfig, ax = plt.subplots(figsize=(10, 3))\nax.bar(range(len(plan.tills)), plan.tills, label='planned tills')\nax.axhline(3, ls='--', c='gray', label='today: 3 tills')\nax.set_xticks(range(0, len(w['slots']), 8)); ax.set_xticklabels([s[11:16] for s in w['slots']][::8])\nax.legend(frameon=False); plt.title('Staffing plan, ρ ≤ 0.85', loc='left'); plt.show()""")

    md("## 5. Before / after\n\nReplay the day with the agent's open-till proposals applied (tills = max(3, plan)). Closing tills off-peak is the staff-hour saving above and is not counted as a wait effect.")
    code("""def total_wait(lams, tills, mu):\n    tot = 0.0\n    for lam, c in zip(lams, tills):\n        m = mmc(lam, mu, c)\n        tot += (m.wq * 60 if m.stable else 30) * lam / 4  # customer-minutes per 15-min slot\n    return round(tot, 1)\nbase = total_wait(w['lam'], [3]*len(w['lam']), w['mu'])\nafter = total_wait(w['lam'], [max(3, c) for c in plan.tills], w['mu'])\nprint(f"customer-minutes waited: baseline {base}, with proposals {after}, reduction {0 if base == 0 else round((1-after/base)*100,1)}%")""")

    md("## 7. v2: Ask quality and the security scorecard\n\nThe v2 evals are code (`cloud/evals/ask/run.py`, `cloud/security/run.py`) and write JSON; this cell reads the committed results so the notebook shows the same numbers as the README, the report and the Security tab.")
    code("""a = json.load(open(RESULTS / 'ask_eval.json'))['summary']\nse = json.load(open(RESULTS / 'security_eval.json'))\nprint(f"Ask: {a['cases']} cases, recall@5 {a['recall_at_5']}, faithfulness {a['faithfulness']}, citation coverage {a['citation_coverage']}, language match {a['language_match']}, hallucinations {a['hallucinations']}")\nprint(f"Security: {se['passed']}/{se['total']} ASI attacks defended on {se['date'][:10]}")\npd.DataFrame([{'lang': l, **v} for l, v in a['by_lang'].items()])""")
    code("""pd.DataFrame([{'asi': r['asi'], 'risk': r['risk'], 'test': r['test'], 'passed': r['passed']} for r in se['results']])""")

    md("## 8. Where the numbers go\n\n`scripts/export_results.py` writes these figures to `docs/results/`; `docs/term4/build_report.py` and `build_deck.py` read them. No number in the report or deck is typed by hand.")

    nb["cells"] = cells
    nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    # Execute with the cloud venv's kernel (registered by `python -m ipykernel install --user --name raqib`),
    # but save the notebook with the generic python3 kernelspec so any grader's Jupyter can open it.
    client = NotebookClient(nb, timeout=600, kernel_name="raqib", resources={"metadata": {"path": str(DOCS)}})
    client.execute()
    nbf.write(nb, OUT)
    print("wrote and executed", OUT)


if __name__ == "__main__":
    main()
