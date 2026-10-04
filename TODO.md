# 🗺️ Roadmap & TO-DO: Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento do sistema de curadoria e enriquecimento de acervo
arquivístico (DDD + micro-workers + HITL).

> **Como ler este documento.** Cada item marcado `[x]` foi **verificado em execução real**
> (Postgres + engines de verdade), não apenas lido no código. Os itens `[ ]` são trabalho
> pendente. Quando um item está parcialmente pronto, ele aparece como `[~]` com a descrição
> explícita do que existe e do que falta.
>
> **Estado do gate de qualidade:** suíte **343 testes** passando (unit + integração),
> `ruff check`/`ruff format --check` limpos, `basedpyright` 0 erros,
> `alembic upgrade head` + `alembic check` sem drift.

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança de base | **Praticamente fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | **Núcleo fechado** — resta o front e o defeito de rótulo |
| 2 | API + Curadoria humana (HITL) | **Fechada no essencial**, faltam ações locais |
| 3 | Descoberta, escala e observabilidade | **Parcial** — busca lexical fechada; semântica funciona mas com qualidade fraca; faltam lematização de tags e operação |
| **3.5** | **Qualidade do dado de entrada** | **PRIORIDADE MÁXIMA — planejada, não iniciada** (ver abaixo) |
| 4 | Interoperabilidade, agentes e publicação | Não iniciada |

O sistema **funciona ponta a ponta** até a camada Archive: ingestão → staging → archive →
enriquecimento por IA → curadoria humana → bloqueio de reprocessamento. O que falta não é
"fazer funcionar", é **arrumar o dado de entrada** — que é a razão de o sistema existir —,
**fechar os eixos semânticos** (macro categorias, ancoragem tag↔entidade) e **tornar o acervo
pesquisável de verdade**.

> **Correção de rota (2026-10-03, decisão do dono do produto).** A busca semântica fechou
> ponta a ponta e mesmo assim não serve ao usuário; medido, o gargalo é o **dado de origem**
> (53% do acervo compartilha o mesmo bloco de escopo, 99,8% tem a mesma proveniência, 53% não
> tem data). A prioridade passou a ser a **Fase 3.5**, e o princípio é explícito: **a máquina
> identifica e propõe; o arquivista decide.** Nada é apagado ou reescrito sem decisão humana
> registrada.

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

- [x] **Ancoragem negativa "isto é TAG, não entidade" — FECHADA (Buraco 2).**
  O ciclo de correção agora funciona nas **duas** direções:
  - ✅ `reclassify_entity` grava um sinônimo de ancoragem → `get_ner_synonyms_rules` injeta
    no EntityRuler → o spaCy passa a extrair com o rótulo corrigido. Verificado ponta a ponta
    (entidade `prefeiruta` PER→ORG, regra criada, o engine passou a extrair `ORG`).
  - ✅ **Quando o juiz LLM (ou o curador) decide que o vencedor é a TAG, a decisão fica
    durável**: o termo entra no catálogo `domain_ner_exclusions` com motivo, autor
    (`JUDGE`/`HUMAN`) e a tag que o justifica. O NER deixa de recriar o falso positivo.
  - ✅ **Antes o mecanismo existia pela metade e com efeito colateral:** o
    `resolve_cross_domain_conflict` gravava um `DomainStopwords(ENTITY)`, indistinguível do
    lixo genérico, sem motivo nem vínculo, e — pior — `TagRepository.get_stopwords()` lia
    **todos** os escopos, então a ação "purgar stopwords" do eixo de Tags **apagava a tag
    vencedora** (`iptu`), exatamente o oposto da decisão registrada.
  - ✅ **Achado da verificação com engine real:** o spaCy funde tokens vizinhos e devolve
    `"IPTU do Batel"` como **uma** entidade. Comparar o nome inteiro contra o blacklist
    deixava o falso positivo passar — o filtro passou a casar por **limite de token**
    (`is_blocked_entity_name`), bloqueando `"iptu do batel"` sem tocar em `"iptuana"`.
    Nenhum teste com `mock_registry` pegaria isso: o mock devolve o nome exato que recebeu.
  - ✅ **O sinônimo positivo também não fura o veto:** `get_ner_synonyms_rules` exclui
    spellings vetados, senão o EntityRuler reintroduziria o termo via `ent_id_`.
- [ ] **`is_anomaly` / `anomaly_reasons` do documento nunca são preenchidos.** Modelados,
  indexados, e sem nenhum produtor.
