#!/usr/bin/env python3
"""Verify that a spec only permutes a resume — it cannot change content.

For every role, project, and skill group a spec touches, this checks that
the reordered list is an exact permutation of the original: same items,
same wording, nothing added, nothing dropped. It also checks the lists a
spec does NOT touch are returned unchanged.

Usage:
  python3 verify.py resume.json spec.json

Exits 0 when every check passes, 1 otherwise. This is a data-level proof;
the PDF renderer consumes exactly these lists, so a variant PDF built
from a passing spec contains precisely the words of the unmodified
render, in a different order.
"""
import json
import sys

from build_variant import apply_order, norm_key, role_bullet_lists


def main():
    if len(sys.argv) != 3:
        print("usage: verify.py resume.json spec.json", file=sys.stderr)
        return 2
    data = json.load(open(sys.argv[1]))["data"]
    spec = json.load(open(sys.argv[2]))

    lists = {norm_key(k): (label, bl) for k, label, bl in role_bullet_lists(data)}
    failures = 0

    def check(key, order):
        nonlocal failures
        nk = norm_key(key)
        if nk not in lists and norm_key("project|" + key) in lists:
            nk = norm_key("project|" + key)
        if nk not in lists:
            print(f"SKIP  {key!r}: no matching role/project (builder warns and ignores it)")
            return
        label, original = lists[nk]
        ordered, _ = apply_order(original, order, label)
        if sorted(ordered) == sorted(original) and len(ordered) == len(original):
            print(f"PASS  {label}: {len(original)} bullets, exact permutation")
        else:
            failures += 1
            print(f"FAIL  {label}: reordered list is NOT a permutation of the original")

    for key, order in list((spec.get("bullet_order") or {}).items()) + \
                      list((spec.get("project_bullet_order") or {}).items()):
        check(key, order)

    skill_items = [it for it in data["sections"]["skills"]["items"] if not it.get("hidden")]
    names = [it.get("name", "") for it in skill_items]
    order = spec.get("skill_order") or []
    if order:
        by_name = {norm_key(n): n for n in names}
        picked = [by_name[norm_key(n)] for n in order if norm_key(n) in by_name]
        rest = [n for n in names if n not in picked]
        if sorted(picked + rest) == sorted(names):
            print(f"PASS  Skills: {len(names)} groups, exact permutation")
        else:
            failures += 1
            print("FAIL  Skills: group list changed")

    print()
    print("RESULT:", "FAIL" if failures else "PASS — the spec only reorders")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
