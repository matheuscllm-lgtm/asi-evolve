# sealed_match — experimento ASI-Evolve (sealed scanner) + ACHADO

**Data:** 2026-06-21 · **Veredito: NÃO EVOLUIR (lógica já no ótimo global).**

## O que é
Evolui a LÓGICA do matcher de produto SELADO Pokémon (`match_title(title, skus)` —
título BR bagunçado → SKU canônico) do `sealed-arbitrage-scanner`. Precision-first:
casar SKU errado = margem fantasma = capital do operador.

- `initial_program` — a lógica atual do matcher (normalize + contains_term whole-word
  + guards single/acessório + tiebreak era_umbrella). Extraída de `sealed_arbitrage_scanner.py`.
- `evaluator.py` — pontua contra `cases.json` usando `registry_terms.json` (vocabulário
  REAL do registry = DADO fixo, NÃO evoluído). F0.5 + piso de precisão 0.95.
- `cases.json` — 56 casos rotulados de scans reais 2026-06 (40 positivos HIGH reais +
  16 rejects/armadilhas). `registry_terms.json` — 105 SKUs (set/type/exclude/requires terms).

## Baseline (rodado)
```
python evaluator.py initial_program out.json   ->  eval_score = 1.0
precision 1.0 · recall 1.0 · 56/56 corretos (tp=40 fp=0 fn=0 tn=16)
```

## Por que NÃO foi rodada a evolução (decisão eu + 2 agentes revisores)
1. **Sem gradiente:** baseline já em 1.0 com piso de precisão; o loop maximiza um
   score já no teto → caminhada aleatória, nada a descobrir.
2. **A única direção alcançável (fuzzy/substring) QUEBRA precisão** — exatamente o que
   o design whole-word + exclude-tokens evita de propósito. Pagar LLM p/ empurrar no
   modo de falha que custa dinheiro.
3. **Headroom real está em DADO, não lógica:** dos ~483 anúncios EN sem match em 2
   scans, só ~3 FNs plausíveis, TODOS gaps de vocabulário (SKU/termo faltando) que a
   evolução-de-lógica não toca. E enriquecer vocabulário PT espalharia risco de FP
   (edição Copag PT sem palavra de idioma) — Liga já titula com o nome EN do set, então
   o ganho de recall é ínfimo. Auditoria independente dos 66 GREEN do scan = 0 FP.
4. **Corrobora memória:** mesmo desfecho do CardTrader/MYP (fluxo real limpo → no-port).

## Resultado aproveitado
O eval (56 casos reais) foi PORTADO como teste de regressão de precisão no scanner:
`tests/test_matcher_regression.py` (PR #38, mergeado) — trava precisão=1.0 contra
mudanças futuras. O experimento fica como guarda reutilizável: re-rodar o baseline
após mexer no matcher/registry deve dar 1.0.

## Risco latente documentado (teórico, 0 em dado real)
SKUs que JÁ têm aliases PT (`asc-tech-sticker`, `meg-*`) casam nome PT do set SEM
palavra de idioma ("Heróis Excelsos Tech Sticker") → uma edição Copag PT viraria FP.
Não materializou em 2 scans. Fix (se um dia aparecer): exigir marcador EN p/ match via
alias PT, ou rebaixar p/ REVIEW. Decisão adiada (gate de revisor).
