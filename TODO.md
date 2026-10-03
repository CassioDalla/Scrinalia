# 🗺️ Roadmap & TO-DO: Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento do sistema de curadoria e enriquecimento de acervo
arquivístico (DDD + micro-workers + HITL).

> **Como ler este documento.** Cada item marcado `[x]` foi **verificado em execução real**
> (Postgres + engines de verdade), não apenas lido no código. Os itens `[ ]` são trabalho
> pendente. Quando um item está parcialmente pronto, ele aparece como `[~]` com a descrição
> explícita do que existe e do que falta.
>
> **Estado do gate de qualidade:** suíte **270 testes** passando (unit + integração),
> `ruff check`/`ruff format --check` limpos, `basedpyright` 0 erros,
> `alembic upgrade head` + `alembic check` sem drift.

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança de base | **Praticamente fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | **Núcleo fechado** — resta o front e o defeito de rótulo |
| 2 | API + Curadoria humana (HITL) | **Fechada no essencial**, faltam ações locais |
| 3 | Descoberta, escala e observabilidade | **Parcial** — busca é o maior buraco |
| 4 | Interoperabilidade, agentes e publicação | Não iniciada |

O sistema **funciona ponta a ponta** até a camada Archive: ingestão → staging → archive →
enriquecimento por IA → curadoria humana → bloqueio de reprocessamento. O que falta não é
"fazer funcionar", é **fechar os eixos semânticos** (macro categorias, ancoragem
tag↔entidade) e **tornar o acervo pesquisável de verdade**.

---

## 🟢 Fase 1 — Fundação e Core Pipeline de IA

### Camadas e modelagem

- [x] **Camadas Ingestion & Staging:** extração, limpeza e controle de linhagem (Hash CDC).
  Verificado: `raw_data` → `run_staging_pipeline` converte payload cru em colunas ISAD(G)
  tipadas, parseia datas (`15/03/1954` → `1954-03-15`, `1972-05-10`) e normaliza
  `pontos de acesso` em tags. Documentos não mapeados caem em `raw_metadata` (zero perda).
- [x] **Camada Archive:** modelagem, schemas Pydantic estritos, trava de idempotência
  (`execution_log` JSONB) e índice GIN `ix_archive_exec_log`.
- [x] **Infraestrutura de Testes:** Pytest com savepoints, isolamento transacional,
  marcação automática `unit`/`integration` por caminho.
- [x] **Migrações:** Alembic é dona do schema; `pg_trgm` criado na migração inicial;
  `alembic check` sem drift.

### Workers de enriquecimento

- [x] **Worker de Transferência** (`transfer`): carga staging→archive, limpeza de taxonomia
  via `TagService`, inicialização do `execution_log`.
- [x] **Worker NER** (`ner`): extração LOC/PER/ORG via spaCy `pt_core_news_lg`, EntityRuler
  dinâmico alimentado pelo banco, filtros de Data Quality e blacklist de stopwords.
- [x] **Worker Thumbnail** (`thumbnail`): download resiliente, conversão para JPEG,
  upload para Object Storage com carimbo de falha (`thumbnail_failed`) para não reprocessar.
