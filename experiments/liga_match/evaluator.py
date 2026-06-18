"""Offline, deterministic evaluator for the Liga<->TCG matching scorer.

Contract (matches the ASI-Evolve engineer/eval.sh interface):
    python3 evaluator.py <candidate_code_file> <results_json_path>

Loads the candidate program (must expose `score_match` and `FUZZY_THRESHOLD`),
runs it over an embedded labeled set of offer->candidate cases, and writes
`results.json` with `{"success": bool, "eval_score": <F1>, "temp": {...}}`.

No network, no API — pure stdlib. The labeled set mirrors real Liga gotchas:
short set codes (PRE/SSP/151), accents, V-MAX/VMAX, same-name-different-set
disambiguation, and "must reject" distractors (a fake margin from a wrong match
is worse than a missed deal).
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback

# Each case: offer (name, set), candidates [(name, set), ...], and `gold`
# = index of the correct candidate, or None when the offer must be REJECTED.
CASES = [
    # 0) clean exact match
    {"offer": ("Charizard ex", "Obsidian Flames"),
     "cands": [("Charizard ex", "Obsidian Flames"),
               ("Charmander", "Obsidian Flames"),
               ("Charizard ex", "Paldea Evolved")],
     "gold": 0},
    # 1) short set code PRE -> Prismatic Evolutions (alias headroom)
    {"offer": ("Umbreon ex", "PRE"),
     "cands": [("Umbreon ex", "Prismatic Evolutions"),
               ("Espeon ex", "Prismatic Evolutions"),
               ("Umbreon ex", "Surging Sparks")],
     "gold": 0},
    # 2) V-MAX vs VMAX normalization
    {"offer": ("Charizard V-MAX", "Darkness Ablaze"),
     "cands": [("Charizard VMAX", "Darkness Ablaze"),
               ("Charizard V", "Darkness Ablaze")],
     "gold": 0},
    # 3) same name, different set -> set must disambiguate
    {"offer": ("Iono", "Paldean Fates"),
     "cands": [("Iono", "Paldean Fates"),
               ("Iono", "Paldea Evolved")],
     "gold": 0},
    # 4) short set code SSP -> Surging Sparks (alias headroom)
    {"offer": ("Pikachu ex", "SSP"),
     "cands": [("Pikachu ex", "Surging Sparks"),
               ("Pikachu ex", "Stellar Crown")],
     "gold": 0},
    # 5) trainer card, clean
    {"offer": ("Rare Candy", "Paldea Evolved"),
     "cands": [("Rare Candy", "Paldea Evolved"),
               ("Ultra Ball", "Paldea Evolved")],
     "gold": 0},
    # 6) "151" set code vs canonical "Scarlet & Violet 151" (token-subset headroom)
    {"offer": ("Alakazam ex", "151"),
     "cands": [("Alakazam ex", "Scarlet & Violet 151"),
               ("Alakazam ex", "Surging Sparks")],
     "gold": 0},
    # 7) accents / punctuation in name
    {"offer": ("Mr. Mime", "Base Set"),
     "cands": [("Mr Mime", "Base Set"),
               ("Mime Jr.", "Base Set")],
     "gold": 0},
    # 8) clean SIR-style name match
    {"offer": ("Gardevoir ex", "Scarlet & Violet"),
     "cands": [("Gardevoir ex", "Scarlet & Violet"),
               ("Gardevoir", "Scarlet & Violet")],
     "gold": 0},
    # 9) MUST REJECT: no correct candidate (different Pokémon, same set)
    {"offer": ("Pikachu", "Base Set"),
     "cands": [("Raichu", "Base Set"),
               ("Pikachu V", "Surging Sparks")],
     "gold": None},
    # 10) MUST REJECT: right name but only wrong-set distractors present
    {"offer": ("Mewtwo", "Obscure Local Promo"),
     "cands": [("Mewtwo", "Scarlet & Violet Promo"),
               ("Mew", "Scarlet & Violet Promo")],
     "gold": None},
]


def _load_candidate(path):
    # The candidate file ("code" / "initial_program") has no .py extension, so we
    # load it with an explicit source loader instead of suffix-based detection.
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "score_match"):
        raise AttributeError("candidate must define score_match(...)")
    threshold = float(getattr(mod, "FUZZY_THRESHOLD", 0.85))
    return mod.score_match, threshold


def evaluate(path):
    score_match, threshold = _load_candidate(path)
    tp = fp = fn = tn = 0
    decisions = []
    for i, case in enumerate(CASES):
        on, os_ = case["offer"]
        scores = [float(score_match(on, os_, cn, cs)) for (cn, cs) in case["cands"]]
        best_i = max(range(len(scores)), key=lambda k: scores[k])
        best = scores[best_i]
        accepted = best >= threshold
        gold = case["gold"]
        if gold is None:
            outcome = "TN" if not accepted else "FP"
            if accepted:
                fp += 1
            else:
                tn += 1
        else:
            if accepted and best_i == gold:
                outcome = "TP"
                tp += 1
            elif accepted and best_i != gold:
                outcome = "FP+FN"
                fp += 1
                fn += 1
            else:
                outcome = "FN"
                fn += 1
        decisions.append({"case": i, "best_score": round(best, 4),
                          "accepted": accepted, "picked": best_i,
                          "gold": gold, "outcome": outcome})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(CASES)
    return {
        "eval_score": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "threshold": threshold,
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
