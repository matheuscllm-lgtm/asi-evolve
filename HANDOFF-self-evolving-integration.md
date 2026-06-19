# HANDOFF — Integração do ASI-Evolve nos scanners + padronização de entrega (modelo MYP)

## 🟢 FECHAMENTO 2026-06-19 — 4 scanners no método, 3 ports + Liga confirmado ótimo

**Parte A (precision-weighted objective F0.5 + piso) aplicada nos 4 evals.** Provado que o
piso ZERA candidatos que trocam precisão por recall (overfit) → a evolução só "ganha"
preservando precisão. 4 scanners passados pelo método com objetivo correto:

- **CardTrader** GG## guard → PR #25 MERGEADO.
- **COMC** gap-gate Tier 2 → PR #5 MERGEADO.
- **MYP** rarity-confidence (supranumerário "Comum" = raridade mal-rotulada, flag/review não
  bloqueio; validado em dado real, flag precisão 0,28→1,0) → PR #49 MERGEADO. Eval enriquecido
  com 33 casos reais. Re-run plateauou no baseline (rarity-gate não re-descoberto pela LLM, mas
  já shipado).
- **Liga** (era o mais defasado): liga_match Part A (piso 0,90) + reseed do initial_program pro
  estado #25 (F0.5 0,9091). Evolução FORWARD plateauou — nenhum candidato superou #25 (os que
  tentaram zeraram pelo piso ou perderam recall). **#25 é o ótimo precision-safe → sem port novo.**

**Conclusão:** os 4 ótimos precision-safe estão shipados/confirmados. Próximos ganhos exigiriam
NOVAS superfícies de função ou mais dado real (retorno decrescente). Loop encerrado sem ganho novo.

