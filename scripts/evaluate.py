#!/usr/bin/env python3
"""
Reads supplier research and config.json, calculates real net profit per
sale for each candidate product, and writes a verdict report to
reports/report-YYYY-MM-DD.md.

Usage:
    python3 scripts/evaluate.py path/to/supplier-results.json [path/to/another.json ...]

    If no path is given, evaluates the most recent file in research/
    matching candidates-*.json (as written by the supplier-checker agent,
    expected to have merged product-scout candidates with supplier data).

Input JSON shape expected, a list of objects like:
    {
      "product": "Name",
      "retail_price": 39.99,
      "unit_cost": 8.50,
      "shipping_cost": 3.20,
      "shipping_days": 9,
      "source": "https://...",
      "confidence": "high" | "medium" | "low" | "not found"
    }

Any missing/"not found" numeric field makes that product SKIP with a clear
reason instead of guessing. Nothing here invents numbers.
"""

import json
import sys
import glob
import os
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
RESEARCH_DIR = os.path.join(ROOT_DIR, "research")
REPORTS_DIR = os.path.join(ROOT_DIR, "reports")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def find_latest_candidates_file():
    pattern = os.path.join(RESEARCH_DIR, "candidates-*.json")
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    return matches[-1]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_product(item, config):
    """Returns a dict with computed numbers and a verdict, never guessing
    at missing data."""
    name = item.get("product", "Unnamed product")
    reasons = []

    retail = item.get("retail_price")
    unit_cost = item.get("unit_cost")
    shipping_cost = item.get("shipping_cost")
    shipping_days = item.get("shipping_days")
    confidence = item.get("confidence", "not found")

    missing = []
    for field_name, value in [
        ("retail_price", retail),
        ("unit_cost", unit_cost),
        ("shipping_cost", shipping_cost),
        ("shipping_days", shipping_days),
    ]:
        if value is None or value == "not found" or not is_number(value):
            missing.append(field_name)

    if missing:
        return {
            "product": name,
            "verdict": "SKIP",
            "reasons": [f"Missing or unverified data: {', '.join(missing)}. "
                        f"Never guessing at these numbers."],
            "net_profit": None,
            "margin": None,
        }

    payment_fee = retail * config["payment_fee_pct"] + config["payment_fee_flat"]
    ad_cost = config["target_ad_cost_per_sale"]

    net_profit = retail - unit_cost - shipping_cost - payment_fee - ad_cost
    margin = net_profit / retail if retail else None

    verdict = "TEST"

    if shipping_days > config["max_shipping_days"]:
        verdict = "SKIP"
        reasons.append(
            f"Shipping takes {shipping_days} days, over the "
            f"{config['max_shipping_days']}-day max. Customers will "
            f"complain or chargeback."
        )

    if margin is not None and margin < config["min_net_margin"]:
        verdict = "SKIP" if verdict != "SKIP" else verdict
        reasons.append(
            f"Margin is {margin:.0%}, below the "
            f"{config['min_net_margin']:.0%} minimum you set."
        )

    if confidence in ("low", "not found"):
        if verdict != "SKIP":
            verdict = "VERIFY"
        reasons.append(
            f"Supplier data confidence is '{confidence}' — verify costs "
            f"and shipping time yourself before ordering samples."
        )

    if not reasons:
        reasons.append(
            f"Margin {margin:.0%}, shipping {shipping_days} days, "
            f"confidence {confidence}. Looks worth a real test."
        )

    return {
        "product": name,
        "verdict": verdict,
        "reasons": reasons,
        "net_profit": round(net_profit, 2),
        "margin": round(margin, 4) if margin is not None else None,
        "retail_price": retail,
        "unit_cost": unit_cost,
        "shipping_cost": shipping_cost,
        "shipping_days": shipping_days,
        "confidence": confidence,
        "source": item.get("source", "not provided"),
    }


def write_report(results, config, out_path):
    lines = []
    lines.append(f"# Product Evaluation Report — {date.today().isoformat()}")
    lines.append("")
    lines.append("Config used: " + json.dumps(config))
    lines.append("")

    order = {"TEST": 0, "VERIFY": 1, "SKIP": 2}
    results_sorted = sorted(results, key=lambda r: order.get(r["verdict"], 3))

    for r in results_sorted:
        lines.append(f"## {r['product']} — **{r['verdict']}**")
        lines.append("")
        if r["net_profit"] is not None:
            lines.append(f"- Retail price: ${r['retail_price']:.2f}")
            lines.append(f"- Unit cost: ${r['unit_cost']:.2f}")
            lines.append(f"- Shipping cost: ${r['shipping_cost']:.2f}")
            lines.append(f"- Shipping time: {r['shipping_days']} days")
            lines.append(f"- Estimated net profit per sale: ${r['net_profit']:.2f}")
            lines.append(f"- Margin: {r['margin']:.0%}")
            lines.append(f"- Supplier data confidence: {r['confidence']}")
            lines.append(f"- Source: {r['source']}")
        lines.append("")
        lines.append("Reasons:")
        for reason in r["reasons"]:
            lines.append(f"- {reason}")
        lines.append("")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))


def main():
    config = load_config()
    os.makedirs(REPORTS_DIR, exist_ok=True)

    paths = sys.argv[1:]
    if not paths:
        latest = find_latest_candidates_file()
        if not latest:
            print(
                "No input file given and no research/candidates-*.json "
                "found. Run product-scout and supplier-checker first, or "
                "pass a JSON file path as an argument."
            )
            sys.exit(1)
        paths = [latest]

    all_items = []
    for path in paths:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        all_items.extend(data)

    if not all_items:
        print("Input file(s) contained no products.")
        sys.exit(1)

    results = [evaluate_product(item, config) for item in all_items]

    out_path = os.path.join(REPORTS_DIR, f"report-{date.today().isoformat()}.md")
    write_report(results, config, out_path)

    print(f"Wrote {out_path}")
    for r in results:
        print(f"  {r['verdict']:6s} {r['product']}")


if __name__ == "__main__":
    main()
