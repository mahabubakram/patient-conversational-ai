#!/usr/bin/env python3
"""
Offline evaluation runner:
- Loads YAML cases under eval/cases/*.yaml
- Plays turns against /api/chat with unique session_ids
- Computes simple metrics and writes eval/report.json

Usage:
  python eval/run_eval.py --base-url http://localhost:8000
  python eval/run_eval.py --fast    # only the first N cases
"""

import argparse
import glob
import json
import os
from typing import Any, Dict, List

import httpx
import yaml

DEFAULT_BASE_URL = "http://localhost:8000"
CASES_GLOB = os.path.join(os.path.dirname(__file__), "cases", "*.yaml")
TIMEOUT = 8.0

def load_cases(limit: int | None = None) -> List[Dict[str, Any]]:
    paths = sorted(glob.glob(CASES_GLOB))
    cases: List[Dict[str, Any]] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
            if isinstance(data, list):
                cases.extend(data)
    if limit is not None:
        cases = cases[:limit]
    return cases

def post_chat(client: httpx.Client, base_url: str, session_id: str, message: str) -> Dict[str, Any]:
    url = f"{base_url}/api/chat"
    r = client.post(url, params={"session_id": session_id}, json={"message": message}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def eval_case(client: httpx.Client, base_url: str, case: Dict[str, Any]) -> Dict[str, Any]:
    sid = f"eval-{case['id']}"
    last = {}
    for msg in case["turns"]:
        last = post_chat(client, base_url, sid, msg)

        # DEBUG: print raw when something’s missing
        if "status" not in last or not last.get("disclaimer"):
            print(f"[DEBUG] raw response for {case['id']}: {last}")

    got_status = last.get("status")
    got_cats = [c.lower() for c in last.get("categories", [])]
    disclaimer = (last.get("disclaimer") or "").lower()

    expect_status = case.get("expect_status")
    expect_cats_any = [c.lower() for c in case.get("expect_categories_any", [])]

    status_ok = (got_status == expect_status)
    cats_ok = True
    if expect_cats_any:
        cats_ok = any(any(ec in g for g in got_cats) for ec in expect_cats_any)

    disc_ok = ("not a diagnosis" in disclaimer and "not for emergencies" in disclaimer) or ("not a diagnosis" in disclaimer and "emergency" in disclaimer)

    return {
        "id": case["id"],
        "turns": case["turns"],
        "expect_status": expect_status,
        "got_status": got_status,
        "status_ok": status_ok,
        "expect_categories_any": expect_cats_any,
        "got_categories": got_cats,
        "categories_ok": cats_ok,
        "disclaimer_ok": disc_ok,
        "raw": last,  # keep for debugging
    }

def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(results)
    acc_status = sum(r["status_ok"] for r in results) / max(1, n)
    acc_cats = sum(r["categories_ok"] for r in results if r["expect_categories_any"]) / max(1, sum(bool(r["expect_categories_any"]) for r in results))
    acc_disc = sum(r["disclaimer_ok"] for r in results) / max(1, n)

    return {
        "total_cases": n,
        "status_accuracy": round(acc_status, 3),
        "category_hit_rate": round(acc_cats, 3),
        "disclaimer_coverage": round(acc_disc, 3),
    }

def print_table(results: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    # Minimal pretty table without extra deps
    headers = ["id", "expect", "got", "status✓", "cats✓", "disc✓"]
    rows = []
    for r in results:
        rows.append([
            r["id"],
            r["expect_status"],
            r["got_status"],
            "✓" if r["status_ok"] else "✗",
            "-" if not r["expect_categories_any"] else ("✓" if r["categories_ok"] else "✗"),
            "✓" if r["disclaimer_ok"] else "✗",
        ])
    colw = [max(len(str(x)) for x in col) for col in zip(*([headers] + rows))]
    def fmt_row(row): return "  ".join(str(x).ljust(w) for x, w in zip(row, colw))

    print(fmt_row(headers))
    print("-" * (sum(colw) + 2 * (len(headers) - 1)))
    for row in rows:
        print(fmt_row(row))
    print("\nSummary:")
    for k, v in summary.items():
        print(f"- {k}: {v}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--fast", action="store_true", help="Run only the first 5 cases")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "report.json"))
    args = ap.parse_args()

    cases = load_cases(limit=5 if args.fast else None)
    if not cases:
        print("No cases found under eval/cases/*.yaml")
        return

    results: List[Dict[str, Any]] = []
    with httpx.Client() as client:
        for c in cases:
            try:
                res = eval_case(client, args.base_url, c)
                results.append(res)
            except Exception as e:
                results.append({
                    "id": c["id"],
                    "error": str(e),
                    "status_ok": False,
                    "categories_ok": False,
                    "disclaimer_ok": False,
                    "expect_status": c.get("expect_status"),
                    "got_status": None,
                    "raw": {},
                    "turns": c.get("turns", []),
                    "expect_categories_any": c.get("expect_categories_any", []),
                })

    summary = summarize(results)

    # Write JSON report for CI / diffing
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

    print_table(results, summary)

    # Optional CI gating: non-zero exit if status accuracy < 0.9
    target = 0.90
    if summary["status_accuracy"] < target:
        print(f"\nStatus accuracy below target ({summary['status_accuracy']} < {target})")
        # exit non-zero to fail CI (comment this out if you don't want gating)
        # raise SystemExit(1)

if __name__ == "__main__":
    main()



# Explanation & tips
#
# Schema: Every case has id, turns (list of user messages), and expect_status. Optional expect_categories_any lets you check that the assistant tagged the case with at least one of the expected labels.
#
# Session handling: Each case uses a unique session_id=eval-<id> so multi-turn flows keep context.
#
# Metrics (key ones):
#
# status_accuracy: fraction of cases where got == expect_status.
#
# category_hit_rate: fraction of cases (that specify categories) where at least one expected tag appears.
#
# disclaimer_coverage: fraction where the disclaimer contains “not a diagnosis” and “emergency”.
#
# Extending:
#
# Add more YAML files (e.g., respiratory.yaml, gi.yaml).
#
# Add fields like expect_next_step_contains or allow_status_any_of if you want flexible assertions.
#
# If you later expose debug retrieval info from the API, we can add a retrieval coverage check (e.g., “at least one of top-k chunks had the expected topic”).
#
# In CI: keep the JSON report checked in for a while to compare before/after; uncomment the SystemExit(1) to gate merges on status_accuracy