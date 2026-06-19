"""Offline, deterministic evaluator for the COMC confidence-tier calibration.

Contract (matches the ASI-Evolve engineer/eval.sh interface):
    python3 evaluator.py <candidate_code_file> <results_json_path>

Loads the candidate program (must expose `assign_confidence(features)` and the
threshold constants), runs it over an embedded labeled set of feature->gold
cases, and writes `results.json` with
`{"success": bool, "eval_score": <F1>, "combined_score": <F1>,
  "eval_time": float, "temp": {...}}`.

No network, no API — pure stdlib. The labeled set mirrors real COMC gotchas:
set+number exact, multi-variant disambiguation, name-fuzzy-within-set, no-number
strong-name, unresolvable set, plus "must reject" distractors (a wrong accept
invents a fake margin -> precision matters) and recall/precision *headroom* cases
where a name sits just under / just over a cutoff.

`eval_score` = F1 of ACCEPT-vs-REJECT. accept = `assign_confidence` returned a
confidence (not None). TP = accepted & gold is a real match; FP = accepted & gold
is None (a wrong accept), FN = rejected & gold is a real match; TN = rejected &
gold is None. (Accepting a real match but at a far-off tier is still counted as a
TP for ACCEPT/REJECT F1, but its tier mismatch is surfaced in `calibration`.)
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback

# Each case: a feature dict + `gold`. gold is the correct confidence tier when the
# candidate IS a true match, or None when it must be REJECTED. Tier semantics:
#   0.95 set+number exact unique | 0.90 set+number multi-variant disambiguated
#   0.85 number present, no exact hit, strong name | 0.70 no number, very strong name
CASES = [
    # --- ported from comc_scanner/tests/test_matcher.py --------------------
    # 0) tier1 exact (Blastoise 2/102, unique) -> 0.95   [test_tier1_exact]
    {"name": "tier1_exact_blastoise",
     "f": {"set_known": True, "number_present": True, "exact_count": 1,
           "name_score": 100.0, "runner_score": 0.0},
     "gold": 0.95},
    # 1) tier1' disambiguation (Charizard vs error variant at 4/102) -> 0.90
    {"name": "tier1_disambig_charizard",
     "f": {"set_known": True, "number_present": True, "exact_count": 2,
           "name_score": 100.0, "runner_score": 67.0},
     "gold": 0.90},
    # 2) tier3 no-number strong name (Blastoise, no number) -> 0.70
    {"name": "tier3_no_number_blastoise",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 100.0, "runner_score": 40.0},
     "gold": 0.70},
    # 3) MUST REJECT: unresolvable set (set_hint "Not A Set") -> None
    {"name": "reject_unresolvable_set",
     "f": {"set_known": False, "number_present": True, "exact_count": 0,
           "name_score": 100.0, "runner_score": 0.0},
     "gold": None},

    # --- tier-2 "number present, no exact hit, strong name within set" -----
    # 4) tier2 fuzzy-within-set, name 93 (>= NAME_STRONG 90) -> 0.85
    {"name": "tier2_fuzzy_within_set",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 93.0, "runner_score": 50.0},
     "gold": 0.85},

    # --- exact-set+number sanity-floor (a coincidental number) -------------
    # 5) MUST REJECT: set resolved + coincidental number, exact unique, but name
    #    wildly different (Topps/Bandai bleed-through), score 20 < NAME_FLOOR 45
    {"name": "reject_coincidental_number_low_name",
     "f": {"set_known": True, "number_present": True, "exact_count": 1,
           "name_score": 20.0, "runner_score": 10.0},
     "gold": None},
    # 6) tier1 exact but name absent -> still accept (0.95): number is decisive
    {"name": "tier1_exact_name_absent",
     "f": {"set_known": True, "number_present": True, "exact_count": 1,
           "name_score": 0.0, "runner_score": 0.0, "name_absent": True},
     "gold": 0.95},

    # --- recall headroom: a TRUE match whose name sits JUST UNDER a cutoff --
    # 7) no number, name 90 (< NAME_VERY_STRONG 92) -> baseline REJECTS, but this
    #    IS the right card (gold 0.70). Recall headroom: a smarter scorer accepts.
    {"name": "headroom_recall_no_number_89",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 90.0, "runner_score": 30.0},
     "gold": 0.70},
    # 8) number present, no exact hit, name 88 (< NAME_STRONG 90) -> baseline
    #    REJECTS, but gold is a real 0.85 match. Recall headroom.
    {"name": "headroom_recall_num_88",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 88.0, "runner_score": 55.0},
     "gold": 0.85},

    # --- precision headroom: a distractor JUST OVER a cutoff that must reject -
    # 9) MUST REJECT: no number, name 93 (>= 92) BUT runner-up 92 too -> gap 1
    #    (< NAME_GAP 3). Ambiguous; baseline rejects (correct). A naive scorer that
    #    drops the gap check would wrongly accept -> precision headroom.
    {"name": "reject_ambiguous_runner_close",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 93.0, "runner_score": 92.0},
     "gold": None},
    # 10) MUST REJECT: number present, no exact hit, name 60 (well < 90) -> weak.
    {"name": "reject_weak_name_with_number",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 60.0, "runner_score": 45.0},
     "gold": None},
    # 11) MUST REJECT: no number, weak name 70 (< 92) -> not confident enough.
    {"name": "reject_weak_name_no_number",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 70.0, "runner_score": 20.0},
     "gold": None},

    # --- clean accepts that pad the positive class -------------------------
    # 12) tier1' disambiguation, name 95, runner 70 -> 0.90
    {"name": "tier1_disambig_clean",
     "f": {"set_known": True, "number_present": True, "exact_count": 2,
           "name_score": 95.0, "runner_score": 70.0},
     "gold": 0.90},
    # 13) tier3 no-number, name 96 clearly ahead (runner 50) -> 0.70
    {"name": "tier3_no_number_clean",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 96.0, "runner_score": 50.0},
     "gold": 0.70},
    # 14) tier2, number present, name 91 (>= 90), no exact hit -> 0.85
    {"name": "tier2_fuzzy_91",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 91.0, "runner_score": 40.0},
     "gold": 0.85},

    # ---- precision/generalization probes (2026-06-18): cases at name_score 86-90,
    # BALANCED between real matches (recall headroom) and wrong cards that MUST
    # reject (precision traps). A candidate that wins only by lowering the name
    # cutoffs will catch the real-86/88s but also wrongly accept the wrong-88/90s,
    # dropping precision — exposing the tune as boundary-overfit, not generalization. ----

    # real fuzzy matches just under the original cutoffs (should ACCEPT)
    {"name": "tier2_real_88",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 88.0, "runner_score": 35.0},
     "gold": 0.85},
    {"name": "tier3_real_90",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 90.0, "runner_score": 30.0},
     "gold": 0.70},

    # WRONG cards whose best-name fuzzy lands in 86-90 -> MUST REJECT (precision trap)
    {"name": "tier2_wrong_88_reject",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 88.0, "runner_score": 80.0},
     "gold": None},
    {"name": "tier2_wrong_89_reject",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 89.0, "runner_score": 84.0},
     "gold": None},
    {"name": "tier3_wrong_90_reject",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 90.0, "runner_score": 88.0},
     "gold": None},
    {"name": "tier3_wrong_91_close_runner_reject",
     "f": {"set_known": True, "number_present": False, "exact_count": 0,
           "name_score": 91.0, "runner_score": 89.0},
     "gold": None},
    # ambiguous: number present, name strong but a near-tie runner -> reject (wrong variant risk)
    {"name": "tier2_ambiguous_runner_reject",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 92.0, "runner_score": 90.0},
     "gold": None},
    # genuinely strong, clear -> accept (anchor TP so it's not all rejects)
    {"name": "tier2_strong_95_clear",
     "f": {"set_known": True, "number_present": True, "exact_count": 0,
           "name_score": 95.0, "runner_score": 40.0},
     "gold": 0.85},
]

# Tiers the candidate is allowed to emit; used to bucket calibration.
_TIERS = (0.95, 0.90, 0.85, 0.70)


def _load_candidate(path):
    # The candidate file ("code" / "initial_program") has no .py extension, so we
    # load it with an explicit source loader instead of suffix-based detection.
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "assign_confidence"):
        raise AttributeError("candidate must define assign_confidence(features)")
    consts = {
        "NAME_FLOOR": float(getattr(mod, "NAME_FLOOR", 45.0)),
        "NAME_STRONG": float(getattr(mod, "NAME_STRONG", 90.0)),
        "NAME_VERY_STRONG": float(getattr(mod, "NAME_VERY_STRONG", 92.0)),
        "NAME_GAP": float(getattr(mod, "NAME_GAP", 3.0)),
        "TIER_EXACT": float(getattr(mod, "TIER_EXACT", 0.95)),
        "TIER_DISAMBIG": float(getattr(mod, "TIER_DISAMBIG", 0.90)),
        "TIER_FUZZY_NUM": float(getattr(mod, "TIER_FUZZY_NUM", 0.85)),
        "TIER_NO_NUMBER": float(getattr(mod, "TIER_NO_NUMBER", 0.70)),
    }
    return mod.assign_confidence, consts


def _nearest_tier(value):
    return min(_TIERS, key=lambda t: abs(t - value))


def evaluate(path):
    assign_confidence, consts = _load_candidate(path)
    tp = fp = fn = tn = 0
    decisions = []
    # calibration[predicted_tier] = [n_real_match, n_total] among cases the
    # candidate assigned to that tier bucket.
    calibration = {t: [0, 0] for t in _TIERS}

    for i, case in enumerate(CASES):
        pred = assign_confidence(dict(case["f"]))
        accepted = pred is not None
        gold = case["gold"]
        gold_is_match = gold is not None

        if accepted:
            bucket = _nearest_tier(float(pred))
            calibration[bucket][1] += 1
            if gold_is_match:
                calibration[bucket][0] += 1

        if gold_is_match:
            if accepted:
                outcome = "TP"
                tp += 1
            else:
                outcome = "FN"
                fn += 1
        else:
            if accepted:
                outcome = "FP"
                fp += 1
            else:
                outcome = "TN"
                tn += 1

        tier_match = (accepted and gold_is_match
                      and abs(float(pred) - float(gold)) < 1e-9)
        decisions.append({
            "case": i,
            "name": case["name"],
            "pred": (round(float(pred), 4) if accepted else None),
            "gold": gold,
            "accepted": accepted,
            "outcome": outcome,
            "tier_match": tier_match,
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(CASES)
    # Precision-weighted objective (2026-06-19): plain F1 rewards recall, which let
    # the evolution "win" by lowering cutoffs (precision 0.90 -> 0.81) — wrong for a
    # precision-first scanner. eval_score = F0.5 (precision weighted 2x) AND a hard
    # floor at the baseline precision: any candidate that regresses precision below
    # baseline scores 0, so a precision-losing recall boost can never win. Under
    # this, the Tier-2 gap-gate (P 0.90->1.0) beats the cutoff-lowering overfit.
    PRECISION_FLOOR = 0.90   # accept-class precision of the baseline matcher
    _b2 = 0.25               # beta**2 for F0.5
    fbeta = ((1 + _b2) * precision * recall / (_b2 * precision + recall)) if (_b2 * precision + recall) else 0.0
    score = fbeta if precision >= PRECISION_FLOOR else 0.0

    # Per-tier calibration: fraction of cases assigned to each tier whose gold was
    # a real match (1.0 = perfectly calibrated; lower = that tier leaked rejects).
    calib = {}
    for t in _TIERS:
        real, total = calibration[t]
        calib[str(t)] = {
            "n": total,
            "real_matches": real,
            "calibration": round(real / total, 4) if total else None,
        }

    return {
        "eval_score": round(score, 4),
        "f1": round(f1, 4),
        "fbeta05": round(fbeta, 4),
        "precision_floor": PRECISION_FLOOR,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "constants": consts,
        "calibration": calib,
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
