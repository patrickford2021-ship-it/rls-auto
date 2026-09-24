---
description: Run product-scout, then supplier-checker, then evaluate.py, and summarize the top 3
---

Run the full product research pipeline:

1. Call the `product-scout` subagent to find candidate products (or, if
   the user specified a niche/topic in "$ARGUMENTS", pass that along as
   the focus). It saves to `research/candidates-YYYY-MM-DD.json`.
2. Call the `supplier-checker` subagent on the resulting candidate list to
   fill in real supplier data (cost, shipping, stock, ratings) for each
   candidate.
3. Run `python3 scripts/evaluate.py` (no arguments needed — it will pick
   up today's `research/candidates-*.json` automatically) to generate a
   verdict report in `reports/`.
4. Read the generated report and summarize, in plain English, the top 3
   products by verdict (prefer TEST, then VERIFY, then note if everything
   came back SKIP and why). For each, give: product name, estimated net
   profit per sale, margin, shipping time, and the one-line reason for its
   verdict.
5. Tell the user the clear next step (e.g. "order a sample of [product]"
   or, if everything was SKIP, "none of these cleared the bar — want me to
   run this again with a different niche?").

Be honest if the results are weak — don't dress up a bad batch of
candidates as promising.
