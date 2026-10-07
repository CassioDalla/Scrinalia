# 🗺️ Roadmap & TO-DO — Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não
> apenas lido no código. `[ ]` = pendente. `[~]` = parcial, com o que falta descrito.
>
> **Estado do gate (2026-10-06, as três lacunas de curadoria fechadas):** **1.114 testes**
> passando · `ruff` limpo · `basedpyright` **0 erros** · **27 migrações** aplicando sem drift
> (`alembic check` limpo) · contrato OpenAPI **79 paths / 94 operações / 161 schemas**, regenerado e
> verificado por CI · SPA do curador construindo (`tsc`, `eslint`, `vite build`) e servida pelo
> próprio Litestar · **Streamlit removido do repositório** (diretório, dependência, `uv.lock`,
> `Procfile`, docs). O sitemap do curador está **completo**: as 17 telas existem, mais as **3 telas
> de sistema** (`/sistema/workers`, `/sistema/execucoes`, `/sistema/diagnostico`) e o **catálogo de
> tipologias** (`/arranjo/tipologias`). Falta só o site público, que ficou fora deste ciclo por
> decisão.
>
> **As duas últimas capacidades sem botão foram fechadas** (`POST /hierarchy/nodes` e
> `POST /taxonomy/tags/merge`) e a rota legada de stopwords de entidade **foi removida**.
> **Acervo real medido: 4.826 descrições**, não 3.608 — ver "Pendências operacionais".
>
> **O painel de operação fechou a lacuna "não há como ver nem configurar o sistema"**: os 9 workers
> aparecem com engine, preset e modelo resolvidos, fila, última execução, override persistido e
> botão de executar; toda execução (CLI ou tela) deixa linha em `archive_worker_runs`. Decisão em
> `docs/adr/0004-worker-execution-from-the-api.md`; limites conhecidos na seção do painel.
>
> **As três lacunas que o dono apontou no TODO foram fechadas** — a colisão tag × entidade
> (preview, ledger reversível e o veredito do juiz na leitura), a faceta de anomalia por motivo
> (com a projeção pública que impede o vazamento) e as sugestões de "não é assunto" (o guarda
> determinístico, com evidência). Nada foi escrito no acervo real: as duas verificações que
> precisavam de dado usaram uma **cópia** do banco, e a terceira é read-only por construção.
>
> **A última lacuna de catálogo foi fechada.** As tipologias documentais **não eram hardcoded** — a
> tabela `archive_typologies` existia desde a migração inicial e o worker de classificação a lia
> como conjunto de rótulos — mas **não havia rota de escrita**: as 10 linhas do banco de dev foram
> inseridas fora do código e nada as reproduzia. Agora `GET/POST /api/v1/typologies` e
> `PATCH /api/v1/typologies/{id}` sustentam a tela, `is_active` substitui o delete (a FK é
> `SET NULL`), a migração `d1bc15fb6beb` semeia o conjunto com `ON CONFLICT DO NOTHING` — sem
> reescrever os ids de um catálogo já curado — e `typology_id` entrou no `PATCH /documents/{id}`,
> porque até então o classificador era o **único** autor do campo.

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança | ✅ **Fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | ✅ **Fechada** — vocabulário reprojetado e medido |
| 2 | API + Curadoria humana (HITL) | ✅ **Fechada** — backend e as duas ações locais que faltavam (criar nó, unificar tags) |
| 2.5 | Hierarquia das descrições | ✅ **H1–H8 fechadas sem UI** |
| 3 | Descoberta, performance e observabilidade | 🟡 **Quase fechada** — busca fechada; operação entregue (painel, ledger, diagnóstico); faltam Sentry, agendamento e um `/health` de orquestrador |
| 3.5 | Qualidade do dado de entrada | ✅ **A–E fechadas sem UI** |
| 4 | **UI nova, BFF e publicação** | 🟡 **Em andamento** — contrato fechado, **ondas 1–6 entregues** e **painel de operação** (sitemap do curador completo + 3 telas de sistema); Streamlit desligado e removido; faltam o site público e o auth |

**O sistema está funcionalmente pronto.** Ingestão → staging → archive → enriquecimento por
IA → curadoria humana → bloqueio de reprocessamento, tudo verificado ponta a ponta.

**O que falta é tela.** Todas as feats recentes (hierarquia, assuntos, qualidade, merge
reversível) foram entregues **como API**, sem UI — por decisão, já que o Streamlit seria
substituído. O front do curador fechou esse buraco: o **sitemap do curador está completo** (17
telas), e o Streamlit saiu do repositório. Falta o **site público** (`apps/public/`) e o **auth**.

> **Primeiro ciclo entregue (2026-10-05).** O **contrato** está fechado: as lacunas que a UI
> expunha foram resolvidas, o OpenAPI é um artefato gerado e commitado com CI bloqueante, e a
> **allowlist pública** existe com teste de partição exata. A **onda 1** do front também está de
> pé: início com a fila de trabalho, lista com facetas e dossiê com quatro abas.
>
> **Segundo ciclo entregue (2026-10-05, o mesmo dia).** A **onda 2** entrou — `/arranjo/plano` e
> `/arranjo/diagnostico` —, que é a razão de existir deste front. Três lacunas de contrato que só
> a tela revelou: `status_counts` na lista de rungs (a barra "N de M decididos" não se deriva de
> uma página), `GET /hierarchy/diagnostics/summary` (uma contagem por issue, pelo **mesmo** código
> que serve cada página) e a publicação da **união de quatro vocabulários** em `/hierarchy/flags`.
> A última foi um defeito de verdade, achado **olhando a tela**: as linhas carregavam
> `NEAR_DUPLICATE_NODE`, `MID_CODE_IDENTIFIER` e `LEVEL_NOT_ALLOWED_AS_CHILD`, e a rota anunciava
> só `ProposalFlag` — o front renderizava código cru para o arquivista.
>
> **Terceiro ciclo entregue (2026-10-06).** As **ondas 4–6** (níveis, árvore, entidades,
> qualidade, descoberta, exceções) e o **B8**: o Streamlit foi desligado e removido do repositório.
> Este ciclo também fechou a última família de lacunas de contrato — as rotas de escrita que
> devolviam `dict` cru agora devolvem DTOs tipados —, porque sem isso a tela leria a resposta por
> um `cast` e um campo renomeado chegaria como `undefined`.
>
> **Sequenciamento (2026-10-04).** Auth entra **por último**, depois do front novo e
> imediatamente antes de tornar público. Duas UIs (curador + difusão pública) com BFFs
> separados, em monorepo. Planos em `.analysis/roadmap-bff-curador.md` (arquitetura) e
> `.analysis/sitemap-front-curador.md` (telas). Decisão de stack registrada em
> `docs/adr/0003-monorepo-and-curator-frontend-stack.md`.

---

## ▶️ Handoff — o que falta, em ordem, e como rodar

> **Onde está o plano.** O detalhe (ondas do sitemap, arquitetura do BFF, o porquê de cada decisão)
> vive em `.analysis/plano-proximas-etapas.md`, `.analysis/roadmap-bff-curador.md` e
> `.analysis/sitemap-front-curador.md`. **`.analysis/` é gitignored** — os arquivos existem neste
> checkout, mas não viajam num clone. O que precisa sobreviver a um clone está **aqui** e no
> `AGENTS.md`; as notas de trabalho são descartáveis de propósito.

### Subir o stack e rodar os gates

```bash
bun run dev            # docker compose up -d + API :8000 + SPA :5173 (proxy /api -> :8000)
# peças soltas: bun run db:up | bun run api:dev | bun run curator:dev
```

Um **502 em `/api`** quer dizer que a API não está no ar — a SPA responde 200 e o sintoma parece
bug de front. Se o Vite imprimir outra porta, a `:5173` estava ocupada.

```bash
# banco de teste deste checkout está na porta 5434
TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_db .venv/bin/pytest -q
.venv/bin/basedpyright && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/alembic check
bun run --cwd apps/curator typecheck && bun run --cwd apps/curator lint && bun run --cwd apps/curator build
```

**Nunca** rode `alembic upgrade head` no banco de **teste**: o `create_all` do conftest pula o que já
existe e a suíte passa a rodar contra o schema migrado (53 falhas + 42 erros que parecem regressão).

### Estado do acervo — **re-meça antes de confiar**

Este bloco envelhece em minutos: enquanto ele era escrito, a árvore foi materializada (00:15),
entraram 15 merges novos e o worker de macro-categoria classificou 973 tags. **Números congelados
são mentira com data de validade** — rode isto e leia o estado real:

```bash
docker exec memoria_curitibana_db psql -U admin -d memoriacuritibana -c "
SELECT 'descrições' AS medida, count(*)::text AS valor FROM archive_documents
UNION ALL SELECT 'com pai (árvore)', count(*)::text FROM archive_documents WHERE parent_id IS NOT NULL
UNION ALL SELECT 'sem nível', count(*)::text FROM archive_documents WHERE level_id IS NULL
UNION ALL SELECT 'tags', count(*)::text FROM archive_tags
UNION ALL SELECT 'tags sem gaveta', count(*)::text FROM archive_tags WHERE macro_category_id IS NULL
UNION ALL SELECT 'vínculos', count(*)::text FROM archive_document_tags
UNION ALL SELECT 'merges no ledger', count(*)::text FROM archive_taxonomy_merge_log
UNION ALL SELECT 'propostas aplicadas', count(*)::text FROM archive_tag_merge_proposals WHERE status='APPLIED'
UNION ALL SELECT 'propostas aprovadas', count(*)::text FROM archive_tag_merge_proposals WHERE status='APPROVED'
UNION ALL SELECT 'propostas sugeridas', count(*)::text FROM archive_tag_merge_proposals WHERE status='SUGGESTED'
UNION ALL SELECT 'rungs decididos', count(*)::text FROM archive_hierarchy_node_plans WHERE status <> 'SUGGESTED'
UNION ALL SELECT 'rungs no total', count(*)::text FROM archive_hierarchy_node_plans
UNION ALL SELECT 'materializações', count(*)::text FROM archive_hierarchy_materialisation_log
UNION ALL SELECT 'stopwords TAG/ENTITY', count(*) FILTER (WHERE word_scope='TAG')::text || '/' || count(*) FILTER (WHERE word_scope='ENTITY') FROM domain_stopwords
UNION ALL SELECT 'carimbos IA (ner/tipo/macro/val/emb)', (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_ner_v2')::text || '/' || (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_typology_classifier_v2')::text || '/' || (SELECT count(*) FROM archive_tags WHERE execution_log ? 'worker_macro_category_v1')::text || '/' || (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_quality_validator_v1')::text || '/' || (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_embedding_v1')::text;"
```

Leitura de **2026-10-06 00:16 UTC** — ordem de grandeza, não verdade: enquanto este documento era escrito a
curadoria andou (a árvore foi materializada às 00:15, as duas aprovadas órfãs foram arquivadas, os
rungs passaram de 4 para 5 e os merges aplicados de 95 para 101). **O comando acima é a fonte**, este
parágrafo é só o retrato de um instante: 4.830 descrições, 4.816 com pai, 13 sem nível, 8.242 tags
com 695 em gaveta, 58.618 vínculos, 148 merges no ledger, propostas 101 aplicadas / 0 aprovadas / 780
sugeridas, 5 de 81 rungs, 1 materialização, stopwords 96/88 e carimbos de IA `0 / 0 / 973 / 0 / 41`.

### Os passos, na ordem em que eu faria

| # | Passo | Onde / comando | Por que agora |
| --- | --- | --- | --- |
| 1 | ✅ **Arquivar as 2 aprovadas sem membros** — feito em 2026-10-06 00:1x | `/assuntos/tags?aba=propostas&status=APPROVED` → "arquivar as já cumpridas" | **0 aprovadas** na última medição: a fila ficou limpa |
| 2 | **Triar os 780 clusters sugeridos** | mesma tela, `status=SUGGESTED` (mais pesados primeiro) | Decisão do arquivista; cada um tem "Conferir impacto" antes |
| 3 | **Revisar 1 merge perigoso** | ledger em `/assuntos/tags?aba=propostas`, com **desfazer** | `residencial ← área residencial, casa residencial, região residencial` (65+6+6 docs) perde sentido; está aplicado e é reversível |
| 4 | **Continuar os rungs (5 de 81 decididos)** — e **conferir a materialização que já rodou** | `/arranjo/plano` e `/arranjo/diagnostico`; o undo está em `archive_hierarchy_materialisation_log` | A árvore foi materializada em 2026-10-06 00:15 (**4.816 descrições ganharam pai**) com 4 rungs aprovados. O diagnóstico diz se o resultado ficou coerente — e a materialização é reversível |
| 5 | **Rodar os workers de IA que faltam** — macro-categoria **já rodou** (973 tags, 695 com gaveta); faltam `ner`, `typology`, `conflict-judge`, `quality-validator` e `embedding` | `uv run python -m memoria_curitibana.domains.archive.workers.runner <nome>`, na ordem `ner → typology → conflict-judge → macro-category → quality-validator → embedding` | A janela fecha na **primeira ficha aprovada por humano**, e as 7.547 tags ainda sem gaveta são o que a tela de assuntos não mostra |
| 6 | ✅ **Onda 4 do front** — feito em 2026-10-06 | `/arranjo/niveis` e `/acervo/arvore` | Fecha a seção Arranjo do sitemap |
| 7 | ✅ **Ondas 5–6 do front** — feito em 2026-10-06 | `/entidades/*`, `/qualidade/*`, `/assuntos/descobrir` e `/assuntos/excecoes` | Sitemap do curador completo |
| 8 | **B8 — desligar e remover o Streamlit** — feito em 2026-10-06 | diretório, dependência, `uv.lock`, `Procfile` e docs | Uma superfície a menos divergindo |

