#!/usr/bin/env python3
"""Seed the cognition store for the cardtrader_vintage experiment.

Run once before evolving:  python experiments/cardtrader_vintage/init_cognition.py

Knowledge distilled from card-trader-scanner/CLAUDE.md, CHANGELOG.md (2026-05-18),
and cardtrader_postprocess.py — primes the Researcher so it doesn't rediscover the
vintage false-positive rules from scratch.
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
            content="reverseHolofoil variant inflation is a documented vintage FP class: "
                    "a NON-foil vintage listing gets priced off the expensive HOLOFOIL "
                    "reference. Confirmed: Pichu Expedition #22 ($224.99 holofoil vs $50.41 "
                    "reverseHolofoil), Tyranitar Aquapolis ($210 vs $69.99). The scanner "
                    "exposes this as the `low_conf_variant` flag ('Variante Baixa Confiança'), "
                    "but classify_decision currently IGNORES it — that is the main headroom. "
                    "Route low_conf_variant listings to REVISAR (conservative, not NAO).",
            source="CHANGELOG 2026-05-18 + CLAUDE.md 'Variante Baixa Confiança'",
            metadata={"topic": "low_conf_variant", "importance": "critical"},
        ),
        CognitionItem(
            content="Vintage 'suspect sets' apply pokemontcg.io's reverseHolofoil fallback "
                    "and inflate 5-30x: Legendary Collection (code 'lc'), Battle Academy "
                    "2020 ('ba-20'/'ba20') and 2022 ('ba-22'/'ba22'). Production only flags "
                    "these in a separate advisory sheet (VINTAGE_SUSPECT_SETS), never in the "
                    "COMPRA/REVISAR decision. Routing them to REVISAR closes the gap.",
            source="cardtrader_postprocess.py VINTAGE_SUSPECT_SETS + memory 2026-05-19",
            metadata={"topic": "vintage_suspect_sets", "importance": "critical"},
        ),
        CognitionItem(
            content="A WRONG COMPRA on an inflated vintage card is the expensive error: it "
                    "invents a margin that does not exist (real money lost). Over-flagging a "
                    "clean genuine deal is the cheaper, opposite error (a lost opportunity). "
                    "Prefer precision: do NOT flag every vintage card — clean vintage deals "
                    "(Charizard Base Set, Neo Genesis, supported sets, normal numbers, "
                    "foil-matched) must stay COMPRA. Flag only on a concrete inflation signal.",
            source="operator rule (cross-scanner precision-first)",
            metadata={"topic": "precision_over_recall", "importance": "critical"},
        ),
        CognitionItem(
            content="Already-handled vintage traps (keep them): TG##/GG## gallery numbers "
                    "(TRAINER_GALLERY_RE ^(?:TG|GG)\\d+) -> NAO; alpha-suffix collector "
                    "numbers (ALPHA_SUFFIX_RE ^\\d+[a-zA-Z]+, e.g. 153a = 1st Place League) "
                    "-> REVISAR; unsupported sets (clb, wcd2004/06/07, m24, phs, pplf, xybsp, "
                    "deckexclusives, xytkn) -> REVISAR. Note 'H30' (letter PREFIX) does NOT "
                    "match ALPHA_SUFFIX_RE, so Tyranitar Aquapolis escapes that rule.",
            source="cardtrader_postprocess.py classify_decision",
            metadata={"topic": "existing_guards", "importance": "high"},
        ),
        CognitionItem(
            content="Margin is GROSS (no embedded fees) and is NOT the lever here: every "
                    "evaluation case carries a healthy margin (net >= 30%, profit >= R$50, "
                    "chase TOP/MID, validation OK) so the margin/chase/validation branches "
                    "never decide. The only thing that should change the decision is the "
                    "vintage/variant/promo/set surface. Do not retune margin thresholds.",
            source="DecisionConfig defaults + operator margin rule 2026-06-06",
            metadata={"topic": "margin_is_not_the_lever", "importance": "medium"},
        ),
        CognitionItem(
            content="Decision is a MECHANICAL rule, not an opinion, and routing is "
                    "conservative: a guard may downgrade COMPRA->REVISAR/NAO on a suspicion, "
                    "never upgrade. The operator validates REVISAR rows manually via the "
                    "TCG link. Keep `classify_listing(row) -> (decision, reason)` pure stdlib.",
            source="feedback_no_purchase_decisions + contract",
            metadata={"topic": "contract", "importance": "high"},
        ),
    ]

    ids = cog.add_batch(knowledge)
    print(f"Seeded {len(ids)} cognition items into {exp_dir / 'cognition_data'}")


if __name__ == "__main__":
    init_cognition()