### ▶️ PRÓXIMO PASSO escolhido pelo operador: CardTrader — enriquecer com dado real
O eval do `cardtrader_classify` está SATURADO (GG## shipado → score **1.0, precisão 1.0**), então
forward-run não tem headroom. As 5 classes de FP do eval (TG##/GG##/alpha-suffix/sets sem
cobertura/markup) já estão todas tratadas. Pra achar ganho novo, **enriquecer com dado real +
descobrir classes de FP NOVAS** (mesmo caminho do MYP):
1. `~/card-trader-scanner/outputs/*.xlsx` (weekly/vintage) → extrair linhas reais + features do
   `classify_decision` (net_margin, lucro_liq, chase_tier, card_number, set_code, validation_status,
   markup) + Decisão COMPRA/REVISAR/NAO.
2. **Operador rotula** quais COMPRA são FP e de que CLASSE NOVA (reverse-holo mismatch, vintage
   inflado LC/BA-20, low-confidence holo "Variante Baixa Confiança"…).
3. `experiments/cardtrader_classify/real_cases.json` (gitignored). LOADER já pronto em
   `myp_match/evaluator.py::_load_real_cases` — **replicar** no cardtrader_classify (CASES =
   sintético + real).
4. `python main.py --experiment cardtrader_classify --steps 25 --sample-n 3 --eval-script
   "C:/Users/mathe/asi-evolve/experiments/cardtrader_classify/eval.sh"`.
5. Portar SÓ precision-safe (precisão ≥ piso 0.57) ao `cardtrader_postprocess.py::classify_decision`
   com pytest verde (94) + draft PR. §0: nunca push main, não recomendar compra.

---

## 🟢 ATUALIZAÇÃO 2026-06-19 (overnight autônoma) — CardTrader portado, MYP no-port

- **CardTrader (NOVO):** experimento `experiments/cardtrader_classify` (evolui
  `classify_decision` COMPRA/REVISAR/NAO; COMPRA-F1, precision-first). Gap real:
  produção guardava só Trainer Gallery `TG##`, não o irmão **Galarian Gallery `GG##`**
  (mesma inflação pokemontcg.io). Baseline COMPRA-F1 **0,7273** → evolução generalizou
  `^(?:TG|GG)\d+` no step 1 → **1,0** (regex, sem hardcode). **IDEIA portada** →
  **draft PR `card-trader-scanner#25`** (`feat/galarian-gallery-fp-guard`, 94 testes verdes).
  Mudança CONSERVADORA (guard ADITIVO: GG→NAO/manual como TG, nunca auto-compra). Caveat no PR:
  inflação GG inferida por identidade estrutural, operador valida no merge.
- **MYP (re-run):** `myp_match` 25 steps fresh → **EMPACOU no baseline 0,875, NO-PORT**
  (confirma sessão anterior). 2 FN = promos non-Comum mal-flagados supranumerário. Candidato
  offline "gate supranumerário por rarity==Comum" recupera 1 FN → **0,9412, precisão 1,0** — mas
  ESTREITA um guard de precisão (em dado real um supranumerário FP non-Comum vazaria); eval é
  sintético. **Não portado** — validar contra dado MYP real antes (próxima sessão).
- **COMC (re-run):** `comc_tiers` → evolução "ganhou" 0,78→0,90 F1 mas **OVERFIT** (baixou cutoffs
  NAME_STRONG 90→88 etc. → precisão 0,90→0,81, +2 FP). REJEITEI o candidato F1-max. O lever
  PRECISION-SAFE no MESMO eval = **gap-gate no Tier 2** (exigir best−runner≥gap, como o Tier 3 já
  faz): precisão **0,90→1,0**, recall igual (FP 1→0). Validado externamente (matcher.py: Tiers
  0,90/0,85 não tinham o gap que o Tier 3 tem). **PORTADO** → draft PR `scanner-comc#5`
  (gap-gate Tier 2 + 2 testes; 52 verdes). Tier 1' não gated (same-name finish dropparia recall).
- **Lição:** guard ADITIVO (GG) ou gap-gate de PRECISÃO (COMC Tier 2) portam limpo; guard
  RESTRITIVO de recall em eval sintético (MYP) não. **F1 é objetivo errado p/ scanner precision-first
  — escolher o candidato precision-safe, não o F1-max.**

---

## 🟢 ESTADO ATUAL — LEIA PRIMEIRO (fim de sessão 2026-06-18)

A integração está **rodando de verdade** e a primeira leva de trabalho foi
**mergeada no `main`**. Resumo pra retomar sem reler tudo:

**Feito e mergeado (3 PRs):**
- `liga-cards-scanner#25` ✅ **merged** — matching token-aware + containment + aliases
  reais + threshold 0,82 (descoberto pelo ASI-Evolve, **portado à mão** — o código
  do LLM tinha aliases alucinados). F1 (33 casos) 0,63→0,90, **precisão mantida**, 158 testes verdes.
- `scanner-comc#3` ✅ **merged** — entrega COMC na coluna única `Links` (padrão MYP/Liga), 50 testes.
- `asi-evolve#1` ✅ **merged** — este handoff + 3 experimentos + 4 fixes de Windows + runbook §9.

**Resultado dos 3 runs ao vivo (gpt-4o, ~US$6 na sessão):** só **liga** rendeu port limpo.
**myp_match** empacou no baseline (sem ganho). **comc_tiers** bateu 1,0 mas era overfit de
fronteira — eval enriquecido revelou troca precisão↔recall (0,90→0,81) → **não portado** (COMC
é precision-first). Ver §6 (fim) pros detalhes.

**Ambiente (tudo persistido como User env var no Windows — toda sessão herda):**
`OPENAI_API_KEY`, `ASI_EVOLVE_BASH=C:\Program Files\Git\bin\bash.exe`,
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`. `.venv` montado em `~/asi-evolve`.
Modelo de embedding já no cache do HF. **Como rodar = §9** (runbook Windows, comando exato;
`--eval-script` ABSOLUTO é obrigatório, senão tudo pontua 0,0).

**Gotchas que custaram caro (não re-descobrir):**
- CI dos repos fica **VERMELHA por billing do GitHub Actions** (operador não custeia; jobs
  falham em 3-4s sem rodar step). **Validar SEMPRE com `pytest` LOCAL.** Merge normal passa
  (check não-obrigatório, estado `UNSTABLE`); **não** usar `gh pr merge --admin` (guard-rail bloqueia, e com razão).
- O downloader do HuggingFace **trava em 0 B** nesta máquina → modo offline + cache via `curl`.
- `bash` nu no Windows = WSL (falha HCS) → por isso `ASI_EVOLVE_BASH`.

**Próximos passos (quando quiser continuar):**
1. **Extrair mais ganho:** reseedar a evolução a partir do **melhor candidato** (não do baseline
   fraco — ele empaca/overfita). Ex.: trocar `experiments/<exp>/initial_program` pelo melhor `code`
   e rodar `--steps 30`.
2. **myp_match / comc_tiers:** só rendem se os evals forem **enriquecidos com dado real** (os
   atuais são sintéticos; o comc tentou trapacear baixando cortes). Sem isso, não portar.
3. Branches `claude/self-evolving-agent-integration-budf77` seguem nos 3 repos (não deletadas;
   o operador roda `git push origin --delete <branch>` se quiser limpar — harness/remote dá 403).
4. **Regras invioláveis seguem (§0):** PR draft + testes verdes; entrega = tabela no chat; margem
   bruta; não recomendar compra.

> Memória local equivalente: `~/.claude/.../memory/asi_evolve_integration.md` (auto-carregada
> em sessão local). O resto deste documento (§1–§9) é o detalhe técnico/histórico.

---

> **Para quem é isto:** uma sessão do Claude Code **rodando no terminal local do
> Matheus** (com shell completo, venvs e — se configurado — uma chave de LLM).
> Este documento foi gerado numa sessão de **nuvem** que **não pôde executar** o
> ASI-Evolve (sem endpoint de LLM, sem deps instaladas, container efêmero). Aqui
> está tudo mapeado para você **dar seguimento no terminal**: instalar pendências,
> rodar a evolução, padronizar a entrega dos scanners e abrir os PRs.
>
> **Data:** 2026-06-18 · **Branch de trabalho (todos os repos):**
> `claude/self-evolving-agent-integration-budf77`

---

## 0. Regras invioláveis (do operador)

1. **Desenvolver sempre na branch** `claude/self-evolving-agent-integration-budf77`.
   **Nunca** dar push em `main`. Toda entrega é **PR draft** para revisão.
2. **Não comprometer os scanners.** Mudança de código só entra com os **testes do
   repo passando** (`pytest`/suites offline). Sem teste verde, não abre PR.
3. **Não recomendar compra.** Os scanners reportam dados; capital é decisão do
   operador. (Regra cross-scanner.)
4. **Entrega = tabela markdown no chat**, gerada **pela ferramenta do repo**, nunca
   montada à mão. Arquivo (`.xlsx`/`.csv`) só sob pedido explícito.
5. **Margem é BRUTA** (sem taxas embutidas), piso de relevância por scanner. Não mexer.

---

## 1. O que é o ASI-Evolve (resumo operacional)

Framework de **otimização evolutiva de código**: dado (a) um *programa-semente*,
(b) um *evaluator* que devolve um score e (c) conhecimento de domínio, ele roda o
loop **LEARN → DESIGN → EXPERIMENT → ANALYZE** por N rounds e devolve um banco de
candidatos ranqueados + o melhor código.

- **Agentes:** Researcher (propõe candidato), Engineer (roda `eval.sh`, lê
  `results.json`, pontua), Analyzer (destila lições). Manager (opcional) sintetiza prompts.
- **Memória:** *Cognition Store* (conhecimento semeado, FAISS) + *Experiment Database*
  (todo trial com motivação/código/resultado/análise; sampling UCB1/island/greedy/random).
- **Entrada:** `python main.py --experiment <nome> --steps N --sample-n K`.
- **Estrutura de um experimento** (`experiments/<nome>/`):
  `input.md` · `config.yaml` · `initial_program` · `evaluator.py` · `eval.sh`
  (escreve `results.json` com `{"success":bool,"eval_score":float,...}`) ·
  `init_cognition.py` · `prompts/{researcher,analyzer}.jinja2`.
- `asi-evolve`, `asi-main` e `github.com-GAIR-NLP-ASI-Evolve` são **clones idênticos**
  do mesmo upstream (GAIR-NLP/ASI-Evolve). Trabalhe em **`asi-evolve`**.

---

## 2. Pendências para o ASI-Evolve rodar (passo a passo no terminal)

```bash
cd ~/asi-evolve            # ou onde o clone está
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # openai, pyyaml, jinja2, numpy, faiss-cpu, sentence-transformers, wandb
```

**Configurar o LLM (obrigatório — sem isto a evolução NÃO roda).** O ASI-Evolve usa
um cliente **compatível com OpenAI**. Edite o bloco `api:` em
`experiments/<exp>/config.yaml` (ou no `config.yaml` raiz):

```yaml
api:
  provider: "openai"
  base_url: "https://api.openai.com/v1"   # ou endpoint local: http://localhost:30000/v1 (sglang/vLLM/Ollama-shim)
  api_key: "${OPENAI_API_KEY}"            # export OPENAI_API_KEY=...  (NUNCA commitar a chave)
  model: "gpt-4o"                          # ou o nome do seu modelo local
```

> Nota: o ambiente de nuvem do Claude Code só tem `ANTHROPIC_BASE_URL` (do próprio
> Claude) — **não** serve como endpoint OpenAI para o ASI-Evolve. Use uma chave
> OpenAI-compatível sua ou um servidor local (sglang/vLLM/Ollama).

**Smoke test do framework** (confirma que tudo liga antes de plugar os scanners):

```bash
python experiments/circle_packing_demo/init_cognition.py
python main.py --experiment circle_packing_demo --steps 10 --sample-n 3
```

Se o demo evoluir e gravar `steps/step_*/results.json`, o framework está OK.

---

## 3. Workstream A — Experimentos ASI-Evolve por scanner

A ideia: para cada scanner, escolher **uma função pequena e bem-definida** com um
**evaluator offline determinístico** (sem rede), evoluí-la, e **devolver o código
evoluído como PR** no repo do scanner (na branch, com `pytest` verde). **Não** ligar
o ASI-Evolve direto na produção; ele é um laboratório separado dentro de `asi-evolve`.

### 3.1 JÁ PRONTO — `experiments/liga_match/` (template de referência)

Construído e **validado offline** nesta sessão (baseline **F1 = 0,75**, com headroom
claro). Evolui o **scorer de matching da Liga** (nome 0.7 / set 0.3, difflib, thr 0.85)
para maximizar F1 num conjunto rotulado embutido (aliases de set PRE/SSP/151, acentos,
V-MAX, desambiguação por set, e casos "rejeitar" que punem threshold baixo).

```bash
# smoke do evaluator (offline, stdlib — não precisa de LLM):
bash experiments/liga_match/eval.sh experiments/liga_match/initial_program
cat experiments/liga_match/results.json     # eval_score = F1 do baseline (~0.75)

# semear conhecimento e evoluir (precisa do LLM do passo 2):
python experiments/liga_match/init_cognition.py
python main.py --experiment liga_match --steps 30 --sample-n 3
```

Contrato do programa evoluído: expõe `score_match(offer_name, offer_set, cand_name,
cand_set) -> float` e `FUZZY_THRESHOLD`. **Use este experimento como molde** para os
próximos dois.

**Como devolver o ganho à Liga (PR):** se um candidato superar o baseline de forma
robusta, porte as melhorias (novos aliases em `SET_ALIASES`, similaridade token-aware,
threshold) para `liga-cards-scanner/src/matching/{normalization,card_matcher}.py`,
rode `pytest -q` (158 testes — **não pode quebrar nenhum**) e abra PR draft na branch.

### 3.2 A CONSTRUIR — `experiments/myp_match/` (MYP)

- **O que evoluir:** a lógica de detecção de deal/false-positive do MYP (filtros TCG
  suspect / supranumerário / margem) — alvo: maximizar `deals_clean` sem inflar ruído.
- **Evaluator offline:** reaproveite `myp-arbitrage-scanner/bench.py` (modo **mockado**,
  sem rede) e os fixtures de `test_v5_8_offline.py` (Jirachi=suspect, Psyduck=paginação,
  Darumaka=override de preço). `eval_score` = ex.: `deals_clean` / `deals` ou F1 de
  "suspect vs limpo" sobre os fixtures rotulados.
- **Cognition:** semeie com `myp-arbitrage-scanner/CLAUDE.md` (margem bruta, NM-only,
  EN-only, supranumerário `card_num > set_total`, TCG suspect = TCG declarado ≫ última
  venda, fonte primária pokemontcg.io). Veja também `docs/optimization-loop.md` (o MYP
  já tem um loop medir→mudar→verificar — alinhe o evaluator a ele).

### 3.3 A CONSTRUIR — `experiments/comc_tiers/` (COMC)

- **O que evoluir:** a **calibração dos tiers de confiança** do matcher
  (`scanner-comc/comc_scanner/matcher.py`: T1 0.95/0.90, T2 0.85, T3 0.70).
- **Evaluator offline:** os fixtures de `scanner-comc/tests/test_matcher.py` (índice de
  produtos sintético + preços). `eval_score` = **calibração** (precisão por tier: o TP%
  previsto bate com o real) e/ou F1 de match.
- **Cognition:** `scanner-comc/CLAUDE.md` + `README.md` (NM-only, EN-only, margem bruta
  30%, piso US$10, holofoil preferido, flag `validar` < 0.90).

> **Fora de escopo agora:** eBay (graded + trust score), Pokémon-Outlook (score de longo
> prazo) e Integrado/Sealed têm superfícies diferentes — documentar e deixar para depois.

---

## 4. Workstream B — Padronização da entrega (modelo MYP)

**Modelo canônico:** `myp-arbitrage-scanner/myp_summary.py` — coluna **Carta**
(nome+número, helper `carta_label`) e coluna **Links** (`[oferta](url) · [TCG](url)`,
ambos lidos do XLSX, nunca inventados), flag **"validar manualmente"** nos buckets
suspeitos, **todos** os deals (não amostra). Gap analysis dos demais:

| Scanner | Arquivo / função | Estado | Ação |
|---|---|---|---|
| **CardTrader** | `cardtrader_postprocess.py::build_delivery_markdown` | **já bate** (links + coluna Flag) | confirmar; travar com teste se faltar |
| **Liga** | `src/reporting/markdown.py::build_markdown` | **já bate** (links + Nota fuzzy) | nenhuma mudança |
| **COMC** | `comc_scanner/reporter.py::render_markdown` | quase | **juntar** `Oferta \| Referência` numa coluna **`Links`** = `[oferta](…) · [referência](…)`; flag já existe. Atualizar `tests/test_reporter.py` |
| **eBay** | `src/report.py::to_markdown` | diverge (graded/score) | **fora de escopo** — propósito diferente |
| **Integrado** | `delivery.py::build_markdown` | diverge (multi-fonte, URLs cruas) | opcional: tornar links clicáveis; **não** forçar formato MYP |
| **Pokémon-Outlook** | `outlook/report.py::ranking_markdown` | diverge (score, só link TCG) | **fora de escopo** |
| **Sealed** | só XLSX | diverge (sem markdown) | **fora de escopo** |

**Mudança concreta de maior valor agora = COMC.** Procedimento:
1. Em `comc_scanner/reporter.py::render_markdown`, fundir as duas colunas de link numa
   única `Links` no formato `[oferta](url) · [referência](url)` (espelhando
   `myp_summary.py::delivery_links` e o `_links` da Liga).
2. Ajustar `tests/test_reporter.py` (ele trava o formato — links + flag + nome+número).
3. `python -m pytest tests/` verde → PR draft na branch do `scanner-comc`.

---

## 5. Autonomia — loop de 15 em 15 minutos

Use a skill **`/loop`** para reexecutar um comando-driver a cada 15 min:

```
/loop 15m continue o HANDOFF-self-evolving-integration.md: avance o próximo item do
backlog (§6), rode os testes, e só abra/atualize PR draft se os testes passarem
```

**Guard-rails (não inundar o operador):**
- **No máximo 1 PR draft por repositório.** Ciclos seguintes **iteram no PR já aberto**
  (respondendo review/CI), não abrem PRs novos.
- Cada ciclo: um passo pequeno e verificável; se os testes do repo não passarem,
  **não** abrir/atualizar PR — registrar o bloqueio e seguir.
- **Parar o loop** quando o backlog (§6) acabar ou o operador pedir.
- Nunca push em `main`; sempre na branch; PRs sempre **draft**.

---

## 6. Backlog priorizado (checklist)

> **Progresso (sessão terminal 2026-06-18):** A2/A3/B1/B2 feitos; **A0 ✅ e a
> evolução RODANDO** com chave OpenAI (gpt-4o). Smoke do `liga_match` validado
> ponta-a-ponta: nó inicial = baseline real 0,75 → candidato evoluído **0,8889**
> (token-set similarity + threshold 0,82; recall 0,667→0,889). Ver §9 (runbook
> Windows) — 4 bugs reais foram corrigidos pra chegar aqui.

- [x] **A0.** Instalar deps + configurar LLM + smoke. ✅ deps no `.venv`, chave
      OpenAI persistida (Windows User var), modelo `gpt-4o`. Smoke `liga_match`
      evoluiu 0,75 → 0,8889. Loop LLM (Researcher/Engineer/Analyzer) + cognição
      + avaliação funcionando. (Pulei o `circle_packing_demo`: o `liga_match` é
      smoke melhor — evaluator offline e do nosso domínio.)
- [x] **A1.** Rodar `experiments/liga_match` (§3.1); se superar baseline, PR na Liga.
      ✅ run cheio (30 steps) → melhor candidato F1 0,8889 (token-set + containment).
      Eval enriquecido p/ 33 casos (commit) → candidato 0,898 vs baseline 0,632 (generaliza).
      Re-run do baseline empacou em 0,649 (evoluir do baseline fraco cai em poço local).
      **Ganho portado à mão** (ideia, não código LLM — aliases do LLM eram alucinados):
      **draft PR `liga-cards-scanner#25`** (token-aware score + containment + thr 0,82
      + aliases reais; F1 33-casos 0,63→0,90, precisão 0,92 mantida; **158 testes verdes**).
