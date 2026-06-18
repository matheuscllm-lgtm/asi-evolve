# COMC ↔ TCGplayer match — confidence-tier calibration

## Problem

The COMC scanner (`scanner-comc`) compares a card listed on COMC to its
TCGplayer reference price to spot arbitrage. Before any price comparison it must
decide **how confident** it is that a given COMC listing maps to a specific
TCGplayer product, and label the match with a **confidence tier**. Downstream,
matches below 0.90 are flagged `validar` (review manually) and a *wrong* match
is expensive: pairing a listing with the price of a **different** card invents a
fake margin. A missed match merely drops a real deal — so **precision matters**.

The current production logic (`comc_scanner/matcher.py::match`) computes match
features (did the set string resolve? is there a usable collector number? how
many products sit at that exact (set, number)? how well does the listing name
fuzzy-match the best / runner-up candidate?) and then assigns a tier:

- not `set_known` → **REJECT**
- `NAME_FLOOR = 45.0` (sanity floor against a mis-resolved set + coincidental number)
- number present AND exactly 1 product at (set, number): name_score ≥ 45 (or name
  absent) → **0.95** ("set+number exact")
- number present AND ≥ 2 products at (set, number): best-name disambiguation, name
  ≥ 45 → **0.90**
- else, among candidates in the set: number present AND name_score ≥ 90 → **0.85**
  ("name fuzzy within set")
- else: no number AND name_score ≥ 92 AND (name_score − runner_up) ≥ 3 → **0.70**
- otherwise → **REJECT**

`name_score` / `runner_score` are difflib-style fuzzy ratios on a 0–100 scale,
like `comc_scanner.normalize.fuzzy_ratio`. Pipeline invariants from
`scanner-comc/CLAUDE.md`: piso de preço **US$ 10**, **NM-only**, **English-only**,
holofoil subtype preferred — those gate the listings; this experiment evolves the
**confidence calibration** that runs on the survivors.

## Objective

Evolve the tier-assignment so it **maximizes F1** (and per-tier calibration) on a
labeled set of feature → gold cases, without overfitting. Improve:

- **Thresholds** — the `NAME_FLOOR` sanity floor (45), the strong-name cutoff (90),
  the very-strong cutoff (92), and the runner-up `NAME_GAP` (3).
- **Tier boundaries** — when a number-but-no-exact-hit match deserves 0.85, when a
  no-number match deserves 0.70, and when a case should simply REJECT.
- **Precision vs. recall** — a *wrong accept* invents a fake margin, so a distractor
  sitting just over a cutoff must still reject; a true match sitting just under a
  cutoff is recall left on the table.

Hard invariants (do NOT change the contract): the program is a single pure-stdlib
Python file exposing exactly:

```python
def assign_confidence(features: dict) -> float | None:
    """Return the confidence tier (0.95/0.90/0.85/0.70 or any value in [0,1])
    for a candidate COMC->TCG match, or None to REJECT. `features` keys:
      set_known: bool
      number_present: bool
      exact_count: int        # products at exact (set, number): 0, 1, or >=2
      name_score: float       # 0..100 fuzzy ratio of best candidate name
      runner_score: float     # 0..100 fuzzy ratio of runner-up
    """
```

plus module-level threshold constants the evolver can tune:
`NAME_FLOOR`, `NAME_STRONG` (90), `NAME_VERY_STRONG` (92), `NAME_GAP` (3), and the
tier values `TIER_EXACT` (0.95), `TIER_DISAMBIG` (0.90), `TIER_FUZZY_NUM` (0.85),
`TIER_NO_NUMBER` (0.70). Use ONLY the Python standard library — no third-party
imports, no network.

## Evaluation

- **Primary (`eval_score`)**: F1 of ACCEPT-vs-REJECT over the labeled set. accept =
  `assign_confidence` returned a confidence (not None). TP = accepted & gold is a
  real match; FP = accepted & gold is None (a wrong accept); FN = rejected & gold
  is a real match; TN = rejected & gold None.
- **Reported also (`temp`)**: precision, recall, accuracy, per-tier **calibration**
  (for each predicted tier, the fraction of those cases whose gold was a real match
  — higher = better-calibrated), the threshold constants used, and per-case
  decisions (incl. whether the predicted tier matched the gold tier).
- Pure-Python, offline, deterministic (stdlib only). No network, no API.

## Target

The baseline (current production logic) scores a solid-but-imperfect F1 and leaves
genuine headroom: true matches whose name sits just under the 90/92 cutoffs are
rejected (recall headroom), while a few distractors are correctly rejected only
because of the `NAME_GAP` check (precision headroom). Beat the baseline F1 without
overfitting — keep precision high, because a fake margin is worse than a missed deal.
