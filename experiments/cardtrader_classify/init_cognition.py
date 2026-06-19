#!/usr/bin/env python3
"""Seed the cognition store for the cardtrader_classify experiment.

Run once before evolving:  python experiments/cardtrader_classify/init_cognition.py

Knowledge distilled from card-trader-scanner/cardtrader_postprocess.py + CLAUDE.md
and the operator's memory — primes the Researcher so it doesn't rediscover the
rules (and points it at the known GG## gap).
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if "Evolve" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "Evolve", REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["Evolve"] = _mod
    _spec.loader.exec_module(_mod)

from Evolve.cognition.cognition import Cognition          # noqa: E402
from Evolve.utils.structures import CognitionItem          # noqa: E402


def init_cognition():
    exp_dir = Path(__file__).parent
    cog = Cognition(storage_dir=exp_dir / "cognition_data")
    cog.reset()

    knowledge = [
        CognitionItem(
            content="Trainer Gallery (TG##, regex ^TG\\d+, SWSH era) cards are a massive "
                    "false-positive source: pokemontcg.io inflates their reference price "
                    "5-10x, so the scanner sees a fake huge margin. Production routes any "
                    "TG## card to NAO/manual. The GALARIAN GALLERY subset (GG##) is the "
                    "structurally identical sibling (alt-art gallery subset numbered "
                    "separately from the main set) with the SAME inflation — but production "
                    "has NO GG## guard, so GG## cards slip through as a fake COMPRA. "
                    "Generalise the gallery guard to catch GG## too (route away from "
                    "COMPRA), using a case-insensitive regex/prefix — never hardcode numbers.",
            source="cardtrader_trainer_gallery_bug + postprocess TRAINER_GALLERY_RE",
            metadata={"topic": "gallery_inflation", "importance": "critical"},
        ),
        CognitionItem(
            content="Alpha-suffix collector numbers (^\\d+[a-zA-Z]+$, e.g. 153a, 022a, 091a) "
                    "are probable promo/League/1st-2nd-Place variants that pokemontcg.io is "
                    "blind to -> the matched reference price is the wrong (often much "
                    "cheaper) version -> inflated margin. Route to REVISAR (forced manual). "
                    "CAUTION: gallery codes like TG12/GG44 START with letters so the "
                    "^\\d+[a-zA-Z]+$ regex does NOT match them — keep the two rules separate; "
                    "a gallery code must not be swallowed by the alpha-suffix branch.",
            source="postprocess ALPHA_SUFFIX_RE (v2.3 Layer 5, bug-hunt 2026-05-18)",
            metadata={"topic": "alpha_suffix_variant", "importance": "high"},
        ),
        CognitionItem(
            content="Decision contract: COMPRA requires net_margin >= MIN_NET_MARGIN (0.25) "
                    "AND lucro_liq >= MIN_LUCRO (R$50) AND chase_tier in {TOP, MID} AND no "
                    "red flag. NAO when data is missing, TG## (and should-be GG##), "
                    "validation STALE, chase BULK, or net < REVISAR_MIN_NET (0.20). REVISAR "
                    "(gray zone) for: net in [0.20, 0.25), net OK but lucro < R$50, MODEST "
                    "chase with net >= MODEST_MIN_NET (0.30) (else NAO), markup anomaly "
                    "(>0.45), or a validation status present-but-not-OK.",
            source="cardtrader_postprocess.py::classify_decision (v2.x mechanical rule)",
            metadata={"topic": "decision_contract", "importance": "critical"},
        ),
        CognitionItem(
            content="Precision over noise: a false COMPRA hands the operator a FAKE margin, "
                    "which is far worse than a missed deal. CardTrader's false-positive rate "
                    "without per-blueprint validation was ~76%. Optimize COMPRA-class F1 but "
                    "NEVER inflate COMPRA by loosening the gallery/variant/unsupported guards "
                    "or dropping the floors. Check precedence: variant/gallery/unsupported "
                    "guards and the hard NAO outs are evaluated BEFORE the COMPRA decision.",
            source="operator rule (no purchase decisions) + 76% FP history",
            metadata={"topic": "precision_over_noise", "importance": "critical"},
        ),
        CognitionItem(
            content="Margin is GROSS and PURE: (tcg_market - ct_price)/tcg_market, with NO "
                    "embedded fees, Hub fee, FX, IOF or shipping (cross-scanner policy "
                    "2026-06-06; the operator adds fees by hand). The per-blueprint validated "
                    "price (live checkout) is the ground truth, not the per-expansion RAW "
                    "price. The R$50 profit floor and $10 price floor are relevance gates "
                    "(cheap cards' percentage margins don't cover fixed costs).",
            source="CardTrader CLAUDE.md / feedback_gross_margin_only",
            metadata={"topic": "gross_margin", "importance": "high"},
        ),
        CognitionItem(
            content="Unsupported sets (poor/divergent pokemontcg.io coverage) and anomalous "
                    "seller markup (>45%) are review signals, not auto-buys -> REVISAR. "
                    "Robust feature handling matters: None net_margin/lucro_liq must return "
                    "NAO without crashing; codes and statuses arrive mixed-case/padded "
                    "(strip + upper/lower before matching); a lowercase tg05/gg09 must still "
                    "be caught by the gallery guard.",
            source="postprocess UNSUPPORTED_SETS + markup anomaly + robustness",
            metadata={"topic": "review_signals_robustness", "importance": "medium"},
        ),
    ]

    ids = cog.add_batch(knowledge)
    print(f"Seeded {len(ids)} cognition items into {exp_dir / 'cognition_data'}")


if __name__ == "__main__":
    init_cognition()
