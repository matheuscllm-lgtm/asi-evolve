# MYP deal / false-positive classifier

## Problem

The MYP Cards scanner (`myp-arbitrage-scanner`) scrapes a Brazilian Pokémon
marketplace and cross-references each offer with a TCGplayer reference price
(pokemontcg.io, the ground truth) to surface domestic arbitrage. The last layer
of that pipeline decides, per row, **whether an MYP→TCG row is a CLEAN deal or a
false positive** — and if false, *which kind*:

- **CLEAN** — an EN, Near-Mint offer with a real gross margin, an in-range
  collector number, and a declared TCG price consistent with the last real sale.
- **SUPRANUMERARY** — collector number exceeds the set denominator
  (`card_num > set_total`, e.g. `226/217`). MYP mislabels these IR/SIR/SAR
  variants as "Comum"; the margin is suspect (variant misclassification).
- **TCG-SUSPECT** — the declared TCG price dwarfs the last observed sale
  (`declared_tcg / last_sale` large). A probable `.estat-tcg` mis-map that
  invents a fake margin.
- **REJECT** — fails a hard invariant (not Near-Mint, or not English) or falls
  below the gross-margin floor.

A wrong call is expensive: marking a supranumerary or TCG-suspect row **CLEAN**
hands the operator a **fake margin**. Dropping a real clean deal forgoes profit.

## Objective

Evolve the classifier to **maximize F1 on detecting CLEAN deals** on a labeled
set, without inflating noise — a false "clean" on a flagged/reject row is the
costly error, so **precision on the CLEAN class matters most**. Levers to improve:

- **The margin floor** (`MIN_MARGIN`, gross fraction, production default 0.30).
- **The supranumerary rule** (`card_num > set_total` and any refinement, e.g.
  guarding against unparseable / zero denominators).
- **The TCG-suspect ratio** (`SUSPECT_RATIO`, declared/last_sale cutoff;
  production uses 10.0) and the precedence/order of the checks.
- **Robust feature handling** (None `last_sale`, mixed-case / padded condition &
  language strings) without breaking the hard invariants.

Hard invariants (do NOT change the contract or relax these):

- **NM-only** — condition must be exactly Near-Mint (`"NM"`), matched exactly
  (substring matching historically leaked `"SP"`).
- **EN-only** — language must be English (`"EN"`); domestic arbitrage targets the
  English TCGplayer reference.
- **Gross margin** — margin is the pure gross fraction `(tcg − myp) / myp`, with
  **no embedded fees**; the R$50 floor is an upstream relevance filter, not part
  of this contract.

The program is a single pure-stdlib Python file exposing exactly:

```python
def classify_deal(features: dict) -> str:
    """Return one of: "clean", "supranumerary", "tcg_suspect", "reject".

    features keys (all offline-derivable):
      margin: float            # gross margin fraction (e.g. 0.42)
      condition: str           # "NM", "SP", ...
      language: str            # "EN", "PT", ...
      card_num: int            # collector number
      set_total: int           # set size denominator
      declared_tcg: float      # TCG price declared by source
      last_sale: float | None  # last observed sale (suspect signal)
      rarity: str
    """
    ...

MIN_MARGIN: float    # gross-margin floor (default 0.30)
SUSPECT_RATIO: float # declared_tcg / last_sale suspect cutoff (default 10.0)
```

Use ONLY the Python standard library — no third-party imports, no network, no
import of the MYP scanner package.

## Evaluation

- **Primary (`eval_score`)**: BINARY F1 over the CLEAN class.
  - TP = predicted clean & gold clean
  - FP = predicted clean but gold is flagged/reject (the **costly** error)
  - FN = gold clean but predicted flagged/reject (a dropped deal)
- **Reported also** (in `temp`): CLEAN precision/recall, macro-F1 across all four
  labels, a 4×4 confusion summary, the constants used, and per-case decisions.
- Several cases derive from the scanner's offline fixtures
  (`test_v5_8_offline.py`): Jirachi (75× → suspect), borderline 9.5× (NOT
  suspect), Psyduck pagination (clean), Darumaka 097/086 (supranumerary). Plus
  headroom cases: an EN-NM high-margin clean, an SP/PT row that must reject, a
  `card_num > set_total` supranumerary, a declared≫last_sale suspect, margins
  just under/over `MIN_MARGIN`, and a borderline suspect ratio.
- Pure-Python, offline, deterministic. No network, no API.

## Target

The baseline (faithful production rules) scores a non-trivial F1 but leaves
headroom on the boundary cases (margin & ratio borders, supranumerary traps,
None/dirty features). Beat the baseline F1 **without overfitting** — keep CLEAN
precision high (a fake margin is worse than a missed deal) and never relax the
NM-only / EN-only invariants.
