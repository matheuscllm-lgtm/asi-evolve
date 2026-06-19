"""Offline, deterministic evaluator for the MYP deal / false-positive classifier.

Contract (matches the ASI-Evolve engineer/eval.sh interface):
    python3 evaluator.py <candidate_code_file> <results_json_path>

Loads the candidate program (must expose `classify_deal(features) -> str` and the
tunable constants MIN_MARGIN, SUSPECT_RATIO), runs it over an embedded labeled set
of MYP->TCG rows, and writes `results.json` with
`{"success": bool, "eval_score": <CLEAN-F1>, "combined_score": ..., "temp": {...}}`.

No network, no API — pure stdlib. Several cases are derived from the scanner's
known offline fixtures (test_v5_8_offline.py): Jirachi (TCG declared 75x last sale
-> suspect), borderline 9.5x ratio (NOT suspect), Psyduck pagination (the EN-NM
price is recoverable -> a clean in-range deal), Darumaka 097/086 (supranumerary
SIR mislabeled). Plus headroom cases: EN-NM high-margin clean, an SP/PT row that
must reject, a card_num>set_total supranumerary, a declared>>last_sale suspect,
margins just under/over MIN_MARGIN, and a borderline suspect ratio.

Primary metric (eval_score): BINARY F1 of detecting CLEAN deals.
  TP = predicted clean & gold clean
  FP = predicted clean but gold is flagged/reject  (the COSTLY error: fake margin)
  FN = gold clean but predicted flagged/reject     (a dropped real deal)
A false "clean" on a supranumerary/suspect/reject row hands the operator a fake
margin, so CLEAN precision is the axis that matters most.
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback

LABELS = ("clean", "supranumerary", "tcg_suspect", "reject")

# Each case: a feature dict (offline-derivable) + the gold label.
# Keys: margin, condition, language, card_num, set_total, declared_tcg,
#       last_sale, rarity.
_SYNTHETIC_CASES = [
    # 0) Jirachi PR-SM SM161 — TCG declared R$1499 vs last sale R$19.99 = 75x.
    #    EN-NM, in-range collector#, high margin, but the declared price is a
    #    .estat-tcg mis-map -> tcg_suspect (NOT a clean deal).
    {"name": "Jirachi PR-SM (75x)",
     "features": {"margin": 14.0, "condition": "NM", "language": "EN",
                  "card_num": 161, "set_total": 200, "declared_tcg": 1499.00,
                  "last_sale": 19.99, "rarity": "Holo Rara"},
     "gold": "tcg_suspect"},
    # 1) Legit deal: ratio TCG/last_sale ~1.1x, in-range, EN-NM -> clean.
    {"name": "Charizard ex SS (1.1x)",
     "features": {"margin": 1.5, "condition": "NM", "language": "EN",
                  "card_num": 125, "set_total": 191, "declared_tcg": 200.00,
                  "last_sale": 180.00, "rarity": "Special Illustration"},
     "gold": "clean"},
    # 2) Borderline ratio 9.5x — just UNDER the 10x suspect threshold -> clean.
    #    (Headroom: tightening SUSPECT_RATIO would wrongly flag this as suspect.)
    {"name": "Mew V borderline (9.5x)",
     "features": {"margin": 18.0, "condition": "NM", "language": "EN",
                  "card_num": 158, "set_total": 191, "declared_tcg": 950.00,
                  "last_sale": 100.00, "rarity": "Ultra Rara"},
     "gold": "clean"},
    # 3) Borderline ratio exactly 10.0x — AT the threshold (>= ) -> suspect.
    #    (Headroom: loosening SUSPECT_RATIO above 10 would let this through.)
    {"name": "Gengar exactly 10x",
     "features": {"margin": 9.0, "condition": "NM", "language": "EN",
                  "card_num": 100, "set_total": 191, "declared_tcg": 1000.00,
                  "last_sale": 100.00, "rarity": "Rara"},
     "gold": "tcg_suspect"},
    # 4) Psyduck (053/198) — pagination case: EN-NM price recoverable, in-range
    #    collector#, healthy margin, ratio normal -> clean.
    {"name": "Psyduck 053/198 (pagination)",
     "features": {"margin": 0.55, "condition": "NM", "language": "EN",
                  "card_num": 53, "set_total": 198, "declared_tcg": 110.00,
                  "last_sale": 95.00, "rarity": "Comum"},
     "gold": "clean"},
    # 5) Darumaka (097/086) — Black Bolt SIR mislabeled "Comum"; collector#
    #    97 > 86 -> supranumerary (margin suspect, variant misclassification).
    {"name": "Darumaka 097/086 (SIR)",
     "features": {"margin": 12.0, "condition": "NM", "language": "EN",
                  "card_num": 97, "set_total": 86, "declared_tcg": 67.10,
                  "last_sale": 32.00, "rarity": "Comum"},
     "gold": "supranumerary"},
    # 6) Mew ex 232/091 — 151 SIR, 232 > 91 -> supranumerary.
    {"name": "Mew ex 232/091 (151 SIR)",
     "features": {"margin": 5.0, "condition": "NM", "language": "EN",
                  "card_num": 232, "set_total": 91, "declared_tcg": 400.00,
                  "last_sale": 380.00, "rarity": "Comum"},
     "gold": "supranumerary"},
    # 7) HEADROOM (baseline FN): a genuine PROMO deal numbered above any base
    #    denominator. MYP promos (e.g. SM-series, "PR" sets) routinely carry a
    #    collector# > set_total yet are legitimate EN-NM chases with a real
    #    margin and a normal declared/last_sale ratio. The faithful baseline
    #    blanket-flags any card_num>set_total as supranumerary -> it MIS-flags
    #    this clean deal. A refined classifier (promo-aware: skip the
    #    supranumerary rule when rarity is a promo/holo type, or require the
    #    declared price to also look inflated) recovers it. Gold = clean.
    {"name": "Charizard PR 191/178 promo clean",
     "features": {"margin": 0.58, "condition": "NM", "language": "EN",
                  "card_num": 191, "set_total": 178, "declared_tcg": 130.00,
                  "last_sale": 112.00, "rarity": "Promo Holo"},
     "gold": "clean"},
    # 8) Clean headroom: genuine in-range high-margin clean.
    {"name": "Gardevoir ex 086/091 clean",
     "features": {"margin": 0.48, "condition": "NM", "language": "EN",
                  "card_num": 86, "set_total": 91, "declared_tcg": 90.00,
                  "last_sale": 78.00, "rarity": "Ultra Rara"},
     "gold": "clean"},
    # 9) MUST REJECT: SP condition (NM-only invariant).
    {"name": "Iono SP (reject cond)",
     "features": {"margin": 0.90, "condition": "SP", "language": "EN",
                  "card_num": 80, "set_total": 91, "declared_tcg": 60.00,
                  "last_sale": 40.00, "rarity": "Rara"},
     "gold": "reject"},
    # 10) MUST REJECT: PT language (EN-only invariant), even at huge margin.
    {"name": "Charizard PT (reject lang)",
     "features": {"margin": 1.20, "condition": "NM", "language": "PT",
                  "card_num": 4, "set_total": 102, "declared_tcg": 300.00,
                  "last_sale": 250.00, "rarity": "Holo Rara"},
     "gold": "reject"},
    # 11) Borderline margin JUST UNDER MIN_MARGIN (0.30) -> reject.
    {"name": "Snorlax margin 0.29 (under)",
     "features": {"margin": 0.29, "condition": "NM", "language": "EN",
                  "card_num": 50, "set_total": 191, "declared_tcg": 70.00,
                  "last_sale": 60.00, "rarity": "Rara"},
     "gold": "reject"},
    # 12) Borderline margin JUST OVER MIN_MARGIN (0.31) -> clean.
    {"name": "Lapras margin 0.31 (over)",
     "features": {"margin": 0.31, "condition": "NM", "language": "EN",
                  "card_num": 41, "set_total": 191, "declared_tcg": 80.00,
                  "last_sale": 70.00, "rarity": "Rara"},
     "gold": "clean"},
    # 13) Suspect from a clear declared>>last_sale (50x), in-range collector#.
    {"name": "Greninja 50x suspect",
     "features": {"margin": 8.0, "condition": "NM", "language": "EN",
                  "card_num": 57, "set_total": 162, "declared_tcg": 1500.00,
                  "last_sale": 30.00, "rarity": "Rara"},
     "gold": "tcg_suspect"},
    # 14) No last_sale signal: cannot run suspect check -> clean (in-range, high
    #     margin). last_sale None must NOT crash or false-flag.
    {"name": "Sylveon ex no last_sale",
     "features": {"margin": 0.70, "condition": "NM", "language": "EN",
                  "card_num": 75, "set_total": 191, "declared_tcg": 150.00,
                  "last_sale": None, "rarity": "Double Rare"},
     "gold": "clean"},
    # 15) MUST REJECT: NM-only via lowercase/typo condition (exact-match guard).
    {"name": "Mewtwo 'nm ' mixed (reject)",
     "features": {"margin": 0.80, "condition": "nm ", "language": "en",
                  "card_num": 10, "set_total": 102, "declared_tcg": 90.00,
                  "last_sale": 80.00, "rarity": "Holo Rara"},
     "gold": "clean"},  # normalized -> NM/EN, in-range, margin ok -> clean
    # 16) Supranumerary that ALSO has a suspect ratio: supranumerary wins
    #     (collector# is checked before the ratio in the baseline order).
    {"name": "Mimikyu 250/198 supra+suspect",
     "features": {"margin": 6.0, "condition": "NM", "language": "EN",
                  "card_num": 250, "set_total": 198, "declared_tcg": 800.00,
                  "last_sale": 20.00, "rarity": "Comum"},
     "gold": "supranumerary"},
    # 17) Reject AND would-be supranumerary: reject (invariant) takes precedence.
    {"name": "Vaporeon 200/91 SP (reject>supra)",
     "features": {"margin": 0.95, "condition": "SP", "language": "EN",
                  "card_num": 200, "set_total": 91, "declared_tcg": 500.00,
                  "last_sale": 400.00, "rarity": "Comum"},
     "gold": "reject"},
    # 18) HEADROOM (baseline FN): a legit high-value chase whose last_sale was a
    #     STALE outlier-low print, pushing declared/last_sale just over 10x
    #     (12x here) even though the declared TCG price is itself a sane chase
    #     value (~R$960). The flat 10x cutoff mis-flags this genuine clean as
    #     suspect; a refined classifier (e.g. gate the ratio on an ABSOLUTE
    #     declared-price sanity floor, or widen the ratio for high-rarity
    #     chases) recovers it. Gold = clean.
    {"name": "Moonbreon 161/131 stale-low last_sale",
     "features": {"margin": 0.74, "condition": "NM", "language": "EN",
                  "card_num": 161, "set_total": 131, "declared_tcg": 960.00,
                  "last_sale": 80.00, "rarity": "Alt Art Secret"},
     "gold": "clean"},
]


def _load_real_cases():
    """Enrich the eval with REAL labeled rows from recent scans (2026-06-19).

    `real_cases.json` (next to this evaluator) is generated from real MYP scan
    outputs and labeled per the operator-confirmed rule (supranumerary + Comum =
    rarity mislabel -> "supranumerary"/review; non-Comum supranumerary = real ->
    "clean"; declared/last_sale >= 10 -> "tcg_suspect"; margin < floor -> "reject").
    The file is git-ignored (deal data stays local). Absent -> synthetic only.
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


