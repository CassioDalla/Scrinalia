# 🗺️ Roadmap & TO-DO — Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não
> apenas lido no código. `[ ]` = pendente. `[~]` = parcial, com o que falta descrito.
>
> **Estado do gate (2026-10-05):** **883 testes** passando · `ruff` limpo · `basedpyright`
> **0 erros** · **22 migrações** aplicando sem drift · contrato OpenAPI gerado e **verificado por
> CI** · SPA do curador construindo (`tsc`, `eslint`, `vite build`).

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança | ✅ **Fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | ✅ **Fechada** — vocabulário reprojetado e medido |
| 2 | API + Curadoria humana (HITL) | ✅ **Fechada no backend**; falta ação local |
| 2.5 | Hierarquia das descrições | ✅ **H1–H8 fechadas sem UI** |
| 3 | Descoberta, performance e observabilidade | 🟡 **Parcial** — busca fechada; falta operação |
| 3.5 | Qualidade do dado de entrada | ✅ **A–E fechadas sem UI** |
| 4 | **UI nova, BFF e publicação** | 🟡 **Em andamento** — contrato fechado e onda 1 do front entregue |

**O sistema está funcionalmente pronto.** Ingestão → staging → archive → enriquecimento por
IA → curadoria humana → bloqueio de reprocessamento, tudo verificado ponta a ponta.

**O que falta é tela.** Todas as feats recentes (hierarquia, assuntos, qualidade, merge
reversível) foram entregues **como API**, sem UI — por decisão, já que o Streamlit será
substituído. O caminho agora é o front do curador.

> **Primeiro ciclo entregue (2026-10-05).** O **contrato** está fechado: as lacunas que a UI
> expunha foram resolvidas, o OpenAPI é um artefato gerado e commitado com CI bloqueante, e a
> **allowlist pública** existe com teste de partição exata. A **onda 1** do front também está de
> pé: início com a fila de trabalho, lista com facetas e dossiê com quatro abas. O que segue
> aberto é a **onda 2** — `/arranjo/plano`, que é a razão de existir deste front.
>
> **Sequenciamento (2026-10-04).** Auth entra **por último**, depois do front novo e
> imediatamente antes de tornar público. Duas UIs (curador + difusão pública) com BFFs
> separados, em monorepo. Planos em `.analysis/roadmap-bff-curador.md` (arquitetura) e
> `.analysis/sitemap-front-curador.md` (telas). Decisão de stack registrada em
> `docs/adr/0003-monorepo-and-curator-frontend-stack.md`.

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
- [~] **B5 — Telas das ondas 1–3.** Onda 1 entregue (`/`, `/acervo/lista`, `/acervo/:id` com as 4
  abas). Ondas 2 e 3 (arranjo, assuntos) pendentes.
- [ ] **B6 — Telas da hierarquia** (ondas 2 e 4 do sitemap).
- [ ] **B7 — Scaffold `apps/public/`** + regras de badge. O BFF público (rotas + projeção) já existe;
  falta o app.
- [ ] **B8 — Desligar o Streamlit** (`src/memoria_curitibana/dashboard/` e o `web` do Procfile).
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

### Achados que a implementação produziu

- ✅ **`GET /conflicts/cross-domain`: 53 s → 1,5 s, mesmo resultado.** Duas causas, medidas e
  corrigidas — ver "Bugs conhecidos" 7 e 8. A análise anterior neste documento estava **errada** ao
  afirmar que o GIN não serve para comparação coluna-a-coluna: ele serve, desde que `%` seja o
  **único** predicado do join.
- **`GET /acervo/lista?term=…` não existe na UI como busca global**; a lista funciona, mas um campo
  de busca dedicado por eixo virá com as telas da onda 3.

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
- [ ] **Aplicar as decisões de merge** — 371 propostas ainda `SUGGESTED` no acervo.

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

- [ ] **A tela** — é o B6 da Fase 4. O catálogo de planos do acervo real está **vazio de
  propósito**: aprovar os ~52 rungs é do arquivista.
- [ ] **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU pede 4 rungs sob o Fundo e a
  escada tem 6. Achado real, a resolver na tela (fundir ou criar nível intermediário).