- [x] **`ai_confidence_score` da Tag nunca é escrito.** ~~A coluna existe na model e é exposta
  no schema, mas nenhum worker a preenche (o `transfer` sempre grava `None`).~~ **Resolvido:**
  o `worker_macro_category` passou a preenchê-la (ver Fase 1.5).
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

> **Sessão de 2026-10-03 (Buraco 3):** a busca deixou de ser `ILIKE` e passou a ser
> full-text nativa com ranking, alcançando tags e entidades e com filtros facetados.
> Ver a evidência no fim do documento.

- [x] **Busca textual com ranking:** `DocumentRepository.search()` deixou o
  `ILIKE '%termo%'` e passou a usar `search_vector @@ to_tsquery(...)` com
  `ts_rank`. Ordenação: relevância, depois `updated_at` e `description_id`
  (paginação estável).
- [x] **Full-Text Search nativo (PostgreSQL):**
  - [x] **Coluna morta resolvida por remoção:** `semantic_search_vector` (Text, sempre
    `None`) foi **dropada** na migração `d4e7a1c9f3b2`. O roadmap §3 manda escolher entre
    dar produtor ao campo ou tirá-lo do schema — não havia produtor honesto, então saiu.
  - [x] **`search_vector tsvector` GERADO (STORED) + índice GIN** com dicionário
    `portuguese`. Por ser coluna gerada pelo Postgres, é sempre consistente com o texto,
    inclusive depois de edição humana (`update_review`) — sem worker e sem carimbo.
  - [x] **Título pesa mais que corpo:** `setweight(..., 'A')` em
    `final_title`/`original_title` e `'B'` em `scope_content`/`admin_bio_history`/`provenance`.
  - [x] **Acento-insensível:** o dicionário `portuguese` sozinho **não** é confiável
    (`gaucho` não achava `Gaúcho`; medido). Entrou `unaccent` + wrapper
    `immutable_unaccent` (`unaccent(regdictionary,text)` é STABLE e não pode ir em coluna
    gerada). Ganho medido no acervo real: `historica` → **0** no ILIKE antigo, **2489** agora.
  - [x] **Prefixo do último token** (`matad:*`): busca enquanto se digita, com o
    `to_tsquery` aplicando o mesmo stemming do vetor.
  - [x] **Fallback de substring** para fragmento no meio da palavra, que o FTS não vê:
    só roda quando a busca ranqueada (FTS + tags + entidades) não acha **nada**, para não
    varrer a tabela em toda busca.
- [x] **Busca em tags e entidades:** a busca cobre `archive_tags.name` e
  `archive_entities.name` por `EXISTS` + `ILIKE` (acelerado pelos índices `gin_trgm_ops`
  que já existiam). `EXISTS` evita duplicar documento com várias tags que casam e evita
  contar duas vezes no `total`. Casamento por taxonomia entra no ranking com bônus.
- [x] **Filtros facetados:** `typology_id`, `macro_category_id` (qualquer tag da gaveta),
  `entity_type` (LOC/PER/ORG) e `date_from`/`date_to`. As facetas valem para a página e
  para o `total`.
