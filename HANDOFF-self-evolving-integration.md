# HANDOFF — Integração do ASI-Evolve nos scanners + padronização de entrega (modelo MYP)

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

- [ ] **A0.** Instalar deps + configurar LLM + smoke do `circle_packing_demo` (§2).
- [ ] **A1.** Rodar `experiments/liga_match` (§3.1); se superar baseline, PR na Liga.
- [ ] **B1.** COMC: fundir links em `render_markdown` + atualizar testes + PR (§4).
- [ ] **A2.** Construir `experiments/myp_match` ligado a `bench.py`/fixtures (§3.2).
- [ ] **A3.** Construir `experiments/comc_tiers` ligado a `test_matcher.py` (§3.3).
- [ ] **B2.** Confirmar CardTrader/Liga já no formato; travar com teste se faltar.
- [ ] **PR-meta.** Manter o PR draft do `asi-evolve` (este handoff + scaffold) atualizado.

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
