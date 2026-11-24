"""Unit tests for apply_order()."""
from collections import Counter
import unittest

import build_variant as bv


class TestApplyOrder(unittest.TestCase):
    def setUp(self):
        self.bullets = [
            "Own weekly service reviews for stakeholders.",
            "Cut ticket backlog 30% via triage rota.",
            "Led incident-response through severity-1 outages.",
            "Automated Monday reporting pack in Python.",
        ]

    def test_integer_indices_place_items_and_keep_rest_in_order(self):
        res, warns = bv.apply_order(self.bullets, [2, 0], "Role")
        self.assertEqual(warns, [])
        self.assertEqual(
            res,
            [self.bullets[2], self.bullets[0], self.bullets[1], self.bullets[3]],
        )

    def test_substring_matching_is_case_insensitive(self):
        res, warns = bv.apply_order(self.bullets, ["PYTHON", "BACKLOG"], "Role")
        self.assertEqual(warns, [])
        self.assertEqual(
            res,
            [self.bullets[3], self.bullets[1], self.bullets[0], self.bullets[2]],
        )

    def test_substring_picks_first_unplaced_match(self):
        items = ["Runbook for printers", "Triage queue", "Runbook for scanners"]
        res, warns = bv.apply_order(items, ["runbook", "runbook"], "Role")
        self.assertEqual(warns, [])
        self.assertEqual(
            res,
            ["Runbook for printers", "Runbook for scanners", "Triage queue"],
        )

    def test_boolean_entries_rejected_not_treated_as_indices(self):
        res, warns = bv.apply_order(self.bullets, [True, False], "Role")
        self.assertEqual(res, self.bullets)
        self.assertEqual(len(warns), 2)
        self.assertTrue(all("unsupported order entry" in w for w in warns))

    def test_non_list_order_warns_and_returns_copy_of_original(self):
        for bad_order in ("backlog", 0, {"0": 1}, None, (1, 0), True):
            with self.subTest(bad_order=bad_order):
                res, warns = bv.apply_order(self.bullets, bad_order, "Role")
                self.assertEqual(res, self.bullets)
                self.assertIsNot(res, self.bullets)
                self.assertEqual(len(warns), 1)
                self.assertIn("expected a list", warns[0])

    def test_empty_and_whitespace_string_entries_warn_and_skip(self):
        res, warns = bv.apply_order(self.bullets, ["", "   ", "\t\n", 2], "Role")
        self.assertEqual(len(warns), 3)
        self.assertTrue(all("empty substring" in w for w in warns))
        self.assertEqual(res[0], self.bullets[2])
        self.assertEqual(Counter(res), Counter(self.bullets))

    def test_unknown_indices_and_substrings_warn_and_skip(self):
        res, warns = bv.apply_order(
            self.bullets, [-1, 99, "nonexistent-keyword", 1], "Role"
        )
        self.assertEqual(len(warns), 3)
        self.assertIn("out of range", warns[0])
        self.assertIn("out of range", warns[1])
        self.assertIn("matched no unplaced bullet", warns[2])
        self.assertEqual(
            res,
            [self.bullets[1], self.bullets[0], self.bullets[2], self.bullets[3]],
        )

    def test_already_placed_index_warns_and_is_not_placed_twice(self):
        # Duplicate integer index AND index already claimed by a prior substring.
        res, warns = bv.apply_order(self.bullets, [2, 2, "backlog", 1], "Role")
        self.assertEqual(len(warns), 2)
        self.assertTrue(all("already placed" in w for w in warns))
        self.assertEqual(
            res,
            [self.bullets[2], self.bullets[1], self.bullets[0], self.bullets[3]],
        )

    def test_empty_list_order_returns_copy_without_warnings(self):
        res, warns = bv.apply_order(self.bullets, [], "Role")
        self.assertEqual(warns, [])
        self.assertEqual(res, self.bullets)
        self.assertIsNot(res, self.bullets)

    def test_result_is_always_exact_permutation(self):
        cases = [
            (self.bullets, [3, 2, 1, 0]),
            (self.bullets, [2, 0, "python"]),
            (self.bullets, [True, False, "", "missing", -5, 100, 1.5, None, {"a": 1}]),
            (self.bullets, [1, 1, "backlog", "BACKLOG", 0, 0]),
            (["dup", "unique", "dup"], [2, "dup", 0, 2]),
            ([], [0, "anything", True]),
            (self.bullets, "not-a-list"),
        ]
        for original, order in cases:
            with self.subTest(original=original, order=order):
                res, _ = bv.apply_order(original, order, "Role")
                self.assertEqual(len(res), len(original))
                self.assertEqual(sorted(res), sorted(original))
                self.assertEqual(Counter(res), Counter(original))


if __name__ == "__main__":
    unittest.main()
