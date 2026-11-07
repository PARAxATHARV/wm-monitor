"""Focused checks for figure eligibility, exclusions, and sensitivity counts."""

import sys
from pathlib import Path
import tempfile
import unittest
import sqlite3

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import figure_energy_water as figure


class FigureEligibilityTests(unittest.TestCase):
    def setUp(self):
        def model(identifier, energy=50, water=47, capacity=8, installation="Free-standing", energy_class="A"):
            return {"eprel_id": identifier, figure.ENERGY: energy, figure.WATER: water,
                    figure.CAPACITY: capacity, "installation_type": installation,
                    "energy_class": energy_class}
        self.models = pd.DataFrame([
            model("0001"), model("0002", energy=47), model("0003", energy=500),
            model("0004", water=None), model("0005", installation="Built-in"),
            model("0006", capacity=9), model("0007", energy_class="H"),
        ])
        self.issues = pd.DataFrame([
            {"eprel_id": "0001", "field": "noise_db_spin", "issue_type": "out_of_range"},
            {"eprel_id": "0002", "field": figure.ENERGY, "issue_type": "energy_inconsistent"},
            {"eprel_id": "0003", "field": figure.ENERGY, "issue_type": "out_of_range"},
            {"eprel_id": "0004", "field": figure.WATER, "issue_type": "malformed"},
        ])

    def test_only_relevant_issues_exclude_records(self):
        original = self.models.copy(deep=True)
        eligible = figure.eligible_models(self.models, self.issues)
        self.assertEqual(set(eligible["eprel_id"]), {"0001", "0002", "0005", "0006"})
        self.assertTrue(eligible.set_index("eprel_id").loc["0002", "energy_warning"])
        pd.testing.assert_frame_equal(self.models, original)

    def test_scope_and_sensitivity_have_separate_denominators(self):
        eligible = figure.eligible_models(self.models, self.issues)
        plotted, summary = figure.scope_summary(self.models, eligible, 8, "Free-standing")
        self.assertEqual(summary["scope_models_before_plot_checks"], 5)
        self.assertEqual(summary["excluded_by_plot_checks"], 3)
        self.assertEqual(summary["base_eligible_models"], 2)
        self.assertEqual(summary["energy_warning_models_in_base"], 1)
        self.assertEqual(list(plotted["eprel_id"]), ["0001"])
        self.assertEqual(summary["including_energy_warnings"]["median_energy_kwh_per_100_cycles"], 48.5)
        self.assertEqual(summary["excluding_energy_warnings"]["median_energy_kwh_per_100_cycles"], 50)

    def test_capacity_table_preserves_exact_capacity_and_type(self):
        table = figure.capacity_medians(figure.eligible_models(self.models, self.issues))
        self.assertEqual(len(table), 6)
        self.assertEqual(set(table[figure.CAPACITY]), {8, 9})
        self.assertEqual(set(table["installation_type"]), {"Free-standing", "Built-in"})

    def test_empty_plot_fails_clearly(self):
        eligible = figure.eligible_models(self.models, self.issues)
        with self.assertRaisesRegex(ValueError, "No eligible"):
            figure.scope_summary(self.models, eligible, 20, "Free-standing")

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                figure.read_data(missing)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
