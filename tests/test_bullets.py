"""Unit tests for HTML bullet extraction, escaping, key normalization, and role listing."""
import unittest

import build_variant as bv
from tests.helpers import make_resume_data


class TestBullets(unittest.TestCase):
    def test_li_with_attributes(self):
        html = (
            '<ul>'
            '<li class="x" data-idx="0">First item</li>'
            '<li id="second" style="margin:0;">Second item</li>'
            '</ul>'
        )
        self.assertEqual(bv.bullets(html), ["First item", "Second item"])

    def test_p_with_attributes_when_no_li(self):
        html = (
            '<p class="lead">First paragraph</p>'
            '<p data-role="body" style="color:black">Second paragraph</p>'
        )
        self.assertEqual(bv.bullets(html), ["First paragraph", "Second paragraph"])

    def test_uppercase_and_mixed_case_tags(self):
        self.assertEqual(
            bv.bullets("<UL><LI>Upper one</LI><Li CLASS='x'>Mixed two</lI></UL>"),
            ["Upper one", "Mixed two"],
        )
        self.assertEqual(
            bv.bullets("<P CLASS='a'>Upper para</P><p>Lower para</p>"),
            ["Upper para", "Lower para"],
        )

    def test_br_converted_to_space(self):
        html = (
            "<ul>"
            "<li>Line one<br>Line two</li>"
            "<li>Part A<br/>Part B<br />Part C</li>"
            "<li>Upper<BR class='x'>Break</li>"
            "</ul>"
        )
        self.assertEqual(
            bv.bullets(html),
            ["Line one Line two", "Part A Part B Part C", "Upper Break"],
        )

    def test_nested_inline_tags_stripped(self):
        html = (
            "<ul>"
            '<li><p>Led <strong>core</strong> <a href="https://example.com">migration</a> '
            'with <em>zero</em> <span class="hi">downtime</span>.</p></li>'
            "</ul>"
        )
        self.assertEqual(
            bv.bullets(html),
            ["Led core migration with zero downtime."],
        )

    def test_html_entities_unescaped(self):
        html = (
            "<ul>"
            "<li>R&amp;D &lt;team&gt; &mdash; &quot;fast&quot; &amp; &#39;reliable&#39;</li>"
            "</ul>"
        )
        self.assertEqual(
            bv.bullets(html),
            ['R&D <team> — "fast" & \'reliable\''],
        )

    def test_plain_text_without_tags_returns_single_item(self):
        self.assertEqual(
            bv.bullets("  Plain text description with &amp; entity.  "),
            ["Plain text description with & entity."],
        )

    def test_empty_and_whitespace_inputs_return_empty_list(self):
        for raw in ("", None, "   ", "\n\t  ", "<ul><li></li><li>   </li></ul>", "<p></p>"):
            with self.subTest(raw=raw):
                self.assertEqual(bv.bullets(raw), [])

    def test_li_takes_precedence_over_nested_p(self):
        html = "<ul><li><p>Only once</p></li><li><p>Second bullet</p></li></ul>"
        self.assertEqual(bv.bullets(html), ["Only once", "Second bullet"])


class TestHelpers(unittest.TestCase):
    def test_norm_key_collapses_whitespace_and_lowercases(self):
        self.assertEqual(bv.norm_key("  Cloud   Ops \t "), "cloud ops")
        self.assertEqual(bv.norm_key(""), "")
        self.assertEqual(bv.norm_key(None), "")

    def test_esc_escapes_xml_specials_without_quotes(self):
        self.assertEqual(bv.esc('A & B <C> "D"'), 'A &amp; B &lt;C&gt; "D"')
        self.assertEqual(bv.esc(None), "")

    def test_role_bullet_lists_skips_hidden_and_handles_both_shapes(self):
        data = make_resume_data(
            experience=[
                {
                    "company": "Acme",
                    "roles": [
                        {"position": "Lead", "description": "<ul><li>R1</li></ul>"},
                        {"position": "Eng", "description": "<ul><li>R2</li></ul>"},
                    ],
                },
                {
                    "company": "SoloCo",
                    "position": "Analyst",
                    "description": "<ul><li>S1</li></ul>",
                },
                {
                    "company": "HiddenCo",
                    "hidden": True,
                    "position": "Ghost",
                    "description": "<ul><li>H1</li></ul>",
                },
            ],
            projects=[
                {"name": "ProjA", "description": "<ul><li>P1</li></ul>"},
                {"name": "HiddenProj", "hidden": True, "description": "<ul><li>HP</li></ul>"},
            ],
        )
        entries = bv.role_bullet_lists(data)
        keys = [k for k, _, _ in entries]
        self.assertEqual(keys, ["Acme|Lead", "Acme|Eng", "SoloCo|Analyst", "project|ProjA"])
        self.assertEqual([bl for _, _, bl in entries], [["R1"], ["R2"], ["S1"], ["P1"]])


if __name__ == "__main__":
    unittest.main()
