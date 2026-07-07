# CLAUDE.md — asi-evolve

Instruções para qualquer sessão Claude Code (local ou nuvem) que trabalhe neste repo.
O operador (Matheus) é médico, não-programador: explique termos técnicos em linguagem
simples na primeira ocorrência, mantendo precisão.

> **O que é isto, em uma frase:** um laboratório de **otimização evolutiva de
> código** — dado um programa-semente, um avaliador que devolve uma nota e
> conhecimento de domínio, um LLM (modelo de linguagem) propõe variações do
> programa em rounds sucessivos (LEARN → DESIGN → EXPERIMENT → ANALYZE) até
> achar código melhor. É o fork do framework **ASI-Evolve** (GAIR-NLP/SJTU,
> paper em `assets/paper.pdf`) usado aqui como laboratório para evoluir funções
> pequenas dos scanners de cartas Pokémon da frota — **nunca ligado direto na
> produção**: o ganho é validado offline e portado por PR ao repo do scanner.

## Relação com os repos irmãos (leia antes de mexer em qualquer um dos 3)

Há 3 repos parecidos na conta (`matheuscllm-lgtm/…`). **Este (`asi-evolve`) é o
repo de TRABALHO** — os outros dois não recebem os experimentos da frota:

| Repo | O que é | Diferença real (verificada por diff) |
|---|---|---|
| **`asi-evolve`** (este) | Fork do ASI-Evolve upstream + integração com a frota | Tem os 4 experimentos da frota (`cardtrader_vintage`, `comc_tiers`, `liga_match`, `myp_match`), o `HANDOFF-self-evolving-integration.md`, os fixes de Windows (`ASI_EVOLVE_BASH` em `pipeline/engineer/engineer.py`; expansão de `${ENV_VAR}` em `utils/llm.py`) e um `.gitignore` ampliado (artefatos de run) |
| **`asi-main`** | Espelho "limpo" do mesmo upstream + skill `/auto` | Quase idêntico a este, **SEM** os experimentos da frota, sem o HANDOFF e sem os 2 fixes acima. Não trabalhe nele |
| **`github.com-GAIR-NLP-ASI-Evolve`** | **NÃO é clone do upstream**: é o `asi-core`, uma reimplementação/destilação pequena e reutilizável do loop (`asi_core/` com `loop.py`, `pipeline/base.py`, `cognition/store.py`, `database/`), com `docs/PORTING.md` e `examples/circle_packing` | Motor domain-agnostic para portar o loop a outros projetos; código independente deste |

> O HANDOFF (§1) dizia que os 3 eram "clones idênticos" — isso valia em
> 2026-06-18; desde então **este repo divergiu** (fixes + experimentos). A
> instrução que segue valendo é a mesma: **trabalhe em `asi-evolve`**.

## Como rodar

### Setup (1ª vez, qualquer ambiente)

```bash
pip install -r requirements.txt
# deps: openai, pyyaml, jinja2, numpy, faiss-cpu, sentence-transformers, wandb (opcional)
```

Python 3.10+ (README). No PC do operador o `.venv` já existe em `~/asi-evolve`
(Windows: `.venv\Scripts\python.exe`).

### O loop LLM exige um endpoint OpenAI-compatível (sem isso NÃO roda)

O framework fala com **qualquer endpoint compatível com a API da OpenAI**
(OpenAI hospedado, ou servidor local sglang/vLLM/shim do Ollama). Os 4
experimentos da frota vêm configurados para `https://api.openai.com/v1` com
`model: "gpt-4o"` e `api_key: "${OPENAI_API_KEY}"` (lida do ambiente). O demo
`circle_packing_demo` aponta para um sglang local (`http://localhost:30032/v1`).

> ⚠️ **Sessão de nuvem NÃO consegue rodar o loop LLM** (não há endpoint OpenAI
> no container — o ambiente do Claude Code não serve como endpoint para o
> ASI-Evolve). Na nuvem dá para: editar código/experimentos, e rodar o **smoke
> offline dos evaluators** (abaixo), que é stdlib puro e não usa LLM.

### Smoke offline de um evaluator (sem LLM, roda em qualquer lugar)

```bash
bash experiments/liga_match/eval.sh experiments/liga_match/initial_program
cat results.json   # escreve no diretório atual; esperado: success:true, eval_score ≈ 0.63
                   # (F1 do baseline no eval ENRIQUECIDO de 33 casos; o ≈0.75 antigo era do eval original de 12)
```

### Rodar uma evolução (fluxo canônico)

