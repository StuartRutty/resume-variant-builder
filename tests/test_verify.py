"""Unit and CLI tests for verify.py."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import verify
from tests.helpers import make_resume_envelope

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestVerify(unittest.TestCase):
    def _run_verify_in_process(self, resume_obj, spec_obj):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            res_path = os.path.join(tmpdir, "resume.json")
            spec_path = os.path.join(tmpdir, "spec.json")
            with open(res_path, "w", encoding="utf-8") as f:
                json.dump(resume_obj, f)
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(spec_obj, f)
            with (
                mock.patch.object(sys, "argv", ["verify.py", res_path, spec_path]),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                rc = verify.main()
        return rc, stdout.getvalue(), stderr.getvalue()

    # Target 7: duplicate skill group names in verify.py
    def test_duplicate_skill_group_names_exact_match_passes(self):
        resume = make_resume_envelope(
            skills=[
                {"name": "Automation", "keywords": ["Python"]},
                {"name": "Automation", "keywords": ["Bash"]},
                {"name": "Operations", "keywords": ["Triage"]},
            ]
        )
        spec = {"skill_order": ["Automation"]}
        rc, out, _ = self._run_verify_in_process(resume, spec)

        self.assertEqual(rc, 0)
        self.assertIn("PASS  Skills: 3 groups, exact permutation", out)
        self.assertIn("RESULT: PASS", out)

    def test_duplicate_skill_group_names_normalized_collision_passes(self):
        resume = make_resume_envelope(
            skills=[
                {"name": "Cloud  Ops", "keywords": ["AWS"]},
                {"name": "cloud ops", "keywords": ["GCP"]},
                {"name": "Data", "keywords": ["SQL"]},
            ]
        )
        spec = {"skill_order": ["cloud ops", "Data"]}
        rc, out, _ = self._run_verify_in_process(resume, spec)

        self.assertEqual(rc, 0)
        self.assertIn("PASS  Skills: 3 groups, exact permutation", out)
        self.assertIn("RESULT: PASS", out)

    def test_duplicate_skill_group_named_multiple_times_in_order_passes(self):
        resume = make_resume_envelope(
            skills=[
                {"name": "Cloud  Ops", "keywords": ["AWS"]},
                {"name": "cloud ops", "keywords": ["GCP"]},
                {"name": "Data", "keywords": ["SQL"]},
            ]
        )
        # Named twice (both claimed) and even a 3rd time (unmatched, ignored).
        for order in (["cloud ops", "Cloud  Ops"], ["cloud ops", "cloud ops", "cloud ops"]):
            with self.subTest(order=order):
                rc, out, _ = self._run_verify_in_process(resume, {"skill_order": order})
                self.assertEqual(rc, 0)
                self.assertIn("PASS  Skills: 3 groups, exact permutation", out)

    def test_hidden_duplicate_skill_groups_excluded_cleanly(self):
        resume = make_resume_envelope(
            skills=[
                {"name": "Automation", "keywords": ["Python"]},
                {"name": "Automation", "keywords": ["Hidden"], "hidden": True},
                {"name": "Operations", "keywords": ["Triage"]},
            ]
        )
        rc, out, _ = self._run_verify_in_process(resume, {"skill_order": ["Automation"]})
        self.assertEqual(rc, 0)
        self.assertIn("PASS  Skills: 2 groups, exact permutation", out)

    def test_role_and_bare_project_bullet_orders_and_unknown_key_skip(self):
        resume = make_resume_envelope()
        spec = {
            "bullet_order": {
                "Northwind Logistics|Operations Lead": [1, 0],
                "Unknown Co|Unknown Role": [0],
            },
            "project_bullet_order": {
                "Migration Runbook": [1, 0],
            },
            "skill_order": ["Automation", "Delivery & Operations"],
        }
        rc, out, _ = self._run_verify_in_process(resume, spec)

        self.assertEqual(rc, 0)
        self.assertIn("PASS  Northwind Logistics — Operations Lead: 2 bullets, exact permutation", out)
        self.assertIn("SKIP  'Unknown Co|Unknown Role'", out)
        self.assertIn("PASS  Project: Migration Runbook: 2 bullets, exact permutation", out)
        self.assertIn("PASS  Skills: 2 groups, exact permutation", out)

    # Duplicate role/project keys: verify must mirror build(), which refuses
    # to reorder an ambiguously named entry. The old verify.py collapsed
    # duplicates last-wins and would PASS a spec against the last colliding
    # entry's list even though the builder silently ignores that key.
    def test_duplicate_role_and_project_keys_skip_not_pass_against_last(self):
        resume = make_resume_envelope(
            experience=[
                {
                    "company": "Northwind Logistics",
                    "location": "Seattle, WA",
                    "period": "2021 — Present",
                    "roles": [
                        {
                            "position": "Operations Lead",
                            "period": "2022 — Present",
                            "description": (
                                "<ul>"
                                "<li><p>Alpha bullet one.</p></li>"
                                "<li><p>Beta bullet two.</p></li>"
                                "</ul>"
                            ),
                        }
                    ],
                },
                {
                    "company": "Northwind Logistics",
                    "location": "Seattle, WA",
                    "period": "2019 — 2021",
                    "roles": [
                        {
                            "position": "Operations Lead",
                            "period": "2019 — 2021",
                            "description": (
                                "<ul>"
                                "<li><p>Gamma bullet three.</p></li>"
                                "<li><p>Delta bullet four.</p></li>"
                                "</ul>"
                            ),
                        }
                    ],
                },
            ],
            projects=[
                {
                    "name": "Migration Runbook",
                    "period": "2024",
                    "description": (
                        "<ul>"
                        "<li><p>First project step.</p></li>"
                        "<li><p>Second project step.</p></li>"
                        "</ul>"
                    ),
                },
                {
                    "name": "Migration Runbook",
                    "period": "2023",
                    "description": (
                        "<ul>"
                        "<li><p>Third project step.</p></li>"
                        "<li><p>Fourth project step.</p></li>"
                        "</ul>"
                    ),
                },
            ],
        )
        spec = {
            "bullet_order": {"Northwind Logistics|Operations Lead": [1, 0]},
            "project_bullet_order": {"Migration Runbook": [1, 0]},
        }
        rc, out, _ = self._run_verify_in_process(resume, spec)

        self.assertEqual(rc, 0)
        self.assertIn("SKIP  'Northwind Logistics|Operations Lead'", out)
        self.assertIn("duplicate", out)
        self.assertIn("SKIP  'Migration Runbook'", out)
        self.assertNotIn("PASS  Northwind Logistics — Operations Lead", out)
        self.assertNotIn("PASS  Project: Migration Runbook", out)
        self.assertIn("RESULT: PASS", out)

    def test_cli_wrong_arg_count_exits_2(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "verify.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stderr)

    def test_cli_sample_examples_pass(self):
        proc = subprocess.run(
            [
                sys.executable,
                os.path.join(REPO_ROOT, "verify.py"),
                os.path.join(REPO_ROOT, "examples", "sample-resume.json"),
                os.path.join(REPO_ROOT, "examples", "sample-spec.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