- [ ] **31 códigos ilegíveis** (`... 10047 (1) 1915`, `... 369B`) — listados, **nunca
  adivinhados**.
- [ ] **18 `LEVEL_DEPTH_MISMATCH`** — 13 Itens em profundidade 6 entre 1.095 Dossiês.

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
- [ ] **Editar tags/entidades de um documento individual pela UI.** Hoje só por rotas globais
  de merge. Vai para `/acervo/:id` aba Assuntos.
- [ ] **Vitrine reflete os enriquecimentos.** `DocumentSummary` ainda não expõe tipologia.

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
- [ ] **Rastreamento de erros nos workers** (ex.: Sentry) para falhas silenciosas de IA.
- [ ] **Health/readiness** (`/health`) verificando o banco.
- [ ] **Retomada e agendamento** — não há scheduler nem retry policy; os workers rodam pelo
  runner manualmente.
- [ ] **Testes de pipeline com engines reais.** A suíte usa `mock_registry` (correto para
  isolamento), o que deixa invisível a classe de bug que quebrou o `suggest-macro`. Falta um
  teste de fumaça opcional marcado `slow`/`e2e`.

---

## 🔧 Pendências operacionais no acervo (não são código)

O código está pronto; **o acervo está intocado**. Descoberto na auditoria de 2026-10-04.

| # | Pendência | Detalhe |
| --- | --- | --- |
| 1 | **Carimbos v1→v2 nunca reprocessados** | O acervo tem `worker_ner_v1`/`worker_typology_classifier_v1` em 3.608 docs; o código filtra `_v2`. O bump é deliberado ("re-read with the clean text"), a releitura **não rodou** — o ganho medido (Hit@10 0.562 → 0.625) **não está nos dados** |
| 2 | **Regra de limpeza de teste ativa** | `ArchiveCleaningRule` `rule_id=1` "aaaaa" (`REWRITE`, regex `\bpalavra\b` sobre `original_title`). **Verificado em 2026-10-05: não casou com nada** — 0 ocorrências em staging e em archive, só o carimbo `cleaning_rule_1`. Desativar é higiene, não há texto a desfazer |
| 3 | **5.446 tags órfãs de assunto** | de 6.142 — a maioria porque o worker rodou com o vocabulário antigo |
| 4 | **0 de 52 rungs decididos** | a árvore existe no código e não no acervo |
| 5 | **371 propostas de merge pendentes** | 40 já aprovadas (aplicadas em lote) e 0 rejeitadas |
| 6 | **0 revisões humanas** | relevante para a decisão B2 (predicado de publicação) |
| 7 | **`domain_text_templates` e `domain_ner_exclusions` vazios** | as duas feats estão implementadas e sem uso no acervo |

> **Decisão de produto pendente:** rodar os workers (itens 1 e 3) **antes ou depois** do front?
> Enquanto não rodarem, a UI mostra menos do que o sistema sabe fazer.

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
4. **O acervo está desatualizado em relação ao código** — carimbos v1→v2 e regra de teste
   ativa. São operações, não código (ver "Pendências operacionais").
5. **`path` desnormalizado** pode divergir — teste de invariante no CI (`PATH_DIVERGENCE` = 0
   hoje, mas a garantia precisa ser automática).
6. **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU não cabe na escada de 6 níveis
   sem repetir um ordinal. Achado real, a resolver na tela.
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
9. **`access_conditions` existia no staging e não no archive** — corrigido neste ciclo; fica
   registrado porque o modo de falha (campo parseado, coluna ausente, nenhum erro) pode se repetir
   em qualquer campo novo do ISAD(G).

---

## 📚 Referências

- `AGENTS.md` — convenções e regras arquiteturais fáceis de errar.
- `README.md` — porta de entrada (o que é, como rodar).
- `docs/adr/` — decisões aceitas (Litestar, layout `src/`).
- `.analysis/roadmap-bff-curador.md` — plano do monorepo, BFFs e UI.
- `.analysis/sitemap-front-curador.md` — **sitemap e especificação das telas**.
- `.analysis/adr-arquitetura-alvo.md` — proposta hexagonal por domínio.
- `.analysis/analise-domains.md` · `.analysis/revisao-testes.md` — análises arquiteturais.