- [x] **`rank` exposto no `DocumentSummary`** (relevância), para o front explicar a ordem.
- [x] **Busca semântica (pgvector) — IMPLEMENTADA.** `mode=semantic` na listagem busca por
  conceito em vez de por palavra:
  - [x] **Infra:** imagem própria `docker/postgres/Dockerfile` (`pgvector/pgvector:pg15` +
    PostGIS 3.6). O `postgis/postgis` oficial ainda é Debian 11 (bullseye), cujo repositório
    PGDG foi aposentado — nem `apt-get update` funciona. PostGIS fica **instalado e não
    habilitado**: o mapa por bairro/pin é trabalho futuro e uma migração de uma linha o liga.
  - [x] **Migração `e7b2c4a91d38`:** extensão `vector`, coluna `ArchiveDocument.embedding`
    `vector(384)` e índice **HNSW** (`vector_cosine_ops`). HNSW e não IVFFlat porque não exige
    treino e mantém recall conforme o acervo cresce. O tipo `Vector` é local
    (`core/types.py`) — mapear a coluna é tudo que o projeto precisa, sem trazer o pacote
    `pgvector`. A dimensão é guardada por teste (`EMBEDDING_DIMENSIONS` × preset do engine).
  - [x] **Engine plugável** `engines/embeddings/` (`sentence_transformer`, preset
    `multilingual_minilm` = `paraphrase-multilingual-MiniLM-L12-v2`, 384 dims), reusando o
    modelo que o BERTopic já usava. Import pesado só na construção.
  - [x] **Worker `embedding`** (último do `PIPELINE_ORDER`, roda depois de todo texto mutado).
    O carimbo é o **MD5 do texto embedado**, calculado pelo Postgres (`WorkerStamp.mark_value`),
    e não um status: o predicado de pendência vira uma comparação SQL única que cobre a
    primeira execução **e** qualquer mudança posterior de texto.
  - [x] **Exceção de governança documentada:** é o único worker que **não** aplica
    `ai_writable_documents()`. O embedding é índice derivado do texto, não conteúdo
    arquivístico: se o humano edita um documento `HUMAN_APPROVED`, o vetor precisa ser
    refeito, senão a busca semântica serve dado obsoleto. Ele escreve **apenas** a coluna
    `embedding` e o próprio carimbo; `REJECTED` é ignorado.
  - [x] **Busca:** o termo é embedado no **serviço** (não no repositório) via fábrica de
    engine injetada e **cacheada por processo** — uma busca lexical não carrega o modelo.
    Facetas continuam valendo; `rank` passa a ser a similaridade de cosseno.
  - [x] **Verificado no acervo real:** worker com o modelo de verdade embedou **3608/3608**
    documentos em ~1 min (CPU), 0 pendentes depois, 384 dims em todos, e
    `cos(guardado, recalculado) = 1.0` com o `<=>` do Postgres batendo exatamente.
  - [ ] ⚠️ **Qualidade semântica medida é FRACA — próximo passo obrigatório.** Com o acervo
    real, "enchentes" dá no máximo **0.33** para "Enchente em região marginalizada" e o topo
    da busca por "desastres naturais" são documentos de *acidente de trânsito*.
    **Não é bug de armazenamento** (verificado acima) nem falta de modelo maior: o
    `paraphrase-multilingual-mpnet-base-v2` (768 dims) foi medido no mesmo corpus e
    discrimina **pior** (0.265 vs 0.361). Causa provável: o texto embedado é curto/genérico
    (título + um bloco de escopo repetido em milhares de itens), então falta sinal.
    Ver `.analysis/` para as hipóteses. **Não vender a busca semântica como pronta antes
    disso:** ela funciona ponta a ponta, mas ainda não é melhor que a lexical para o usuário.
- [ ] **Busca híbrida (RRF):** fundir o ranking lexical e o vetorial. Ficou de fora por
  decisão explícita desta sessão; é o passo natural depois de a qualidade semântica subir.

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

---

## 🧹 Fase 3.5 — Qualidade do dado de entrada — **PRIORIDADE MÁXIMA**

> **Por que esta fase existe:** o sistema foi construído para *arrumar a bagunça* do dado de
> origem. A busca semântica fechou ponta a ponta e mesmo assim **não serve ao usuário**, e a
> causa medida não é infraestrutura nem modelo — é o dado que entra.
>
> **Princípio de governança (decisão do dono do produto, 2026-10-03):** *o sistema não decide
> o que é lixo.* A máquina **identifica e propõe**; **o arquivista decide**. Toda remoção passa
> pela curadoria, com dry-run, undo e trilha de quem decidiu. Isso vale para boilerplate,
> template de título e qualquer valor derivado.
>
> **Não implementar limpeza automática destrutiva.** Nenhuma fase abaixo pode apagar ou
> reescrever dado do acervo sem aprovação humana registrada.

### Diagnóstico medido (acervo real, 3608 documentos — 2026-10-03)

| Sintoma medido | Número | Consequência |
| --- | --- | --- |
| `scope_content` preenchido, mas **12 textos distintos** | 2477 docs | **1930 docs (53%)** compartilham o mesmo bloco "Acervo de 35.327 fotografias…" |
| `admin_bio_history` repetido | 682 docs com o mesmo texto | o histórico institucional some como sinal |
| `provenance` preenchido em **99,8%** | 3600 docs | preenchimento em massa; quase sempre o mesmo valor → inútil como sinal |
| `original_title` | 2232 distintos p/ 3608 docs | template `"Registros Fotográficos - X"` (um título repetido 46×) |
| `document_date` ausente | **1925 docs (53%)** | metade do acervo fora da faceta de data e do mapa futuro |
| `final_title` preenchido | **0** | coluna morta (terceira do mesmo padrão) |