# Synthetic cases keep the hard invariants (SP/PT reject, condition exact-match)
# and boundary headroom; the real cases ground the supranumerary/rarity question
# in actual scan rows. Together they form the evaluation set.
CASES = _SYNTHETIC_CASES + _load_real_cases()


def _load_candidate(path):
    # The candidate file ("code" / "initial_program") has no .py extension, so we
    # load it with an explicit source loader instead of suffix-based detection.
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "classify_deal"):
        raise AttributeError("candidate must define classify_deal(features)")
    min_margin = float(getattr(mod, "MIN_MARGIN", 0.30))
    suspect_ratio = float(getattr(mod, "SUSPECT_RATIO", 10.0))
    return mod.classify_deal, min_margin, suspect_ratio


def evaluate(path):
    classify_deal, min_margin, suspect_ratio = _load_candidate(path)

    # Binary CLEAN-detection counters (the primary metric).
    tp = fp = fn = tn = 0
    # 4x4 confusion (gold -> predicted), and per-label F1 for macro-F1.
    confusion = {g: {p: 0 for p in LABELS} for g in LABELS}
    decisions = []

    for i, case in enumerate(CASES):
        gold = case["gold"]
        # Defensive copy so the candidate can't mutate the shared fixtures.
        pred = str(classify_deal(dict(case["features"])))
        if pred not in LABELS:
            raise ValueError(
                f"case {i} ({case['name']}): classify_deal returned {pred!r}, "
                f"not one of {LABELS}"
            )
        confusion[gold][pred] += 1

        gold_clean = gold == "clean"
        pred_clean = pred == "clean"
        if pred_clean and gold_clean:
            outcome = "TP"
            tp += 1
        elif pred_clean and not gold_clean:
            outcome = "FP"   # costly: fake margin handed to the operator
            fp += 1
        elif not pred_clean and gold_clean:
            outcome = "FN"   # a dropped real deal
            fn += 1
        else:
            outcome = "TN"
            tn += 1

        decisions.append({
            "case": i, "name": case["name"],
            "gold": gold, "pred": pred,
            "correct": pred == gold, "clean_outcome": outcome,
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    # Precision-weighted objective (2026-06-19): plain F1 rewards recall, which let
    # the evolution "win" by lowering cutoffs (precision loss) — wrong for a
    # precision-first scanner. eval_score = F0.5 (precision weighted 2x) AND a hard
    # floor at the baseline precision: any candidate that regresses precision below
    # baseline scores 0, so a precision-losing recall boost can never win.
    PRECISION_FLOOR = 1.0    # CLEAN-class precision of the baseline classifier
    _b2 = 0.25               # beta**2 for F0.5
    fbeta = ((1 + _b2) * precision * recall / (_b2 * precision + recall)) if (_b2 * precision + recall) else 0.0
    score = fbeta if precision >= PRECISION_FLOOR else 0.0

    # Macro-F1 across all 4 labels (per-label one-vs-rest).
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
        "clean_precision": round(precision, 4),
        "clean_recall": round(recall, 4),
        "clean_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "macro_f1": round(macro_f1, 4),
        "overall_accuracy": round(overall_acc, 4),
        "per_label": per_label,
        "confusion": confusion,
        "constants": {"MIN_MARGIN": min_margin, "SUSPECT_RATIO": suspect_ratio},
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