- [x] **B1.** COMC: fundir links em `render_markdown` + atualizar testes + PR (§4).
      ✅ **draft PR `scanner-comc#3`** — coluna única `Links` (`[oferta] · [referência]`),
      README+CLAUDE.md atualizados, suíte offline 50 verde (reporter 5→7).
- [x] **A2.** Construir `experiments/myp_match` ligado a `bench.py`/fixtures (§3.2).
      ✅ scaffold offline — baseline F1 (clean-class) = 0,875 (prec 1.0, rec 0,778).
- [x] **A3.** Construir `experiments/comc_tiers` ligado a `test_matcher.py` (§3.3).
      ✅ scaffold offline — baseline F1 (accept/reject) = 0,889 (prec 1.0, rec 0,8).
- [x] **B2.** Confirmar CardTrader/Liga já no formato; travar com teste se faltar.
      ✅ ambos já batem **e já travados por teste** — CardTrader 27 verdes
      (`test_delivery_markdown.py`/`test_ct_myp_model.py`), Liga 10 verdes
      (`test_markdown.py`). Sem mudança necessária.
- [x] **PR-meta.** Manter o PR draft do `asi-evolve` (este handoff + scaffold) atualizado.
      ✅ A2/A3 commitados na branch (PR draft `asi-evolve#1` atualizado).