**Prova do efeito no embedding** (modelo real, `paraphrase-multilingual-MiniLM-L12-v2`):

| Par de documentos (assuntos **diferentes**) | Texto de hoje | Só o título |
| --- | --- | --- |
| enchente × matadouro (deveria ser baixo) | **0,4478** | **0,1038** |
| matadouro × matadouro (deveria ser alto) | 0,6537 | 0,7650 |

O bloco de boilerplate **sozinho** tem 0,95 de similaridade com o documento de enchente: ele
domina o vetor. Remover o texto repetido **melhora a separação em ~4×**.

### Fase A — Ferramenta de curadoria de boilerplate

O arquivista é quem manda; a máquina só aponta. Nada aqui altera dado do acervo.

- [ ] **Modelar `DomainTextTemplate`** (nome provisório): catálogo de trechos repetidos com
  `text`/`fingerprint` (unique), `scope` (DEFAULT/IGNORE/REPLACE), `replacement`, `reason`,
  `source` (`SUGGESTED`/`HUMAN`), `is_active`, `created_by`, `created_at`.
  Mesmo espírito de `domain_ner_exclusions` e `domain_stopwords`: decisão durável, auditável e
  reversível.
- [ ] **Rotina de sugestão por frequência** (não destrutiva): agrupar por
  normalização de espaços e apontar trechos acima de um limiar de repetição (ex.: > 20% do
  acervo), com contagem e amostra de documentos. **Ela só escreve sugestões** (`source=SUGGESTED`),
  nunca aplica.
- [ ] **Rotas de curadoria** (mesmo padrão de `/entities/ner-exclusions`):
  `GET` (listar sugeridos + aprovados), `POST` (aprovar/editar/rejeitar um trecho),
  `DELETE` (desfazer, com expurgo retroativo do efeito).
- [ ] **Dry-run obrigatório:** mostrar quantos documentos e quais seriam afetados antes de
  qualquer aplicação (`CleaningService` já faz simulação de impacto — reusar a ideia).
- [ ] **UI:** tela de curadoria (aba de Qualidade de Dados, que já existe) listando candidatos
  com contagem, texto e amostra, com aprovar/editar/rejeitar. Decidir o quanto investir no
  Streamlit sabendo que ele será substituído.
- [ ] **Testes:** sugestão por frequência (limiar, normalização), aprovação/rejeição, undo
  retroativo e dry-run.

### Fase B — Consumo do que foi aprovado (destrava a IA)

Só depois de a Fase A existir e ter decisões humanas registradas.

- [ ] **`build_embedding_text` subtrai os trechos aprovados** antes de compor o texto. O hash
  de idempotência do `worker_embedding` **já é MD5 do texto**, então mudar a composição
  re-queija tudo sozinho, sem `force` e sem carimbo novo.
- [ ] **NER, typology e macro-category leem o texto limpo**, não o cru: o boilerplate hoje
  também polui a extração de entidades e a classificação.
- [ ] **Medir antes/depois com um conjunto rotulado** (10–20 pares consulta→documento
  esperado). Sem número, não se afirma melhoria — foi exatamente a ausência disso que deixou a
  busca semântica "pronta" e inútil.
- [ ] **Registrar o ganho medido** no TODO e no roadmap, na tabela de evidências.

### Fase C — Template de título e campos mortos

- [ ] **Título repetido (`"Registros Fotográficos - X"`):** a máquina **propõe** a parte fixa e
  o arquivista confirma; o candidato a `final_title` derivado é sugerido, nunca gravado
  sozinho.
- [ ] **`final_title` — decidir com número:** ou ganha produtor de verdade (derivação assistida
  + revisão humana), ou **sai do schema**. Hoje é `NULL` em 100% do acervo e está exposto no
  `DocumentSummary`: promessa não cumprida.
- [ ] **`is_anomaly` / `anomaly_reasons` — decidir:** ou ganham produtor (validador estrutural:
  data no futuro, título vazio, escopo que era 100% boilerplate, entidade impossível), ou saem
  do schema. Modelados, indexados e sem produtor desde o schema inicial.
- [ ] **Regra geral a aplicar sem exceção:** *ou o campo ganha produtor na fase em que foi
  modelado, ou sai do schema.*

### Fase D — Cobertura e vocabulário

