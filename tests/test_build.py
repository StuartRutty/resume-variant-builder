"""Unit and integration tests for build_variant.build()."""
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import build_variant as bv
from tests.helpers import HAS_REPORTLAB, extract_pdf_text, make_resume_data


def _bind_nested_heading(paragraph_cls, hr_cls, style, story):
    """Instantiate build_variant.build's real nested heading() closure."""
    code = next(
        c
        for c in bv.build.__code__.co_consts
        if isinstance(c, types.CodeType) and c.co_name == "heading"
    )
    freevars = {
        "HRFlowable": hr_cls,
        "Paragraph": paragraph_cls,
        "s_h2": style,
        "story": story,
    }
    closure = tuple(types.CellType(freevars[name]) for name in code.co_freevars)
    return types.FunctionType(code, bv.build.__globals__, "heading", None, closure)


class TestHeadingEscapingOrderNoReportLab(unittest.TestCase):
    """Test build()'s nested heading() escaping order without requiring ReportLab."""

    def test_heading_uppercases_before_escaping_entities(self):
        captured = []

        class StubParagraph:
            def __init__(self, markup, style):
                self.markup = markup
                self.style = style
                captured.append(markup)

        class StubHR:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        story = []
        heading = _bind_nested_heading(StubParagraph, StubHR, "STYLE_H2", story)

        heading("Research & Development")
        heading("A < B & C > D")
        heading(None)

        self.assertEqual(
            captured,
            [
                "RESEARCH &amp; DEVELOPMENT",
                "A &lt; B &amp; C &gt; D",
                "",
            ],
        )
        # Ensure entities were never uppercased into &AMP;, &LT;, &GT;.
        for markup in captured:
            self.assertNotIn("&AMP;", markup)
            self.assertNotIn("&LT;", markup)
            self.assertNotIn("&GT;", markup)


class TestBuildImportGuard(unittest.TestCase):
    def test_missing_reportlab_raises_helpful_import_error(self):
        data = make_resume_data()
        with mock.patch.dict(
            sys.modules,
            {
                "reportlab": None,
                "reportlab.lib": None,
                "reportlab.lib.pagesizes": None,
                "reportlab.lib.styles": None,
                "reportlab.lib.units": None,
                "reportlab.platypus": None,
            },
        ):
            with self.assertRaises(ImportError) as ctx:
                bv.build(data, {}, "/tmp/unused-test-output.pdf")
        self.assertIn("reportlab", str(ctx.exception))


