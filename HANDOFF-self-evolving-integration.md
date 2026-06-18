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
- [~] **A1.** Rodar `experiments/liga_match` (§3.1); se superar baseline, PR na Liga.
      ▶️ smoke (4 steps) JÁ superou (0,8889); falta o run cheio (`--steps 30`) e,
      se robusto, portar o ganho (token-set similarity) pra
      `liga-cards-scanner/src/matching/`. **Custa crédito OpenAI** — aguardando ok.
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

### Próximo passo (quando houver chave LLM)
Configurar `OPENAI_API_KEY` + `base_url`/`model` (§2) e então: smoke do
`circle_packing_demo` (A0) → rodar `liga_match`/`myp_match`/`comc_tiers`
(`python main.py --experiment <nome> --steps 30 --sample-n 3`) → se um candidato
superar o baseline de forma robusta, portar o ganho como PR draft no repo do
scanner. Os três evaluators já rodam offline e dão o baseline a bater.

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
