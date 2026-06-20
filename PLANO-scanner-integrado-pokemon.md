# PLANO — Scanner Integrado de cartas Pokémon (juntar todos os scanners)

> **Objetivo (do operador):** juntar **todos os scanners de cartas Pokémon** que
> existem no GitHub num só — o `integrated-scanner` — entregando **uma visão
> única** por carta, comparando as fontes lado a lado.
>
> **Status deste documento:** plano de design escrito na sessão de nuvem
> `asi-evolve` (2026-06-20), que **não tem o `integrated-scanner` no escopo**.
> A parte de design (contrato, arquitetura, regras, entrega) **independe** de ler
> o código e está resolvida aqui. A execução acontece numa sessão que tenha os
> repos no escopo (ver §9). **Primeiro passo lá: ler o código atual antes de mexer
> — o `integrated-scanner` já é multi-fonte, isto é expansão, não recomeço.**

---

## 1. Inventário dos scanners Pokémon

Levantado em `github.com/matheuscllm-lgtm` (2026-06-20).

| Scanner | Repo | Tipo | Unidade | Referência de preço | Moeda da oferta | Saída hoje |
|---|---|---|---|---|---|---|
| **MYP** | `myp-arbitrage-scanner` | Arbitragem | Carta avulsa | pokemontcg.io / última venda | BRL | `myp_summary.py` (Carta + Links, flag, todos os deals) |
| **Liga** | `liga-cards-scanner` | Arbitragem | Carta avulsa | TCGplayer | BRL | `src/reporting/markdown.py::build_markdown` |
| **CardTrader** | `card-trader-scanner` | Arbitragem | Carta avulsa | Referência TCG | EUR/USD | `cardtrader_postprocess.py::build_delivery_markdown` |
| **COMC** | `scanner-comc` | Arbitragem (precision-first) | Carta avulsa | Referência TCG | USD | `comc_scanner/reporter.py::render_markdown` |
| **eBay** | `ebay-arbitrage-scanner` | Arbitragem (graded + raw) | Carta avulsa | Referência TCG | USD | `src/report.py::to_markdown` (graded + trust score) |
| **Sealed** | `sealed-scanner` | Produto lacrado | Booster/box | — | — | só XLSX |
| **Outlook** | `pokemon-longterm-outlook` | Previsão | Carta avulsa | Score de longo prazo | — | `outlook/report.py::ranking_markdown` |
| **Integrado** | `integrated-scanner` | **Junção (alvo)** | — | — | — | `delivery.py::build_markdown` (multi-fonte, URLs cruas) |

### Classificação por superfície (decide o que entra na v1)
- **Núcleo — arbitragem de carta avulsa (mesmo "deal"):** MYP, Liga, CardTrader,
  COMC, eBay. **Compartilham o mesmo conceito de oferta→referência→margem** → é o
  coração da integração e onde a comparação entre fontes faz sentido.
- **Superfície diferente (entram como seção própria OU ficam fora da v1):**
  - **Sealed** — unidade é produto lacrado (box/booster), não carta avulsa. Não
    casa com a chave "carta". Tratar como **seção separada** ("Lacrado"), nunca
    misturar na mesma tabela de cartas.
  - **Outlook** — é **previsão** (score de longo prazo), não arbitragem agora.
    Entra como **coluna de contexto** ("tendência" da carta) ou seção própria, não
    como um "deal".
  - **eBay graded** — cartas graded (PSA/CGC) são outro produto que a raw; manter a
    distinção `graded`/`raw` no registro (não comparar graded com raw).

> **Recomendação v1:** integrar o **núcleo (MYP, Liga, CardTrader, COMC, eBay-raw)**
> sob um contrato único de deal e uma entrega única. Sealed e Outlook entram como
> **seções anexas** opcionais. Assim a "junção" entrega valor real (comparar a
> mesma carta entre marketplaces) sem forçar coisas de naturezas diferentes na
> mesma tabela.

---

## 2. Arquitetura da integração

A pergunta central: **como o `integrated-scanner` recebe os dados de cada scanner?**
Como cada scanner é um **repo separado** com seu próprio pipeline, a opção robusta é
**acoplamento fraco por artefato**:

```
  [MYP]  [Liga]  [CardTrader]  [COMC]  [eBay]        cada scanner roda como hoje
    │       │         │           │       │
    ▼       ▼         ▼           ▼       ▼
  deals.json (contrato comum §3)  ...   ...           cada um emite o MESMO schema
    └───────┴────┬────┴───────────┴───────┘
                 ▼
        integrated-scanner (adapters → normaliza → dedup §5 → entrega §6)
                 ▼
        relatório único (modelo MYP §6)  [+ XLSX sob pedido]
```

- **Opção A (recomendada): cada scanner escreve um `deals.json`** no contrato comum
  (§3); o integrado **lê os arquivos** e funde. Vantagens: cada scanner continua
  rodando isolado (sem instalar tudo junto), o integrado não quebra se um scanner
  falha (degrada para "fonte ausente"), e dá pra rodar fontes em máquinas/horários
  diferentes. **É o caminho do HANDOFF** (padronização de entrega no modelo MYP).