- [ ] **1925 documentos sem data (53%).** Investigar se a data existe na origem e não é
  parseada (o `staging` já parseia `15/03/1954`, `1972-05-10` e ano solto) ou se realmente não
  existe. Sem isso, a faceta de data e o mapa por bairro nascem pela metade.
- [ ] **Lematização de tags** (o Buraco 4, ainda aberto): "parque"/"parques" seguem distintos.
  Aplicar **nas tags**, nunca no texto do documento — e provar que não destrói nomes próprios.
- [ ] **Deduplicação de tags por trigramas em lote:** `/tags/similar` já encontra os pares;
  falta agrupar e sugerir merges — de novo, **sugerir**, com o arquivista aprovando.

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
| `pytest` (unit + integração) | **343 passed** |
| `ruff check` / `ruff format --check` | limpos (192 arquivos) |
| `basedpyright` | **0 errors, 0 warnings** |
| `alembic upgrade head` + `alembic check` | aplica (inclui downgrade/upgrade); **sem drift** |
| `raw_data` → `run_staging_pipeline` | 2/2 docs; datas e ISAD(G) corretos |
| worker `transfer` | 2 docs, 7 tags vinculadas |
| worker `ner` (spaCy real) | entidades extraídas e vinculadas |
| worker `typology` (mDeBERTa real) | classificou e carimbou; **2/2 corretas** após corrigir o rótulo |
| worker `macro-category` (mDeBERTa real) | **4/4 categorias corretas** após corrigir o rótulo (antes: 0/4) |
| `HUMAN_APPROVED` bloqueia IA | confirmado — o worker de tipologia ignorou o doc aprovado |
| `reclassify_entity` → EntityRuler | PER→ORG propagou para o NER (ciclo completo) |
| **Ciclo negativo do NER** (engine real + Postgres real) | termo vetado `iptu` → **bloqueado**; `prefeitura de curitiba` preservada; regra de sinônimo vetada não entra no EntityRuler |
| **Vazamento por token fundido** (achado na verificação real) | spaCy devolve `"IPTU do Batel"` como uma entidade; o filtro por limite de token bloqueia, sem afetar `"iptuana"` |
| `get_stopwords` só TAG/ALL | o purge do eixo de Tags **não** apaga mais a tag vencedora de um conflito |
| `POST /tags/suggest-macro` | **corrigido**: 41 tags → 3 clusters; 6 tags → vazio com mensagem |
| Voto majoritário no `DocumentSummary` | derivado na leitura; editar tag **não** escreve em `archive_documents` |
| Leitura/escrita via HTTP | listagem, busca, detalhe, merge, cleaning, conflitos: OK |
| **Busca FTS com acento** (acervo real, 3608 docs) | `historica` → **2489** documentos; o `ILIKE` antigo devolvia **0** |
| **Busca FTS com stemming** (acervo real) | `enchentes` → 17; o `ILIKE` antigo devolvia 0 |
| **Busca alcança tags/entidades** (acervo real) | `matadouro` → 27; o `ILIKE` antigo devolvia 12 |
| **Ranking título > corpo** (acervo real + HTTP) | página de `curitiba` ordenada por `rank` decrescente, título no topo |
| **Facetas** (acervo real + HTTP) | tipologia 64 · `entity_type=LOC` 3509 · década de 1950 4 · macro categoria 2467, todas batendo com o SQL |
| **Índices usados** (`EXPLAIN`) | `ix_archive_documents_search_vector` (GIN) na FTS e `idx_archive_tags_name_trgm` no `ILIKE` de tag |
| **Fallback de substring** | fragmento no meio da palavra (sem tag/entidade que case) recupera a contagem do `ILIKE` antigo, sem `rank` |
| Migração em banco limpo | `upgrade head` → `check` (exit 0) → `downgrade -1` → `upgrade head` → `check` sem drift |
| **Imagem com pgvector + PostGIS** | `CREATE EXTENSION vector` funciona; `vector 0.8.7`, `postgis 3.6.4` e `unaccent` disponíveis no mesmo container |
| **Banco de dev reconstruído** | 15 tabelas copiadas (3608 docs · 6182 tags · 3808 entidades · 4785 de ingestão), `alembic check` **sem drift**, busca lexical ainda OK (`historica` → 2489) |
| **Worker `embedding` (modelo real, CPU)** | **3608/3608** documentos embedados em ~1 min; 0 pendentes na segunda execução; 384 dims em todos |
| **Embedding persistido corretamente** | `cos(guardado, recalculado) = 1.0` e o `<=>` do Postgres bate exatamente com o cosseno calculado em Python |
| **Busca semântica ponta a ponta (HTTP)** | `mode=semantic` responde, `rank` é a similaridade e decresce, facetas continuam valendo (tipologia 64 · LOC 3509), `mode` inválido → **400** |
| ⚠️ **Qualidade semântica (medida, NÃO aprovada)** | "enchentes" × "Enchente em região marginalizada" = **0.33**; topo de "desastres naturais" = acidentes de trânsito. `mpnet-base` (768) medido no mesmo corpus discrimina **pior** (0.265 vs 0.361) → o gargalo é o texto, não o modelo |

