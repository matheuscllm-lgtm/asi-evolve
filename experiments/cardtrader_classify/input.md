# CardTrader deal-decision classifier (COMPRA / REVISAR / NAO)

## Problem

The CardTrader scanner (`card-trader-scanner`) compares English, Near-Mint,
ungraded Pokémon singles on the European marketplace CardTrader against a US
TCGplayer reference price (pokemontcg.io) to surface EU→US arbitrage. The final
postprocess layer decides, per row, **whether a row is a buy** — returning one of:

- **COMPRA** — a clean deal: net gross margin and R$ profit above the floors, a
  liquid chase tier (TOP/MID), a supported set, no inflation/variant red flag.
- **REVISAR** — manual review: borderline margin, profit under the floor, a
  MODEST chase, an alpha-suffix promo/League variant (`091a`), an unsupported
  set, anomalous seller markup, or an unclean validation status.
- **NAO** — skip: missing data, a Trainer-Gallery `TG##` card (pokemontcg.io
  inflates these 5–10x → fake margin), STALE validation, a BULK chase, or a
  margin below the floor.

A wrong call is expensive: returning **COMPRA** on an inflated or mis-mapped row
hands the operator a **FAKE margin**. CardTrader's historical false-positive rate
without per-blueprint validation was **~76%**, so **precision on the COMPRA class
is the axis that matters most**. Dropping a real clean deal forgoes profit.

## Objective

Evolve the classifier to **maximize F1 on detecting COMPRA** on a labeled set,
**without inflating noise** — a false COMPRA on a flagged row is the costly error.
Known levers and a known gap:

- **Inflated gallery subsets.** Production guards `TG##` (Trainer Gallery) only.
  The structurally identical **`GG##` (Galarian Gallery)** subset has the SAME
  pokemontcg.io inflation but is **not** guarded — those rows currently slip
  through as a fake COMPRA. Recognising gallery subsets generally (route them
  away from COMPRA, as TG## is) raises precision.
- **Alpha-suffix variant rule** (`^\d+[a-zA-Z]+$`, e.g. `091a`) — promo/League
  variants blind to pokemontcg.io → REVISAR. Do not mistake a gallery code
  (`TG12`, `GG44`) for a plain alpha-suffix.
- **The floors** (`MIN_NET_MARGIN` 0.25, `MIN_LUCRO` R$50, `REVISAR_MIN_NET`
  0.20, `MODEST_MIN_NET` 0.30) and the **markup anomaly** cutoff (0.45).
- **Robust feature handling** (None margin/profit, mixed-case/padded codes,
  lowercase `tg05`/`gg09`) without breaking the guards.

Hard invariants (do NOT change the contract or relax these): the scanner is
English + Near-Mint + ungraded only; **margin is GROSS** (pure `(tcg − ct)/tcg`,
no embedded fees — the operator adds fees by hand); the R$50 profit floor and $10
price floor are relevance gates.

The program is a single pure-stdlib Python file exposing exactly:

```python
def classify_decision(features: dict) -> str:
    """Return one of: "COMPRA", "REVISAR", "NAO".

    features keys (all offline-derivable):
      net_margin: float | None   # gross net margin fraction (e.g. 0.35)
      lucro_liq: float | None    # R$ profit per unit
      chase_tier: str            # "TOP" | "MID" | "MODEST" | "BULK"
      card_num: str              # collector number ("199", "TG12", "091a", "GG67")
      set_code: str              # CardTrader set code
      validation_status: str     # "OK" | "STALE" | other
      markup_pct: float          # seller markup fraction (e.g. 0.06, 0.50)
    """
    ...

MIN_NET_MARGIN: float    # net-margin floor for COMPRA (default 0.25)
MIN_LUCRO: float         # R$ profit floor for COMPRA (default 50.0)
REVISAR_MIN_NET: float   # below -> NAO; [this, MIN_NET_MARGIN) -> REVISAR (default 0.20)
MODEST_MIN_NET: float    # MODEST chase min net to be REVISAR-worthy (default 0.30)
MARKUP_ANOMALY: float    # seller markup above this -> REVISAR (default 0.45)
```

Use ONLY the Python standard library — no third-party imports, no network, no
import of the CardTrader scanner package.

## Evaluation

- **Primary (`eval_score`)**: BINARY F1 over the COMPRA class.
  - TP = predicted COMPRA & gold COMPRA
  - FP = predicted COMPRA but gold REVISAR/NAO (the **costly** error)
  - FN = gold COMPRA but predicted REVISAR/NAO (a dropped deal)
- **Reported also** (in `temp`): COMPRA precision/recall, macro-F1 across the
  three labels, a 3×3 confusion summary, the constants used, per-case decisions.
- Cases cover CardTrader's false-positive classes: TG##/GG## gallery inflation,
  alpha-suffix variants, unsupported sets, markup anomaly, STALE/BULK, sub-floor
  margin/profit, plus clean COMPRA deals. Pure-Python, offline, deterministic.

## Target

The baseline (faithful production rules) scores a non-trivial COMPRA-F1 but
leaves headroom — it has no `GG##` guard, so it mis-buys Galarian Gallery cards.
Beat the baseline F1 **without overfitting** (generalise `GG##`, don't hardcode
specific numbers) and **keep COMPRA precision high** — a fake margin is worse than
a missed deal. Never relax the EN/NM/ungraded or gross-margin invariants.