> **Decisão de produto ainda aberta:** rodar a IA (passo 5) **antes ou depois** dos rungs (passo 4)?
> Enquanto não rodar, a UI mostra menos do que o sistema sabe — mas decidir os rungs primeiro faz a
> classificação trabalhar sobre uma árvore que já existe.

### O que **não** pode ser rodado no acervo real sem decisão do dono

- `POST /hierarchy/materialisation/apply` — **já rodou uma vez** (2026-10-06 00:15, 4.816
  descrições ganharam pai). Rodar de novo move mais; tem preview e undo no
  `archive_hierarchy_materialisation_log`.
- Aprovar rungs e aplicar merges em massa — decisões de conteúdo, não de engenharia.
- `POST /taxonomy/tags/stopwords/purge` — **apaga tags e não tem undo** (o merge tem ledger; a purga
  não). Tem preview obrigatório na tela.
- `DELETE /documents/{id}` — **exclusão definitiva**, com duas guardas: recusa nó com filhos (o FK de
  pai é `RESTRICT`) e exige o código de referência digitado na tela. Deixa o retrato ISAD(G) no ledger
  `archive_document_deletions`, que **não restaura**: é trilha, não lixeira.
- Os workers de IA — a janela de reprocessamento fecha na primeira ficha aprovada por humano.

### Dívidas técnicas registradas, ainda em aberto

- **Entidades não têm catálogo de propostas**: os defeitos de merge de entidade foram corrigidos
  (upsert de sinônimo + `repoint_synonyms` antes do delete), mas não há proposta, ledger nem undo
  como nas tags. A onda 5 encostou nisso e a tela **avisa** que unificar não tem desfazer; criar o
  ledger é a decisão que falta.