```bash
# 1) semear o cognition store (o "conhecimento de domínio" que o LLM consulta):
python experiments/liga_match/init_cognition.py

# 2) rodar o loop:
python main.py --experiment liga_match --steps 30 --sample-n 3 \
  --eval-script /caminho/ABSOLUTO/para/experiments/liga_match/eval.sh
```

**Flags do `main.py`** (verificadas no argparse):

- `--config` — arquivo de config explícito (opcional; ver "Configuração").
- `--experiment` — nome do experimento (pasta em `experiments/`).
- `--steps` — número de rounds de evolução (default **10**).
- `--sample-n` — quantos nós históricos amostrar por round (default **3**).
- `--eval-script` — caminho do script de avaliação.

> ⚠️ **Armadilha nº 1: `--eval-script` é obrigatório na prática e tem que ser
> ABSOLUTO.** O Engineer roda o eval com diretório de trabalho =
> `experiments/<exp>/steps/step_N/` — caminho relativo não acha o script e
> **tudo pontua 0.0 sem erro claro**. Sem `--eval-script` nenhum candidato é
> avaliado.

Saídas do run (todas gitignored): `experiments/<exp>/steps/step_N/` (código do
candidato em `code`, `results.json`, `eval.log`), melhor nó em `steps/best/`,
logs em `experiments/<exp>/logs/`, estado retomável em `pipeline_state.json`
(o pipeline **retoma sozinho** um experimento interrompido: rodar de novo o
mesmo `--experiment` continua de onde parou; para recomeçar, apague
`pipeline_state.json` + `database_data/` + `steps/`).

### Windows (PC do operador) — runbook validado no HANDOFF §9

```powershell
cd C:\Users\mathe\asi-evolve
$env:OPENAI_API_KEY  = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')
$env:ASI_EVOLVE_BASH = 'C:\Program Files\Git\bin\bash.exe'
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
.venv\Scripts\python.exe -u main.py --experiment liga_match --steps 30 --sample-n 3 `
  --eval-script "C:/Users/mathe/asi-evolve/experiments/liga_match/eval.sh"
```

Essas 4 env vars **já estão persistidas como User env vars** no PC do operador
(toda sessão nova herda). Gotchas de Windows já resolvidos NO CÓDIGO — não
re-descobrir: `bash` nu vira WSL e falha (por isso `ASI_EVOLVE_BASH`); o
downloader do HuggingFace trava em 0 B nessa máquina (por isso modo offline — o
modelo de embedding já está no cache HF, baixado via `curl`); `eval.sh` já trata
paths MSYS→Windows via `cygpath` e usa `python` em vez do stub `python3` da Store.

## Configuração

A config é montada em camadas (`utils/config.py::load_config`), a de baixo
sobrescreve a de cima:

1. `config.yaml` da raiz (defaults do repo — traz placeholders `your_api_key`
   etc.; na prática os experimentos sobrescrevem);
2. `experiments/<nome>/config.yaml` (a config que vale de fato);
3. arquivo passado em `--config` (opcional, vence tudo).

Blocos do `config.yaml` (o que cada um controla):

| Bloco | Controla |
|---|---|
| `experiment_name` | nome default do experimento |
| `api` | o LLM: `provider`, `base_url`, `api_key`, `model`, `temperature`, `top_p`, `max_tokens`, `seed`, `timeout`, `retry_times`, `retry_delay`. Chaves extras (ex.: `extra_body`) são repassadas à API |
| `logging` | nível, console e Weights & Biases (`wandb.enabled` — ligado no default da raiz, **desligado** nos experimentos da frota) |
| `pipeline.agents` | liga/desliga os agentes: `manager` (off por padrão), `researcher`, `engineer`, `analyzer` |
| `pipeline.researcher` | `diff_based_evolution` (edita o pai via diffs SEARCH/REPLACE; **false** nos experimentos da frota = reescrita completa), `diff_pattern`, `max_code_length` |
| `pipeline.max_retries` / `engineer_timeout` | tentativas por agente / timeout (s) do eval |
| `pipeline.parallel.num_workers` | workers paralelos (1 = sequencial/debug; 2–4 produção) |
| `pipeline.sample_n` | nós históricos mostrados ao Researcher por round |
| `pipeline.judge` | juiz LLM opcional (off): `final_score = (1-ratio)*eval + ratio*judge`; exige `judge.jinja2` nos prompts do experimento |
| `cognition` | store de conhecimento: `storage_dir`, embedding `sentence-transformers/all-MiniLM-L6-v2` (dim 384), índice FAISS `IP`, `retrieval.top_k` / `score_threshold` |
| `database` | banco de experimentos: `storage_dir`, `max_size` (cheio → remove o pior), embedding, `sampling.algorithm` = `ucb1` (default, `ucb1_c`) / `greedy` / `random` / `island` (MAP-Elites, com parâmetros próprios) |

**Chaves de API e env vars (NUNCA versionar chave literal):**

- Qualquer valor string na config aceita `${ENV_VAR}` — resolvido do ambiente
  em dois pontos: `utils/config.py::_resolve_env_vars` (config inteira) e
  `utils/llm.py::_resolve_env` (`api_key`/`base_url`, com **erro claro** se a
  variável não existir, em vez de um 401 opaco).
- **`OPENAI_API_KEY`** — a chave que os 4 experimentos da frota referenciam.
- **`ASI_EVOLVE_BASH`** — caminho de um bash POSIX real (lido em
  `pipeline/engineer/engineer.py`; só necessário no Windows).
- `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` — lidas pelas libs do
  HuggingFace (não pelo código deste repo); workaround do PC do operador.
- Custo é real: os 3 runs ao vivo de 2026-06-18 (gpt-4o) custaram **~US$6**.

## Arquitetura

```
main.py                 entry point CLI; registra a raiz do repo como pacote importável "Evolve"
config.yaml             defaults do repo (camada 1 da config)
pipeline/
  main.py               Pipeline: orquestra o loop, estado retomável (pipeline_state.json), best snapshot
  researcher/           Researcher: lê database+cognition e propõe o próximo candidato
  engineer/             Engineer: grava o candidato em steps/step_N/code, roda `bash eval.sh`
                        (cwd = step dir; respeita ASI_EVOLVE_BASH), lê results.json e pontua
  analyzer/             Analyzer: destila a lição de cada trial para os rounds seguintes
  manager/              Manager (opcional, off por padrão): sintetiza prompts
