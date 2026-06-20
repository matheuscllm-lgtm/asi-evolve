"""Offline, deterministic evaluator for the CardTrader deal-decision classifier.

Contract (matches the ASI-Evolve engineer/eval.sh interface):
    python3 evaluator.py <candidate_code_file> <results_json_path>

Loads the candidate program (must expose `classify_decision(features) -> str` and
the tunable constants MIN_NET_MARGIN, MIN_LUCRO, REVISAR_MIN_NET, MODEST_MIN_NET,
MARKUP_ANOMALY), runs it over an embedded labeled set of CardTrader→TCG rows, and
writes `results.json` with `{"success": bool, "eval_score": <COMPRA-F1>, ...}`.

No network, no API — pure stdlib. Cases derive from CardTrader's known
false-positive classes (cardtrader_postprocess.py + memory):
  - TG## Trainer Gallery: pokemontcg.io inflates 5–10x → NAO.
  - GG## Galarian Gallery: the SWSH-era sibling subset with the SAME inflation,
    but production has NO guard for it → it slips through as a fake COMPRA. This
    is the headroom: a classifier that also routes GG## away from COMPRA raises
    COMPRA precision (the costly axis) without touching the genuine deals.
  - alpha-suffix promo/League variant (091a) → REVISAR.
  - unsupported set coverage → REVISAR.
  - markup anomaly, STALE, BULK, sub-floor margin/lucro → REVISAR/NAO.

Primary metric (eval_score): BINARY F1 of detecting COMPRA.
  TP = predicted COMPRA & gold COMPRA
  FP = predicted COMPRA but gold REVISAR/NAO  (the COSTLY error: fake margin)
  FN = gold COMPRA but predicted REVISAR/NAO  (a dropped real deal)
A false COMPRA hands the operator a fake margin, so COMPRA precision matters most.
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback

LABELS = ("COMPRA", "REVISAR", "NAO")

# Each case: a feature dict (offline-derivable) + the gold label.
# Keys: net_margin, lucro_liq, chase_tier, card_num, set_code,
#       validation_status, markup_pct.
_SYNTHETIC_CASES = [
    # ── Genuine COMPRA (clean strong deals) ──────────────────────────────────
    {"name": "Charizard ex 199/165 clean",
     "features": {"net_margin": 0.35, "lucro_liq": 140.0, "chase_tier": "TOP",
                  "card_num": "199", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "COMPRA"},
    {"name": "Pikachu 058/078 clean",
     "features": {"net_margin": 0.28, "lucro_liq": 85.0, "chase_tier": "MID",
                  "card_num": "058", "set_code": "pgo2", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "COMPRA"},
    {"name": "Giratina V 186/196 clean",
     "features": {"net_margin": 0.52, "lucro_liq": 220.0, "chase_tier": "TOP",
                  "card_num": "186", "set_code": "lot", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "COMPRA"},
    {"name": "Gengar ex 156/091 markup-ok",
     "features": {"net_margin": 0.30, "lucro_liq": 75.0, "chase_tier": "MID",
                  "card_num": "156", "set_code": "sfa", "validation_status": "OK",
                  "markup_pct": 0.20}, "gold": "COMPRA"},
    # ── GG## Galarian Gallery — THE HEADROOM (baseline mis-buys these) ────────
    # Same inflation class as TG##, but production has no GG guard → baseline
    # falls through to COMPRA (a fake margin). Gold = NAO (route like TG##).
    {"name": "Rayquaza GG67 (galarian gallery)",
     "features": {"net_margin": 0.55, "lucro_liq": 260.0, "chase_tier": "TOP",
                  "card_num": "GG67", "set_code": "ast", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Mewtwo GG44 (galarian gallery)",
     "features": {"net_margin": 0.40, "lucro_liq": 110.0, "chase_tier": "MID",
                  "card_num": "GG44", "set_code": "bri", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Lugia GG09 lowercase gg",
     "features": {"net_margin": 0.48, "lucro_liq": 175.0, "chase_tier": "TOP",
                  "card_num": "gg09", "set_code": "sit", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    # ── TG## Trainer Gallery (baseline already routes to NAO) ─────────────────
    {"name": "Lucario TG12 (trainer gallery)",
     "features": {"net_margin": 0.60, "lucro_liq": 300.0, "chase_tier": "TOP",
                  "card_num": "TG12", "set_code": "ast", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Giratina tg05 lowercase",
     "features": {"net_margin": 0.48, "lucro_liq": 130.0, "chase_tier": "MID",
                  "card_num": "tg05", "set_code": "lo, ", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    # ── Alpha-suffix promo/League variant → REVISAR (baseline handles) ────────
    {"name": "Iono 091a (alpha suffix variant)",
     "features": {"net_margin": 0.45, "lucro_liq": 150.0, "chase_tier": "TOP",
                  "card_num": "091a", "set_code": "paf", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    {"name": "Pikachu 022a (alpha suffix)",
     "features": {"net_margin": 0.33, "lucro_liq": 90.0, "chase_tier": "MID",
                  "card_num": "022a", "set_code": "swsh", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    # ── Unsupported set → REVISAR (baseline handles) ─────────────────────────
    {"name": "Snorlax 067 unsupported set (cel)",
     "features": {"net_margin": 0.40, "lucro_liq": 100.0, "chase_tier": "MID",
                  "card_num": "067", "set_code": "cel", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    # ── Markup anomaly → REVISAR ─────────────────────────────────────────────
    {"name": "Sylveon 211 markup 50%",
     "features": {"net_margin": 0.50, "lucro_liq": 160.0, "chase_tier": "TOP",
                  "card_num": "211", "set_code": "evs", "validation_status": "OK",
                  "markup_pct": 0.50}, "gold": "REVISAR"},
    # ── NAO outs ─────────────────────────────────────────────────────────────
    {"name": "Magikarp 080 BULK",
     "features": {"net_margin": 0.40, "lucro_liq": 100.0, "chase_tier": "BULK",
                  "card_num": "080", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Eevee 045 low margin 15%",
     "features": {"net_margin": 0.15, "lucro_liq": 30.0, "chase_tier": "MID",
                  "card_num": "045", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Umbreon 095 STALE",
     "features": {"net_margin": 0.60, "lucro_liq": 250.0, "chase_tier": "TOP",
                  "card_num": "095", "set_code": "evs", "validation_status": "STALE",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Snorlax 050 MODEST under 30%",
     "features": {"net_margin": 0.25, "lucro_liq": 60.0, "chase_tier": "MODEST",
                  "card_num": "050", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    {"name": "Charmander missing margin",
     "features": {"net_margin": None, "lucro_liq": None, "chase_tier": "MID",
                  "card_num": "004", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "NAO"},
    # ── REVISAR gray zone ────────────────────────────────────────────────────
    {"name": "Lapras 041 borderline net 22%",
     "features": {"net_margin": 0.22, "lucro_liq": 65.0, "chase_tier": "TOP",
                  "card_num": "041", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    {"name": "Drowzee 075 lucro under floor",
     "features": {"net_margin": 0.30, "lucro_liq": 40.0, "chase_tier": "MID",
                  "card_num": "075", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    {"name": "Haunter 060 MODEST high net",
     "features": {"net_margin": 0.38, "lucro_liq": 95.0, "chase_tier": "MODEST",
                  "card_num": "060", "set_code": "mew", "validation_status": "OK",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
    {"name": "Abra 063 validation not-OK",
     "features": {"net_margin": 0.35, "lucro_liq": 80.0, "chase_tier": "MID",
                  "card_num": "063", "set_code": "mew", "validation_status": "MARKUP",
                  "markup_pct": 0.06}, "gold": "REVISAR"},
]


def _load_real_cases():
    """Enrich the eval with REAL labeled rows from recent CardTrader scans.

    `real_cases.json` (next to this evaluator) is generated from real
    card-trader-scanner outputs and labeled by the operator. It grounds the
    synthetic FP classes (TG/GG/alpha-suffix/unsupported-set/markup) in actual
    scan rows and surfaces NEW classes the synthetic set misses (e.g.
    supranumerary collector#, low-confidence holo variant, vintage LC/BA-20
    inflation). The file is git-ignored (deal data stays local). Absent ->
    synthetic only, so the eval still runs on a clean checkout.

    Each entry mirrors a synthetic case: {"name", "features": {...}, "gold"}.
    Only entries with a valid gold label and a dict of features are kept.
    """
    import json as _json
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "real_cases.json")
    if not _os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            data = _json.load(fh)
        return [c for c in data if c.get("gold") in LABELS and isinstance(c.get("features"), dict)]
    except Exception:
        return []


# Synthetic cases keep the hard FP-class invariants (TG/GG route to NAO, alpha
# suffix to REVISAR) and boundary headroom; the real cases ground the COMPRA /
# false-positive question in actual scan rows. Together they form the eval set.
CASES = _SYNTHETIC_CASES + _load_real_cases()


def _load_candidate(path):
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "classify_decision"):
        raise AttributeError("candidate must define classify_decision(features)")
    consts = {
        "MIN_NET_MARGIN": float(getattr(mod, "MIN_NET_MARGIN", 0.25)),
        "MIN_LUCRO": float(getattr(mod, "MIN_LUCRO", 50.0)),
        "REVISAR_MIN_NET": float(getattr(mod, "REVISAR_MIN_NET", 0.20)),
        "MODEST_MIN_NET": float(getattr(mod, "MODEST_MIN_NET", 0.30)),
        "MARKUP_ANOMALY": float(getattr(mod, "MARKUP_ANOMALY", 0.45)),
    }
    return mod.classify_decision, consts


def evaluate(path):
    classify_decision, consts = _load_candidate(path)

    tp = fp = fn = tn = 0
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS}
    decisions = []

    for i, case in enumerate(CASES):
        gold = case["gold"]
        pred = str(classify_decision(dict(case["features"])))
        if pred not in LABELS:
            raise ValueError(
                f"case {i} ({case['name']}): classify_decision returned {pred!r}, "
                f"not one of {LABELS}"
            )
        confusion[gold][pred] += 1

        gold_buy = gold == "COMPRA"
        pred_buy = pred == "COMPRA"
        if pred_buy and gold_buy:
            outcome = "TP"; tp += 1
        elif pred_buy and not gold_buy:
            outcome = "FP"; fp += 1   # costly: fake margin handed to the operator
        elif not pred_buy and gold_buy:
            outcome = "FN"; fn += 1   # a dropped real deal
        else:
            outcome = "TN"; tn += 1

        decisions.append({"case": i, "name": case["name"], "gold": gold,
                          "pred": pred, "correct": pred == gold,
                          "compra_outcome": outcome})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    # Precision-weighted objective (2026-06-19): plain F1 rewards recall, which let
    # the evolution "win" by lowering cutoffs (precision loss) — wrong for a
    # precision-first scanner. eval_score = F0.5 (precision weighted 2x) AND a hard
    # floor at the baseline precision: any candidate that regresses precision below
    # baseline scores 0, so a precision-losing recall boost can never win.
    PRECISION_FLOOR = 0.57   # COMPRA-class precision of the baseline classifier
    _b2 = 0.25               # beta**2 for F0.5
    fbeta = ((1 + _b2) * precision * recall / (_b2 * precision + recall)) if (_b2 * precision + recall) else 0.0
    score = fbeta if precision >= PRECISION_FLOOR else 0.0

    per_label = {}
    macro_sum = 0.0
    for lab in LABELS:
        l_tp = confusion[lab][lab]
        l_fp = sum(confusion[g][lab] for g in LABELS if g != lab)
        l_fn = sum(confusion[lab][p] for p in LABELS if p != lab)
        l_prec = l_tp / (l_tp + l_fp) if (l_tp + l_fp) else 0.0
        l_rec = l_tp / (l_tp + l_fn) if (l_tp + l_fn) else 0.0
        l_f1 = (2 * l_prec * l_rec / (l_prec + l_rec)) if (l_prec + l_rec) else 0.0
        per_label[lab] = {"precision": round(l_prec, 4), "recall": round(l_rec, 4),
                          "f1": round(l_f1, 4), "support": sum(confusion[lab].values())}
        macro_sum += l_f1
    macro_f1 = macro_sum / len(LABELS)
    overall_acc = sum(confusion[l][l] for l in LABELS) / len(CASES)

    return {
        "eval_score": round(score, 4),
        "f1": round(f1, 4),
        "fbeta05": round(fbeta, 4),
        "precision_floor": PRECISION_FLOOR,
        "compra_precision": round(precision, 4),
        "compra_recall": round(recall, 4),
        "compra_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "macro_f1": round(macro_f1, 4),
        "overall_accuracy": round(overall_acc, 4),
        "per_label": per_label,
        "confusion": confusion,
        "constants": consts,
        "n_cases": len(CASES),
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
