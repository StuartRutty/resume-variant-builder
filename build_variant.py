#!/usr/bin/env python3
"""Build a per-role variant of a resume PDF by reordering bullets only.

Input is a Reactive Resume JSON export. Faithful reordering only — this
script NEVER edits, adds, or removes resume text:

- Bullets may be reordered WITHIN one role (or one project). Every
  original bullet stays, in its original wording; unlisted bullets keep
  their original relative order after the listed ones.
- Skill groups may be reordered within the Skills section.
- Employers are NEVER reordered (chronology is factual, not presentational).
- The Summary is NEVER rewritten; it renders verbatim. The tailored
  narrative for a role belongs in the cover letter, not in a rewritten
  summary.
- The contact email renders from the resume record by default; pass
  --email to override it (useful when applications should reply to a
  different inbox than the one on file).

Usage:
  # Show every role/project with numbered bullets (write specs from this)
  python3 build_variant.py --list resume.json

  # Build a variant PDF from a spec
  python3 build_variant.py [--email you@example.com] resume.json spec.json out.pdf
  # (pass "-" as the spec path for an unmodified render)

Spec format (JSON):
  {
    "role": "Acme Corp - Delivery Manager",
    "bullet_order": {
      "Northwind Logistics|Operations Lead": [2, 0, "stakeholder"],
      "Northwind Logistics|Support Engineer": [1, 0]
    },
    "project_bullet_order": {
      "Warehouse migration runbook": [1, 0]
    },
    "skill_order": ["Delivery & Operations", "Automation"]
  }

Role keys are "Company|Position" (case-insensitive). Order entries may
be 0-based bullet indices (as shown by --list) or substrings matched
case-insensitively against bullet text (first unplaced match wins).
Unknown keys, out-of-range indices, and unmatched substrings print a
warning to stderr and are ignored; they never invent content.

The output is a clean one- or two-page PDF (ReportLab, Letter,
Helvetica). The target role is carried in the FILE NAME only (e.g.
Resume-Acme-DeliveryManager.pdf); nothing is added to the PDF body.
"""
import html as htmlmod
import json
import re
import sys


def bullets(desc):
    """Extract <li> items as clean text; fall back to paragraphs or plain text."""
    raw = desc or ""
    items = re.findall(r"<li(?:\s[^>]*)?>(.*?)</li\s*>", raw, flags=re.S | re.I)
    if not items:
        items = re.findall(r"<p(?:\s[^>]*)?>(.*?)</p\s*>", raw, flags=re.S | re.I)
    if not items and raw.strip():
        items = [raw]
    out = []
    for it in items:
        cleaned = re.sub(r"<br(?:\s[^>]*)?/?>", " ", it, flags=re.I)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        text = htmlmod.unescape(cleaned).strip()
        if text:
            out.append(text)
    return out


def esc(s):
    return htmlmod.escape(s or "", quote=False)


def norm_key(s):
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def role_bullet_lists(data):
    """Return [(key, label, bullets)] for every experience role/project.

    Experience items with roles[] yield one entry per role; items without
    roles yield one entry for the item itself. Projects yield one entry
    per project, keyed by project name.
    """
    out = []
    secs = data["sections"]
    for it in secs["experience"]["items"]:
        if it.get("hidden"):
            continue
        company = it.get("company", "")
        roles = it.get("roles") or []
        if roles:
            for r in roles:
                pos = r.get("position", "")
                out.append(
                    (f"{company}|{pos}", f"{company} — {pos}",
                     bullets(r.get("description", "")))
                )
        else:
            pos = it.get("position", "")
            out.append(
                (f"{company}|{pos}", f"{company} — {pos}" if pos else company,
                 bullets(it.get("description", "")))
            )
    for it in secs["projects"]["items"]:
        if it.get("hidden"):
            continue
        name = it.get("name", "")
        out.append((f"project|{name}", f"Project: {name}",
                    bullets(it.get("description", ""))))
    return out


def apply_order(original, order, label):
    """Reorder `original` per `order`; unlisted items keep original order.

    order entries: int index, or str substring (case-insensitive, first
    unplaced match). Unknown entries warn and are skipped. The result is
    always a permutation of the original list — nothing added or dropped.
    """
    if not isinstance(order, list):
        return list(original), [
            f"  WARN [{label}]: expected a list for order, got {type(order).__name__}; ignored"
        ]
    if not order:
        return list(original), []
    placed = []
    used = set()
    warnings = []
    for entry in order:
        if isinstance(entry, int) and not isinstance(entry, bool):
            if 0 <= entry < len(original) and entry not in used:
                placed.append(original[entry])
                used.add(entry)
            else:
                warnings.append(
                    f"  WARN [{label}]: index {entry} out of range or "
                    "already placed; ignored"
                )
        elif isinstance(entry, str):
            if not entry.strip():
                warnings.append(
                    f"  WARN [{label}]: empty substring {entry!r}; ignored"
                )
                continue
            needle = entry.lower()
            match = None
            for i, b in enumerate(original):
                if i not in used and needle in b.lower():
                    match = i
                    break
            if match is None:
                warnings.append(
                    f"  WARN [{label}]: substring {entry!r} matched no "
                    "unplaced bullet; ignored"
                )
            else:
                placed.append(original[match])
                used.add(match)
        else:
            warnings.append(
                f"  WARN [{label}]: unsupported order entry {entry!r}; ignored"
            )
    rest = [b for i, b in enumerate(original) if i not in used]
    return placed + rest, warnings


