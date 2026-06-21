"""Offline, deterministic evaluator for the CardTrader vintage FP guard.

Contract (matches the ASI-Evolve engineer/eval.sh interface):
    python3 evaluator.py <candidate_code_file> <results_json_path>

Loads the candidate program (must expose `classify_listing(row) -> (decision,
reason)`), runs it over an embedded labeled set of real vintage / variant /
promo listings, and writes results.json with
`{"success": bool, "eval_score": <F1>, "temp": {...}}`.

No network, no API — pure stdlib. The labeled set mirrors documented CardTrader
gotchas (CHANGELOG 2026-05-18 + CLAUDE.md "Cuidados"):
  * TG##/GG## gallery -> pokemontcg.io matches a same-name secret rare (5-10x).
  * Alpha-suffix collector numbers (153a) -> promo/League variant (Lusamine).
  * Unsupported sets (clb, wcd*, m24) -> bad pokemontcg.io coverage.
  * reverseHolofoil variant inflation: a NON-foil vintage listing priced off the
    expensive holofoil reference (Pichu Expedition, Tyranitar Aquapolis) -> the
    `low_conf_variant` flag.  *** The production guard does NOT act on this. ***
  * Vintage "suspect sets" (Legendary Collection lc, Battle Academy ba-20/ba-22)
    -> reverseHolofoil fallback inflates 5-30x.  *** Guard does NOT act on this. ***

POSITIVE CLASS = "needs_guard": a listing that must NOT be auto-bought (a fake or
inflated margin). The guard predicts positive when it returns REVISAR or NAO, and
negative (clean) when it returns COMPRA. A wrong COMPRA on an inflated vintage
card is the expensive error (false margin -> real money). Over-flagging a clean
genuine deal is the opposite error (a lost real deal) — the clean-vintage cases
(Charizard Base, Neo) are precision traps that punish a lazy "flag all vintage"
rule: that rule reaches recall 1.0 but loses precision, while the precise rule
(flag low_conf_variant OR suspect-set, keep clean vintage) reaches F1 1.0.

Every case carries a HEALTHY margin (net >= 30%, profit >= R$100, chase TOP/MID,
validation OK) so the *only* discriminator is the vintage/variant/promo/set guard
— margin/chase rules never decide here, isolating exactly the surface we evolve.
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback

# Each case: a listing `row` (dict) + `needs_guard` (gold). needs_guard=True ->
# the listing is a vintage/variant/promo false-positive and must be routed to
# REVISAR or NAO (NOT COMPRA). needs_guard=False -> a clean genuine deal that
# must stay COMPRA.
def _row(**kw):
    base = dict(
        card_number="", set_code="", chase_tier="MID", net_margin=0.40,
        lucro_liq=200.0, validation_status="VALIDATED_REAL",
        trainer_gallery_potential_fp=False, low_conf_variant=False,
        set_era="modern",
    )
    base.update(kw)
    # Derive the TG/GG flag the way enrich_df does (from the card number).
    import re as _re
    if _re.match(r"^(?:TG|GG)\d+", str(base["card_number"]), _re.IGNORECASE):
        base["trainer_gallery_potential_fp"] = True
    return base


CASES = [
    # ---- NEEDS GUARD = True (vintage / variant / promo FP risk) ----
    # 0) Trainer Gallery subset -> inflated same-name secret rare.
    {"row": _row(card_number="TG12", set_code="swsh11", set_era="modern",
                 chase_tier="MID"), "needs_guard": True},
    # 1) Galarian Gallery subset (GG##) -> same class as TG## (PR #25).
    {"row": _row(card_number="GG05", set_code="swsh12pt5gg",
                 chase_tier="MID"), "needs_guard": True},
    # 2) Lusamine sm5/153a — alpha suffix = 1st Place League ($160 vs $13.77).
    {"row": _row(card_number="153a", set_code="sm5", set_era="modern",
                 chase_tier="TOP"), "needs_guard": True},
    # 3) Another alpha-suffix promo/staff variant.
    {"row": _row(card_number="022a", set_code="ces", chase_tier="MID"),
     "needs_guard": True},
    # 4) Unsupported set: Pokemon TCG Classic reprint (matched Team Rocket).
    {"row": _row(card_number="14", set_code="clb", chase_tier="TOP"),
     "needs_guard": True},
    # 5) Unsupported set: World Championship 2006 deck (non-tradeable on ptcg.io).
    {"row": _row(card_number="3", set_code="World Champ 2006 (wcd2006)",
                 chase_tier="MID"), "needs_guard": True},
    # 6) Unsupported set: McDonald's 2024 promo.
    {"row": _row(card_number="7", set_code="m24", chase_tier="MID"),
     "needs_guard": True},
    # 7) STALE validation -> price unsafe.
    {"row": _row(card_number="58", set_code="base1",
                 validation_status="STALE", chase_tier="TOP",
                 set_era="vintage"), "needs_guard": True},
    # 8) Anomalous markup tier.
    {"row": _row(card_number="100", set_code="par",
                 validation_status="MARKUP_TIER_ANOMALOUS", chase_tier="MID"),
     "needs_guard": True},

    # ---- NEEDS GUARD = True, but the PRODUCTION guard MISSES these (headroom) ----
    # 9) Legendary Collection (lc) — vintage suspect set, reverseHolofoil inflation.
    {"row": _row(card_number="20", set_code="Legendary Collection (lc)",
                 low_conf_variant=True, set_era="vintage", chase_tier="MID"),
     "needs_guard": True},
    # 10) Battle Academy 2020 (ba-20) — vintage suspect set.
    {"row": _row(card_number="5", set_code="ba-20",
                 low_conf_variant=True, set_era="vintage", chase_tier="MID"),
     "needs_guard": True},
    # 11) Pichu Expedition ecard1/22 — NON-foil listing priced off holofoil ref
    #     ($224.99 holofoil vs $50.41 reverseHolofoil): low_conf_variant.
    {"row": _row(card_number="22", set_code="Expedition (ecard1)",
                 low_conf_variant=True, set_era="vintage", chase_tier="MID"),
     "needs_guard": True},
    # 12) Tyranitar Aquapolis — same reverseHolofoil pattern ($210 vs $69.99).
    #     Number "H30" has a letter PREFIX, so ALPHA_SUFFIX_RE (^\d+[a-z]+) misses it.
    {"row": _row(card_number="H30", set_code="Aquapolis (ecard2)",
                 low_conf_variant=True, set_era="vintage", chase_tier="TOP"),
     "needs_guard": True},

    # ---- NEEDS GUARD = False (clean genuine deals — must stay COMPRA) ----
    # 13) Clean modern SIR, validated, high margin.
    {"row": _row(card_number="201", set_code="par", chase_tier="TOP",
                 net_margin=0.42, lucro_liq=200.0,
                 validation_status="VALIDATED_REAL"), "needs_guard": False},
    # 14) Clean modern MID.
    {"row": _row(card_number="88", set_code="scr", chase_tier="MID",
                 net_margin=0.35, lucro_liq=150.0), "needs_guard": False},
    # 15) Clean modern, validated markup.
    {"row": _row(card_number="045", set_code="jtg", chase_tier="TOP",
                 net_margin=0.50, lucro_liq=300.0,
                 validation_status="VALIDATED_MARKUP"), "needs_guard": False},
    # 16) PRECISION TRAP: clean VINTAGE Charizard Base Set — supported, normal
    #     number, foil-matched (NOT low_conf), NOT a suspect set. A lazy
    #     "flag all vintage" rule wrongly rejects this real deal.
    {"row": _row(card_number="4", set_code="Base Set (base1)", chase_tier="TOP",
                 net_margin=0.33, lucro_liq=400.0, low_conf_variant=False,
                 set_era="vintage"), "needs_guard": False},
    # 17) PRECISION TRAP: clean VINTAGE Neo Genesis — supported, clean variant.
    {"row": _row(card_number="17", set_code="Neo Genesis (neo1)",
                 chase_tier="MID", net_margin=0.36, lucro_liq=120.0,
                 low_conf_variant=False, set_era="vintage"),
     "needs_guard": False},
    # 18) Clean modern double-rare.
    {"row": _row(card_number="150", set_code="ssp", chase_tier="MID",
                 net_margin=0.40, lucro_liq=180.0), "needs_guard": False},
    # 19) Clean modern, top chase, validated.
    {"row": _row(card_number="174", set_code="pre", chase_tier="TOP",
                 net_margin=0.45, lucro_liq=260.0), "needs_guard": False},
]


def _load_candidate(path):
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "classify_listing"):
        raise AttributeError("candidate must define classify_listing(row)")
    return mod.classify_listing


def evaluate(path):
    classify = _load_candidate(path)
    tp = fp = fn = tn = 0
    decisions = []
    for i, case in enumerate(CASES):
        decision, reason = classify(dict(case["row"]))
        decision = str(decision).upper()
        flagged = decision != "COMPRA"            # REVISAR or NAO -> predicted positive
        gold = case["needs_guard"]
        if gold:
            if flagged:
                outcome = "TP"; tp += 1
            else:
                outcome = "FN"; fn += 1            # inflated vintage slipped to COMPRA
        else:
            if flagged:
                outcome = "FP"; fp += 1            # clean genuine deal lost
            else:
                outcome = "TN"; tn += 1
        decisions.append({"case": i, "decision": decision,
                          "flagged": flagged, "gold": gold,
                          "outcome": outcome, "reason": str(reason)[:120]})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(CASES)
    return {
        "eval_score": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "decisions": decisions,
    }


def main():
    code_file = sys.argv[1]
    out_json = sys.argv[2]
    t0 = time.time()
    try:
        metrics = evaluate(code_file)
        result = {
            "success": True,
            "eval_score": metrics["eval_score"],
            "combined_score": metrics["eval_score"],
            "eval_time": round(time.time() - t0, 4),
            "temp": metrics,
        }
    except Exception:
        result = {
            "success": False,
            "eval_score": 0.0,
            "combined_score": 0.0,
            "eval_time": round(time.time() - t0, 4),
            "temp": {"error": traceback.format_exc()},
        }
    with open(out_json, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "temp"}))


if __name__ == "__main__":
    main()
