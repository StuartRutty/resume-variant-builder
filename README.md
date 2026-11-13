# resume-variant-builder

Build a per-role variant of your resume PDF by **reordering the bullets you
already have** — and nothing else. It cannot write, edit, add, or remove a
single word, by construction.

## Why

Tailoring a resume for a posting usually means quietly rewriting bullets
until the resume says things the original didn't. This tool takes the other
route: the most relevant *real* bullets lead each role, and everything else
stays exactly as written. Emphasis is presentation, not qualification — a
weak-fit role stays a weak-fit role; the variant just leads with its best
honest evidence.

## The rules it enforces

- **Bullets move only within their own role or project.** Every original
  bullet survives, verbatim, in every variant.
- **Employers are never reordered.** Chronology is factual, not
  presentational.
- **The summary renders verbatim.** Tailored narrative belongs in the cover
  letter, not in a rewritten summary.
- **Skill groups** may be reordered within the Skills section; the keywords
  inside a group are never edited.
- **No keyword injection.** If a posting demands something the resume
  doesn't have, that's a gap to state in the cover letter — this tool can't
  and won't paper over it.
- **The target role appears in the file name only.** Nothing is added to
  the PDF body.

A spec that names a role, bullet, or skill group that doesn't exist produces
a warning and is ignored — never a silent invention.

## Usage

Input is a [Reactive Resume](https://rxresu.me) JSON export.

```bash
pip install reportlab

# 1. See every role/project with numbered bullets
python3 build_variant.py --list resume.json

# 2. Write a spec (see the format below), then build
python3 build_variant.py resume.json spec.json Resume-Acme-DeliveryManager.pdf

# Optional: override the contact email for this variant
python3 build_variant.py --email replies@example.com resume.json spec.json out.pdf

# Unmodified render (empty spec)
python3 build_variant.py resume.json - out.pdf

# 3. Prove the variant only reordered
python3 verify.py resume.json spec.json
```

## Spec format

```json
{
  "role": "Acme Corp — Delivery Manager",
  "bullet_order": {
    "Northwind Logistics|Operations Lead": [2, 0, "backlog"],
    "Northwind Logistics|Support Engineer": ["runbook", 0]
  },
  "project_bullet_order": { "Warehouse migration runbook": [1, 0] },
  "skill_order": ["Delivery & Operations", "Support Systems", "Automation"]
}
```

Order entries are 0-based bullet indices (from `--list`) or substrings
matched case-insensitively against bullet text (first unplaced match wins).
Unlisted bullets keep their original relative order after the listed ones.

## Verification

`verify.py` proves, at the data level, that every list the spec touches
comes back as an exact permutation of the original — same items, same
wording. Because the renderer consumes exactly those lists, a variant PDF
built from a passing spec contains precisely the words of the unmodified
render in a different order. (In production use, the same check was also
run at the PDF level: variant vs. unmodified render, identical word
multisets, identical page count.)

## Example

`examples/` holds a fully fictional resume (`sample-resume.json` — any
resemblance to a real person is coincidental) and a spec written for a
fictional Delivery Manager posting. Run the commands above against them to
see the --list output, a built variant, and the verification pass.

## Limits, stated plainly

- **Specs are snapshot-bound.** If the resume changes (a bullet added or
  reworded), index-based entries can shift. Re-run `--list` and re-derive
  the spec; substring entries are more resilient, but never reuse a spec
  blindly across a resume change.
- **Length doesn't change.** Same bullets, same length — a two-page resume
  yields two-page variants. A one-page resume is a separate, human rewrite.
- **Build failures should fall back, not block.** If a variant build errors,
  use the unmodified resume.

---

*Built by Stuart Rutty for his own job search, where variants are prepared
per role by an agent pipeline under the rules in
[agent-ops-playbook](https://github.com/StuartRutty/agent-ops-playbook).
MIT licensed — see [LICENSE](LICENSE).*