def list_bullets(data):
    for key, label, bl in role_bullet_lists(data):
        print(f"## {label}  [key: {key}]")
        if not bl:
            print("   (no bullets)")
        for i, b in enumerate(bl):
            print(f"   [{i}] {b}")
        print()
    print("## Skills groups")
    for it in data["sections"]["skills"]["items"]:
        if not it.get("hidden"):
            print(f"   - {it.get('name', '')}")


def build(data, spec, pdf_path, email_override=None):
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            ListFlowable,
            ListItem,
            Paragraph,
            SimpleDocTemplate,
        )
    except ImportError as exc:
        raise ImportError(
            "reportlab is required to build PDFs (install it with: pip install reportlab)"
        ) from exc

    b = data["basics"]
    secs = data["sections"]

    # Resolve emphasis orders against the real bullet lists first, so a
    # bad spec key fails loudly as a warning, never silently.
    lists = {}
    dup_keys = set()
    for k, label, bl in role_bullet_lists(data):
        nk = norm_key(k)
        if nk in lists or nk in dup_keys:
            lists.pop(nk, None)
            if nk not in dup_keys:
                dup_keys.add(nk)
                print(
                    f"  WARN: duplicate role/project key {nk!r} ({label}); "
                    "not reordering, each entry keeps its own bullets",
                    file=sys.stderr,
                )
        else:
            lists[nk] = (label, bl)

    bullet_order = spec.get("bullet_order", {}) or {}
    project_order = spec.get("project_bullet_order", {}) or {}
    ordered = {}   # norm key -> reordered bullet list
    for key, order in list(bullet_order.items()) + list(project_order.items()):
        nk = norm_key(key)
        pnk = norm_key("project|" + key)
        if nk in dup_keys:
            print(
                f"  WARN: spec key {key!r} matches duplicate key {nk!r}; "
                "ignored so each entry keeps its own bullets",
                file=sys.stderr,
            )
            continue
        if nk not in lists:
            # Project keys are stored as "project|<name>"; accept a bare
            # project name too.
            if pnk in dup_keys:
                print(
                    f"  WARN: spec key {key!r} matches duplicate key {pnk!r}; "
                    "ignored so each entry keeps its own bullets",
                    file=sys.stderr,
                )
                continue
            if pnk in lists:
                nk = pnk
            else:
                print(f"  WARN: spec key {key!r} matched no role/project; ignored",
                      file=sys.stderr)
                continue
        label, bl = lists[nk]
        ordered[nk], warns = apply_order(bl, order, label)
        for w in warns:
            print(w, file=sys.stderr)

    skill_order = spec.get("skill_order", []) or []
    skill_items = [it for it in secs["skills"]["items"] if not it.get("hidden")]
    ordered_skills = []
    claimed_skills = set()
    for name in skill_order:
        nk = norm_key(name)
        match = None
        for i, it in enumerate(skill_items):
            if i not in claimed_skills and norm_key(it.get("name", "")) == nk:
                match = i
                break
        if match is not None:
            ordered_skills.append(skill_items[match])
            claimed_skills.add(match)
        else:
            print(f"  WARN: skill group {name!r} matched nothing or repeats; ignored",
                  file=sys.stderr)
    ordered_skills += [it for i, it in enumerate(skill_items)
                       if i not in claimed_skills]

    s_title = ParagraphStyle("Title2", fontName="Helvetica-Bold", fontSize=19, leading=22)
    s_head = ParagraphStyle("Head", fontName="Helvetica", fontSize=11, leading=13, textColor="#333333")
    s_contact = ParagraphStyle("Contact", fontName="Helvetica", fontSize=9.5, leading=12, textColor="#333333")
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, leading=14, spaceBefore=12, spaceAfter=2)
    s_h3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=8, spaceAfter=1)
    s_meta = ParagraphStyle("Meta", fontName="Helvetica", fontSize=9.5, leading=12, textColor="#444444", spaceAfter=3)
    s_body = ParagraphStyle("Body", fontName="Helvetica", fontSize=10.5, leading=13.5, spaceAfter=4)
    s_bullet = ParagraphStyle("Bullet", fontName="Helvetica", fontSize=10.5, leading=13.5, leftIndent=14, bulletIndent=4, spaceAfter=2)
    s_skill = ParagraphStyle("Skill", fontName="Helvetica", fontSize=10, leading=13, spaceAfter=3)

    story = []
    story.append(Paragraph(esc(b["name"]), s_title))
    story.append(Paragraph(esc(b["headline"]), s_head))
    links = []
    for cf in b.get("customFields", []):
        if cf.get("link"):
            links.append(cf["link"])
    contact = " | ".join(x for x in [email_override or b.get("email"), b.get("phone"), b.get("location"), *links] if x)
    story.append(Paragraph(esc(contact), s_contact))

    def heading(text):
        story.append(Paragraph(esc((text or "").upper()), s_h2))
        story.append(HRFlowable(width="100%", thickness=1, color="#222222", spaceAfter=4))

    def bullet_list(items):
        story.append(
            ListFlowable(
                [ListItem(Paragraph(esc(t), s_bullet), leftIndent=14) for t in items],
                bulletType="bullet",
                start="bulletchar",
                leftIndent=14,
            )
        )

    def pick(key, default):
        return ordered.get(norm_key(key), default)

    summary = data["summary"].get("content", "")
    summary_text = (
        " ".join(bullets(summary))
        or htmlmod.unescape(re.sub(r"<[^>]+>", "", summary)).strip()
    )
    if summary_text:
        heading("Summary")
        story.append(Paragraph(esc(summary_text), s_body))

    heading("Experience")
    for it in secs["experience"]["items"]:
        if it.get("hidden"):
            continue
        head = esc(it["company"])
        if it.get("location"):
            head += " — " + esc(it["location"])
        story.append(Paragraph(head, s_h3))
        story.append(Paragraph(esc(it.get("period", "")), s_meta))
        roles = it.get("roles") or []
        if roles:
            for r in roles:
                story.append(
                    Paragraph(
                        f"<b>{esc(r.get('position', ''))}</b> "
                        f"<font color='#444444'>{esc(r.get('period', ''))}</font>",
                        s_body,
                    )
                )
                bl = pick(f"{it['company']}|{r.get('position', '')}",
                          bullets(r.get("description", "")))
                if bl:
                    bullet_list(bl)
        else:
            if it.get("position"):
                story.append(Paragraph(f"<b>{esc(it['position'])}</b>", s_body))
            bl = pick(f"{it['company']}|{it.get('position', '')}",
                      bullets(it.get("description", "")))
            if bl:
                bullet_list(bl)

    heading("Projects")
    for it in secs["projects"]["items"]:
        if it.get("hidden"):
            continue
        story.append(Paragraph(esc(it["name"]), s_h3))
        story.append(Paragraph(esc(it.get("period", "")), s_meta))
        bl = pick(f"project|{it['name']}", bullets(it.get("description", "")))
        if bl:
            bullet_list(bl)

    heading("Education")
    for it in secs["education"]["items"]:
        if it.get("hidden"):
            continue
        line = f"<b>{esc(it.get('school', ''))}</b> — {esc(it.get('degree', ''))}"
        if it.get("area"):
            line += f", {esc(it['area'])}"
        line += f" <font color='#444444'>({esc(it.get('period', ''))}"
        if it.get("location"):
            line += f", {esc(it['location'])}"
        line += ")</font>"
        story.append(Paragraph(line, s_body))

    heading("Skills")
    for it in ordered_skills:
        kws = it.get("keywords") or []
        story.append(
            Paragraph(f"<b>{esc(it.get('name', ''))}:</b> {esc(', '.join(kws))}", s_skill)
        )

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"{b['name']} — Resume",
        author=b["name"],
    )
    doc.build(story)
    print("wrote", pdf_path)


def main():
    argv = sys.argv[1:]
    email_override = None
    if "--email" in argv:
        i = argv.index("--email")
        email_override = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) >= 2 and argv[0] == "--list":
        with open(argv[1], encoding="utf-8") as f:
            data = json.load(f)["data"]
        list_bullets(data)
        return
    if len(argv) != 3:
        print("usage: build_variant.py --list resume.json", file=sys.stderr)
        print("       build_variant.py [--email addr] resume.json spec.json out.pdf", file=sys.stderr)
        sys.exit(2)
    src, spec_path, pdf_path = argv
    with open(src, encoding="utf-8") as f:
        data = json.load(f)["data"]
    if spec_path != "-":
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
    else:
        spec = {}
    try:
        build(data, spec, pdf_path, email_override=email_override)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