### Resultados dos 3 runs ao vivo (2026-06-18) — 1 port, 2 não
- **liga_match → PORTADO** (`liga-cards-scanner#25`). Único port limpo: o ganho
  (token-set + containment + aliases reais + thr 0,82) **manteve a precisão**
  (0,92) ao subir o recall. Eval enriquecido p/ 33 casos confirmou generalização.
- **myp_match → SEM GANHO.** Run de 30 steps empacou no baseline 0,875; os 2 FN
  (supranumerário difícil) exigem feature nova, não ajuste de regra. Não portado.
- **comc_tiers → NÃO PORTADO (troca precisão↔recall).** Bateu F1 1,0 no eval de 15
  casos só **baixando os cortes** (90→88, 92→90) — overfit de fronteira. Eval
  enriquecido p/ 23 casos (com armadilhas de precisão) revelou: F1 sobe (0,78→0,90)
  **mas precisão cai 0,90→0,81** (3 FP). Conflita com a filosofia precision-first
  do COMC → não portado. Insight: travar Tier 2 por gap (como o Tier 3) capturaria
  o recall sem perder precisão — mas é heurística nova, precisa de dado real.

**Lição transversal:** evoluir a partir do baseline fraco/eval pequeno → platô ou
overfit de fronteira. O caminho que funcionou (liga): evoluir → **enriquecer o eval
offline** → confirmar que precisão se mantém → só então portar a IDEIA (nunca o
código LLM cru; aliases vinham alucinados). Para novos ganhos: reseedar a evolução
a partir do melhor candidato e/ou enriquecer os evals de myp/comc com dado real.

