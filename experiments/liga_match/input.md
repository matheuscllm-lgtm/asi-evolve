# Liga ↔ TCGplayer card matching — fuzzy scorer

## Problem

The Liga Pokémon scanner (`liga-cards-scanner`) compares a Brazilian marketplace
offer to a TCGplayer reference price. To do that it must decide **which** TCG
reference corresponds to a given Liga offer, using only the (card name, set name)
text on each side (the collector number is matched exactly in an earlier layer and
is out of scope here).

The current production logic (`src/matching/card_matcher.py`) normalizes both sides
and scores similarity with `difflib.SequenceMatcher`, weighting name 0.7 / set 0.3,
accepting a candidate when the combined score ≥ a fixed threshold (0.85). Mismatches
are expensive: a wrong match pairs an offer with the price of a *different* card,
producing a fake margin. A missed match drops a real deal.

## Objective

Evolve a matching scorer that **maximizes F1** on a labeled set of offer→candidate
cases (correct match vs. distractors, plus cases that must be rejected). Improve:

- **Normalization** (set aliases, accents, casing, `ex`/`EX`, `V-MAX`→`VMAX`,
  punctuation, "Pokémon" diacritics, trainer/energy suffixes).
- **Similarity scoring** (token-aware, order-insensitive, name/set weighting).
- **Acceptance threshold** (precision vs. recall trade-off).

Hard invariants (do NOT change the contract): the program is a single Python file
exposing exactly:

```python
def score_match(offer_name: str, offer_set: str, cand_name: str, cand_set: str) -> float:
    """Return a similarity in [0.0, 1.0] between a Liga offer and a TCG candidate."""
    ...

FUZZY_THRESHOLD: float  # acceptance cutoff in [0.0, 1.0]
```

The evaluator picks, for each offer, the candidate with the highest `score_match`;
it is *accepted* iff that best score ≥ `FUZZY_THRESHOLD`.

## Evaluation

- **Primary (`eval_score`)**: F1 over the labeled set (TP = accepted & correct;
  FP = accepted & wrong, or accepted when it should have been rejected; FN = a real
  match that was rejected).
- **Reported also**: precision, recall, accuracy, and per-case decisions.
- Pure-Python, offline, deterministic (`difflib` + stdlib). No network, no API.

## Target

Baseline (current production logic) scores well but leaves headroom on alias/accent
and threshold cases. Beat the baseline F1 without overfitting (the held-back intent:
keep precision high — a fake margin is worse than a missed deal).
