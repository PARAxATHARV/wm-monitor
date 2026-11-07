"""Step 5: comparable energy/water figure and an energy-warning sensitivity check.

Run from the project root: python src/figure_energy_water.py
The database is opened read-only. Only derived figures and summaries are written.
"""

import argparse
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import matplotlib
matplotlib.use("Agg")
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as c


ROOT = Path(__file__).resolve().parents[1]
ENERGY = "energy_kwh_per_100_cycles_eco4060"
WATER = "water_l_per_cycle_eco4060"
CAPACITY = "rated_capacity_kg"
CLASS_ORDER = "ABCDEFG"
FIGURE_FIELDS = set(c.FIGURE_FIELDS) | {"installation_type"}
COLOURS = dict(zip(CLASS_ORDER, [
    "#21854b", "#68a349", "#a3ad36", "#c6a52b",
    "#d98531", "#cd5738", "#b6383c",
]))


def read_data(db_path):
    """A missing database must fail rather than create an empty SQLite file."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        models = pd.read_sql_query("SELECT * FROM products_clean", con)
        issues = pd.read_sql_query("SELECT * FROM validation_issues", con)
    if models.empty or set(models["snapshot_id"]) != {c.SNAPSHOT_ID}:
        raise ValueError("Expected the configured, nonempty snapshot; check config.py.")
    if models["eprel_id"].isna().any() or not models["eprel_id"].is_unique:
        raise ValueError("Model IDs must be populated and unique in this snapshot.")
    if not set(issues["eprel_id"]).issubset(set(models["eprel_id"])):
        raise ValueError("Validation issues refer to models outside this snapshot.")
    return models, issues


def eligible_models(models, issues):
    """Exclude plotting-field problems; keep unrelated noise/duration warnings.

    Energy-consistency warnings are held separately so both scenarios can be
    compared. The original model and issue tables are never modified.
    """
    relevant = issues["field"].isin(FIGURE_FIELDS)
    blocking = issues[relevant & issues["issue_type"].ne("energy_inconsistent")]
    eligible = ~models["eprel_id"].isin(blocking["eprel_id"])
    for field in (CAPACITY, ENERGY, WATER):
        values = models[field]
        lo, hi = c.PLAUSIBLE[field]
        eligible &= values.notna() & np.isfinite(values) & values.between(lo, hi)
    eligible &= models["energy_class"].isin(list(CLASS_ORDER))
    eligible &= models["installation_type"].isin(["Free-standing", "Built-in"])
    eligible &= models["eprel_id"].str.strip().ne("")

    result = models.loc[eligible].copy()
    warnings = issues.loc[
        issues["issue_type"].eq("energy_inconsistent") & issues["field"].eq(ENERGY),
        "eprel_id",
    ]
    result["energy_warning"] = result["eprel_id"].isin(warnings)
    return result


def median_values(frame):
    if frame.empty:
        return {"models": 0, "median_energy_kwh_per_100_cycles": None,
                "median_water_l_per_cycle": None}
    return {"models": len(frame),
            "median_energy_kwh_per_100_cycles": float(frame[ENERGY].median()),
            "median_water_l_per_cycle": float(frame[WATER].median())}


def capacity_medians(eligible):
    """Exact capacity and installation type; two explicitly named scenarios."""
    records = []
    for (capacity, installation), group in eligible.groupby([CAPACITY, "installation_type"]):
        for scenario, sample in [
            ("including_energy_warnings", group),
            ("excluding_energy_warnings", group.loc[~group["energy_warning"]]),
        ]:
            records.append({CAPACITY: capacity, "installation_type": installation,
                            "scenario": scenario, **median_values(sample)})
    return pd.DataFrame(records)


def scope_summary(models, eligible, capacity, installation):
    scope = models.loc[models[CAPACITY].eq(capacity)
                       & models["installation_type"].eq(installation)]
    base = eligible.loc[eligible[CAPACITY].eq(capacity)
                        & eligible["installation_type"].eq(installation)]
    plotted = base.loc[~base["energy_warning"]]
    if plotted.empty:
        raise ValueError("No eligible unflagged models for this capacity/type.")
    summary = {
        "snapshot_id": c.SNAPSHOT_ID,
        "snapshot_date": date.fromisoformat(c.SNAPSHOT_ID.rsplit("_", 1)[-1]).isoformat(),
        "source_url": "https://eprel.ec.europa.eu/screen/product/washingmachines2019",
        "programme": "eco 40-60",
        "capacity_kg": capacity,
        "installation_type": installation,
        "all_snapshot_models": len(models),
        "scope_models_before_plot_checks": len(scope),
        "excluded_by_plot_checks": len(scope) - len(base),
        "base_eligible_models": len(base),
        "energy_warning_models_in_base": int(base["energy_warning"].sum()),
        "plotted_models": len(plotted),
        "including_energy_warnings": median_values(base),
        "excluding_energy_warnings": median_values(plotted),
        "plot_counts_by_energy_class": {
            k: int(plotted["energy_class"].eq(k).sum()) for k in CLASS_ORDER},
        "plot_ranges": {k: list(c.PLAUSIBLE[k]) for k in (CAPACITY, ENERGY, WATER)},
        "energy_warning_rule": "Stored energy_inconsistent validation issues; >1 kWh/100 cycles",
        "interpretation": "Unweighted registered models, not unit sales or causal policy impact.",
    }
    return plotted, summary


def draw_figure(plotted, summary, output_path):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(12.8, 7.2), facecolor="white")
    ax = fig.add_axes([0.08, 0.22, 0.63, 0.57])
    capacity = f"{summary['capacity_kg']:g}"
    fig.text(0.08, 0.94, f"Energy and water use across {capacity} kg washing machines",
             fontsize=21, weight="bold", color="#162638")
    fig.text(0.08, 0.88,
             f"{summary['installation_type']} | eco 40–60 | "
             f"{summary['plotted_models']:,} registered models plotted",
             fontsize=12, color="#52616e")

    legend_handles = []
    for energy_class in CLASS_ORDER:
        group = plotted.loc[plotted["energy_class"].eq(energy_class)]
        if group.empty:
            continue
        ax.scatter(group[ENERGY], group[WATER], s=27, alpha=0.35,
                   color=COLOURS[energy_class], edgecolors="white", linewidths=0.25)
        legend_handles.append(Line2D(
            [0], [0], marker="o", linestyle="", color=COLOURS[energy_class],
            markersize=7, label=f"{energy_class}   ({len(group):,} models)"))

    med = summary["excluding_energy_warnings"]
    ax.axvline(med["median_energy_kwh_per_100_cycles"], color="#6b7782", lw=1, ls="--", zorder=0)
    ax.axhline(med["median_water_l_per_cycle"], color="#6b7782", lw=1, ls="--", zorder=0)
    ax.set_xlabel("Energy consumption (kWh / 100 cycles)", labelpad=10)
    ax.set_ylabel("Water consumption (L / cycle)", labelpad=10)
    ax.set_axisbelow(True)
    ax.grid(alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(handles=legend_handles, title="Energy class", frameon=False,
              loc="upper left", bbox_to_anchor=(1.04, 1.02), borderaxespad=0)

    including = summary["including_energy_warnings"]
    sensitivity = (
        "Median sensitivity check\n"
        "Including / excluding warnings\n\n"
        f"Energy: {including['median_energy_kwh_per_100_cycles']:g} / "
        f"{med['median_energy_kwh_per_100_cycles']:g} kWh/100 cycles\n"
        f"Water:  {including['median_water_l_per_cycle']:g} / "
        f"{med['median_water_l_per_cycle']:g} L/cycle"
    )
    fig.text(0.76, 0.42, sensitivity, va="top", fontsize=10.5, linespacing=1.6,
             color="#263746", bbox={"boxstyle": "round,pad=0.8", "fc": "#f1f4f6", "ec": "none"})
    fig.text(0.08, 0.115,
             f"Selection: {summary['scope_models_before_plot_checks']:,} models in scope; "
             f"{summary['excluded_by_plot_checks']:,} fail plotting checks; "
             f"{summary['energy_warning_models_in_base']:,} further energy warnings excluded.",
             fontsize=9.5, color="#52616e")
    fig.text(0.08, 0.072,
             "Each point is a registered model; points can overlap. Dashed lines mark the plotted medians.",
             fontsize=9.5, color="#52616e")
    source_date = date.fromisoformat(summary["snapshot_date"]).strftime("%d %b %Y").lstrip("0")
    fig.text(0.08, 0.032,
             f"Source: European Commission, EPREL CSV snapshot, {source_date}. "
             "Supplier-declared data; unweighted model counts.",
             fontsize=9, color="#52616e")
    fig.savefig(output_path, dpi=200, facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / c.DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--capacity", type=float, default=8.0)
    parser.add_argument("--installation-type", choices=["Free-standing", "Built-in"], default="Free-standing")
    args = parser.parse_args()
    models, issues = read_data(args.db)
    eligible = eligible_models(models, issues)
    plotted, summary = scope_summary(models, eligible, args.capacity, args.installation_type)
    summary["input_database_sha256"] = hashlib.sha256(args.db.read_bytes()).hexdigest()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    image_path = args.output_dir / "figure_energy_water.png"
    draw_figure(plotted, summary, image_path)
    capacity_medians(eligible).to_csv(args.output_dir / "energy_water_medians.csv", index=False)
    (args.output_dir / "figure_energy_water_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(f"In scope: {summary['scope_models_before_plot_checks']:,}")
    print(f"Excluded by plotting checks: {summary['excluded_by_plot_checks']:,}")
    print(f"Base eligible: {summary['base_eligible_models']:,}")
    print(f"Energy-flagged in base: {summary['energy_warning_models_in_base']:,}")
    print(f"Plotted: {summary['plotted_models']:,}")
    for scenario in ("including_energy_warnings", "excluding_energy_warnings"):
        stat = summary[scenario]
        print(f"{scenario}: N={stat['models']:,}; median energy "
              f"{stat['median_energy_kwh_per_100_cycles']:g} kWh/100 cycles; "
              f"median water {stat['median_water_l_per_cycle']:g} L/cycle")
    print(f"Figure: {image_path}")


if __name__ == "__main__":
    main()