- [x] **Worker Typology** (`typology`): classificação zero-shot com mDeBERTa
  (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`) contra as tipologias ativas do banco,
  com limiar de confiança configurável.
- [x] **Worker Cleaning** (`cleaning`): aplica regras Regex dinâmicas criadas pelos
  curadores, com carimbo por regra (`cleaning_rule_{id}`).
- [x] **Worker Juiz de Conflito** (`conflict-judge`): LLM local (Ollama) decide se um termo
  ambíguo é TAG ou ENTITY, com resolução automática acima do limiar e fila de revisão abaixo.
- [x] **Runner unificado** (`workers/runner.py`) com descoberta por assinatura, `--engine`,
  `--preset`, `--batch` e `--option key=value`.

### Governança (Human-in-the-Loop)

- [x] **Bloqueio de reescrita por IA:** `ai_writable_documents()` exclui `HUMAN_APPROVED`
  e `REJECTED`. Verificado nos **6 workers** (transfer, cleaning, ner, typology, thumbnail,
  conflict-judge) — nenhum worker escreve sobre documento aprovado por humano.
- [x] **Fila de revisão da IA:** `archive_ai_review_queue` com `AnomalyType`,
  decisão/confiança/justificativa do LLM e payload de contexto em JSONB.
- [x] **Anti-rework do juiz:** o worker verifica `context_payload.contains(...)` antes de
  reconsultar o LLM para o mesmo par (tag, entidade).

### ⚠️ Lacunas reais da Fase 1

- [ ] **Ancoragem negativa "isto é TAG, não entidade" não existe.**
  É o buraco mais importante da fase. O ciclo de correção do NER **funciona**, mas só em
  uma direção:
  - ✅ `reclassify_entity` grava um sinônimo de ancoragem → `get_ner_synonyms_rules` injeta
    no EntityRuler → o spaCy passa a extrair com o rótulo corrigido. Verificado ponta a ponta
    (entidade `prefeiruta` PER→ORG, regra criada, o engine passou a extrair `ORG`).
  - ❌ Quando o **juiz LLM decide que o vencedor é a TAG** (`iptu`), o entity é apagado mas
    **nenhuma regra de bloqueio é gravada**. O termo não fica marcado como "não é entidade";
    a única rede é o blacklist global de `DomainStopwords`.
  - ❌ O `CheckConstraint chk_exclusive_synonym_target` **impede representar** um sinônimo
    de TAG que aponte para uma entidade: `category='TAG'` exige `canonical_tag_id` e proíbe
    `canonical_entity_id`. E `get_ner_synonyms_rules` filtra `category IN ('ORG','LOC','PER')`,
    então sinônimos de TAG **nunca** chegam ao NER.
  - **Impacto:** a decisão humana/LLM "isto é assunto, não nome próprio" não é durável em
    nível de termo. Sem uma entidade-alvo vigilante, a partir de amanhã o NER recria o falso
    positivo e o conflito volta para a fila de revisão.
  - **Direção sugerida:** um catálogo explícito de termos vetados para NER (distinto do
    blacklist genérico de stopwords), alimentado pelo juiz e pela reclassificação humana.
- [ ] **`ai_confidence_score` da Tag nunca é escrito.** ~~A coluna existe na model e é exposta
  no schema, mas nenhum worker a preenche (o `transfer` sempre grava `None`).~~ **Resolvido:**
  o `worker_macro_category` passou a preenchê-la (ver Fase 1.5).
- [ ] **`is_anomaly` / `anomaly_reasons` do documento nunca são preenchidos.** Modelados,
  indexados, e sem nenhum produtor.
- [x] **`worker_macro_category.py` existe.** Ver Fase 1.5 — fechado.

---

## 🔵 Fase 1.5 — Macro Categorias (eixo de Assuntos) — **PRIORIDADE**

O eixo semântico de assuntos está modelado e pela metade implementado. Hoje a IA **sugere**
"gavetas" mas nada as consome.

> **Sessão de 2026-10-03:** o núcleo do eixo foi fechado (sugestão → cadastro humano → worker →
> payload). A UI do Streamlit ficou de fora por decisão explícita, já que o front será
> substituído. Restam os itens de front-end e o defeito de rótulo descrito no fim da seção.

### Banco de dados

- [x] **Model `ArchiveMacroCategory`:** `category_id`, `name` (unique), `description`,
  `is_active`, `created_at`, relationship `tags`.
- [x] **FK em `ArchiveTag`:** `macro_category_id` com `ondelete="SET NULL"` + índice.
- [x] **`ai_confidence_score` em `ArchiveTag`:** tem produtor (o `worker_macro_category`).
- [x] **`execution_log` JSONB em `ArchiveTag`** + índice GIN `ix_archive_tags_exec_log`
  (migração `b7f1c2d4e9a0`). A tag ganhou ledger de idempotência próprio: `WorkerStamp`
  opera sobre `ArchiveDocument.execution_log`, e `archive_tags` não tinha equivalente.

### Descoberta de categorias (BERTopic)

- [x] **Engine de clustering:** `BERTopicEngine` com presets `exploratory_fine` e
  `exploratory_macro`, analyzer lematizado via spaCy + stopwords do domínio.
- [x] **Helper de coleta:** `TagRepository.fetch_tags_for_clustering()` busca apenas tags
  com `macro_category_id IS NULL` (as "órfãs").
- [x] **Endpoint:** `POST /api/v1/taxonomy/tags/suggest-macro` (`source_type`: tags|documents).
- [x] **BUG corrigido — o endpoint quebrava no preset padrão.**
  Verificado com 41 tags reais: com o `min_topic_size` fixo de 15 o engine estourava
  `Found array with 0 sample(s) (shape=(0, 384))` e devolvia `422 EngineExecutionError`.
  - **Correção:** `min_topic_size` passou a ser dimensionado pelo corpus
    (`max(2, min(ceiling_do_preset, len // 10))`) e o preset virou **intenção, não
    configuração rígida**: se o macro não formar cluster, há uma retentativa com
    `exploratory_fine`. Corpus que não clusteriza nenhuma vez devolve
    `total_suggestions=0` com mensagem, **nunca 422**.
  - **Verificado com engine real:** 41 tags → `min_topic_size=4` → 3 clusters coerentes
    ("Lei - Urbanização - Transporte", "Legislação - Livre - Portario",
    "Saúde - Sanitário - Pôr"). Corpus de 6 tags → resposta vazia com mensagem, sem exceção.
  - **Importante:** apenas `ValueError` de configuração (engine/preset inexistente) ainda
    vira `EngineExecutionError`. Erro de configuração não é mascarado como "sem dados".
- [x] **Guard de volume reflete a restrição real do modelo:** a rota deixou de usar o `10`
  arbitrário e passou a ler `MIN_TEXTS_TO_CLUSTER` (5) do próprio worker, então a API não
  pode divergir do engine.
- [x] **Ação humana de cadastro:** rotas `POST/GET/PATCH /api/v1/taxonomy/macro-categories`
  (cadastrar, listar com `only_active`, renomear/re-descrever/(des)ativar).
  Sem `DELETE`: desativar basta e a FK já é `SET NULL`. É o pré-requisito do worker — sem
  categoria cadastrada não há contra o que classificar.

### Classificação de tags

- [x] **`worker_macro_category.py` EXISTE** (`macro-category` no runner, último do
  `PIPELINE_ORDER`):
  - [x] Loop em lotes sobre tags órfãs (`macro_category_id IS NULL`), com **cursor por
    `tag_id`**: um `force` que ressuscita órfãs carimbadas continua sendo finito.
  - [x] `get_engine("deberta_typology", preset=...)` classificando o nome da tag contra as
    macro categorias ativas.
  - [x] Persiste `macro_category_id` + `ai_confidence_score` **na própria Tag**.
  - [x] Carimbo de idempotência por tag (`MACRO_CATEGORY` = `worker_macro_category_v1`).
  - [x] `try/except` com `db.rollback()` e `db.expunge_all()`.
  - [x] **`ai_confidence_score` é gravado mesmo abaixo do limiar** (0.40, igual ao de
    tipologia): o "quase acerto" fica observável em vez de invisível.
  - [x] **`force=True` via `--option force=true`:** uma tag carimbada mas órfã (o curador
    cadastrou a categoria que faltava depois) pode ser reclassificada.
- [x] **Registrado no `runner.py`** (`WORKERS` + `PIPELINE_ORDER`).
- [ ] **Considerar multi-label (Sigmoid) em vez de Softmax.** Decisão desta sessão foi
  single-label (usa a FK existente, zero migração). Multi-label exige tabela de junção.
  **Não fazer antes de resolver o defeito de rótulo abaixo.**

### ✅ Defeito de rótulo — **corrigido**

- [x] **Rótulo `"Nome: descrição"` fazia o mDeBERTa colapsar tudo na primeira categoria.**
  Achado durante a verificação ponta a ponta com engine real e **corrigido**:
  - **Causa raiz (medida, não suposta):** não era plumbing nem ordem de lista — o modelo
    perde progressivamente o entailment conforme o rótulo cresce. Degradação gradual, e por
    isso uma confiança alta não denuncia o erro:

    | Descrição no rótulo | `epidemia de dengue` | Confiança |
    | --- | --- | --- |
    | sem descrição | **Saúde** ✅ | 0.99 |
    | 1 palavra | **Saúde** ✅ | 0.99 |
    | 2 palavras | **Saúde** ✅ | 0.90 |
    | 4 palavras | **Saúde** ✅ | 0.62 |
    | descrição longa | **Urbanismo** ❌ | 0.98 |

  - **Correção:** os rótulos enviados ao engine passaram a ser o **nome nu**
    (`get_active_macro_categories` e `get_active_typologies`).
  - **`hypothesis_template` foi testado e descartado como canal:** com rótulos descritivos,
    o template recomendado pelo model card *piora* o resultado (0.73 → 0.81 para o lado
    errado). Não levar a descrição para o template.
  - **A descrição permanece no schema** como documentação da gaveta para o curador, com o
    motivo da exclusão registrado no docstring — para ninguém reintroduzir a concatenação.
  - **Verificado com engine real:** macro categorias 4/4 corretas (era 0/4 no mesmo cenário),
    tipologia 2/2, votos corretos no `DocumentSummary`.
  - **Guardas de regressão:** 6 testes falham se a concatenação voltar (repositório, payload
    do worker e unitário) — verificado reintroduzindo o bug de propósito.

### API e payload

- [x] **Voto majoritário no backend:** `DocumentRepository` conta quantas tags do documento
  pertencem a cada categoria, ordenado por contagem (desempate por nome).
- [x] **`DocumentSummary` enriquecido** com `macro_categories: [{category_id, name, tag_count}]`.
- [x] **JOIN das tags com suas macro categorias** nos 3 pontos de leitura (`search`,
  `get_by_id`, `update_review`) via `selectinload(...).selectinload(ArchiveTag.macro_category)`
  — sem N+1. O voto é **derivado na leitura**: editar uma tag reflete em todos os documentos
  atrelados **sem escrever na tabela de documentos** (verificado por teste de `updated_at`).

### Front-end (regras de badge) — **não iniciado**

- [ ] **Renderização padrão:** sem filtro ativo, exibir a categoria vencedora `[0]` + contador
  de secundárias (`[ 🏙️ Urbanismo ] [+1]`).
- [ ] **Relevância contextual:** com filtro ativo por "Legislação", se o documento contiver
  essa categoria no array, exibi-la no topo ignorando o vencedor por votos.
- [ ] **Aba macro do Streamlit:** hoje é um `st.info("aguardando embeddings")`. O caminho
  "analisar cluster → cadastrar categoria" já existe na API; falta a tela. Decidir se vale
  investir no Streamlit ou levar direto para o front novo.

### Testes

- [x] Repositório: atualizar uma Tag reflete em todos os documentos atrelados **sem** tocar
  na tabela de documentos.
- [x] Worker: `mock_registry` validando batch size, persistência dos IDs corretos, limiar,
  `force`, ausência de categorias e rollback em OOM.
- [x] Worker: engine real (`deberta_typology`) contra Postgres real, ponta a ponta.

---

## 🟡 Fase 2 — APIs e Governança (Human-in-the-Loop)

### Camada de API (Litestar)

- [x] **Roteamento RESTful DDD:** controllers em `api/controllers/` (`Taxonomy`, `Documents`,
  `Data Quality`), serviços por domínio.
- [x] **Leitura:** listagem paginada do acervo, busca textual, detalhe com tags e entidades.
- [x] **Escrita:** aprovação humana (`PATCH /documents/{id}`) que muda o status para
  `HUMAN_APPROVED` e blinda o documento.
- [x] **Composição por request:** `provide_unit_of_work` (`api/dependencies.py`) dono da
  transação — commit no sucesso, rollback na exceção.
- [x] **Erros de domínio:** handler global para `DomainException` + `IntegrityError`.
- [x] **Anotações explícitas** de parâmetros Litestar (`NamedDependency`, `FromPath`,
  `FromQuery`) e `sync_to_thread` em todas as rotas — pronto para Litestar 3.0.
- Decisão registrada em [`docs/adr/0001-litestar-as-http-framework.md`](docs/adr/0001-litestar-as-http-framework.md).

### Serviços de Taxonomia

- [x] **`TagService`:** relevância (TF-IDF e contagem), similaridade fuzzy via `pg_trgm`,
  merge com transferência de vínculos, sinônimos de ancoragem, stopwords, purge.
- [x] **`EntityService`:** relevância, similaridade, merge, reclassificação com ancoragem,
  purga de órfãs, blacklist de falsos positivos, resolução de conflito entre domínios.
- [x] **`DocumentService`:** busca, detalhe e revisão humana.
- [x] **`CleaningService`:** CRUD de regras + dry-run (simulação de impacto antes de salvar).

### Painel de Curadoria (Streamlit — **temporário**)

- [x] **5 páginas funcionais**, todas consumindo a API por HTTP (nunca Postgres direto):
  Vitrine de Busca, Tags e Assuntos, Entidades Nomeadas, Conflitos de Domínio,
  Qualidade de Dados.
- [x] **Ação Global:** mesclagem de tags e entidades, reclassificação, blacklist,
  resolução de conflitos.
- [~] **Ação Local no documento:** `PATCH` existe e funciona (verificado: `final_title` +
  `archivist_notes` → `HUMAN_APPROVED`), mas aceita **apenas 3 campos**
  (`final_title`, `scope_content`, `archivist_notes`).
- [ ] **Editar tags/entidades de um documento individual pela UI.** Hoje só é possível por
  rotas globais de merge, não no contexto do documento.
- [ ] **Confirmar que a Vitrine reflete os enriquecimentos.** O `DocumentSummary` expõe
  macro categorias desde a sessão de 2026-10-03, mas **ainda não expõe a tipologia** — a
  vitrine segue sem mostrar todo o resultado da IA.

---

## 🟠 Fase 3 — Descoberta, Performance e Observabilidade

### Motor de Busca

- [~] **Busca textual:** `DocumentRepository.search()` faz `ILIKE '%termo%'` em
  `original_title`, `final_title` e `scope_content`. Funciona e tem paginação, mas é
  *contains* sem ranking, sem stemming, sem índice de texto — não escala.
- [ ] **Full-Text Search nativo (PostgreSQL):**
  - [ ] Preencher `semantic_search_vector`. **A coluna existe e nunca é escrita** —
    hoje é `None` em todos os documentos.
  - [ ] Coluna `tsvector` + índice GIN com dicionário `portuguese`.
  - [ ] Trocar o `ILIKE` por `@@` com ranking (`ts_rank`).
- [ ] **Busca em tags e entidades:** hoje a busca cobre só 3 colunas do documento. As ~40
  tags e as entidades não entram na busca.
- [ ] **Busca semântica (pgvector):** embeddings + similaridade de conceito
  ("desastres naturais" encontrar "enchentes"). Requer trocar a imagem para
  `pgvector/pgvector` e adicionar a extensão via migração.
- [ ] **Filtros facetados:** por tipologia, macro categoria, tipo de entidade, década.

### Qualidade de dados

- [x] **Lei de normalização de tags:** separadores `,` e `|`, stopwords por escopo
  (TAG/ENTITY/ALL), rejeição de tags muito curtas/longas, normalização lowercase+trim.
- [ ] **Lematização de tags (não implementada).** `normalize_tag()` é apenas
  `strip().lower()`. Consequência verificada: "parque"/"parques" e
  "lei municipal"/"leis municipais" permanecem entradas distintas.
  - O spaCy **já está** no projeto e o lematizador **já funciona** (é usado no BERTopic
    via `entity.lemmatize`), só não é aplicado na ingestão de tags.
  - [ ] Aplicar lematização em `extract_and_clean_tags`, com cuidado para não destruir
    termos técnicos e nomes próprios.
  - [ ] Aplicar **nas tags soltas**, nunca no texto do documento que vai para a IA.
- [ ] **Deduplicação automática por trigramas:** o `pg_trgm` já está instalado e a rota
  `/tags/similar` já encontra pares (verificado: `prefeitura` × `prefeiruta` = 0.375).
  Falta o passo de agrupar e sugerir merges em lote.

### Observabilidade e operação

- [x] **CI:** GitHub Actions roda ruff + basedpyright + `alembic check` + pytest em Postgres.
- [x] **Logging:** loguru com sinks por nível, interceptação de logs de terceiros
  (uvicorn/Litestar) e `InterceptHandler`.
- [ ] **Rastreamento de erros nos workers** (ex.: Sentry) para capturar falhas silenciosas
  de IA em produção.
- [ ] **Health/readiness endpoint** (`/health`) verificando o banco.
- [ ] **Retomada e agendamento:** não há scheduler nem retry policy para os workers; hoje
  são executados manualmente pelo runner.
- [ ] **Testes de pipeline com engines reais.** A suíte usa `mock_registry` (correto para
  isolamento), mas isso deixa invisível a classe de bug que quebrou o `suggest-macro`.
  Precisa de um teste de fumaça opcional marcado como `slow`/`e2e`.

---

## 🔴 Fase 4 — Interoperabilidade e Publicação (v2.0)

### Autenticação e exposição pública — **última etapa antes de trocar o front**

> Decisão de sequenciamento: auth entra **depois** da troca de front-end, imediatamente antes
> de tornar o sistema público. Não é bloqueio para as fases 1.5–3.

- [ ] **Autenticação e autorização.** Hoje **não existe nenhuma**: sem auth, sem CORS, sem
  rate limit. Qualquer cliente alcança rotas que aprovam documentos e fundem taxonomia.
- [ ] **Trilha de auditoria por usuário.** `ArchiveCleaningRule.created_by` e o
  `PATCH /documents` não registram quem fez o quê.
- [ ] **CORS / headers de segurança / rate limit.**
- [ ] **Migrar do Streamlit para back-end + React.** O Streamlit é declaradamente temporário;
  a API é o contrato estável. Manter as regras de badge (Fase 1.5) no novo front.

### Interoperabilidade

- [~] **Sistema de Adapters (Plugins de Ingestão):** as ABCs `IDiscoveryAdapter` e
  `IDetailAdapter` **já existem** e o `PMCScraperAdapter` as implementa com tradução de
  erros HTTP/HTML em exceções de domínio. Falta:
  - [ ] Registro/descoberta dinâmica de adapters (hoje é instanciação direta no `__main__`).
  - [ ] Configuração por instituição (como um novo adapter é plugado sem alterar o core).
  - [ ] Segundo adapter real para provar que a abstração se sustenta.
- [ ] **Worker de Visão Computacional (OCR/VLM):** extrair texto de imagens históricas no
  MinIO e injetar na tabela fato.
- [ ] **Chatbot Arquivista (RAG):** conversar com o acervo cruzando entidades, tags e
  macro categorias com o LLM.
- [ ] **Exportação para Preservação (OAIS):** empacotamento de DIPs para sistemas de guarda
  permanente (ex.: Archivematica).

---

## ✅ Verificação executada (evidências)

Tudo abaixo foi executado contra Postgres real + engines reais, não apenas inspecionado:

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **270 passed** |
| `ruff check` / `ruff format --check` | limpos (180 arquivos) |
| `basedpyright` | **0 errors, 0 warnings** |
| `alembic upgrade head` + `alembic check` | aplica; **sem drift** |
| `raw_data` → `run_staging_pipeline` | 2/2 docs; datas e ISAD(G) corretos |
| worker `transfer` | 2 docs, 7 tags vinculadas |
| worker `ner` (spaCy real) | entidades extraídas e vinculadas |
| worker `typology` (mDeBERTa real) | classificou e carimbou; **2/2 corretas** após corrigir o rótulo |
| worker `macro-category` (mDeBERTa real) | **4/4 categorias corretas** após corrigir o rótulo (antes: 0/4) |
| `HUMAN_APPROVED` bloqueia IA | confirmado — o worker de tipologia ignorou o doc aprovado |
| `reclassify_entity` → EntityRuler | PER→ORG propagou para o NER (ciclo completo) |
| `POST /tags/suggest-macro` | **corrigido**: 41 tags → 3 clusters; 6 tags → vazio com mensagem |
| Voto majoritário no `DocumentSummary` | derivado na leitura; editar tag **não** escreve em `archive_documents` |
| Leitura/escrita via HTTP | listagem, busca, detalhe, merge, cleaning, conflitos: OK |

### Bugs conhecidos e abertos

1. **Ancoragem "isto é TAG" não existe** — o juiz LLM apaga a entidade sem gravar bloqueio
   durável — Fase 1.
2. **Lematização de tags ausente** — duplicação na origem — Fase 3.
3. **`semantic_search_vector` nunca preenchido** — a busca híbrida prometida não existe — Fase 3.
4. **`is_anomaly`, `anomaly_reasons` sem produtor** — colunas mortas.
5. **Sem autenticação** — bloqueio para exposição pública — Fase 4.

> **Corrigido em 2026-10-03:** o rótulo `"Nome: descrição"` colapsava o mDeBERTa na
> primeira categoria, em `worker_macro_category` **e** `worker_typology`. Classificação
> agora usa o nome nu; ver Fase 1.5 para a medição que isolou a causa.
