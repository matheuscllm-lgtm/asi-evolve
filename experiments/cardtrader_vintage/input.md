# CardTrader vintage false-positive guard

## Problem

The CardTrader scanner (`card-trader-scanner`) compares a European cardtrader.com
offer against the US TCGplayer reference (via pokemontcg.io) and reports gross
arbitrage margins. The dangerous failure mode on **vintage / promo** cards is a
*fake* margin: pokemontcg.io prices the listing off the WRONG variant, so a cheap
card looks like a steal that does not exist.

`cardtrader_postprocess.py::classify_decision` is the mechanical guard that routes
each listing to `COMPRA` (clean auto-buy), `REVISAR` (manual validation), or `NAO`
(reject). It already catches several vintage traps:

- **Trainer/Galarian Gallery (`TG##`/`GG##`)** → pokemontcg.io matches a same-name
  secret/alt-art (5–10× price). Routed to `NAO`.
- **Alpha-suffix collector numbers (`153a`)** → promo/League variant (1st Place,
  Prerelease) invisible to pokemontcg.io (Lusamine sm5/153a: $160 vs real $13.77).
  Routed to `REVISAR`.
- **Unsupported sets** (`clb`, `wcd*`, `m24`, `phs`, …) → poor coverage → `REVISAR`.

But two **documented** vintage false-positive classes slip straight through to
`COMPRA` today, because the guard does **not** read the signals for them:

- **reverseHolofoil variant inflation** — a NON-foil vintage listing priced off the
  expensive holofoil reference. Confirmed cases (CHANGELOG 2026-05-18): Pichu
  Expedition #22 ($224.99 holofoil vs $50.41 reverseHolofoil), Tyranitar Aquapolis
  ($210 vs $69.99). The scanner exposes this as `low_conf_variant` ("Variante Baixa
  Confiança"), but it is only an advisory column — `classify_decision` ignores it.
- **Vintage suspect sets** — Legendary Collection (`lc`), Battle Academy
  (`ba-20`/`ba-22`): pokemontcg.io's reverseHolofoil fallback inflates 5–30×. These
  only surface in a separate sheet, never in the COMPRA/REVISAR decision.

## Objective

Evolve the guard to **maximize F1** at separating "must NOT auto-buy" listings
(vintage/variant/promo false positives → `REVISAR`/`NAO`) from clean genuine deals
(→ `COMPRA`), on a labeled set of real CardTrader cases. The headroom is recall on
the two missed classes above — **without** losing precision: a lazy "flag every
vintage card" rule wrongly rejects clean vintage deals (Charizard Base Set, Neo
Genesis) and is penalized. A wrong `COMPRA` (fake margin → real money lost) is the
expensive error; an over-flagged clean deal is a lost opportunity.

Hard invariants (do NOT change the contract): a single Python file exposing exactly:

```python
def classify_listing(row: dict) -> tuple[str, str]:
    """Return (decision, reason); decision in {"COMPRA", "REVISAR", "NAO"}."""
    ...
```

The evaluator treats `REVISAR`/`NAO` as "flagged" (predicted positive) and `COMPRA`
as "clean". Use ONLY the Python standard library (`re`, etc.) — no third-party
imports, no network. Conservative routing only: the guard may send a suspect
listing to `REVISAR`/`NAO`, never invent an auto-buy.

## Evaluation

- **Primary (`eval_score`)**: F1 over the labeled set (positive class = needs_guard).
  TP = inflated/promo/variant listing correctly flagged; FN = it slipped to `COMPRA`
  (expensive); FP = a clean genuine deal wrongly flagged (lost deal); TN = clean
  deal kept as `COMPRA`.
- **Reported also**: precision, recall, accuracy, per-case decisions.
- Pure-Python, offline, deterministic. Every case carries a healthy margin so only
  the vintage/variant/promo/set surface decides — margin/chase rules never fire here.

## Target

Baseline (faithful port of production `classify_decision`) scores **F1 ≈ 0.818**
(precision 1.0, recall 0.69) — it misses exactly the `low_conf_variant` and
vintage-suspect-set cases. The precise, portable fix (flag `low_conf_variant` OR a
suspect set, keep clean vintage) reaches F1 1.0 at precision 1.0. Beat the baseline
without dropping precision below 1.0; the resulting IDEA (not the raw LLM code) is
what gets ported back to `cardtrader_postprocess.py` behind tests.
