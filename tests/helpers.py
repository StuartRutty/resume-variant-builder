"""Shared fixtures and stdlib-only PDF text extraction helpers for tests."""
import base64
import copy
import importlib.util
import re
import zlib

HAS_REPORTLAB = importlib.util.find_spec("reportlab") is not None


def make_resume_data(
    *,
    basics=None,
    summary_content="<p>Operations lead with ten years of experience.</p>",
    experience=None,
    projects=None,
    education=None,
    skills=None,
):
    """Build a minimal Reactive Resume ``data`` dict matching build_variant.py's schema."""
    default_basics = {
        "name": "Alex Rivera",
        "headline": "Operations Lead",
        "email": "alex@example.com",
        "phone": "(555) 010-1234",
        "location": "Seattle, WA",
        "customFields": [],
    }
    if basics:
        default_basics.update(basics)

    default_experience = [
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
        }
    ]

    default_projects = [
        {
            "name": "Migration Runbook",
            "period": "2024",
            "description": (
                "<ul>"
                "<li><p>First project step.</p></li>"
                "<li><p>Second project step.</p></li>"
                "</ul>"
            ),
        }
    ]

    default_education = [
        {
            "school": "State University",
            "degree": "B.S.",
            "area": "Information Systems",
            "period": "2014 — 2018",
            "location": "Seattle, WA",
        }
    ]

    default_skills = [
        {"name": "Delivery & Operations", "keywords": ["service reviews", "triage"]},
        {"name": "Automation", "keywords": ["Python", "SQL"]},
    ]

    return {
        "basics": copy.deepcopy(default_basics),
        "summary": {"content": summary_content},
        "sections": {
            "experience": {
                "items": copy.deepcopy(default_experience if experience is None else experience)
            },
            "projects": {
                "items": copy.deepcopy(default_projects if projects is None else projects)
            },
            "education": {
                "items": copy.deepcopy(default_education if education is None else education)
            },
            "skills": {
                "items": copy.deepcopy(default_skills if skills is None else skills)
            },
        },
    }


def make_resume_envelope(**kwargs):
    """Return a full Reactive Resume JSON top-level object: ``{"data": ...}``."""
    return {"data": make_resume_data(**kwargs)}


def _unescape_pdf_literal(raw_bytes):
    """Decode a PDF literal string's raw bytes (without outer parens) using cp1252."""
    out = bytearray()
    i = 0
    n = len(raw_bytes)
    while i < n:
        ch = raw_bytes[i]
        if ch == 0x5C and i + 1 < n:  # backslash escape
            nxt = raw_bytes[i + 1]
            if 0x30 <= nxt <= 0x37:  # 1-to-3 digit octal escape
                oct_digits = bytes([nxt])
                j = i + 2
                while j < n and len(oct_digits) < 3 and 0x30 <= raw_bytes[j] <= 0x37:
                    oct_digits += bytes([raw_bytes[j]])
                    j += 1
                out.append(int(oct_digits, 8) & 0xFF)
                i = j
                continue
            simple = {
                ord("n"): 0x0A,
                ord("r"): 0x0D,
                ord("t"): 0x09,
                ord("b"): 0x08,
                ord("f"): 0x0C,
                ord("("): ord("("),
                ord(")"): ord(")"),
                ord("\\"): ord("\\"),
            }
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt in (0x0A, 0x0D):  # line continuation
                i += 2
                if nxt == 0x0D and i < n and raw_bytes[i] == 0x0A:
                    i += 1
                continue
            out.append(nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return out.decode("cp1252", errors="replace")


def _extract_strings_from_stream(stream_bytes):
    """Extract rendered lines from PDF ``Tj`` / ``TJ`` operators in order.

    ReportLab splits inline markup (bold runs, unescaped entities) into
    adjacent ``Tj`` calls within one ``BT ... ET`` block and emits ``T*`` or
    ``ET`` at line/block boundaries. Joining fragments within a line keeps
    phrases like ``Ops & Delivery lead — <core> systems`` intact.
    """
    lines = []
    cur = []
    i = 0
    n = len(stream_bytes)

    def flush():
        if cur:
            lines.append("".join(cur))
            cur.clear()

    def read_literal(pos):
        # pos points to '('
        depth = 1
        pos += 1
        start = pos
        while pos < n and depth > 0:
            b = stream_bytes[pos]
            if b == 0x5C:  # backslash
                pos += 2
                continue
            if b == ord("("):
                depth += 1
            elif b == ord(")"):
                depth -= 1
                if depth == 0:
                    return stream_bytes[start:pos], pos + 1
            pos += 1
        return stream_bytes[start:pos], pos

    while i < n:
        b = stream_bytes[i]
        if b == ord("("):
            lit, end = read_literal(i)
            j = end
            while j < n and stream_bytes[j] in b" \t\r\n":
                j += 1
            if stream_bytes[j:j + 2] == b"Tj":
                cur.append(_unescape_pdf_literal(lit))
                i = j + 2
                continue
            i = end
        elif b == ord("["):
            j = i + 1
            parts = []
            while j < n and stream_bytes[j] != ord("]"):
                if stream_bytes[j] == ord("("):
                    lit, j = read_literal(j)
                    parts.append(_unescape_pdf_literal(lit))
                else:
                    j += 1
            if j < n and stream_bytes[j] == ord("]"):
                k = j + 1
                while k < n and stream_bytes[k] in b" \t\r\n":
                    k += 1
                if stream_bytes[k:k + 2] == b"TJ":
                    if parts:
                        cur.append("".join(parts))
                    i = k + 2
                    continue
            i = j + 1
        elif stream_bytes[i:i + 2] in (b"T*", b"ET") and (
            i == 0 or stream_bytes[i - 1] in b" \t\r\n"
        ) and (
            i + 2 == n or stream_bytes[i + 2] in b" \t\r\n"
        ):
            flush()
            i += 2
        else:
            i += 1
    flush()
    return lines


def extract_pdf_text(pdf_path):
    """Extract rendered text from a ReportLab PDF using Python stdlib only.

    Decodes each PDF stream (supporting ASCII85Decode and FlateDecode filters
    in order) and pulls text literals from ``Tj`` / ``TJ`` operators decoded
    as ``cp1252`` (PDF WinAnsiEncoding used by ReportLab's Helvetica fonts).
    """
    with open(pdf_path, "rb") as f:
        raw = f.read()

    # Match each object dictionary immediately preceding a stream.
    pattern = re.compile(
        rb"<<(?P<dict>(?:(?!<<|>>).)*?)>>\s*stream\r?\n(?P<body>.*?)endstream",
        re.S,
    )
    chunks = []
    for match in pattern.finditer(raw):
        header = match.group("dict")
        body = match.group("body").strip()
        if b"ASCII85Decode" in header:
            body = base64.a85decode(body, adobe=True)
        if b"FlateDecode" in header:
            body = zlib.decompress(body)
        chunks.extend(_extract_strings_from_stream(body))
    return "\n".join(chunks)