@unittest.skipUnless(HAS_REPORTLAB, "reportlab is not installed")
class TestBuildWithReportLab(unittest.TestCase):
    def _build_and_extract(self, data, spec, email_override=None):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "out.pdf")
            with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
                bv.build(data, spec, pdf_path, email_override=email_override)
            self.assertTrue(os.path.exists(pdf_path))
            text = extract_pdf_text(pdf_path)
        return text, stderr.getvalue(), stdout.getvalue()

    # Target 3: norm_key() collisions in skill ordering
    def test_skill_norm_key_collision_both_groups_survive_single_order_entry(self):
        data = make_resume_data(
            skills=[
                {"name": "Cloud  Ops", "keywords": ["AWS-unique-token"]},
                {"name": "cloud ops", "keywords": ["GCP-unique-token"]},
                {"name": "Data", "keywords": ["SQL-unique-token"]},
            ]
        )
        spec = {"skill_order": ["cloud ops"]}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertEqual(err, "")
        self.assertIn("AWS-unique-token", text)
        self.assertIn("GCP-unique-token", text)
        self.assertIn("SQL-unique-token", text)
        # ReportLab's Paragraph collapses internal runs of spaces in "Cloud  Ops".
        self.assertIn("Cloud Ops: AWS-unique-token", text)
        self.assertIn("cloud ops: GCP-unique-token", text)

    def test_skill_norm_key_collision_both_groups_survive_when_ordered_twice(self):
        data = make_resume_data(
            skills=[
                {"name": "Data", "keywords": ["SQL-token"]},
                {"name": "Cloud  Ops", "keywords": ["AWS-token"]},
                {"name": "cloud ops", "keywords": ["GCP-token"]},
            ]
        )
        spec = {"skill_order": ["cloud ops", "Cloud  Ops"]}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertEqual(err, "")
        self.assertIn("AWS-token", text)
        self.assertIn("GCP-token", text)
        self.assertIn("SQL-token", text)
        # Both colliding groups were promoted ahead of Data.
        self.assertLess(text.index("AWS-token"), text.index("SQL-token"))
        self.assertLess(text.index("GCP-token"), text.index("SQL-token"))

    def test_skill_norm_key_collision_extra_repeat_warns_and_keeps_both(self):
        data = make_resume_data(
            skills=[
                {"name": "Cloud  Ops", "keywords": ["AWS-token"]},
                {"name": "cloud ops", "keywords": ["GCP-token"]},
            ]
        )
        spec = {"skill_order": ["cloud ops", "cloud ops", "cloud ops"]}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertIn("WARN: skill group 'cloud ops' matched nothing or repeats", err)
        self.assertIn("AWS-token", text)
        self.assertIn("GCP-token", text)

    # Target 4: Duplicate role keys in build()
    def test_duplicate_role_keys_warn_and_do_not_cross_apply_bullets(self):
        data = make_resume_data(
            experience=[
                {
                    "company": "Acme Corp",
                    "period": "2022 — 2024",
                    "roles": [
                        {
                            "position": "Operations Lead",
                            "period": "2022 — 2024",
                            "description": (
                                "<ul>"
                                "<li>RoleOneFirstBullet</li>"
                                "<li>RoleOneSecondBullet</li>"
                                "</ul>"
                            ),
                        }
                    ],
                },
                {
                    "company": "acme  corp",
                    "period": "2019 — 2022",
                    "roles": [
                        {
                            "position": "operations  lead",
                            "period": "2019 — 2022",
                            "description": (
                                "<ul>"
                                "<li>RoleTwoFirstBullet</li>"
                                "<li>RoleTwoSecondBullet</li>"
                                "</ul>"
                            ),
                        }
                    ],
                },
            ]
        )
        spec = {"bullet_order": {"Acme Corp|Operations Lead": [1, 0]}}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertIn("WARN: duplicate role/project key 'acme corp|operations lead'", err)
        self.assertIn("matches duplicate key 'acme corp|operations lead'", err)

        # Every bullet from both roles must appear once, in each role's own original order.
        for token in (
            "RoleOneFirstBullet",
            "RoleOneSecondBullet",
            "RoleTwoFirstBullet",
            "RoleTwoSecondBullet",
        ):
            self.assertEqual(text.count(token), 1, f"expected {token} exactly once")

        self.assertLess(text.index("RoleOneFirstBullet"), text.index("RoleOneSecondBullet"))
        self.assertLess(text.index("RoleTwoFirstBullet"), text.index("RoleTwoSecondBullet"))
        self.assertLess(text.index("RoleOneSecondBullet"), text.index("RoleTwoFirstBullet"))

    def test_triple_duplicate_role_keys_never_reenter_ordered_map(self):
        data = make_resume_data(
            experience=[
                {
                    "company": "Acme",
                    "position": "Eng",
                    "description": "<ul><li>E1A</li><li>E1B</li></ul>",
                },
                {
                    "company": "acme",
                    "position": "eng",
                    "description": "<ul><li>E2A</li><li>E2B</li></ul>",
                },
                {
                    "company": "ACME",
                    "position": "ENG",
                    "description": "<ul><li>E3A</li><li>E3B</li></ul>",
                },
            ]
        )
        spec = {"bullet_order": {"Acme|Eng": [1, 0]}}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertIn("WARN: duplicate role/project key 'acme|eng'", err)
        self.assertIn("matches duplicate key 'acme|eng'", err)
        self.assertLess(text.index("E1A"), text.index("E1B"))
        self.assertLess(text.index("E2A"), text.index("E2B"))
        self.assertLess(text.index("E3A"), text.index("E3B"))

    def test_duplicate_project_keys_warn_and_preserve_each_projects_bullets(self):
        data = make_resume_data(
            projects=[
                {
                    "name": "Data Pipeline",
                    "period": "2024",
                    "description": "<ul><li>Proj1First</li><li>Proj1Second</li></ul>",
                },
                {
                    "name": "data  pipeline",
                    "period": "2023",
                    "description": "<ul><li>Proj2First</li><li>Proj2Second</li></ul>",
                },
            ]
        )
        spec = {"project_bullet_order": {"Data Pipeline": [1, 0]}}
        text, err, _ = self._build_and_extract(data, spec)

        self.assertIn("WARN: duplicate role/project key 'project|data pipeline'", err)
        self.assertIn("matches duplicate key 'project|data pipeline'", err)
        self.assertLess(text.index("Proj1First"), text.index("Proj1Second"))
        self.assertLess(text.index("Proj2First"), text.index("Proj2Second"))

    # Target 5: heading() escaping order rendered into a real ReportLab PDF
    def test_heading_with_ampersand_renders_plain_ampersand_in_pdf(self):
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate

        story = []
        s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, leading=14)
        heading = _bind_nested_heading(Paragraph, HRFlowable, s_h2, story)
        heading("Research & Development")

        # Verify the Paragraph received valid lowercase XML entity, not &AMP;.
        self.assertEqual(story[0].text, "RESEARCH &amp; DEVELOPMENT")
        self.assertNotIn("&AMP;", story[0].text)

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "heading.pdf")
            SimpleDocTemplate(pdf_path, pagesize=LETTER).build(story)
            text = extract_pdf_text(pdf_path)

        self.assertIn("RESEARCH & DEVELOPMENT", text)
        self.assertNotIn("&AMP;", text)
        self.assertNotIn("&amp;", text)

    def test_full_build_with_ampersand_in_section_metadata_and_content(self):
        data = make_resume_data(
            basics={"headline": "Logistics & Service Delivery"},
            skills=[{"name": "Delivery & Operations", "keywords": ["R&D", "Q&A"]}],
        )
        # Note: build() hardcodes section titles rather than reading sections[*]["name"],
        # so including a name with "&" verifies build() accepts it without error while
        # TestHeadingEscapingOrderNoReportLab and test_heading_with_ampersand_renders_plain_ampersand_in_pdf
        # directly pin heading()'s escaping order.
        data["sections"]["skills"]["name"] = "Skills & Tools"
        text, err, _ = self._build_and_extract(data, {})

        self.assertEqual(err, "")
        self.assertIn("Logistics & Service Delivery", text)
        self.assertIn("Delivery & Operations:", text)
        self.assertNotIn("&AMP;", text)
        self.assertNotIn("&amp;", text)

    # Target 6: Summary fallback without <li>/<p> tags and with HTML entities
    def test_summary_fallback_plain_text_with_html_entities_not_double_escaped(self):
        data = make_resume_data(
            summary_content="Ops &amp; Delivery lead &mdash; &lt;core&gt; systems"
        )
        text, err, _ = self._build_and_extract(data, {})

        self.assertEqual(err, "")
        self.assertIn("Ops & Delivery lead — <core> systems", text)
        self.assertNotIn("&amp;", text)
        self.assertNotIn("&lt;", text)
        self.assertNotIn("&mdash;", text)

    def test_summary_fallback_inline_tags_only_with_html_entity(self):
        data = make_resume_data(
            summary_content="<span>Reliability &amp; Automation specialist</span>"
        )
        text, err, _ = self._build_and_extract(data, {})

        self.assertEqual(err, "")
        self.assertIn("Reliability & Automation specialist", text)
        self.assertNotIn("&amp;", text)
        self.assertNotIn("<span>", text)

    def test_email_override_replaces_resume_email(self):
        data = make_resume_data(basics={"email": "orig@example.com"})
        text, err, _ = self._build_and_extract(
            data, {}, email_override="replies@example.com"
        )
        self.assertEqual(err, "")
        self.assertIn("replies@example.com", text)
        self.assertNotIn("orig@example.com", text)


if __name__ == "__main__":
    unittest.main()