cognition/cognition.py  Cognition store — conhecimento semeado, busca semântica (embedding + FAISS)
database/               banco de experimentos: todo trial com motivação/código/resultado/análise
  algorithms/           amostragem de pai: ucb1 / greedy / random / island (MAP-Elites)
utils/                  config (merge em camadas + ${ENV_VAR}), llm.py (LLMClient OpenAI-compatível,
                        retry, log por chamada), logger, prompt (Jinja2) + prompts/ default, diff,
                        best_snapshot, structures (Node, CognitionItem, LLMResponse)
experiments/            os experimentos (ver seção abaixo) + best/circle_packing (melhores
                        programas dos ablation runs do paper)
skills/evolve/          Agent Skill "evolve": abstração single-agent do loop com CLI próprio
                        (scripts/evolve-* + evolve_core/); runs em .evolve_runs/. Nota do README:
                        a skill é um "first pass" leve — para trabalho sério, rodar o pipeline
                        deste repo (main.py), que tem controle e qualidade maiores
.claude/commands/auto.md  skill /auto (ver última seção)
assets/                 paper.pdf + Overview.png
HANDOFF-self-evolving-integration.md  handoff canônico da integração com a frota (estado, runbook §9, backlog)
```

## Experimentos

Estrutura padrão de um experimento (`experiments/<nome>/`):

- `input.md` — descrição do problema (vai no prompt do Researcher);
- `config.yaml` — overrides deste experimento (API, sampling, timeouts);
- `initial_program` — o programa-semente (baseline) de onde a evolução parte;
- `evaluator.py` — pontua um candidato **offline** (stdlib, determinístico, sem rede);
- `eval.sh` — wrapper chamado pelo Engineer a cada round; contrato: candidato em
  `${STEP_DIR}/code` (ou 1º argumento, para smoke manual) → escreve
  `results.json` com `{"success": bool, "eval_score": float, ...}` (o Engineer
  exige o campo `eval_score`);
- `init_cognition.py` — semeia o cognition store (rodar 1× antes de evoluir);
- `prompts/researcher.jinja2` + `prompts/analyzer.jinja2` — prompts do experimento.

### Os 4 experimentos da frota (alvo = função pequena de um scanner, eval offline)

| Experimento | Alvo (repo da frota) | Estado (HANDOFF, 2026-06-18/20) |
|---|---|---|
| **`liga_match`** | scorer de matching Liga↔TCGplayer (`liga-cards-scanner/src/matching/`) — contrato: `score_match(...) -> float` + `FUZZY_THRESHOLD` | ✅ **único port limpo**: baseline F1 0,75 → candidato 0,8889 (medidos no eval ORIGINAL de 12 casos); o eval enriquecido p/ 33 casos confirmou generalização (0,63 → 0,90); ideia portada à mão (PR `liga-cards-scanner#25`, mergeado) |
| **`myp_match`** | classificador deal limpo vs false-positive do MYP (supranumerário / TCG suspect) | ❌ run de 30 steps empacou no baseline 0,875 — **não portado**; só rende com eval enriquecido com dado real |
| **`comc_tiers`** | calibração dos tiers de confiança do matcher do COMC | ❌ bateu 1,0 por overfit de fronteira; eval enriquecido revelou troca precisão↔recall (0,90→0,81) — **não portado** (COMC é precision-first) |
| **`cardtrader_vintage`** | guard de false-positive vintage do CardTrader (`classify_decision`: rotear `low_conf_variant` + suspect-sets p/ REVISAR) — contrato: `classify_listing(row) -> (decision, reason)` | ⏳ scaffold pronto e validado offline (baseline F1 0,818, prec 1,0; headroom real até 1,0). **PENDENTE rodar o loop LLM no terminal local** |