- **Opção B: importar cada scanner como biblioteca** e chamar a API Python. Mais
  acoplado, exige todos instalados no mesmo ambiente; só vale se já houver pacote
  publicável. **Decidir na próxima sessão depois de ler `integrated-scanner/delivery.py`**
  (provavelmente já faz uma das duas — seguir o que já existe).

> **Onde o `integrated-scanner` já está:** o HANDOFF diz que `delivery.py::build_markdown`
> **já é multi-fonte com URLs cruas**. Então parte disso existe. O trabalho real:
> (1) garantir que **todas** as fontes Pokémon alimentem; (2) padronizar a saída no
> **modelo MYP** (links clicáveis + flags); (3) **dedup/comparação entre fontes** (§5).

---

## 3. Contrato comum de "deal" (a decisão de maior alavancagem)

Definir **um** registro por oferta, idêntico entre fontes. Isto **pode e deve ser
fixado agora** — é o que destrava o resto. Proposta (JSON, uma oferta por objeto):

```json
{
  "fonte": "myp | liga | cardtrader | comc | ebay",
  "carta": "Charizard ex",
  "numero": "199/165",
  "set": "SV2a / 151",
  "idioma": "EN",
  "condicao": "NM",
  "tipo": "raw | graded",
  "grade": null,
  "preco_oferta": 123.45,
  "moeda_oferta": "USD",
  "preco_referencia": 210.00,
  "fonte_referencia": "tcgplayer | pokemontcg.io",
  "margem_bruta_pct": 0.70,
  "link_oferta": "https://...",
  "link_referencia": "https://...",
  "flag_validar": true,
  "flag_motivo": "supranumerário 226/217",
  "scanner_versao": "myp v5.8"
}
```

**Regras de preenchimento (invariantes herdados dos scanners — §7):**
- `margem_bruta_pct` = `(referencia − oferta) / oferta`, **bruta** (sem taxas).
  É o **denominador comum** entre moedas (§8) — comparar fontes por % é correto
  mesmo com BRL/USD/EUR misturados.
- `condicao` sempre **"NM"**, `idioma` sempre **"EN"** (regra cross-scanner do MYP;
  cada scanner já filtra — o integrado só **confere e rejeita** o que vier fora).
- `flag_validar` + `flag_motivo` carregam os alertas de cada scanner
  (MYP: supranumerário `card_num>set_total`, TCG-suspect `declared/last_sale` alto;
  Liga: nota fuzzy baixa; COMC: score < 0.90; eBay: trust score baixo).
- `link_oferta`/`link_referencia` **sempre lidos do scanner, nunca inventados**
  (regra de entrega do HANDOFF).

> Se mudar o contrato depois, muda em um lugar só. Cada scanner ganha um
> `to_deals_json()` (ou o integrado ganha um **adapter** por fonte que lê a saída
> atual — XLSX/markdown — e mapeia para este schema; menos invasivo, não toca os
> scanners). **Preferir adapter no integrado** para não arriscar os scanners.

---

## 4. Adapters por fonte (mapear saída atual → contrato §3)

Um adapter por scanner, isolado e testável. Cada um lê o que o scanner **já produz**
e devolve `list[Deal]`:

| Fonte | Lê de | Notas de mapeamento |
|---|---|---|
| MYP | `myp_summary` / XLSX | já tem Carta+Links+flag → mapeio quase 1:1 |
| Liga | `markdown.py` / XLSX | oferta BRL; `flag` ← Nota fuzzy; link oferta+TCG |
| CardTrader | `cardtrader_postprocess` / XLSX | já tem links + coluna Flag |
| COMC | `reporter.py` / XLSX | coluna `Links` unificada (PR #3); flag `validar` < 0.90 |
| eBay | `report.py` / XLSX | separar `graded` vs `raw`; trust score → flag |

> **Regra:** adapter **não** recalcula margem nem re-filtra — ele **transcreve** o que
> o scanner decidiu (o scanner é a fonte de verdade do seu domínio). O integrado só
> **une, deduplica e ordena**.

---

## 5. Deduplicação / comparação entre fontes (o valor da junção)

A mesma carta aparece em várias fontes — **é exatamente o que o operador quer ver**.

- **Chave de identidade da carta:** `(set, numero, idioma, condicao, tipo)`.
  Normalizar `set`/`numero` com a lógica já evoluída na Liga (aliases de set
  PRE/SSP/151, acentos, `V-MAX`→`VMAX`) — reaproveitar `liga-cards-scanner/src/matching/normalization.py`.
- **Agrupar** os deals por essa chave → para cada carta, mostrar **uma linha por
  fonte** (ou a melhor margem por fonte), ordenadas por margem.
- **Visão "onde está mais barato":** por carta, destacar a fonte de **maior margem
  bruta** e listar as demais para comparação. Esse é o ganho que nenhum scanner
  isolado dá.
- **Conflitos de referência:** se duas fontes discordam muito do preço de
  referência da mesma carta, **marcar `flag_validar`** (provável mis-map de preço,
  como o TCG-suspect do MYP).

---

## 6. Entrega unificada (modelo MYP — regra do HANDOFF §0/§4)

Saída canônica = **tabela markdown no chat, gerada pela ferramenta** (nunca à mão):

| Carta | Fonte | Margem bruta | Links | Flag |
|---|---|---|---|---|
| Charizard ex 199/165 (151) | **MYP** | **70%** | [oferta](…) · [TCG](…) | — |
| Charizard ex 199/165 (151) | CardTrader | 41% | [oferta](…) · [TCG](…) | — |
| Pikachu 173/172 (SSP) | Liga | 33% | [oferta](…) · [TCG](…) | ⚠ validar (nota fuzzy 0,71) |

- **Coluna Carta:** nome + número (helper `carta_label` do MYP).
- **Coluna Links:** `[oferta](url) · [referência](url)`, ambos **lidos** do scanner.
- **Coluna Flag:** "⚠ validar manualmente" + motivo nos buckets suspeitos.
- **Todos os deals** (não amostra). Ordenar por margem desc (com piso de relevância
  por fonte preservado).
- **Seções anexas (opcional):** "Lacrado" (Sealed) e "Tendência" (Outlook) como
  blocos separados, claramente rotulados, fora da tabela de cartas avulsas.
- **XLSX/CSV** só sob pedido explícito.

---

## 7. Regras invioláveis (herdadas do HANDOFF §0 — valem na integração)

1. **Margem é BRUTA** (sem taxas embutidas); piso de relevância por scanner é mantido.
2. **NM-only / EN-only** — o integrado **confere e rejeita** o que vier fora; nunca relaxa.
3. **Nunca recomendar compra.** O integrado reporta dados; capital é decisão do operador.
4. **Entrega = tabela gerada pela ferramenta**, nunca montada à mão; links nunca inventados.
5. **Não comprometer os scanners.** O integrado **lê** as saídas; mudança em scanner
   (se precisar de um `to_deals_json`) só entra com **testes do repo verdes** + **PR draft**.
6. **Branch própria + PR draft** para revisão; nunca push em `main`.

---

## 8. Moeda e normalização

- Ofertas vêm em **moedas diferentes** (Liga/MYP BRL, COMC/eBay USD, CardTrader EUR/USD).
- **Comparar por `margem_bruta_pct`** (adimensional) — correto sem conversão de câmbio.
- Para **exibir** preços absolutos lado a lado (opcional), normalizar para uma moeda
  de referência (ex.: BRL) com uma taxa **configurável e datada** (registrar a taxa
  usada). **Nunca** embutir câmbio na margem (a margem é bruta e em % por construção).

---

## 9. Checklist de execução (na sessão COM os repos no escopo)

Pré-requisito: sessão do Claude Code aberta com **`integrated-scanner`** e os de
origem (**`myp-arbitrage-scanner`, `liga-cards-scanner`, `card-trader-scanner`,
`scanner-comc`, `ebay-arbitrage-scanner`**) no escopo. Ver §10.

- [ ] **E0.** Ler `integrated-scanner/delivery.py::build_markdown` e como ele ingere
      fontes hoje (decide Opção A vs B do §2). **Não redesenhar o que já existe.**
- [ ] **E1.** Fixar o contrato `Deal` (§3) como módulo no `integrated-scanner`
      (`models.py`) + teste de schema.
- [ ] **E2.** Implementar **adapters** por fonte (§4), cada um com fixtures offline
      (reaproveitar fixtures de teste de cada scanner). Sem rede.
- [ ] **E3.** Implementar **dedup/agrupamento** por chave de carta (§5), reusando a
      normalização da Liga. Testes de agrupamento (mesma carta, fontes diferentes).
- [ ] **E4.** Implementar **entrega unificada** no modelo MYP (§6) + teste que trava
      o formato (colunas Carta/Fonte/Margem/Links/Flag, links clicáveis, todos os deals).
- [ ] **E5.** (Opcional) Seções anexas Sealed/Outlook.
- [ ] **E6.** Suíte offline **verde** → **PR draft** no `integrated-scanner` (branch própria).
- [ ] **E7.** Se algum scanner precisar de `to_deals_json` (Opção A pura), PR draft
      **separado** nesse scanner, com a suíte dele verde.

---

## 10. Pré-requisito de acesso (importante)

Esta integração mexe no `integrated-scanner` (e lê os scanners de origem) — repos que
**a sessão atual não enxerga** (escopo = só `asi-evolve`; e não há ferramenta de
`add_repo` aqui). Para executar o §9:

1. **Iniciar uma sessão do Claude Code já com esses repos no escopo** — escolhido no
   seletor de repositório ao abrir a sessão (interface web/app), não no meio de uma sessão.
2. Trazer este `PLANO-scanner-integrado-pokemon.md` como referência (está no `asi-evolve`).
3. Rodar o checklist §9.

> Referência de como o ambiente/escopo é configurado:
> https://code.claude.com/docs/en/claude-code-on-the-web