### Bugs conhecidos e abertos

1. ~~**Ancoragem "isto é TAG" não existe**~~ — **corrigido**: catálogo
   `domain_ner_exclusions` alimentado pelo juiz e pelo curador, com undo e expurgo retroativo.
   Ver Fase 1.
2. **Lematização de tags ausente** — duplicação na origem — Fase 3.
3. ~~**`semantic_search_vector` nunca preenchido** — a busca híbrida prometida não existia.~~
   **Resolvido (Buraco 3):** a coluna morta foi removida e substituída por
   `search_vector` gerado pelo Postgres (Fase 3).
4. **`is_anomaly`, `anomaly_reasons` sem produtor** — colunas mortas.
5. **Sem autenticação** — bloqueio para exposição pública — Fase 4.
6. **Busca semântica com qualidade fraca** — funciona ponta a ponta, mas o ranking por
   similaridade não é melhor que a lexical para o usuário no acervo atual. O gargalo medido é
   o texto embedado (título curto + escopo genérico repetido), não o armazenamento nem o
   modelo. Ver Fase 3 e `.analysis/`.

> **Corrigido em 2026-10-03:** o rótulo `"Nome: descrição"` colapsava o mDeBERTa na
> primeira categoria, em `worker_macro_category` **e** `worker_typology`. Classificação
> agora usa o nome nu; ver Fase 1.5 para a medição que isolou a causa.
>
> **Fechado em 2026-10-03 (Buraco 2):** a ancoragem negativa do NER existe. O catálogo
> `domain_ner_exclusions` guarda a decisão "isto é assunto, não entidade" com motivo, autor
> e a tag que a justifica; o NER respeita o veto (inclusive contra tokens fundidos pelo
> modelo) e o sinônimo positivo não o fura. A verificação com engine real revelou um
> vazamento que nenhum teste com `mock_registry` pegaria — ver Fase 1.
>
> **Fechado em 2026-10-03 (Buraco 3):** a busca virou full-text nativa com ranking
> (título > corpo), acento-insensível (`unaccent` + wrapper `IMMUTABLE`) e passou a
> alcançar tags e entidades, com facetas de tipologia, macro categoria, tipo de entidade
> e intervalo de datas. A coluna morta `semantic_search_vector` saiu; o vetor agora é
> **gerado pelo Postgres** (`search_vector`), logo nunca fica obsoleto nem depende de
> worker. Medição no acervo real: `historica` saiu de 0 (ILIKE) para 2489 resultados.
> **Não reintroduzir `semantic_search_vector` nem concatenar descrição em rótulo.**
>
> **Fechado em 2026-10-03 (Busca semântica):** o `pgvector` entrou no lugar de uma imagem que
> não o suportava, o worker `embedding` populou o acervo inteiro com o modelo real e
> `mode=semantic` responde com ranking por cosseno e facetas. **Com uma ressalva registrada
> de propósito:** a qualidade do ranking semântico no acervo atual é fraca e está medida na
> tabela de evidências — o armazenamento foi verificado (`cos = 1.0`) e um modelo maior foi
> medido e descartado, então o trabalho seguinte é **o texto** (o que se embeda), não a
> infraestrutura.
>
> **Achado de ambiente (2026-10-03):** o volume de desenvolvimento
> (`memoriacuritibana`) **não é gerenciado pelo Alembic** — não tem `alembic_version` e
> diverge das models em 43 pontos (falta `archive_tags.execution_log`, por exemplo). A
> verificação desta sessão rodou em bancos limpos criados por `alembic upgrade head`, com
> os dados reais copiados. Ver a armadilha correspondente em `.analysis/`.
