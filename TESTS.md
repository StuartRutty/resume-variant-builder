# Unit Test Suite (`tests/`)

Stdlib-only `unittest` test suite for `build_variant.py` and `verify.py`. No external test dependencies are required; tests that exercise ReportLab PDF rendering are guarded with `@unittest.skipUnless(HAS_REPORTLAB, ...)` so the suite passes cleanly both with and without `reportlab` installed.

## How to Run

From the repository root:

```bash
# Run with system Python (skips ReportLab-dependent PDF build tests)
python3 -m unittest discover -s tests

# Verbose output
python3 -m unittest discover -s tests -v

# Run with an environment that has reportlab installed (runs all tests)
/tmp/rvb-venv/bin/python -m unittest discover -s tests -v
```

## Coverage Map

| Module | Tests | ReportLab-guarded | What It Covers |
|---|---:|---:|---|
| `tests/test_bullets.py` | 12 | 0 | `bullets()` HTML extraction (`<li>`/`<p>` attributes, uppercase/mixed-case tags, `<br>` to space, nested inline tags stripped, HTML entities unescaped, plain-text fallback, empty/whitespace inputs, `<li>` precedence); `norm_key()`, `esc()`, `role_bullet_lists()`. |
| `tests/test_apply_order.py` | 10 | 0 | `apply_order()` integer indices, case-insensitive substring matching (first unplaced match wins), booleans rejected instead of treated as `1`/`0`, non-list order values, empty/whitespace strings, out-of-range indices and unmatched substrings, already-placed indices not duplicated, exact permutation invariant (`sorted` and `Counter` equality) across edge cases. |
| `tests/test_build.py` | 13 | 11 | `norm_key()` collisions in skill ordering (both groups survive across single, repeated, and over-repeated `skill_order` entries); duplicate role keys (2x and 3x) and duplicate project keys in `build()` warning without cross-applying bullets; `heading()` escaping order (both direct closure check without ReportLab and rendered PDF check with ReportLab); summary fallback without `<li>`/`<p>` tags and with HTML entities (not double-escaped); email override; missing-`reportlab` `ImportError`. |
| `tests/test_verify.py` | 7 | 0 | `verify.py` skill check with exact and normalized duplicate skill group names (single, repeated, over-repeated, and hidden duplicates); role/project permutation checks, bare project name matching, unknown key `SKIP`, CLI exit code `2` on bad args, and `examples/sample-resume.json` + `examples/sample-spec.json`. |
| `tests/test_encoding.py` | 4 | 2 | UTF-8 reading of non-ASCII resume and spec JSONs (curly quotes `“”’`, em dashes `—`, accented characters) under a forced ASCII default file locale (`LC_ALL=C`, `LANG=C`, `PYTHONCOERCECLOCALE=0`, `PYTHONUTF8=0`, `PYTHONIOENCODING=utf-8`) across `build_variant.py --list`, `verify.py`, and `build_variant.py` (with spec and with `-`). |

All fixtures are minimal Reactive Resume dicts/temp JSON files built inside `tests/helpers.py` and the test modules themselves.

## Testing Approaches & Seams

- **Stdlib-only PDF text extraction (`tests/helpers.py:extract_pdf_text`)**: Reads generated PDF bytes directly, decodes `/ASCII85Decode` (`base64.a85decode(..., adobe=True)`) and `/FlateDecode` (`zlib.decompress`) content streams, parses PDF literal strings inside `Tj`/`TJ` operators (including octal escapes like `\227` for em dash), decodes them as `cp1252` (PDF `WinAnsiEncoding` used by ReportLab's Helvetica fonts), and joins inline fragments within each `T*`/`ET` line boundary.
- **Duplicate role/project keys (`tests/test_build.py`)**: Tested end-to-end through `build()` into a temporary PDF (ReportLab-guarded), checking both stderr warnings and the extracted PDF text to prove every bullet from each colliding role/project appears exactly once in its own original order.
- **`heading()` escaping order (`tests/test_build.py`)**: Tested via two complementary tests:
  1. `TestHeadingEscapingOrderNoReportLab.test_heading_uppercases_before_escaping_entities` binds `build_variant.build`'s real nested `heading` code object to stub `Paragraph`/`HRFlowable` classes (runs even without ReportLab) and asserts the exact XML markup passed to `Paragraph` is `"RESEARCH &amp; DEVELOPMENT"` rather than `"RESEARCH &AMP; DEVELOPMENT"` (and lowercase `&lt;`/`&gt;` for `<`/`>`).
  2. `TestBuildWithReportLab.test_heading_with_ampersand_renders_plain_ampersand_in_pdf` binds the same nested `heading` code object to real ReportLab classes, builds a temp PDF with `SimpleDocTemplate`, and asserts the extracted PDF text contains `"RESEARCH & DEVELOPMENT"` with no `&AMP;` or `&amp;`.
- **`verify.py` (`tests/test_verify.py`)**: Driven primarily in-process via `verify.main()` with temporary JSON files and patched `sys.argv` for speed and clean output capture, supplemented by `subprocess.run` CLI tests for exit codes and sample fixtures.

## Observations (Found, Not Modified)

Per project rules, `build_variant.py` and `verify.py` were not modified. Notable observations:

1. **`build()` hardcodes section heading strings**: All five `heading(...)` calls in `build_variant.py` pass literal strings (`"Summary"`, `"Experience"`, `"Projects"`, `"Education"`, `"Skills"`) rather than reading `sections[*]["name"]` from the JSON. Because no resume JSON input can send an `"&"` into `heading()`, pinning the escaping-order fix required invoking `build()`'s nested `heading` code object directly. Furthermore, ReportLab 5.1.1's lenient XML parser happens to render `&AMP;` as `&` without raising an error, so asserting the raw markup passed to `Paragraph` (`&amp;` vs `&AMP;`) is what reliably guards against a regression on stricter parsers or future ReportLab releases.
2. **`verify.py` did not mirror `build_variant.py`'s duplicate role-key guard** — FIXED 2026-11-24 (after this suite landed, at the owner's direction): `build_variant.py` tracks colliding normalized role/project keys in `dup_keys` and leaves every colliding entry untouched, whereas `verify.py` built `lists` with `{norm_key(k): ...}` (last entry wins), so a spec referencing a duplicated role key was checked only against the last colliding entry rather than skipped as duplicate. `verify.py` now builds the same dup-key set and prints `SKIP ... duplicate role/project key` for such keys; the behavior is pinned by `tests/test_verify.py::test_duplicate_role_and_project_keys_skip_not_pass_against_last`. The same pass also corrected the `verify.py` docstring, which claimed untouched lists are checked; they are not (the builder returns them unchanged by construction).

## Latest Run Results

- **System Python (`python3` 3.12.3, without `reportlab`)**: **46 tests** — **33 passed**, **13 skipped** (all 13 skipped with reason `reportlab is not installed`: 11 in `tests/test_build.py`, 2 in `tests/test_encoding.py`), **0 failures**, **0 errors**.
- **Venv Python (`/tmp/rvb-venv/bin/python`, with `reportlab` 5.1.1)**: **46 tests** — **46 passed**, **0 skipped**, **0 failures**, **0 errors**.
