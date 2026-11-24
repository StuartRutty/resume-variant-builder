"""Encoding tests: UTF-8 JSONs with non-ASCII text under forced ASCII default locale."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import HAS_REPORTLAB, extract_pdf_text, make_resume_envelope

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ascii_locale_env():
    """Force Python's default open() encoding to ASCII while allowing UTF-8 stdio.

    If a script calls open() without encoding='utf-8', reading non-ASCII JSON
    files under this environment raises UnicodeDecodeError.
    """
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["PYTHONCOERCECLOCALE"] = "0"
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class TestUtf8Encoding(unittest.TestCase):
    def _write_non_ascii_fixtures(self, tmpdir):
        resume = make_resume_envelope(
            basics={
                "name": "René O’Connor",
                "headline": "Operations Lead — “end-to-end” delivery",
            },
            summary_content="<p>Built “resilient” teams — zero-drama handoffs.</p>",
            experience=[
                {
                    "company": "Café Logistics",
                    "location": "Montréal, QC",
                    "period": "2021 — Present",
                    "roles": [
                        {
                            "position": "Lead — Operations",
                            "period": "2022 — Present",
                            "description": (
                                "<ul>"
                                "<li><p>Wrote “golden path” runbooks — cut escalations 30%.</p></li>"
                                "<li><p>Partnered with teams’ leads on quarterly reviews.</p></li>"
                                "</ul>"
                            ),
                        }
                    ],
                }
            ],
            skills=[
                {"name": "Delivery — Ops", "keywords": ["“postmortems”", "SLAs"]},
                {"name": "Automation", "keywords": ["Python"]},
            ],
        )
        spec = {
            "role": "Acme — Delivery Manager",
            "bullet_order": {"Café Logistics|Lead — Operations": ["teams’ leads", "“golden path”"]},
            "skill_order": ["Delivery — Ops", "Automation"],
        }
        res_path = os.path.join(tmpdir, "resume.json")
        spec_path = os.path.join(tmpdir, "spec.json")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump(resume, f, ensure_ascii=False)
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        return res_path, spec_path

    def test_list_non_ascii_resume_under_c_locale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_path, _ = self._write_non_ascii_fixtures(tmpdir)
            proc = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "build_variant.py"), "--list", res_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_ascii_locale_env(),
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Café Logistics — Lead — Operations", proc.stdout)
        self.assertIn("“golden path”", proc.stdout)
        self.assertIn("teams’ leads", proc.stdout)

    def test_verify_non_ascii_resume_and_spec_under_c_locale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_path, spec_path = self._write_non_ascii_fixtures(tmpdir)
            proc = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "verify.py"), res_path, spec_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_ascii_locale_env(),
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    @unittest.skipUnless(HAS_REPORTLAB, "reportlab is not installed")
    def test_build_non_ascii_resume_and_spec_under_c_locale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_path, spec_path = self._write_non_ascii_fixtures(tmpdir)
            pdf_path = os.path.join(tmpdir, "out.pdf")
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(REPO_ROOT, "build_variant.py"),
                    res_path,
                    spec_path,
                    pdf_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_ascii_locale_env(),
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(pdf_path))
            text = extract_pdf_text(pdf_path)

        self.assertIn("René O’Connor", text)
        self.assertIn("Operations Lead — “end-to-end” delivery", text)
        self.assertIn("Built “resilient” teams — zero-drama handoffs.", text)
        self.assertIn("Wrote “golden path” runbooks — cut escalations 30%.", text)
        self.assertIn("Partnered with teams’ leads on quarterly reviews.", text)
        # Verify the spec actually reordered bullet 1 ahead of bullet 0.
        self.assertLess(text.index("teams’ leads"), text.index("“golden path”"))

    @unittest.skipUnless(HAS_REPORTLAB, "reportlab is not installed")
    def test_build_unmodified_dash_spec_non_ascii_under_c_locale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_path, _ = self._write_non_ascii_fixtures(tmpdir)
            pdf_path = os.path.join(tmpdir, "unmodified.pdf")
            proc = subprocess.run(
                [
                    sys.executable,
                    os.path.join(REPO_ROOT, "build_variant.py"),
                    res_path,
                    "-",
                    pdf_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_ascii_locale_env(),
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = extract_pdf_text(pdf_path)
        self.assertLess(text.index("“golden path”"), text.index("teams’ leads"))


if __name__ == "__main__":
    unittest.main()
