"""Evaluator offline e determinístico do matcher de selados (título BR -> SKU).

Contrato (igual ao engineer/eval.sh do ASI-Evolve):
    python3 evaluator.py <candidate_code_file> <results_json_path>

O candidato deve expor `match_title(title, skus) -> list[str]` (ids de SKU).
Roda sobre `cases.json` (títulos reais rotulados) usando os termos REAIS de
`registry_terms.json` (dado fixo do registry — NÃO se evolui), e escreve
results.json com `{"success", "eval_score", "temp": {...}}`.

Precision-first: casar o SKU errado = margem fantasma = pior que perder um deal.
eval_score = F0.5 (precisão 2x) COM piso de precisão; abaixo do piso -> 0.
Sem rede, sem API — stdlib puro.

Regras de pontuação por caso (o matcher pode devolver 0, 1 ou 2+ ids):
  gold = sku_id esperado  | gold = None (deve ser NONE)
  ------------------------|-------------------------------
  devolveu {gold}         -> TP        | devolveu {}        -> TN
  devolveu {gold, ...}    -> FN (não   | devolveu {qualquer}-> FP (casou ruído/
    resolveu HIGH limpo;       resolveu       errado; o pior caso)
    ambíguo, não é vitória)
  devolveu set sem gold   -> FP (+FN se não-vazio): casou carta errada
  devolveu {}             -> FN: perdeu o deal
"""
import importlib.machinery
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_candidate(path):
    loader = importlib.machinery.SourceFileLoader("candidate", path)
    spec = importlib.util.spec_from_loader("candidate", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    if not hasattr(mod, "match_title"):
        raise AttributeError("candidate must define match_title(title, skus)")
    return mod.match_title


def evaluate(path):
    match_title = _load_candidate(path)
    skus = json.loads((HERE / "registry_terms.json").read_text(encoding="utf-8"))
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))

    tp = fp = fn = tn = 0
    decisions = []
    for i, case in enumerate(cases):
        title = case["title"]
        gold = case.get("gold")
        try:
            got = list(match_title(title, skus))
        except Exception as exc:  # candidato quebrado num caso não derruba tudo
            got = ["__ERROR__"]
        got_set = set(got)

        if gold is None:
            if not got_set:
                outcome, _ = "TN", tn
                tn += 1
            else:
                outcome = "FP"          # casou algo que devia ser NONE
                fp += 1
        else:
            if got_set == {gold}:
                outcome = "TP"          # HIGH limpo no SKU certo
                tp += 1
            elif gold in got_set:
                outcome = "FN(review)"  # casou o certo + extras: não resolveu HIGH
                fn += 1
            elif got_set:
                outcome = "FP+FN"       # casou SKU(s) errado(s)
                fp += 1
                fn += 1
            else:
                outcome = "FN"          # perdeu o deal
                fn += 1
        decisions.append({"case": i, "gold": gold, "got": got, "outcome": outcome})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(cases) if cases else 0.0

    # Precision-first (lição cross-scanner 2026-06): F0.5 + piso DURO de precisão.
    # Um candidato que casa mais SKUs baixando precisão (mais margem fantasma) é
    # REJEITADO (score 0). Piso 0.95: o matcher de selado é determinístico e a
    # baseline já é alta; só passa quem MANTÉM precisão quase perfeita enquanto
    # recupera recall/desambigua.
    PRECISION_FLOOR = 0.95
    _b2 = 0.25  # beta**2 -> F0.5
    fbeta = ((1 + _b2) * precision * recall / (_b2 * precision + recall)) if (_b2 * precision + recall) else 0.0
    score = fbeta if precision >= PRECISION_FLOOR else 0.0
    return {
        "eval_score": round(score, 4),
        "f1": round(f1, 4),
        "fbeta05": round(fbeta, 4),
        "precision_floor": PRECISION_FLOOR,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(cases)},
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