- ✅ **A colisão tag × entidade tem preview, ledger e veredito na leitura.** Fechada em
  2026-10-06: plano único para os dois vereditos, ledger reversível (para o juiz e para o
  arquivista), `GET /conflicts/judged` lendo a fila, e `pair_kind` separando as duas populações
  que a varredura ao vivo misturava. O que **segue aberto** é outra coisa, e é grande: os 5.050
  nomes idênticos são uma decisão *por categoria* ("logradouro é entidade", "nome de pessoa é
  entidade") e a tela ainda pede uma por par — resolver em lote por regra é o próximo passo
  natural, e não foi feito.
- ✅ **As sugestões de "não é assunto" existem, e são o guarda.** Fechada em 2026-10-06: os
  1.489 termos que o guarda já recusava aparecem com o sinal e o peso, e `source=RULE` passou a
  ser escrito. A metade semântica continua sendo decisão humana, por medição — os sinais
  estatísticos disponíveis propõem `igrejas` (2.474 documentos) e `madeira` (0,30 de confiança)
  como não-assunto, e os dois são assuntos.
- **A purga de stopwords é a única escrita destrutiva sem undo** — hoje ela é anunciada e tem
  preview; torná-la reversível (escrevendo no ledger, como o merge) é uma decisão em aberto.
- **Busca híbrida (RRF)** e **qualidade semântica** (o MRR caiu 0.019 enquanto o Hit@10 subiu) —
  ver "Fase 3".

---

## 🔴 Fase 4 — UI nova, BFF e publicação — **FASE ATIVA**

### Decisões já tomadas

- ✅ **Monorepo**, com o núcleo Python no lugar: `apps/{api,curator,public}`.
  As mudanças de backend e front são acopladas; o contrato OpenAPI merece cliente gerado com
  CI bloqueante; o `Procfile` e o CI já são um só.
- ✅ **Duas UIs, dois BFFs.** O `DocumentSummary` vaza metadado interno (`review_status`,
  `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`). Num site público isso
  expõe o processo de curadoria. *Segurança por omissão de campo é frágil; por omissão de
  rota é auditável.* O BFF público reusa os mesmos serviços e difere só na projeção.
- ✅ **Auth adiada** para o fim — o BFF público **nasce aberto por design**, não é "rota não
  pública".
- ✅ **O núcleo Python não se move.** `apps/api` é a casca HTTP que já existe; mover
  `src/memoria_curitibana/api/` fica para depois, num commit só de movimentação.

### Entregáveis

- ✅ **B1 — Superfície pública separada.** `PublicDocumentSummary` com allowlist explícita
  (`api/schemas/public.py`), controller público e um teste que trata a allowlist como **partição
  exata** do `DocumentSummary`: todo campo do read view interno é publicado **ou** declarado em
  `NOT_PUBLIC_FIELDS`, então um campo novo nasce privado e o CI avisa. Rota pública não aceita
  escrita e um teste percorre a tabela de rotas para garantir isso.
- ✅ **B2 — Predicado de publicação: `is_published`** (coluna + índice + `PATCH`). Não foi
  `HUMAN_APPROVED` por dois motivos medidos no desenho: amarrar publicação a revisão faria
  "corrigi uma vírgula" equivaler a "publiquei", e usaria `ai_writable_documents()` como efeito
  colateral, travando a IA em todo documento publicado. O eixo de difusão é separado — e permite
  publicar por ramo quando a árvore existir.
- ✅ **B3 — `GET /api/v1/curation/inbox`** — 8 filas, contagem + rótulo + rota, tudo em coluna
  indexada. Verificado no acervo real: 3.602 órfãos de arranjo, 371 propostas de merge, 4 conflitos,
  5.446 tags sem gaveta.
- ✅ **B4 — Scaffold `apps/curator/`** — Vite + React 19 + TS estrito + TanStack Router/Query +
  Tailwind v4. Bun como gerenciador de pacotes e executor; Vite como bundler. Cliente gerado do
  OpenAPI (`packages/api-contract/openapi.json` → `src/api/schema.d.ts`), com **dois** checks de CI
  bloqueantes (o JSON no job Python, o `.d.ts` no job do front) e `fetch` proibido por lint.
- ✅ **B5 — Telas das ondas 1–3.** Ondas 1, 2 e 3 entregues, mais a **etapa C** (as lacunas que a
  própria onda 1 expôs ao ser usada): busca de tag e de entidade **por nome** com type-ahead,
  reclassificar a gaveta de uma tag na aba Assuntos, escolher a unidade superior na aba Arranjo,
  filtro de data e busca com debounce na lista.
- ✅ **B6 — Telas da hierarquia** (ondas 2 e 4 do sitemap). **Onda 2:** `/arranjo/plano` (decidir
  rung a rung, com nível, título e `collapse_into_code`; filtros por status, aviso e código) e
  `/arranjo/diagnostico` (uma seção por issue, com a evidência e **nenhuma correção automática**).
  **Onda 4 (2026-10-06):** `/arranjo/niveis` (a escada NOBRADE, com peso por degrau, sem delete) e
  `/acervo/arvore` (navegação preguiçosa: raízes por `max_depth=0` e um ramo por expansão, com a
  contagem de `ORPHAN` avisando quando a árvore ainda não está materializada).
- [ ] **B7 — Scaffold `apps/public/`** + regras de badge. O BFF público (rotas + projeção) já existe;
  falta o app. **Fora do escopo deste ciclo, por decisão.**
- ✅ **B8 — Streamlit desligado e removido** (2026-10-06): o diretório
  `src/memoria_curitibana/dashboard/`, a dependência `streamlit` (e o `uv.lock`, com pydeck,
  starlette e cia.), o processo `web` do `Procfile`, a chave `API_BASE_URL` (que só ele lia) e as
  referências em `README.md`, `AGENTS.md`, `.env.example` e no skill de commit. O pacote perdeu o
  segundo root de import que o ADR 0002 registrava.
- ✅ **B10 — Refino da UI do curador** (2026-10-06), em cinco ondas, com o relato do arquivista como
  especificação: (1) as facetas e as paginações voltaram a funcionar (ver "Achados"); (2) as telas que
  editam catálogo passaram a **colapsar** e a pôr a escrita **no topo** (`ui/Disclosure.tsx`), com o
  plano de arranjo ganhando hierarquia visual por profundidade; (3) os merges passaram a abrir o painel
  **na própria linha**, a aceitar **marcação de várias linhas** com barra flutuante, e a permitir
  **editar uma proposta antes de aplicá-la** (tirar um membro do cluster e aplicar pelo mesmo
  planejador, fechando a proposta da máquina como `REJECTED`); (4) a exclusão de descrição com trilha;
  (5) busca e paginação em todos os ledgers. O que ficou de fora, por decisão: **criar rung manual no
  plano** (a tela agora aponta para o "criar nó" da árvore, que é a outra escrita) e o app público (B7).
- [ ] **B9 — Auth + auditoria + CORS + rate limit** no BFF do curador. **Última etapa.**
  (CORS continua desnecessário: o SPA é servido pelo próprio Litestar, mesma origem.)

### Lacunas de API que a UI expõe

| Lacuna | Ação | Estado |
| --- | --- | --- |
| `GET /curation/inbox` não existe | criar (B3) | ✅ |
| `POST /entities/merge` devolve dict cru | `EntityMergeResponse`, como o de tags | ✅ |
| Sem rota para editar tags de **um** documento | `POST/DELETE /documents/{id}/tags[/{tag_id}]` + par de entidades | ✅ |
| `DocumentSummary` não expõe tipologia | campo `typology`/`typology_id` (relação renomeada para `typology_ref`, como `level_ref`) | ✅ |
| Sem contagem por faceta | `facets` no `DocumentListResponse`, com a semântica de não contar a própria dimensão | ✅ |
| `DocumentSummary.tags[]` não trazia a decisão de assunto | `DocumentTagSummary` com `macro_category_id`/`macro_category_name`/`ai_confidence_score` | ✅ |
| Sem filtro por status/anomalia (o inbox prometia `/acervo/lista?status=…`) | `status` e `is_anomaly` no `DocumentSearchQuery` | ✅ |
| `access_conditions` (ISAD(G) 4.1) era **perdido no transfer** | coluna + DTO + `PATCH` | ✅ |
| A barra "N de M decididos" não se deriva de uma página | `status_counts` no `HierarchyPlanListResponse`, contando **todo** o catálogo | ✅ |
| Cinco requisições para contar as seções do diagnóstico | `GET /hierarchy/diagnostics/summary`, contando pelo **mesmo** código que serve cada página, **sem total geral** (as issues se sobrepõem) | ✅ |
| `/hierarchy/flags` anunciava só `ProposalFlag` | `plan_flag_vocabulary()`: a **união dos quatro** vocabulários que escrevem `flags` numa rung | ✅ |
| `PATH_DIVERGENCE` chegava sem evidência | `detail` com `path` e `expected_path` — é o único diagnóstico cuja evidência é uma comparação | ✅ |
| Sem filtro de status no catálogo de rungs | `status` no `GET /hierarchy/plans` (era `Literal` duplicado; agora lido de `PlanStatus`) | ✅ |
| **Buscar tag por nome não existia** (a aba Assuntos pedia o **id**) | `GET /taxonomy/tags?term=` + type-ahead; piso de 2 letras no serviço | ✅ |
| **Não havia como mover uma tag de gaveta** | `PATCH /taxonomy/tags/{tag_id}` — decisão **global**, com carimbo no ledger da tag | ✅ |
| **Buscar entidade por nome não existia** (só remover) | `GET /taxonomy/entities?term=` + type-ahead, mesma leitura da tela de relevância | ✅ |
| Filtro de data existia na API e não na tela | `date_from`/`date_to` na lateral da lista | ✅ |
| Busca da lista só disparava no Enter | debounce de 250 ms com o termo na URL (uma fonte de verdade) | ✅ |
| Não havia como escolher a unidade superior na aba Arranjo | type-ahead de pai + nível + `POST /hierarchy/nodes/{id}/move` | ✅ |
| A gaveta não mostrava o próprio peso | `document_count` no `ArchiveMacroCategoryEntityDTO`, contando **descrições distintas** | ✅ |
| **Stopwords não tinham leitura nem preview** (a purga apagava tags às cegas) | `GET/POST/DELETE /taxonomy/tags/stopwords` (com eixo) + `POST /tags/stopwords/purge/preview` + `purge` aceitando corpo vazio | ✅ |
| Aprovar um merge **parecia** unificar (o ledger parecia travado) | aprovar já seleciona para o lote; banner "aprovada ainda **não** unificada"; "selecionar todas as aprovadas"; teto de 200 no lote | ✅ |
| **Seis rotas de escrita devolviam `dict` cru** (quality, exclusões, entidades) | DTOs tipados: `CleaningRuleMutationResponse`, `DryRunResponseDTO`, `TextTemplateMutationResponse`, `Stopword*Response`, `SubjectExclusion*Response`, `NerExclusion*Response`, `EntityReclassifyResponse`, `EntityDeleteResponse`, `OrphanEntityPurgeResponse` | ✅ |
| **A árvore não sabia pedir as raízes** (o `max_depth` era ignorado sem `root_id`) | `list_subtree` aplica profundidade **absoluta** quando não há raiz: `max_depth=0` devolve as raízes | ✅ |
| **O dossiê mostrava a data em pt-BR num campo AAAA-MM-DD** | `type="date"` com o valor ISO; editar não manda mais "1 de jan. de 1994" para uma rota que parseia data | ✅ |
| **A colisão tag × entidade não tem preview nem veredito do juiz na leitura** | `POST /conflicts/resolve/preview` devolve **os dois vereditos** (vínculos criados, linha que morre, bloqueio plantado), o ledger `archive_conflict_resolution_log` + `DELETE /conflicts/resolutions/{id}` tornam a escrita reversível, `GET /conflicts/judged` lê o **veredito do juiz** na fila (84 auto-resoluções que a varredura ao vivo não pode devolver, porque apagaram a linha perdedora), e `pair_kind` separa os 122 problemas de grafia dos 5.050 nomes idênticos | ✅ |
| **Não há rota de sugestões de "não é assunto"** | `GET /tags/subject-exclusions/suggestions` publica o que o **guarda determinístico já recusa** — 1.489 das 8.155 tags, com o sinal, o peso e as duas evidências que mudam o significado da decisão — e `source=RULE` finalmente é escrito. **Nada é proposto para a metade semântica**, e a medição é a razão | ✅ |
| **Anomalias não têm faceta por motivo** | `anomaly_reason` é dimensão e filtro, agrupando pelo **código** — com `RULE_MATCH:<regra>` nomeado e a prosa do `LLM_SUSPECT` colapsada — sobre o conjunto filtrado inteiro. `PublicDocumentFacets` impede a dimensão de vazar para a difusão | ✅ |
| **Não havia como criar um nó que o código não implica** | `POST /hierarchy/nodes` + formulário em `/acervo/arvore`: pai = raiz **ou** o nó selecionado, nível obrigatório e o impacto é validado pela rota | ✅ |
| **Não havia como unificar duas tags que o arquivista escolheu** | `POST /taxonomy/tags/merge` (+ `/merge/preview` por `canonical_id`+`ids_to_merge`) chamado pelo botão `unificar ↦` da aba Similaridade, com canônica escolhível, dry-run obrigatório e o desfazer do ledger | ✅ |
| **Não havia como excluir uma descrição do acervo** | `DELETE /api/v1/documents/{id}` com guarda de filhos (409 `DocumentHasChildrenError`) + ledger `archive_document_deletions` (retrato ISAD(G) completo, sem FK: o registro que ele nomeia não existe mais) + `GET /documents/deletions` e a tela `/acervo/excluidas`. O ledger de **revisões** não serviria: `description_id` é `ON DELETE CASCADE`, então a revisão morreria com o documento que ela registrava | ✅ |
| **O ledger de merges não tinha busca** (194 linhas hoje, sem teto) | `q` no `GET /tags/merge-log`, casando **os dois lados** da entrada (grafia absorvida e canônica) e escapando curingas: medido, `q=%` responde 0 | ✅ |
| **O ledger de materialização não tinha busca** | `q` no `GET /hierarchy/materialisation/log`, casando autor e nota — os dois campos que identificam uma execução | ✅ |
| **Rota legada superseded** | `POST /entities/stopwords/purge_stopwords` foi substituída por `POST /entities/ner-exclusions` (catálogo durável com `reason`/`source`, reversível por `DELETE`, e que **também** purga e alimenta o blacklist do NER via `load_entity_blacklist`). A legada estava **sem uso no front e sem teste** — removida junto de `save_entity_stopwords`, do `EntityService.purge_entity_stopwords` e do `EntityStopwordPurgeResponse`. `delete_entities_by_names` **ficou**: é o expurgo retroativo das exclusões de NER | ✅ |

**Rotas do backend sem chamada no front que NÃO são lacuna** (auditadas em 2026-10-06, não
reinvestigar):

| Rota | Por que está correta assim |
| --- | --- |
| `GET /hierarchy/nodes/{id}/ancestors` · `/children` | **Redundantes por desenho:** `GET /hierarchy/nodes/{id}` já devolve `ancestors[]` e `children[]` numa leitura. Chamar as três seria três round-trips para o mesmo dado. Mantidas como API pública; a tela usa a leitura única |
| `POST /hierarchy/proposal` | **Read-only e superseded para a UI** por `/plans/suggest` + `/plans` (que persistem a decisão). Continua sendo a entrada da bancada `testing/evaluation/hierarchy_proposal.py` |
| `GET /public/documents` · `/public/documents/{id}` | **Superfície de difusão**, deliberadamente ausente do curador (o `AppShell` documenta isso). É o B7 |

### Achados que a implementação produziu

- ✅ **`GET /conflicts/cross-domain`: 53 s → 1,5 s, mesmo resultado.** Duas causas, medidas e
  corrigidas — ver "Bugs conhecidos" 7 e 8. A análise anterior neste documento estava **errada** ao
  afirmar que o GIN não serve para comparação coluna-a-coluna: ele serve, desde que `%` seja o
  **único** predicado do join.
- ✅ **A escrita pela UI foi exercitada no browser, e passou.** Era a pendência mais antiga do front
  ("o clique nunca foi testado ponta a ponta"). Um browser real, dirigido por DevTools Protocol,
  ligou uma tag pelo nome, viu o documento virar `HUMAN_APPROVED` (a governança agiu), reclassificou
  a tag para "Religião", removeu a tag, escolheu a unidade superior pelo nome e moveu a descrição —
  8 de 8 checagens contra a API. A coleção usada foi a do **banco de teste**, de propósito: escrever
  pela UI marca a ficha como revisada e fecha a janela de reprocessamento de IA.
- ✅ **As facetas numéricas da lista não filtravam nada — e o defeito era um só.** Os validadores de
  `search` do TanStack Router só aceitavam **string**, mas `navigate({ search })` entrega o objeto
  **antes** de serializar: `asNumber(12)` respondia `undefined` e, como o resultado do validador é
  espalhado sobre o destino, ele **sobrescrevia com `undefined`** o valor que acabara de receber.
  Clicar em "Tipologia" não fazia nada; só `entity_type` sobrevivia, porque viaja como string — que é
  exatamente a assimetria que o arquivista relatou ("só as de tipo de entidade funcionam"). A mesma
  causa desligava a paginação de propostas, diagnóstico, anomalias, similaridades e conflitos. Duas
  outras da mesma família apareceram ao ler o código: o `patch` do vocabulário forçava
  `offset: undefined` **depois** do `...changes` (a página nunca avançava) e três filtros de proposta
  viajavam com nomes que a rota não aceita (`motivo`/`min`/`flag` em vez de
  `reason`/`min_documents`/`flagged_only`), então "só com avisos", "mín. docs" e "motivo" respondiam
  "todos". As coerções passaram a viver em um lugar só (`lib/search.ts`) e um validador que
  hand-rolle a checagem de novo volta a perder o filtro.
- ✅ **A busca não escapava curingas.** `ILIKE '%termo%'` com um `%` digitado virava "todos os
  registros": o arquivista recebia o catálogo inteiro por um typo e a consulta abandonava o índice
  de trigrama. `escape_like()` + `LIKE_ESCAPE` (`domain/normalization.py`) resolveram, com teste que
  distingue `0%` de "começa com zero" e `a_b` de "a, qualquer coisa, b".
- ✅ **O `suggest` de merge, re-executado no acervo novo, propôs 500 clusters** (o teto do pedido) em
  **1,0 s**, com **707 pendentes** e **123 com aviso**. A previsão do plano se confirmou: eram 371
  com 6.142 tags, e agora são 8.349 — os pares que o prefilter de comprimento escondia são reais.
  Entre os primeiros: `igrejas ← igreja` (correto), `residencial ← área residencial, casa
  residencial, região residencial` (perigoso: perderia o sentido), `trem ← trens` (com aviso
  `WEAK_MEMBER`). É exatamente a fila que o arquivista decide, e é por isso que os avisos são avisos.
- ✅ **O vocabulário de `/hierarchy/flags` estava incompleto** e isso só apareceu **olhando a
  tela**: as rungs do acervo real carregam `NEAR_DUPLICATE_NODE`, `MID_CODE_IDENTIFIER`,
  `UNPARSED_TAIL` e `LEVEL_NOT_ALLOWED_AS_CHILD`, e a rota publicava apenas os três
  `ProposalFlag`. O front renderizava o código cru. A união passou a ter uma definição só
  (`plan_flag_vocabulary()`) e um teste que a prende aos **quatro** vocabulários de origem, mais
  um teste de comportamento que compara o vocabulário publicado com os `flags` que as linhas do
  fixture realmente carregam.
- ✅ **`GET /hierarchy/diagnostics/summary` conta com `limit=0`**, pelo mesmo caminho que serve
  cada página: assim o cabeçalho da seção não pode discordar da lista que ele abre. **Sem total
  geral**, de propósito — `ORPHAN` e `DOSSIER_WITHOUT_PARENT` se sobrepõem (um Dossiê na raiz é os
  dois), e somar inflaria o acervo.
- ✅ **As tipologias documentais nunca foram hardcoded — nunca tiveram escrita.** A tabela
  `archive_typologies` nasceu na migração inicial e o worker de classificação sempre a leu como
  conjunto de rótulos, mas **não havia serviço, schema nem rota**: as 10 linhas do banco de dev
  foram inseridas fora do código e nada as reproduzia, e `typology_id` estava fora do
  `PATCH /documents/{id}` — o classificador era o **único** autor do campo. Fechado com
  `GET/POST /api/v1/typologies`, `PATCH /{id}`, a tela `/arranjo/tipologias` e o campo no dossiê.
  A migração `d1bc15fb6beb` acrescenta `is_active` (a FK é `SET NULL`: desativar substitui o
  delete, como na escada de níveis) e **semeia** o conjunto com `ON CONFLICT (name) DO NOTHING`,
  testada contra um catálogo já curado: nome renomeado **não** é ressuscitado e os ids do banco de
  dev (1,2,3,4,5,9,12,13,14,15) ficaram intactos, então nenhum `typology_id` foi reescrito.
- ✅ **A resposta do `PATCH /documents/{id}` carregava o nome *antigo* ao lado do id novo.** O
  documento é lido com `_eager_options()`, que já traz `level_ref`/`typology_ref`, e o
  `DocumentSummary` é montado do **mesmo objeto** poucas linhas depois: atribuir a chave estrangeira
  deixava a relação apontando para a linha anterior, e a resposta saía `typology_id: 991` com
  `typology: null`. O defeito existia para o **nível** desde que a coluna virou FK e ninguém o viu
  porque nenhum teste lia o nome derivado; `update_review` agora expira a relação quando a chave
  está em `changes`, com teste de regressão nos dois eixos.
- ✅ **A tela foi renderizada antes de ser dada como pronta.** `chrome-headless-shell` (o binário
  que o Playwright já deixa em `~/.cache/ms-playwright`) tirou screenshot de
  `/arranjo/tipologias` — os 10 rótulos com peso (Planta 284, Fotografia 64), o formulário de
  cadastro aberto — e do dossiê, com o select de tipologia ao lado do de nível mostrando
  "Fotografia (64)": `.analysis/shots/tipologias-catalogo.png` e
  `.analysis/shots/tipologias-dossie.png`. Vale registrar o motivo: `tsc`/`eslint`/`vite build`
  verdes **não** provam que a tela aparece — o modo de falha silencioso do Tailwind v4 (colchete em
  vez de parêntese) passa pelos três. O `chrome` completo despeja núcleo sob o sandbox desta
  sessão; o `chrome-headless-shell` funciona, com `HOME`/`TMPDIR` dentro do repositório.
- **`GET /acervo/lista?term=…` não existe na UI como busca global**; a lista funciona, mas um campo
  de busca dedicado por eixo virá com as telas da onda 3.

### Ciclo das três lacunas de curadoria (2026-10-06)

- ✅ **A colisão tag × entidade: 5.408 cartões, e o juiz invisível.** A medição reorganizou o
  problema: a ≥0,85 a varredura devolve **5.408 pares**, dos quais **5.050 são a mesma grafia nos
  dois eixos** e **122 são a mesma palavra escrita de duas formas** (quase todos abreviação de
  logradouro). São duas perguntas diferentes — estrutural e de grafia — e misturadas nenhuma das
  duas se vê. Do outro lado, o juiz decidiu **88** pares e **84 eram auto-resoluções cuja linha
  perdedora foi apagada**: a varredura ao vivo **não pode** devolvê-las. Nenhum par vivo estava
  liquidado por um bloqueio existente (os bloqueios foram escritos para pares que depois sumiram),
  então "filtrar o que já foi decidido" não reduz a lista — `pair_kind` é o filtro que a torna
  utilizável, e `GET /conflicts/judged` é a leitura que faltava.
- ✅ **O ledger da resolução: o `ban_created` é o detalhe que quase escapou.** O bloqueio é
  plantado com `ON CONFLICT DO NOTHING`, então desfazer uma resolução posterior **não pode** levantar
  um bloqueio que uma anterior escreveu. `created_link_ids` tem a mesma função para os vínculos: a
  inserção também é `ON CONFLICT DO NOTHING`, e sem o subconjunto o desfazer apagaria vínculos que
  existiam antes. Um teste prende cada um.
- ✅ **Dois bugs de SQL que o `ruff` e o teste pegaram.** `typing.cast` foi usado onde era preciso um
  cast **de SQL** (ele devolve o segundo argumento intacto, então o join comparava um objeto de tipo)
  e `as_integer` é **método** no comparador JSONB, não atributo. O primeiro foi o `F821` do ruff
  apontando uma string num subscrito dentro de `cast(...)`, que é onde o ruff lê anotação de tipo.
- ✅ **O `scope` é do Litestar.** A rota da colisão nasceu com um parâmetro chamado `scope` e recebeu
  o **ASGI scope** em vez da query string — exatamente a armadilha que a rota de stopwords já tinha
  documentado. O nome passou a ser `pair_kind`.
- ✅ **A faceta de anomalia, e a armadilha que o TODO não mencionava.** `anomaly_reasons` mistura
  código com payload (`RULE_MATCH:<regra>`, `LLM_SUSPECT:<prosa do modelo>`), então o valor cru não é
  dimensão: o balde é o **código**, com a regra nomeada e a prosa colapsada. E
  `PublicDocumentListResponse` **reusava `DocumentFacets`**, de modo que a dimensão nova teria sido
  publicada sozinha na difusão — "quantos registros estão sem data" é metadado de curadoria. Nasceu
  `PublicDocumentFacets` campo a campo, com `NOT_PUBLIC_FACETS` como **partição exata** e teste.
  Terceiro detalhe: `unnest` precisa estar no FROM (o PostgreSQL recusa `CASE` sobre função que
  devolve conjunto: *"argument of CASE/WHEN must not return a set"*).
- ✅ **O guarda de "não é assunto" recusa 1.489 tags e nada registrava isso.** Medido: 707 números
  com unidade, 689 logradouros, 74 anos soltos, 16 nomes de pessoa, 3 placeholders — `local não
  identificado` sozinho alcança **310 documentos**, e `1925` alcança **437**. `source='RULE'` existia
  na constraint, na assinatura do repositório e em lugar nenhum mais. A tentação era propor a metade
  semântica por estatística, e a medição proíbe: por contagem de documentos o topo dos órfãos é
  `igrejas` (2.474, assunto real faltando gaveta) e por baixa confiança é `madeira` (0,30) e
  `ecletismo` (0,38), também assuntos. O que a rota publica é o veredito que já existia, com a
  evidência ao lado — inclusive `vai para a faceta Lugar` (689), porque "não é assunto" não é "vai
  para o lixo".
- ✅ **Verificação sem tocar no acervo.** As duas telas que precisavam de dado usaram uma **cópia**
  do banco (`CREATE DATABASE ... TEMPLATE`): na da colisão o par foi resolvido, a entidade voltou com
  o id, o bloqueio foi levantado e o par reapareceu na varredura; na das anomalias 34 fichas foram
  marcadas e a faceta contou 20/8/7/7/7 sobre 34 enquanto a página tinha 20. A terceira rota é
  read-only por construção e foi verificada direto no vocabulário real. O acervo real terminou o ciclo
  com 0 anomalias, 0 exclusões de assunto, 0 resoluções e as mesmas 8.155 tags.

### Correção do contrato não determinístico (2026-10-06)

- ✅ **`bun run contract` gerava dois arquivos diferentes do mesmo código.** O `openapi.json` saía com
  duas descrições para `StopwordsScope` conforme o `PYTHONHASHSEED`: a docstring em inglês do enum ou
  a `description` em português de um campo que o referenciava. O mecanismo está no Litestar — ele
  busca o **componente compartilhado** do tipo do campo e aplica os kwargs do campo *nesse componente*
  (`process_schema_result`), só caindo para a docstring do tipo quando a descrição ainda é `None`.
  Ou seja: a descrição de um campo não documenta o campo, ela reescreve o tipo para o documento
  inteiro, e **qual campo vence depende da ordem de varredura**. Medido antes do conserto:
  `PYTHONHASHSEED` 0 e 7 davam PT, os outros EN — 1 variante em 21 execuções aleatórias, e o commit
  `c3f4830` ficou gravado com a variante errada. Conserto: as três descrições de campo saíram e o
  eixo passou a ser documentado **uma vez, no enum** (docstring, que chega ao contrato). Verificado
  com 12 seeds: documento **byte a byte idêntico**. `testing/unit/api/test_openapi_determinism.py`
  prende as duas pontas — a causa (nenhum campo de componente descreve um tipo compartilhado) e o
  sintoma (cada componente de enum no documento servido tem a descrição do próprio tipo).

### Interoperabilidade (v2.0)

- [~] **Adapters de ingestão:** as ABCs existem e o `PMCScraperAdapter` as implementa. Falta
  registro dinâmico, configuração por instituição e um segundo adapter real.
- [ ] **OCR/VLM** — texto de imagens históricas no MinIO.
- [ ] **Chatbot arquivista (RAG)** sobre o acervo.
- [ ] **Exportação OAIS** — a hierarquia (Fase 2.5) era o pré-requisito; agora existe.

---

## ✅ Fase 3.5 — Qualidade do dado de entrada — **FECHADA**

O maior ganho medido do projeto. **53% do acervo** compartilhava o mesmo bloco de
`scope_content`; 2.467 documentos tinham o prefixo `Registros Fotográficos -`. Isso dominava
os embeddings e degradava a busca.

### Diagnóstico medido (acervo real)

| Sintoma | Número |
| --- | ---: |
| Documentos com o mesmo bloco de escopo | 2.467 (53%) |
| Mesma proveniência (`IPPUC…`) | 99,8% |
| Sem data | 53% |
| Datas recuperadas por parsing | +201 (cobertura 47,0% → **52,6%**) |

### Entregue

- ✅ **Fase A — Catálogo de trechos.** `domain_text_templates`; 5 candidatos achados no acervo
  real; dry-run de curadoria funcionando.
- ✅ **Fase B — A IA para de ler boilerplate.** A composição do texto passou a viver **em SQL**
  (`text_quality_repo.py`): o Postgres normaliza espaços e subtrai os trechos aprovados, e a
  **mesma expressão** alimenta o texto do embedding *e* o MD5 do seu carimbo, o NER e a
  tipologia. Não reintroduzir composição em Python — `apply_excerpts_in_python` é espelho de
  leitura, só para o título derivado, e um teste de integração prende os dois.
- ✅ **Fase C — Título derivado, validador e curadoria do registro inteiro.**
  `worker_quality_validator`, `suggested_final_title` derivado na leitura (nunca armazenado) e
  `PATCH /documents/{id}` aceitando **todos** os campos ISAD(G) com trilha em
  `archive_document_revisions`.
- ✅ **Fase D — Cobertura e vocabulário.** Datas recuperadas; sugestão de merges de tags.
- ✅ **Fase E — Ciclo de curadoria dos merges.** Propostas com decisão durável, dry-run que usa
  o **mesmo planejador** do apply (`plan_merge`/`apply_merge`), ledger e **undo**.

### Medições que mudaram o desenho

| Medição | Resultado | Consequência |
| --- | --- | --- |
| Separação média entre pares (16 consultas, 3.608 docs) | 0.769 → **0.504** | O bloco dominava os vetores |
| Ranking com o escopo de produção | Hit@10 0.562 → **0.625** | O ganho existe, mas é modesto |
| **Aprovar tudo o que a máquina sugeriu** | Hit@10 **0.500** — *pior* que não fazer nada | O prefixo de título ajudava o título e **prejudicava** o vetor → nasceu o `scope` |
| Lematização de tags | **Descartada** como reescrita | Reescrever muda a identidade de toda tag nova. Virou **sugestão** (Fase E) |

> ⚠️ **`scope` é a decisão que importa.** Um trecho pode ter vários: `EMBEDDING`, `NER`,
> `TITLE`. Declara qual consumidor **para** de ler o trecho. Não alargar um escopo sem
> re-rodar `testing/evaluation/retrieval_quality.py`.

### O que segue aberto

- [ ] **Busca híbrida (RRF)** — lexical + semântica combinadas.
- [ ] **Qualidade semântica.** O gargalo medido era o texto (tratado na Fase B), mas o ranking
  ainda é fraco: o MRR **caiu 0.019** enquanto o Hit@10 subia. Registrado de propósito.
- [ ] **Aplicar as decisões de merge** — 784 propostas ainda `SUGGESTED` no acervo (95 já
  aplicadas em 2026-10-05; o estado `APPLIED` e o `applicable` calculado na leitura existem para a
  fila não voltar a oferecer trabalho já feito).

### Detalhes que não podem ser quebrados

- `ArchiveCleaningRule.rule_kind` separa `REWRITE` (o worker substitui) de
  `VALIDATE`/`LLM_CHECK` (só sinaliza). O worker de limpeza filtra `REWRITE` **explicitamente**
  — sem isso uma regra de validação reescreveria o texto. O estágio LLM é opt-in.
- A chave CDC staging→archive é o **hash do registro parseado**
  (`StagingRecord.parsed_content_hash()`), não do payload cru. Mudar o parser deixa o payload
  byte-idêntico, então `run_staging_pipeline(force=True)` re-parseia e o transfer vê diferença
  real. **Manter assim, ou correções de parser nunca chegam ao archive.**
- O merge de tags é **uma operação em duas metades**: `plan_merge()` (puro) e `apply_merge()`.
  Aplicar precisa chamar `repoint_synonyms()` **antes** de `delete_tags()` — a FK é
  `ON DELETE CASCADE`, então deletar primeiro destrói as grafias absorvidas por merges
  anteriores e a próxima ingestão recria o termo. O undo precisa apagar **só** os vínculos que
  o merge criou (`created_link_ids`).

---

## ✅ Fase 2.5 — Hierarquia das descrições — **H1–H8 FECHADAS (sem UI)**

O acervo **é** hierárquico e o sistema o tratava como linha plana. Evidência: `reference_code`
preenchido em **100%** dos 3.608 documentos, e o código **é o caminho** até a raiz.

### O que a medição corrigiu no plano

| O plano dizia | Medido | Consequência |
| --- | --- | --- |
| "a fatição por espaço é ~90% correta" | **Falsa para a família SMU** (1.124 docs, 31% do acervo): criaria **1.123 pais de 1 documento** | O fatiador passou a ser **ciente de vocabulário** (`domain/hierarchy_code.py`) |
| "profundidade do código = ordinal" | 5 tokens têm 2.466 Itens, **1 Série e 1 Seção** | A norma é **aprendida da coleção**, não fixada no código |
| Árvore de milhares de nós | **20 rungs → 52 nós propostos** | A tela é curadoria de ~52 nós, não de 3.608 |
| "3.604 órfãos; 4 com pai" | **3.608 órfãos**; os 6 registros estruturais têm **0 filhos** | A árvore precisa ser **materializada**, não ligada |

### Entregue

- ✅ **H1 — Catálogo de níveis.** `archive_description_levels` com seed NOBRADE, migração em
  duas etapas, backfill 3.608/3.608. Assimetria deliberada: a **carga tolera** nível
  desconhecido, o **arquivista recusa**.
- ✅ **H2 — Árvore.** `parent_id`/`path`/`level_id`, `RESTRICT` no pai, índice
  `text_pattern_ops`, recálculo de subárvore em **uma instrução**, diagnóstico
  (`PATH_DIVERGENCE` = **0** no acervo) e move com trilha.
- ✅ **H3 — Proposta read-only.** Rota `POST /hierarchy/proposal` e bancada em
  `testing/evaluation/hierarchy_proposal.py`. Provada read-only por `md5` sobre o acervo.
- ✅ **H4 — Materialização por decisão humana.** `archive_hierarchy_node_plans` (sugestão
  idempotente que **nunca sobrescreve decisão humana**), `collapse_into_code`, preview pelo
  **mesmo planejador** do apply, ledger reversível (`archive_hierarchy_materialisation_log`).
- ✅ **H5 — Edição individual e diagnóstico.** `GET /hierarchy/nodes/{id}` devolve nó,
  ramificação e filhos numa leitura.
- ✅ **H6 — Contrato de ingestão.** `parent_reference_code`/`hierarchy_path` no staging,
  variantes PT no `keys_map`, **pai ausente → órfão marcado e carga sem falha**, com retry no
  fim do transfer (o CDC jamais reprocessaria aquela linha).
- ✅ **H7 — Busca e facetas.** `ancestor_id` ("buscar dentro deste fundo") e `level_id`;
  ramo inexistente → **404**, não página vazia.
- ✅ **H8 — `DocumentSummary`** com `ancestors[]` (raiz primeiro) e `children_count`,
  em **duas** consultas por página.

### Verificação em escala real (cópia descartável dos 3.608)

`suggest` → 52 rungs · decisões do arquivista, incluindo **`AL` + `CONSTR` fundidos** e
`FOTOGRAFIA` → a Série `FOTOGRAFIAS` existente · `preview`: 12 a criar, 1 a adotar,
**3.607 a ligar** · `apply`: **1,7 s**, invariante intacta, **1 raiz**, profundidade 5 ·
`undo`: 3.619 linhas restauradas, **0** nós criados restantes.

### O caso que define a feat

`BR PRADAP SMU ED AL` e `BR PRADAP SMU ED AL CONSTR` são **um único nível**
("Alvenaria - Construções"). **Nenhum fatiador pode saber isso** — a evidência não está na
string. Por isso a materialização não é script: é **decisão humana registrada**.

### O que segue aberto

- [~] **A tela** — entregue na onda 2 (`/arranjo/plano` e `/arranjo/diagnostico`). O catálogo do
  acervo real tem **81 rungs propostas e 0 decididas**: aprovar é do arquivista, e a materialização
  só acontece depois do **preview** (a UI não oferece o apply sem ele).
- [ ] **Materializar a árvore no acervo real** — `POST /hierarchy/materialisation/apply` não foi
  executado neste ciclo: mover 4.813 descrições é decisão do dono do acervo, e a rota tem undo.
- [ ] **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU pede 4 rungs sob o Fundo e a
  escada tem 6. Achado real, agora visível como flag filtrável na tela (fundir ou criar nível
  intermediário).
- [ ] **31 códigos ilegíveis** (`... 10047 (1) 1915`, `... 369B`) — listados, **nunca
  adivinhados**; aparecem como flags `UNPARSED_TAIL`/`MID_CODE_IDENTIFIER` no plano.
- [ ] **25 `LEVEL_DEPTH_MISMATCH`** — eram 18 com 3.608 documentos; o acervo cresceu para 4.826.

### Riscos de pé

- `path` desnormalizado pode divergir → teste de invariante
  (`path == parent.path + "." + id`) obrigatório no CI.
- A árvore muda a busca → re-medir `retrieval_quality.py` (a baseline Hit@10 0.625 deixa de
  ser comparável se o corpus mudar de forma).

---

## ✅ Fase 1.5 — Macro Categorias — **FECHADA**

### O defeito que abriu a fase, e o diagnóstico que a medição corrigiu

O worker funcionava, mas a classificação estava **errada de forma sistemática**: 687 de 980
tags em "Mobilidade e Transporte", com `alvenaria` (826 docs), `casa`, `1924` e `residencial`
no balde errado.

**O plano dizia que a frase NLI consertaria. A medição disse que ela *é* o colapso.**

Bancada de 44 tags rotuladas à mão (aprovadas pelo dono), 3 formatos × 3 arranjos × 2 modelos:

| Arranjo | `sentence` (mDeBERTa) | Leitura |
| --- | ---: | --- |
| `same_format` (frase × frase) | **0.000** | É o colapso, não a correção |
| `mixed_vs_bare` (frase × nomes nus) | 0.450 | O que o plano provavelmente mediu |
| `bare_vs_bare` (baseline) | **0.500** | Melhor que a frase nos dois arranjos |

- ✅ **A frase dá acurácia 0.000** com **65% das tags numa gaveta** e **0/4 controles
  positivos**, nos dois modelos. `alvenaria → Urbanismo (0.536)` do plano **não se reproduz**.
- ✅ **A confiança ESTÁ calibrada** — o TODO anterior estava errado neste ponto. Certas 0.705
  contra erradas 0.455. O caso `1924 → Mobilidade (0.73)` não era "confiança não denuncia o
  erro": era **uma data que nunca deveria ter chegado ao modelo**.
- ✅ **A causa real tinha duas metades, nenhuma sendo o formato do rótulo:**
  1. **O vocabulário não cobria o acervo.** `igrejas` alcança **2.467 documentos** — a maior
     tag — e não existia "Religião". Nenhum rótulo conserta uma gaveta inexistente.
  2. **`Instituição` e `Localidade` nunca foram assuntos** — são proveniência e geografia
     (`ippuc` 2.376, `curitiba` 1.865) e disputavam a gaveta com `alvenaria`.

### Corrigido

- ✅ **Vocabulário de 5 → 8 gavetas de assunto**, derivadas das tags reais.
  `Saúde` e `Administração` foram **cortadas por falta de evidência** (zero tags no top 250) —
  não entraram por intuição. `Instituição`, `Localidade` e `Pessoa` **desativadas**
  (nunca deletadas: a FK é `SET NULL`).
- ✅ **`archive_tag_facets`** — um eixo que não é assunto. `ippuc` é produtor, `curitiba` é
  lugar, e uma tag pode ser os dois: a chave é composta.
- ✅ **`NENHUMA` com dois mecanismos.** O determinístico cobre o que tem forma (data,
  placeholder, logradouro, número) e pegou **1 de 4**; o resto são julgamentos
  (`pessoas` 166 docs, `vista aérea`, `capanema`) e ganharam `domain_subject_exclusions`, no
  padrão de `domain_ner_exclusions`.
- ✅ **Limiar 0.40 → 0.55, com fila atrás.** Uma resposta errada tem 0.455 de média; 0.40
  deixava passar quase todo erro. Abaixo do piso a tag fica órfã **e** entra em
  `archive_ai_review_queue` como `SUBJECT_LOW_CONFIDENCE`.
- ✅ **Carimbo = hash do conjunto de rótulos** (SHA-256, como o `worker_embedding` faz com o
  texto). A V3 expôs a falha na prática: aposentou `Instituição` enquanto suas tags mantinham
  `DONE`, e a correção nunca chegaria a elas.
- ✅ **`classifier_label`** existe como saída de curadoria, **não como padrão** — o docstring
  registra os 0.000 medidos para ninguém semeá-la com frases.

### O que segue aberto

- [ ] **Acurácia de 0.500 (mDeBERTa) / 0.575 (xlm-roberta) em nome nu.** ~42% do topo por
  `document_count` continua errando: `alvenaria`, `casa`, `rio`, `parque iguaçu` erram nos
  **dois** modelos, na mesma ordem — é limite do zero-shot NLI com sintagma nominal.
  **Decisão do dono: aceitar e resolver por curadoria.**
- [ ] **Trocar para `xlm-roberta-large-xnli`** (+0.075, ~3 tags em 40): medido e descartado
  por ora — não compensa um engine novo em produção. Bancada pronta para reavaliar.
- [ ] **Multi-label (Sigmoid)** em vez de Softmax — exige tabela de junção; não fazer antes
  de a curadoria de assunto estar em uso.
- [ ] **Front-end (regras de badge)** — vai para o sitemap (`/acervo/lista`), não para o
  Streamlit: sem filtro ativo, vencedor por votos + contador (`[ 🏙️ Urbanismo ] [+1]`); com
  filtro ativo, a categoria filtrada sobe ao topo ignorando o vencedor.

**Evidência:** `testing/evaluation/macro_category_quality.py` (bancada),
`macro_category_dry_run.py` (projeção), `macro_category_vocabulary.py` (vocabulário),
`macro_category_pairs.json` (gabarito aprovado).

---

## ✅ Fase 2 — API e Curadoria humana — **FECHADA no backend**

- ✅ **63 rotas** em 5 controllers (`Taxonomy`, `Documents`, `Hierarchy`, `Data Quality`,
  `Text Quality`), com anotações explícitas de Litestar e `sync_to_thread` em todas.
  Decisão em [`docs/adr/0001-litestar-as-http-framework.md`](docs/adr/0001-litestar-as-http-framework.md).
- ✅ **Composição por request:** `provide_unit_of_work` é dono da transação — commit no
  sucesso, rollback na exceção. Serviços recebem repositórios por construtor.
- ✅ **Curadoria humana:** `PATCH /documents/{id}` edita qualquer campo ISAD(G), registra o
  antes/depois em `archive_document_revisions` e marca `HUMAN_APPROVED`. `changed_by` é texto
  livre enquanto não há auth (Fase 4).
- ✅ **Serviços:** `TagService`, `EntityService`, `DocumentService`, `CleaningService`,
  `TextQualityService`, `HierarchyService`, `HierarchyMaterialisationService`.
- ✅ **Painel Streamlit (temporário):** 5 páginas, todas via HTTP (nunca Postgres direto).
  **Removido do repositório em 2026-10-06** (B8), quando as 17 telas do curador o cobriram.
- ✅ **Editar tags/entidades de um documento individual pela UI.** `/acervo/:id` aba Assuntos, com
  busca por nome (type-ahead) em vez do id.
- ✅ **Criar um nó que a origem não entregou** (2026-10-06). `/acervo/arvore` → "Criar nó":
  fundo, seção ou série **sem documentos** não sai de código de referência nenhum, e o plano só
  decide o que o fatiador propôs; o nó nasce sob o selecionado ou na raiz, com nível obrigatório.
- ✅ **Unificar duas tags escolhidas pelo arquivista** (2026-10-06). Aba Similaridade de
  `/assuntos/tags`: `unificar ↦` no par, canônica escolhível, dry-run obrigatório antes do write e o
  desfazer no ledger — a capacidade que só existia via `suggest` → aprovar → aplicar.
- ✅ **Vitrine reflete os enriquecimentos.** `DocumentSummary` expõe tipologia, gaveta de assunto e
  contagem de filhos; a lista mostra o badge vencedor por votos com o contador das secundárias.

---

## ✅ Fase 1 — Fundação e Core Pipeline — **FECHADA**

### Camadas e workers

- ✅ **Ingestion & Staging** com controle de linhagem (hash CDC). O staging converte payload
  cru em colunas ISAD(G) tipadas, parseia datas em 3 formatos e normaliza pontos de acesso.
  Zero perda: o não mapeado cai em `raw_metadata`.
- ✅ **Archive** com schemas estritos, idempotência por `execution_log` (JSONB, GIN) e
  governança.
- ✅ **9 workers** no runner unificado: `transfer` → `cleaning` → `ner` → `typology` →
  `thumbnail` → `conflict-judge` → `macro-category` → `quality-validator` → `embedding`.
- ✅ **Governança nos 9 workers.** `ai_writable_documents()` bloqueia `HUMAN_APPROVED` e
  `REJECTED`. **Uma exceção documentada:** o `worker_embedding` deliberadamente não usa o
  guard — o vetor é índice derivado do texto, e um documento aprovado cujo texto mudou precisa
  ser re-embedado; ele escreve só a coluna `embedding` e seu carimbo, e pula `REJECTED`.
- ✅ **Governança bidirecional.** Vitória da entidade → o nome da tag vai para
  `DomainStopwords` (escopo TAG). Vitória da tag → `domain_ner_exclusions` (decisão de
  curadoria com `reason`/`source`/`tag_id`). **Não colapsar as duas.**
- ✅ **Carimbos versionados** com `flag_modified`. O `worker_embedding` guarda o **MD5 do texto
  embedado** (calculado pelo Postgres), então mudar o texto — inclusive edição humana —
  requeue o documento.

### Correções de auditoria

- ✅ **`ai_confidence_score`** tem produtor (`worker_macro_category`).
- ✅ **`is_anomaly`/`anomaly_reasons`** têm produtor (`worker_quality_validator`).
- ✅ **Ancoragem "isto é TAG"** — catálogo `domain_ner_exclusions` alimentado pelo juiz e pelo
  curador, com expurgo retroativo.
- ✅ **Bloqueio por limite de token**, não por nome exato: o spaCy funde tokens vizinhos e
  devolve `"IPTU do Batel"` como **uma** entidade. Um teste com `mock_registry` não pegaria
  isso — o mock devolve o nome exato que recebeu.

---

## 🟡 Fase 3 — Descoberta, Performance e Observabilidade — **PARCIAL**

### Busca

- ✅ **Full-text nativo** com `ts_rank`, acento-insensível (`unaccent` + wrapper `IMMUTABLE`),
  alcançando tags e entidades, com facetas. Medição: `historica` saiu de **0** (no `ILIKE`
  antigo) para **2.489** resultados.
- ✅ **Coluna morta resolvida por remoção:** `semantic_search_vector` (Text, sempre `None`) saiu
  e o vetor passou a ser **gerado pelo Postgres** (`search_vector`) — nunca fica obsoleto nem
  depende de worker. **Não reintroduzir.**
- ✅ **Busca semântica** com `pgvector` (`vector(384)`, HNSW cosseno), `mode=lexical|semantic`,
  embeddings dos 3.608 documentos pelo modelo real. O modelo é cacheado por processo em
  `api/dependencies.py` e **nunca** carregado para um request lexical.
- ✅ **Fallback de substring:** fragmento no meio da palavra recupera a contagem do `ILIKE`
  antigo, sem `rank`.
- ✅ **Taxonomia alcançável pela grafia absorvida.** Após 40 merges de plural, `lojas` perdia
  42 de 54 documentos e `homens` 30 de 35 — o stemmer só cobre documentos cujo *texto* carrega
  a palavra. O mapeamento por `domain_synonyms` levou a **0 perdidos**.
  **Não remover ao mexer no match de taxonomia, e manter nos dois eixos (tag e entidade).**
- [ ] **Busca híbrida (RRF)** — combinar lexical + semântica.
- [ ] **Filtros facetados na UI** (as rotas existem; falta a tela).

### Operação

- ✅ **CI:** ruff + basedpyright + `alembic check` + pytest em Postgres.
- ✅ **Logging** com loguru, interceptação de terceiros e `InterceptHandler`.
- ✅ **Painel de operação** (`/sistema/*` no SPA, `/api/v1/system/*` na API): catálogo dos 9
  workers com engine/preset/modelo resolvidos, filas pendentes/processadas/falhadas, overrides
  persistidos com trilha, ledger de execuções, disparo pela tela e diagnóstico de infra. Detalhe
  na seção "Painel de operação" abaixo; decisão em `docs/adr/0004`.
- ✅ **Diagnóstico de infraestrutura** (`GET /api/v1/system/health`): banco (com os totais do
  acervo), Ollama (modelos instalados × exigidos pelos presets), bucket de miniaturas e a
  configuração efetiva do processo. Cada sonda responde sozinha e nunca devolve segredo.
- 🟡 **Rastreamento de erros nos workers.** O ledger registra a exceção de cada execução
  (`archive_worker_runs.error`) e o painel a mostra; **não há Sentry** nem agregação de falhas
  por causa raiz.
- 🟡 **Retomada e agendamento.** O disparo manual existe (linha de comando **e** tela, com guarda
  de concorrência no banco), e uma execução interrompida pelo processo é marcada como
  `INTERRUPTED` no próximo boot. **Não há scheduler, cron nem retry policy** — e o executor roda
  dentro da API, o que pressupõe um único processo (ver ADR 0004).
- [ ] **Health/readiness para orquestrador** (um `/health` mínimo para k8s/load balancer). O
  `/system/health` é para humano: faz I/O de rede e devolve detalhe.
- [ ] **Testes de pipeline com engines reais.** A suíte usa `mock_registry` (correto para
  isolamento), o que deixa invisível a classe de bug que quebrou o `suggest-macro`. Falta um
  teste de fumaça opcional marcado `slow`/`e2e`.

### Painel de operação (2026-10-06)

Entregue como `/sistema/workers`, `/sistema/execucoes` e `/sistema/diagnostico`, servido por
`/api/v1/system/*`. O que ele resolve, e o que **não** promete:

| Capacidade | Como funciona |
| --- | --- |
| Ver os workers | `workers/catalogue.py` é a definição única (ordem, eixo, governança, carimbo, contador); importa **nenhum** worker, resolvendo por caminho pontilhado com cache — subir a API não paga spaCy |
| Ver preset e modelo | `describe_config` em cada registry é o gêmeo de leitura do `get_engine` (não instancia nada); um teste captura os kwargs do factory e compara os dois |
| Ver a fila | Cada worker expõe `count_pending` com o **mesmo** predicado do `execute`; `thumbnail` lê a URI do storage, `conflict-judge` é explicitamente não mensurável (o scan trigram mediu 53 s) |
| Configurar | `archive_worker_settings` (linha parcial: `NULL` segue o código) + revisões; precedência `argumento explícito > override > default do signature` |
| Rodar | `POST /system/workers/{name}/runs`, com overrides só daquela execução; o executor roda **um worker por vez** |
| Concorrência | Índice único parcial `uq_worker_run_active` em `(worker_name)` para `QUEUED`/`RUNNING` — a guarda é do banco, não de um lock de processo |
| Histórico | `archive_worker_runs`, gravado pelo runner para CLI **e** tela, com a configuração resolvida, duração e resultado |
| Recuperação | `api/lifespan.py` marca `INTERRUPTED` o que um processo morto deixou em voo (tolerante a banco fora) |
| Diagnóstico | Banco, Ollama (modelos exigidos × instalados), bucket e config do processo; nenhum segredo é devolvido |

Também corrigiu um defeito real: os presets de LLM **fixavam** `http://localhost:11434` e
ignoravam `OLLAMA_HOST_URL` — o painel mostraria um host que não era o efetivo. O host saiu dos
presets e passou a vir de `resolve_ollama_host()`; um `--option host=...` ainda vence.

**Limites conhecidos:** sem auth (`changed_by`/`requested_by` são texto livre), sem agendamento,
sem cancelamento de execução em andamento, e a recuperação de órfãos pressupõe **um** processo de
API.

---

## 🧭 Backlog registrado (não planejado)

### Ingestões — configuração por origem

> Registrado em 2026-10-06 a pedido do dono do acervo. **Fora do plano do painel de operação.**

Hoje a ingestão é uma só: o scraping do site público entra em `raw`/`staging` e o transfer leva
para o archive. A ideia é uma feat **"Ingestões"** que trate a origem como um objeto de primeira
classe:

- **Origens plurais:** o scraper do PMC rodando continuamente, uma ingestão manual por CSV e um
  scraper de outra instituição, cada uma com seu ciclo de vida e sua periodicidade.
- **Configuração por origem:** o que hoje é regra global (colunas lidas pelos workers, limpeza,
  limiares, talvez o próprio preset) poderia ser **sobrescrito no nível da origem** — uma coleção
  doada com outra convenção de título não deveria herdar a mesma regra de limpeza.
- **Consequência para o painel:** a tela de operação ganharia um eixo a mais ("de qual origem é
  esta fila?"), e o ledger de execuções passaria a registrar a origem junto do worker.

Nada disso foi desenhado nem medido; é só o registro da ideia para não se perder.

---

## 🔧 Pendências operacionais no acervo (não são código)

O código está pronto. **Primeira metade da Etapa A executada em 2026-10-05** (higiene, re-parse e
transfer) — e ela **corrigiu o número do acervo**: são **4.826 descrições**, não 3.608. O
`raw`/staging tinha 4.785 registros e 1.218 deles nunca haviam chegado ao archive.

Estado medido **depois** da execução:

| # | Pendência | Detalhe |
| --- | --- | --- |
| 1 | ✅ **Regra de limpeza de teste desativada** | `rule_id=1` ("aaaaa") agora `is_active=false`; **0 regras ativas**. Ela nunca casou com nada — só carimbava |
| 2 | ✅ **Re-parse forçado + transfer executados** | `run_staging_pipeline(force=True)`: 4.785 registros, 0 falhas. `transfer`: 4.785 sucessos, 0 falhas, **0 pais declarados** (a origem não os manda — é por isso que a árvore é **materializada**, não ligada) |
| 3 | ⚠️ **Todo o enriquecimento de IA está pendente** | O re-parse mudou o `parsed_content_hash` de todas as linhas **por desenho**, então o transfer reescreveu o conteúdo e zerou os carimbos: **0** `worker_ner_v2`, **0** `worker_typology_classifier_v2`, **0** `worker_macro_category_v1`, **0** `worker_quality_validator_v1`, **41** `worker_embedding_v1`. Os **3.608** vetores antigos continuam na coluna (a busca semântica segue funcionando); as 1.218 descrições novas não têm vetor |
| 4 | ⚠️ **Tags sem gaveta de assunto** | de **8.257** (o acervo cresceu: eram 6.142, depois 8.349, e 92 foram absorvidas por merges em 2026-10-05). 59.388 vínculos documento↔tag |
| 5 | **0 de 81 rungs decididos** | `POST /plans/suggest` rodou e propôs **81** rungs (o plano estimava ~52 com 3.608 documentos; com 4.826 são mais códigos). Decidir é do arquivista — a tela `/arranjo/plano` está pronta |
| 6 | **784 propostas de merge sugeridas** | em 2026-10-05: **95 aplicadas** (92 num lote + as antigas), **2 aprovadas** sem membros para absorver e **4 rejeitadas**. O estado `APPLIED` existe desde a migração `a1b2c3d4e5f6` |
| 7 | **0 revisões humanas** | relevante para a decisão B2 (predicado de publicação) |
| 8 | **`domain_text_templates` e `domain_ner_exclusions` vazios** | as duas feats estão implementadas e sem uso no acervo |

Diagnóstico estrutural do acervo real (pós-transfer):

| Issue | Total | Leitura |
| --- | ---: | --- |
| `ORPHAN` | **4.820** | quase todo o acervo: a árvore ainda não foi materializada |
| `DOSSIER_WITHOUT_PARENT` | **1.612** | Dossiês na raiz, esperando a rung acima ser aprovada |
| `UNKNOWN_LEVEL` | **13** | a carga tolera, o arquivista não |
| `PATH_DIVERGENCE` | **0** | a invariante do caminho está intacta |
| `LEVEL_DEPTH_MISMATCH` | **25** | era 18 com 3.608 documentos |

> **Decisão de produto pendente:** rodar os workers de IA (item 3) **antes ou depois** de decidir os
> 81 rungs? Enquanto não rodarem, a UI mostra menos do que o sistema sabe fazer — e a janela para
> reprocessar fecha na primeira ficha aprovada por humano.

---

## ✅ Verificação executada (evidências)

### Auditoria de 2026-10-04 (acervo real, 3.608 documentos)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **833 passed** |
| Gate | `ruff` limpo (263 arquivos) · `basedpyright` **0 errors** · 21 migrações sem drift |
| **API exercitada por HTTP** | busca lexical 2.468 docs p/ "parque" com `rank`; semântica responde; facetas (`ORG` → 1.873) |
| **`suggest-macro` corrigido** | **56 clusters** em 6.142 tags (antes: 422 no preset padrão) |
| ⚠️ **Classificação de assunto (antes da correção)** | 687 de 980 tags em "Mobilidade"; `alvenaria` (826), `casa` (387), `1924` (260) no balde errado |
| ⚠️ **Carimbos v1→v2** | `_v1` em 3.608 docs; o código filtra `_v2` |
| **Forma do `reference_code`** | 100% preenchido; vocabulário fechado (8 valores no 3º token); código **é** o caminho; 3.608 órfãos |

### Ciclo E0+E1 (2026-10-05, verificado em execução)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **883 passed** |
| Gate | `ruff` limpo · `basedpyright` **0 errors** · 22 migrações sem drift |
| `alembic check` após a migração de difusão | **sem drift** |
| Contrato OpenAPI | **60 paths / 70 operações / 99 schemas**, regenerado e idêntico (o mount do SPA não entra no schema) |
| `inbox` no acervo real | 3.602 órfãos de arranjo · 371 propostas · 4 conflitos · 5.446 tags sem gaveta · 3.608 não revisados |
| Facetas no acervo real | tipologia (Planta 284, Fotografia 64), assunto (Mobiliidade 1.636), entidade (LOC 3.509 / PER 2.129 / ORG 1.873), nível (Item 2.478, Dossiê 1.124) |
| SPA servido pelo Litestar | `/`, `/acervo/lista`, `/acervo/100148` → **200** com `index.html`; `/api/v1/nao-existe` continua **404** |
| Superfície pública | `GET /api/v1/public/documents` → `total: 0` (nada publicado, como esperado) |
| Front | `tsc --noEmit` limpo · `eslint` limpo · `vite build` em ~300 ms (397 kB, 125 kB gzip) |

> **Achado de infraestrutura que custou uma execução de teste inteira:** outro projeto ocupava a
> porta 5433, então o container de teste subiu **sem publicar porta** e a suíte falou com o
> PostgreSQL errado (345 erros que pareciam regressão). `docker-compose.test.yml` agora publica
> `${TEST_DB_PORT:-5433}`.

### Ciclo da onda 2 (2026-10-05, verificado em execução)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **895 passed** |
| Gate | `ruff` limpo (279 arquivos) · `basedpyright` **0 errors** · `alembic check` **sem drift** |
| Contrato OpenAPI | **61 paths / 71 operações / 101 schemas**, regenerado (as 3 rotas/2 schemas novos) |
| Front | `tsc --noEmit` limpo · `eslint` limpo · `vite build` em 189 ms (424 kB, 131 kB gzip) |
| SPA servido pelo Litestar | `/arranjo/plano` e `/arranjo/diagnostico` → **200** com `index.html` (deep link e F5) |
| **Etapa A, primeira metade (acervo real)** | regra de teste **desativada**; `run_staging_pipeline(force=True)` 4.785/4.785; `transfer` 4.785 sucessos, 0 falhas, **0 pais declarados** (a origem não manda) |
| **Acervo medido depois** | **4.826 descrições** (eram 3.608) · 0 com pai · 13 sem nível · 8.349 tags · 59.388 vínculos |
| `POST /hierarchy/plans/suggest` no acervo real | **81 rungs** criadas, 0 preservadas (catálogo estava vazio) |
| Diagnóstico no acervo real | ORPHAN 4.820 · DOSSIER_WITHOUT_PARENT 1.612 · UNKNOWN_LEVEL 13 · **PATH_DIVERGENCE 0** · LEVEL_DEPTH_MISMATCH 25 |
| `/hierarchy/flags` no acervo real | 5 issues · 3 status · **8 flags de rung** · 5 violações |
| Verificação visual | 3 telas renderizadas com `chrome-headless-shell` (plano, plano filtrado, diagnóstico + mismatch); as evidências em `.analysis/shots/wave2-*.png` **é que revelaram** o vocabulário incompleto |

> **A tela é o teste que faltava.** O vocabulário incompleto de `/hierarchy/flags` passou por
> `pytest`, `basedpyright`, `tsc`, `eslint` e `vite build` — todos verdes. Ele apareceu no
> **primeiro** screenshot, como `NEAR_DUPLICATE_NODE` escrita crua no card. É o terceiro defeito
> desta natureza no projeto (já tinham sido o `bg-[--color-surface]` em 105 lugares e o
> `html_mode` do SPA).

### Ciclo da etapa C (2026-10-05, escrita exercitada no browser)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **914 passed** (+19: busca/curation de taxonomia e as rotas novas) |
| Gate | `ruff` limpo (280 arquivos) · `basedpyright` **0 errors** · `alembic check` **sem drift** |
| Contrato OpenAPI | **64 paths / 74 operações / 104 schemas** (3 rotas novas) |
| Front | `tsc --noEmit` limpo · `eslint` limpo · `vite build` em 197 ms (434 kB, 133 kB gzip) |
| **Escrita pela UI, browser real (8/8)** | tag ligada **pelo nome** → documento vira `HUMAN_APPROVED`; gaveta trocada para "Religião" (chegou ao vocabulário); tag removida; unidade superior escolhida pelo nome e **movida** (`parent_id` conferido na API); lista filtrada **sem Enter** |
| Banco usado no exercício | o **de teste**, com 2 descrições semeadas — escrever pela UI marca a ficha como revisada, o que não pode acontecer no acervo real enquanto a IA está pendente |
| Verificação visual | `.analysis/shots/etapa-c-*.png`: type-ahead aberto na aba Assuntos, aba Arranjo com o seletor de pai, lista com o intervalo de datas |

> **A armadilha que custou uma rodada de testes:** rodar `alembic upgrade head` no banco de **teste**
> faz o `create_all` do conftest pular as tabelas que já existem, e a suíte roda contra o schema
> migrado em vez do modelo — **53 falhas + 42 erros** que parecem regressão e somem quando o schema é
> derrubado. Registrado no `AGENTS.md`.

### Ciclo da onda 3 (2026-10-05, assuntos)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **916 passed** (+2: o peso da gaveta conta **descrições**, não vínculos) |
| Gate | `ruff` limpo (280 arquivos) · `basedpyright` **0 errors** · `alembic check` **sem drift** |
| Front | `tsc --noEmit` limpo · `eslint` limpo · `vite build` em 206 ms (459 kB, 139 kB gzip) |
| **`suggest` de merge no acervo novo** | **500 clusters** (o teto do pedido) em **1,0 s** · **707 pendentes** · **123 com aviso** |
| Pesos das gavetas no acervo real | Mobilidade e Transporte **2.296** · Urbanismo e Arquitetura **11** · as outras **0** (a IA ainda não reprocessou) |
| Telas | `/assuntos/tags` (relevância, similaridade, propostas com preview + lote + ledger/undo) e `/assuntos/categorias` (8 ativas, 3 aposentadas, peso, rótulo editável) |
| Verificação visual | `.analysis/shots/wave3-*.png` — os clusters reais aparecem na tela: `igrejas ← igreja` (correto) ao lado de `residencial ← área residencial, casa residencial, região residencial` (perigoso) e `trem ← trens` com `WEAK_MEMBER` |
| **Stopwords no acervo real** | **184 termos**: 96 no eixo `TAG` (o nome próprio venceu o assunto — `albano cunha`, `avenida joão gualberto`) e 88 em `ENTITY` (o assunto venceu o nome — `alvenaria`, `autor`). É a governança bidirecional visível na tela |
| **Preview da purga no acervo real** | **0 tags** seriam apagadas: quando esses 184 termos foram registrados, a purga já rodou. O painel diz "não há o que apagar" em vez de fingir trabalho |
| **Escrita de stopwords pela UI (browser, 6/6)** | banir pela tela chegou ao catálogo (184 → 185); o botão de purga fica **desabilitado** até conferir o impacto; o preview responde `reversible: false`; desbanir voltou a 184. Nada de resíduo — e a purga **não** foi disparada no acervo real |
| **Fluxo de merge corrigido (browser)** | "selecionar todas as aprovadas" enche o lote com **92 clusters** e libera o apply (teto 200). O apply não foi clicado: é a decisão do dono do acervo |

> **O que ficou de fora, e por quê.** A quarta subtela do sitemap (stopwords) **não** entrou: a
> purga apaga tags, e não existe rota para ler as stopwords atuais nem preview do que seria apagado.
> A tela diz isso no rodapé em vez de oferecer um botão destrutivo sem impacto — a regra do próprio
> sitemap é que nenhuma tela escreve sem mostrar o antes.

### Ciclo do estado aplicado (2026-10-05, o relato "dá erro e não sai de aprovadas")

| Verificação | Resultado |
| --- | --- |
| **O apply tinha funcionado** | ledger **41 → 133** linhas, tags **8.349 → 8.257**, tudo às **23:55:25** — 92 clusters absorvidos de uma vez |
| **O erro era a segunda tentativa** | os membros daqueles 20 já tinham sido absorvidos pela primeira; o status ficava `APPROVED` para sempre e a tela oferecia um apply impossível |
| Migração `a1b2c3d4e5f6` | estado `APPLIED` + backfill: **95** propostas casadas pelo `fingerprint` (86) e pelo **nome absorvido** no ledger (9, das mesclagens por `POST /tags/merge`, que não têm fingerprint) |
| Fila depois do backfill | **2 aprovadas** (ambas `applicable=false`, canônica morta), **95 aplicadas**, **784 sugeridas** com `applicable=true` |
| `pytest` | **932 passed** (+2 de integração: o lote ignora o já aplicado em `skipped`; a proposta aplicada sai da fila de aprovadas) |
| Gate | `ruff` limpo (281 arquivos) · `basedpyright` **0 erros** · `alembic check` sem drift · `tsc`/`eslint`/`vite build` limpos |
| Verificação visual | `.analysis/shots/wave3-cumpridas.png` e `wave3-aplicadas.png` — a tela diz "já não têm o que absorver. Não são falhas" e oferece arquivar, em vez de 20 linhas vermelhas |

### Ciclo das ondas 4–6 e B8 (2026-10-06, o sitemap do curador fechado)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **933 passed** (+1: `max_depth` absoluto devolve só as raízes) |
| Gate | `ruff` limpo (265 arquivos) · `basedpyright` **0 erros** · `alembic check` **sem drift** (23 migrações; nenhuma nova) |
| Contrato OpenAPI | **66 paths / 78 operações / 128 schemas** (era 110: as rotas de escrita tipadas entraram) |
| Front | `tsc --noEmit` limpo · `eslint` limpo · `vite build` em 176 ms (543 kB, 157 kB gzip) |
| **Streamlit removido** | diretório `dashboard/`, dependência `streamlit`, 8 pacotes transitivos no `uv.lock`, processo `web` do `Procfile`, `API_BASE_URL` (só ele lia), referências em `README.md`/`AGENTS.md`/`.env.example` |
| Telas novas | `/acervo/arvore` · `/arranjo/niveis` · `/entidades/{lista,excecoes,conflitos}` · `/qualidade/{trechos,regras,anomalias}` · `/assuntos/{descobrir,excecoes}` — **17 telas no menu**, todas rotas que a API serve |
| **Rotas de leitura exercitadas por HTTP** | 12 rotas em 200; a árvore com `max_depth=0` responde em **10 ms** (ler a floresta seriam 4.831 linhas) |
| **Dry-runs exercitados (só leitura)** | regra de limpeza: `is_valid_regex=true`, **5 ocorrências**; trecho `Registros Fotográficos - `: **3.162 de 4.844 documentos** mudariam |
| Links profundos e F5 | `/acervo/arvore`, `/entidades/conflitos`, `/acervo/100148` e `/acervo/100148?aba=arranjo` → **200** com `index.html`; `/api/v1/nao-existe` continua **404** |
| Verificação visual | `.analysis/shots/waves456/*.png`: 17 telas renderizadas com `chrome-headless-shell`, incluindo as antigas (nenhuma regressão) |
| **Acervo real, pelo que a tela mostrou** | árvore **materializada** (`Acervo do Departa…` com **1.717 filhos**, 18 raízes, 13 sem nível) · níveis: 6 degraus, 4.831 descrições · entidades: **41.077 vínculos** nos 50 primeiros · conflitos tag × entidade: **2.502** acima de 0,85 · trechos: **0** (feature sem uso) · regras ativas: **0** · anomalias: **0** |

**O que a tela corrigiu neste ciclo** (`tsc`, `eslint`, `vite build` verdes antes disso):

1. **A árvore repetia "SEM TÍTULO" seis vezes.** Não é defeito de dado — é o placeholder que o
   parser de staging grava quando a origem não manda título —, mas um rótulo que se repete não diz
   *qual* descrição é. Agora cai para o código de referência e, sem ele, para o identificador, com o
   título cru no `title=`.
2. **"1 descrições".** O primeiro card do catálogo de níveis dizia isso; nasceu `descricoes(n)`.
3. **A colisão tag × entidade eram 2.502 cards de uma vez.** A rota devolve tudo e não tem
   paginação: a tela desenha 50 e oferece "mostrar mais". O mesmo corte foi aplicado à similaridade
   de entidades (647 pares a 0,5), espelhando o que a aba de tags já fazia.
4. **O limiar da colisão disparava uma varredura por tecla.** `onChange` no campo rodava o join de
   trigrama a cada dígito de "0,75"; passou a aplicar no blur/Enter.
5. **A data do dossiê era um campo de texto com valor em pt-BR** num rótulo que pedia `AAAA-MM-DD`:
   editar uma vez mandaria "1 de jan. de 1994" para uma rota que parseia data. Virou `type="date"`
   com o valor ISO.
6. **A similaridade de entidades não mostrava os identificadores** — e o acervo real tem pares com
   os **dois nomes idênticos** (`Cia. #228 ≈ Cia. #291`, similaridade 1.000), onde a confirmação
   dizia só "unificar Cia. → Cia.". Os ids passaram a acompanhar cada lado.

> **O que este ciclo não fez.** Não escreveu nada no acervo real e **não** exercitou o clique de
> escrita pela UI nas telas novas — as rotas de escrita estão cobertas por teste de integração e o
> corpo é tipado contra o contrato, mas o clique ponta a ponta continua sendo a verificação que
> falta (a do ciclo da etapa C usou o banco de teste, e é o caminho para repetir).

### Ciclo das lacunas fechadas (2026-10-06, as duas capacidades sem botão)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **934 passed** (+1: o preview do merge aceita o par escolhido à mão, não só a proposta) |
| Gate | `ruff` limpo (265 arquivos) · `basedpyright` **0 erros** · `alembic check` **sem drift** · `tsc`/`eslint`/`vite build` limpos (553 kB, 159 kB gzip) |
| Contrato OpenAPI | **65 paths / 77 operações / 127 schemas**: a rota legada e o `EntityStopwordPurgeResponse` saíram. Dois dumps seguidos saem **byte a byte iguais**, que é o que o CI compara |
| **Criar nó (`/acervo/arvore`)** | o formulário escolhe a raiz **ou** o nó selecionado (o nome do pai vem da leitura do nó), e exige código, título **e nível** — a mesma decisão que aprovar uma rung exige. O botão fica desabilitado até os três existirem; a escada é validada pela rota, não por uma segunda cópia das regras na tela |
| **Unificar par (`/assuntos/tags?aba=similaridade`)** | `unificar ↦` por par, canônica escolhível, dry-run **obrigatório** antes do botão (o mesmo planejador do write) e o aviso de gaveta perdida nomeando a gaveta |
| **Dry-run exercitado no acervo real (só leitura)** | `avenida iguaçú esquina com rua brigadeiro franco` (#1328) ← `avenida iguassú esquina com brigadeiro franco` (#2686): **1 documento**, 1 vínculo, 1 tag absorvida, `CATEGORY_WOULD_BE_LOST`. A tela diz "apaga uma classificação de assunto: a tag absorvida está na gaveta **Mobilidade e Transporte** e a canônica não tem gaveta". Nada foi escrito |
| Verificação visual | `.analysis/shots/tree-create-node-{1,2,3}*.png` e `.analysis/shots/tags-merge-{1,2,3}*.png`, com `chrome-headless-shell` + CDP contra o SPA servido pelo próprio Litestar (e o acervo real atrás, por isso **nenhum** clique de escrita foi dado) |

> **O que a tela corrigiu neste ciclo.** O painel do merge imprimia `gaveta 618` — o id cru que o
> `MergePreviewResponse` carrega em `macro_category_id`. A tela passou a resolver o nome pelo
> catálogo que já tem em cache (`queries.macroCategories()`) e o aviso de perda diz **qual** gaveta
> morre. É o mesmo modo de falha do `NEAR_DUPLICATE_NODE` da onda 2: um identificador de máquina
> chegando ao arquivista porque ler o código parecia suficiente.
>
> **O que ficou de fora.** O `ProposalCard` da aba Propostas continua mostrando `gaveta {id}` no
> "Conferir impacto": é anterior a este ciclo, não foi tocado, e é a mesma correção de uma linha
> para quem encostar nele. E o clique de escrita das duas telas novas **não** foi exercitado ponta a
> ponta no acervo real — o caminho para repetir é o banco de teste, como no ciclo da etapa C.

### Execuções anteriores (preservadas)

| Verificação | Resultado |
| --- | --- |
| Migração em banco limpo (todas) | `upgrade` → `check` → `downgrade -1` → `upgrade` → `check` sem drift |
| **Imagem pgvector + PostGIS** | `vector 0.8.7`, `postgis 3.6.4` e `unaccent` no mesmo container |
| **Worker `embedding`** | 3.608/3.608 em ~1 min; 384 dims; 0 pendentes na 2ª execução |
| **Embedding persistido** | `cos(guardado, recalculado) = 1.0`; o `<=>` do Postgres bate com o cosseno em Python |
| **Catálogo de trechos** | 3.608 docs → **5 candidatos** (bloco 2.467, prefixo 2.467, etc.) |
| **Datas recuperadas** | 201 documentos saíram de "sem data"; cobertura 47,0% → **52,6%** |
| **Sugestões de merge** | **411 clusters** (267 `TRIGRAM` · 101 `MIXED` · 43 `PLURAL`), 2.074 documentos tocados |
| **Aplicação no acervo** | 40 clusters `PLURAL`: 40/40 sem falha em 2,9 s; tags 6.182 → **6.142** |
| **Undo ao vivo** | `vendas ← venda` desfeito e reaplicado: tag, `tag_id` e vínculo restaurados exatamente |
| **Hierarquia em escala** | `apply` 1,7 s; **1 raiz**; profundidade 5; `undo` com 3.619 linhas restauradas |
| **Bancada do classificador** | 44 tags × 3 formatos × 3 arranjos × 2 modelos |

### Bugs conhecidos e abertos

1. **Acurácia de assunto em 0.500/0.575** — limite do zero-shot NLI com sintagma nominal.
   Decisão: aceitar e resolver por curadoria (Fase 1.5).
2. **Busca semântica com qualidade fraca** — parcialmente endereçada; a híbrida (RRF) continua
   pendente e o MRR caiu 0.019.
3. **Sem autenticação** — bloqueio para exposição pública; entra no B9, por último.
4. **O acervo está desatualizado em relação ao código** — a regra de teste foi desativada e o
   re-parse/transfer rodaram, mas **todo o enriquecimento de IA está pendente** (0 carimbos `_v2`).
   São operações, não código (ver "Pendências operacionais"), e a janela fecha na primeira ficha
   aprovada por humano.
5. **`path` desnormalizado** pode divergir — teste de invariante no CI (`PATH_DIVERGENCE` = 0
   hoje, mas a garantia precisa ser automática).
6. **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU não cabe na escada de 6 níveis
   sem repetir um ordinal. Achado real, a resolver na tela: agora é uma das flags que
   `/hierarchy/flags` publica, e o filtro do plano sabe mostrá-la.
7. ✅ **`GET /conflicts/cross-domain` levava 53 s** — corrigido. A causa **não** era o GIN: a
   comparação coluna-a-coluna **usa** o índice (o Postgres empurra a linha externa como chave de
   bitmap). A causa era o `OR lower(t.name) = lower(e.name)` no join, que o transforma em
   `Join Filter`, faz o planejador materializar o lado interno e varre os 23,4 M pares. E o `OR` era
   **redundante**: a similaridade do `pg_trgm` é insensível a maiúsculas
   (`similarity('Batel','batel') = 1`), então todo par que ele pegava o `%` já pegava. Medido:
   **52,9 s → 1,42 s**, diferença simétrica dos conjuntos **zero** (2.418 pares nos dois).
8. ✅ **Prefilter de comprimento descartava pares reais** — corrigido. Havia um
   `abs(length(a) - length(b)) <= 3` rotulado "PERFORMANCE HACK" antes do `%` nos dois
   `find_all_similar_pairs`. Diferença de comprimento **não** é limitada pela similaridade de
   trigrama: `'alameda cabral'` ~ `'al. alameda cabral'` tem similaridade **1.000** e difere em 4.
   Descartava **419 de 647** pares de entidades (65%) e **467 de 906** de tags (52%), e os pares
   escondidos eram justamente os valiosos (abreviações: `rua des. desembargador ermelino de leão`).
   Removido: o índice já é o filtro (tags 906 pares em 2,1 s; entidades 647 em 203 ms).
9. **`access_conditions` existia no staging e não no archive** — corrigido no ciclo E0+E1; fica
   registrado porque o modo de falha (campo parseado, coluna ausente, nenhum erro) pode se repetir
   em qualquer campo novo do ISAD(G).
10. ✅ **`/hierarchy/flags` publicava um vocabulário incompleto** — corrigido no ciclo da onda 2.
    As rungs carregam flags de **quatro** origens (`ProposalFlag`, `HierarchyIssue.NEAR_DUPLICATE_NODE`,
    `HierarchyViolation.LEVEL_NOT_ALLOWED_AS_CHILD` e `CodeFlag`), e a rota anunciava só a primeira:
    o front renderizava `NEAR_DUPLICATE_NODE` e `MID_CODE_IDENTIFIER` cru. Modo de falha a vigiar em
    qualquer rota que publique um vocabulário: **a lista tem de cobrir todo produtor**, e um teste
    que a prenda aos produtores vale mais que a leitura do código.
11. ✅ **"Aprovar" um merge parecia unificar** — corrigido no ciclo da subtela de stopwords. O
    sintoma relatado foi "o ledger travou em 20 de 41", e o diagnóstico foi outro: o ledger tinha 41
    linhas e as tags continuavam 8.349, com as aprovações de hoje e a última linha do ledger de
    **ontem 20:31**. O dry-run das aprovadas mostrava trabalho real esperando (`trabalhadores`: 19
    documentos, `mapas`: 16). Ou seja: a API está certa (aprovar registra intenção, aplicar escreve) e
    a **tela** não deixava o passo seguinte óbvio. Agora aprovar já seleciona para o lote, um banner
    diz quantas aprovadas ainda não foram unificadas, e há "selecionar todas as aprovadas" — sem
    precisar percorrer cinco páginas marcando caixinhas.
12. ✅ **O parâmetro `scope` de uma rota recebia o request cru** — corrigido no mesmo ciclo. Litestar
    reserva o nome `scope` para o ASGI scope: o handler `GET /tags/stopwords` recebia o dicionário do
    request em vez do valor da query, e o `basedpyright` não tinha como ver isso — **o teste de rota
    pegou**. A chave da query passou a ser `axis`, com o motivo escrito ao lado do parâmetro.
13. ✅ **Aplicar um cluster não tirava a proposta da fila** — corrigido no ciclo seguinte, com o
    relato "dá erro e não sai de aprovadas". O ledger provou que o apply **funcionou**: 92 mesclagens
    escritas às 23:55:25 (41 → 133 linhas, 8.349 → 8.257 tags). O erro era a *segunda* tentativa: os
    membros daqueles 20 já tinham sido absorvidos pela primeira. Duas causas somadas: (a) o status
    ficava `APPROVED` para sempre depois de aplicado, então a fila nunca esvaziava; (b) os membros são
    um *snapshot* sem foreign key, e a tela oferecia um apply que só podia falhar. Agora existe o
    estado `APPLIED` (migração `a1b2c3d4e5f6`, que também **repara** as linhas antigas: 95 propostas
    casadas pelo fingerprint ou pelo nome absorvido no ledger), o DTO traz `members_alive`,
    `canonical_alive` e `applicable` calculados na leitura, e o lote reporta "já aplicado" em
    `skipped` em vez de `failed` — "não havia o que fazer" não é o mesmo que "deu errado".
14. ✅ **`ILIKE` sobre texto digitado não escapava curingas** — corrigido no ciclo da etapa C. Um `%`
    na caixa de busca significava "todos os registros": o acervo respondia 8.349 tags a um typo e a
    consulta abandonava o índice de trigrama. `escape_like()`/`LIKE_ESCAPE` passaram a ser a única
    forma de montar o padrão, com teste que distingue `0%` de "começa com zero" e `a_b` de "a,
    qualquer coisa, b". **A busca do acervo nunca teve esse defeito** porque passa por
    `domain/search.tokenize` (`[^\W_]+`), que descarta `%` e `_` antes do SQL; o que estava exposto
    era o termo **cru** das rotas de type-ahead, criadas neste ciclo — daí o utilitário existir e ser
    o único caminho para montar um padrão.

---

## 📚 Referências

- `AGENTS.md` — convenções e regras arquiteturais fáceis de errar.
- `README.md` — porta de entrada (o que é, como rodar).
- `docs/adr/` — decisões aceitas (Litestar, layout `src/`).
- `.analysis/roadmap-bff-curador.md` — plano do monorepo, BFFs e UI.
- `.analysis/sitemap-front-curador.md` — **sitemap e especificação das telas**.
- `.analysis/adr-arquitetura-alvo.md` — proposta hexagonal por domínio.
- `.analysis/analise-domains.md` · `.analysis/revisao-testes.md` — análises arquiteturais.
