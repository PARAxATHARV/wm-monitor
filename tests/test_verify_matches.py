"""Focused checks for the verification logic in src/verify_matches.py (synthetic cases only).

Run from the project root:
    python -m unittest tests.test_verify_matches
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from verify_matches import classify, summarise  # noqa: E402

SNAPSHOT = {"100", "200", "300"}


class ClassifyExplicitId(unittest.TestCase):
    def test_correct(self):
        self.assertEqual(classify("100", "100", "M1", ["100"], SNAPSHOT), ("eprel_number", "correct"))

    def test_wrong(self):
        self.assertEqual(classify("100", "200", "", [], SNAPSHOT), ("eprel_number", "wrong"))

    def test_missed_when_sheet_id_in_snapshot(self):
        self.assertEqual(classify("", "200", "", [], SNAPSHOT), ("eprel_number", "missed"))

    def test_outside_snapshot_when_sheet_id_not_in_snapshot(self):
        self.assertEqual(classify("", "999", "", [], SNAPSHOT),
                         ("eprel_number", "reference_outside_snapshot"))

    def test_printed_id_wins_over_model_lookup(self):
        # the model lookup disagrees, but the printed EPREL number decides
        self.assertEqual(classify("100", "100", "M2", ["200"], SNAPSHOT), ("eprel_number", "correct"))


class ClassifyModelName(unittest.TestCase):
    def test_consistent(self):
        self.assertEqual(classify("100", "", "M1", ["100"], SNAPSHOT), ("sheet_model", "consistent"))

    def test_inconsistent(self):
        self.assertEqual(classify("100", "", "M1", ["200"], SNAPSHOT), ("sheet_model", "inconsistent"))

    def test_candidate_found_unmatched(self):
        self.assertEqual(classify("", "", "M1", ["200"], SNAPSHOT),
                         ("sheet_model", "candidate_found_unmatched"))

    def test_ambiguous(self):
        self.assertEqual(classify("100", "", "M1", ["100", "200"], SNAPSHOT),
                         ("sheet_model", "ambiguous_model_match"))

    def test_failed_lookup_is_unresolved_not_absent(self):
        # e.g. Siemens WG34G2070: no model match must never be reported as "not in snapshot"
        for ours in ("", "100"):
            ref, outcome = classify(ours, "", "WG34G2070", [], SNAPSHOT)
            self.assertEqual((ref, outcome), ("sheet_model", "unresolved_no_model_match"))
            self.assertNotIn("snapshot", outcome)

    def test_no_reference(self):
        self.assertEqual(classify("100", "", "", [], SNAPSHOT), ("none", "no_reference"))


def row(status, ref, outcome, in_snapshot=True):
    return {"match_status": status, "reference_type": ref, "outcome": outcome,
            "sheet_id_in_snapshot": in_snapshot}


class Summarise(unittest.TestCase):
    def test_pilot_shaped_counts(self):
        rows = ([row("matched", "eprel_number", "correct")] * 14
                + [row("unmatched", "eprel_number", "missed")]
                + [row("matched", "sheet_model", "consistent")] * 8
                + [row("unmatched", "sheet_model", "candidate_found_unmatched")] * 2
                + [row("unmatched", "sheet_model", "unresolved_no_model_match")])
        s = summarise(rows)
        self.assertEqual((s["matched"], s["listings"]), (22, 26))
        self.assertEqual(s["explicit_id_subset"], 15)
        self.assertEqual(s["precision_explicit"], [14, 14])
        self.assertEqual(s["recall_explicit"], [14, 15])
        self.assertEqual(s["model_name_subset"], 11)
        self.assertEqual(s["model_name_outcomes"]["consistent"], 8)

    def test_model_checks_do_not_enter_precision_or_recall(self):
        rows = [row("matched", "sheet_model", "inconsistent"),
                row("unmatched", "sheet_model", "candidate_found_unmatched")]
        s = summarise(rows)
        self.assertEqual(s["precision_explicit"], [0, 0])
        self.assertEqual(s["recall_explicit"], [0, 0])

    def test_recall_excludes_ids_outside_snapshot(self):
        rows = [row("matched", "eprel_number", "correct"),
                row("unmatched", "eprel_number", "reference_outside_snapshot", in_snapshot=False),
                row("matched", "eprel_number", "wrong", in_snapshot=False),
                row("matched", "eprel_number", "wrong", in_snapshot=True)]
        s = summarise(rows)
        self.assertEqual(s["precision_explicit"], [1, 3])     # both wrong matches count against precision
        self.assertEqual(s["recall_explicit"], [1, 2])        # only IDs in the snapshot are findable


if __name__ == "__main__":
    unittest.main()