### Demos originais do upstream

- **`circle_packing_demo`** — empacotar 26 círculos num quadrado unitário
  (benchmark dos ablation studies do paper); config aponta para sglang local.
- **`experiments/best/circle_packing/`** — os melhores programas obtidos nos
  runs do paper (referência, não experimento rodável).

### Lições já pagas (não re-aprender com dinheiro)

- **Nunca portar código cru do LLM** ao scanner — portar a **IDEIA**, reescrita
  à mão com os testes do repo-alvo verdes (os aliases gerados pelo LLM no
  liga_match eram alucinados).
- Evoluir a partir de baseline fraco / eval pequeno → platô ou overfit de
  fronteira. Caminho que funcionou: evoluir → **enriquecer o eval offline** →
  confirmar que a precisão se mantém → só então portar. Para extrair mais
  ganho, reseedar o `initial_program` com o melhor candidato.

## Testes

**Este repo NÃO tem suíte de testes** (não há `tests/`, pytest nem CI). A
verificação é operacional:

- smoke offline do evaluator: `bash experiments/<exp>/eval.sh
  experiments/<exp>/initial_program` → `results.json` com `success: true` e o
  `eval_score` do baseline;
- smoke do framework: o `circle_packing_demo` (ou `liga_match`, que é offline e
  do nosso domínio) evolui alguns steps sem erro;
- e — regra dura da integração — **os testes do repo-alvo do port** (pytest de
  cada scanner) precisam estar verdes antes de qualquer PR lá.

## Fluxo de desenvolvimento e segurança

- **Branch + PR, nunca push direto em `main`** — é como todo o histórico foi
  construído (PRs #1, #2 e #4–#6 mergeados — o #3 foi fechado sem merge; regra
  inviolável nº 1 do HANDOFF §0). PRs de
  trabalho autônomo saem como **draft**.
- **Artefatos de run NUNCA entram no repo** (gitignored de propósito):
  `experiments/*/results.json`, `eval.log`, `database_data/`, `cognition_data/`,
  `steps/`, `logs/`, `pipeline_state.json`, `wandb/`, `candidate_*.py`, além de
  `.venv/`, `.evolve_runs/` (runs da skill evolve), `*.env` e artefatos de smoke
  na raiz (`/results.json`, `/eval.log`, `run_smoke.log`).
- **Segredos nunca versionados**: `OPENAI_API_KEY` vive só no ambiente (User
  env var no PC do operador) e entra na config via `${OPENAI_API_KEY}` — jamais
  chave literal em `config.yaml`.
- Regras invioláveis herdadas da frota (HANDOFF §0): não comprometer os
  scanners (port só com testes do repo-alvo verdes), não recomendar compra,
  entrega = tabela markdown gerada pela ferramenta do repo, margem bruta.
- Repo GitHub: `matheuscllm-lgtm/asi-evolve`. Upstream de origem:
  `GAIR-NLP/ASI-Evolve`.

## Skill `/auto` (`.claude/commands/auto.md`)

O repo tem uma skill/command: **`/auto`** — modo autônomo genérico da frota
(executa a tarefa ponta a ponta: corrige, integra, testa, commita, abre **PR
draft**, mergeia só quando trivialmente seguro), com pré-voo obrigatório
(ler o CLAUDE.md do repo, verificar handoff e branch), 4 freios duros (perda de
dados, segredo, custo relevante, decisão irreversível) e a nota de nuvem: o
container não tem `gh` CLI — operações GitHub via ferramentas `mcp__github__*`.
Leia o arquivo antes de operar nesse modo. (A skill `skills/evolve/` é outra
coisa: é o Agent Skill do próprio framework, ver Arquitetura.)