---

## 7. Verificação

- **Scaffold (offline, sem LLM):** `bash experiments/liga_match/eval.sh
  experiments/liga_match/initial_program` deve gerar `results.json` com
  `success: true` e `eval_score ≈ 0.75`. Um candidato melhor sobe esse número.
- **Framework:** smoke do `circle_packing_demo` evolui por 10 steps sem erro.
- **Scanners:** `pytest`/suite offline de cada repo **verde** antes de qualquer PR.
- **PRs:** todos **draft**, na branch `claude/self-evolving-agent-integration-budf77`,
  base `main`.

---

## 8. Referência rápida de caminhos

- ASI-Evolve: `~/asi-evolve` (entry `main.py`; experimentos em `experiments/`)
- MYP: `~/myp-arbitrage-scanner` (`myp_summary.py`, `bench.py`, `test_v5_8_offline.py`, `docs/optimization-loop.md`)
- Liga: `~/liga-cards-scanner` (`src/matching/card_matcher.py`, `src/reporting/markdown.py`, `pytest` 158)
- COMC: `~/scanner-comc` (`comc_scanner/reporter.py`, `comc_scanner/matcher.py`, `tests/test_reporter.py`)
- CardTrader: `~/card-trader-scanner` (`cardtrader_postprocess.py`)

---

## 9. Runbook Windows (como rodar a evolução nesta máquina) — 2026-06-18

Validado nesta máquina (Windows 10, sem GPU). O `.venv` já existe com as deps.
**4 bugs reais** foram corrigidos pra chegar a um run que pontua de verdade
(commits nesta branch): expansão de `${ENV_VAR}` em `utils/llm.py`; `eval.sh`
(cygpath p/ paths MSYS→Windows + `python` em vez de `python3` stub da Store);
`engineer` aceita `ASI_EVOLVE_BASH` (o `bash` nu vira WSL e falha com HCS
0x800705aa). Detalhe abaixo do que **persiste sozinho** vs. o que passar **por run**.

**Já persistido (User env vars — toda sessão nova herda, não re-setar):**
- `OPENAI_API_KEY` (chave OpenAI) · `ASI_EVOLVE_BASH=C:\Program Files\Git\bin\bash.exe`
- `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` — o downloader do HuggingFace
  **trava em 0 bytes** nesta máquina (não é rede: `curl` baixa a ~1 MB/s; é o
  cliente do hub). O modelo de embedding `all-MiniLM-L6-v2` já foi baixado via
  `curl` pro cache (`~/.cache/huggingface/hub/...`); offline lê do cache em 0,4s.
  Se faltar o modelo um dia: `curl` os arquivos do repo HF pro snapshot do cache.

**Comando que funciona (PowerShell):**
```powershell
cd C:\Users\mathe\asi-evolve
$env:OPENAI_API_KEY      = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:ASI_EVOLVE_BASH     = 'C:\Program Files\Git\bin\bash.exe'
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
# --eval-script É OBRIGATÓRIO e ABSOLUTO (sem ele a avaliação não roda → tudo 0.0;
# o engineer roda o eval com cwd=steps/step_N, então caminho relativo não acha):
.venv\Scripts\python.exe -u main.py --experiment liga_match --steps 30 --sample-n 3 `
  --eval-script "C:/Users/mathe/asi-evolve/experiments/liga_match/eval.sh"
```
Trocar `liga_match` por `myp_match` / `comc_tiers` (e o caminho do `--eval-script`).
Logs do framework vão pra `experiments/<exp>/logs/` e por step em
`experiments/<exp>/steps/step_N/`. O melhor nó fica em `steps/best/`.
