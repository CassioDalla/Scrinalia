# 🗺️ Roadmap & TO-DO: Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento do sistema de curadoria e enriquecimento de acervo
arquivístico (DDD + micro-workers + HITL).

> **Como ler este documento.** Cada item marcado `[x]` foi **verificado em execução real**
> (Postgres + engines de verdade), não apenas lido no código. Os itens `[ ]` são trabalho
> pendente. Quando um item está parcialmente pronto, ele aparece como `[~]` com a descrição
> explícita do que existe e do que falta.
>
> **Estado do gate de qualidade:** suíte **771 testes** passando (unit + integração),
> `ruff check`/`ruff format --check` limpos, `basedpyright` 0 erros,
> `alembic upgrade head` + `alembic check` sem drift (18 migrações).

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança de base | **Praticamente fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | **Fechada na medição** — vocabulário refeito, defeito 2/2 fechado; acurácia ~0.575, dívida explícita |
| 2 | API + Curadoria humana (HITL) | **Fechada no essencial**, faltam ações locais |
| **2.5** | **Hierarquia das descrições** | **H1–H3 fechadas e medidas** no acervo real; H4–H8 abertas |
| 3 | Descoberta, escala e observabilidade | **Parcial** — busca lexical fechada; semântica funciona mas com qualidade fraca |
| 3.5 | Qualidade do dado de entrada | **A–D fechadas** (sem UI, por decisão); resta medir o efeito no ranking |
| 4 | Interoperabilidade, **UI nova** e publicação | Não iniciada — plano do BFF pronto |

O sistema **funciona ponta a ponta** até a camada Archive: ingestão → staging → archive →
enriquecimento por IA → curadoria humana → bloqueio de reprocessamento. O que falta não é
"fazer funcionar", é **arrumar o dado de entrada** — que é a razão de o sistema existir —,
**fechar os eixos semânticos** (macro categorias, hierarquia) e **tornar o acervo
pesquisável de verdade**.

> **Correção de rota (2026-10-03, decisão do dono do produto).** A busca semântica fechou
> ponta a ponta e mesmo assim não serve ao usuário; medido, o gargalo é o **dado de origem**
> (53% do acervo compartilha o mesmo bloco de escopo, 99,8% tem a mesma proveniência, 53% não
> tem data). A prioridade passou a ser a **Fase 3.5**, e o princípio é explícito: **a máquina
> identifica e propõe; o arquivista decide.** Nada é apagado ou reescrito sem decisão humana
> registrada.

> **Correção de rota (2026-10-04, auditoria + decisão do dono do produto).** Duas feats
> entram **antes** da UI nova, e a UI nova passa a ser planejada explicitamente:
> 1. **Rótulos NLI** (Fase 1.5, defeito 2/2) — a classificação de assunto está errada de forma
>    sistemática e **não se denuncia pela confiança**. Curto, alto impacto.
> 2. **Hierarquia** (Fase 2.5) — o acervo é hierárquico, o sistema o trata como plano. Grande,
>    mexe no modelo.
> 3. **UI do curador + BFF público** (Fase 4) — monorepo, duas UIs, dois BFFs.
>
> **Motivo da ordem:** uma UI boa **amplifica** o erro. Se ela nascer antes, vai exibir badge
> `[🚌 Mobilidade e Transporte]` em 826 documentos sobre alvenaria. A hierarquia, por sua vez,
> muda o contrato inteiro — a UI deve nascer sabendo desenhar árvore.
>
> **Planos completos em `.analysis/`:** `plano-nli-e-rotulos.md`,
> `roadmap-hierarquia.md`, `roadmap-bff-curador.md`.

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
- [x] **`is_anomaly` / `anomaly_reasons`.** ~~Modelados, indexados, e sem nenhum produtor.~~
  **Resolvido:** o `worker_quality_validator` (Fase 3.5-C) é o produtor. Verificado no acervo
  real: o carimbo `worker_quality_validator_v1` está presente; `is_anomaly=0` porque nenhuma
  regra `VALIDATE`/`LLM_CHECK` está ativa hoje (a única regra ativa é `REWRITE`).
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

### ✅ Defeito de rótulo (1/2) — **corrigido**

> **São dois eixos independentes do mesmo prompt.** O eixo 1 (descrição concatenada) está
> corrigido abaixo. O eixo 2 (o nome nu **também** não é um alvo NLI válido) foi **descoberto
> na auditoria de 2026-10-04** e é o assunto de `plano-nli-e-rotulos.md`.
> Não reverter o eixo 1 para consertar o eixo 2.

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

### ✅ Defeito de rótulo (2/2) — **FECHADO (2026-10-04), e o diagnóstico era outro**

> **O plano dizia que a frase NLI conserta. A medição disse que ela é o colapso.** Este é o
> achado que reordenou a fase inteira, e vale registrar com o número: bancada de 44 tags
> rotuladas à mão (aprovadas pelo dono), 3 formatos × 3 arranjos × 2 modelos.

- [x] **A frase NLI, aplicada de forma consistente, dá acurácia 0.000.** Zero acertos em 40
  tags, nos dois modelos, com duas redações (`"um assunto sobre X"` e `"trata de X"`), com
  **65% das tags colapsando numa única gaveta** e **0/4 controles positivos**. O plano citava
  `alvenaria → Urbanismo (0.536)`; não se reproduz em nenhuma combinação medida.
- [x] **O ganho do plano era artefato do arranjo experimental.** A frase sai de 0.000 para
  0.450 apenas quando comparada **contra nomes nus** — conjunto misto, onde ela ganha por
  proximidade lexical — e ainda assim **perde** do baseline (0.500). Medido:

  | Arranjo | `sentence` (mDeBERTa) | Leitura |
  | --- | ---: | --- |
  | `same_format` (frase × frase) | **0.000** | é o colapso, não a correção |
  | `mixed_vs_bare` (frase × nomes nus) | 0.450 | o que o plano provavelmente mediu |
  | `bare_vs_bare` (baseline) | **0.500** | melhor que a frase nos dois arranjos |

- [x] **A confiança ESTÁ calibrada — o TODO estava errado neste ponto.** Certas 0.705 contra
  erradas 0.455 (mDeBERTa, nome nu). O caso `1924 → Mobilidade (0.73)` não era "a confiança não
  denuncia o erro": era **uma data que nunca deveria ter chegado ao modelo**. O guard resolve,
  não o limiar.
- [x] **A causa real tinha duas metades, e nenhuma era o formato do rótulo:**
  1. **O vocabulário não cobria o acervo.** `igrejas` alcança **2.467 documentos** — a maior tag
     — e não existia "Religião". Nenhum rótulo conserta uma gaveta inexistente.
  2. **`Instituição` e `Localidade` nunca foram assuntos.** São proveniência e geografia
     (`ippuc` 2.376, `curitiba` 1.865), e disputavam a mesma gaveta que `alvenaria`.
- [x] **Corrigido: o vocabulário passou de 5 para 8 gavetas de assunto**, derivadas das tags
  reais. `Saúde` e `Administração` foram **cortadas por falta de evidência** (zero tags no top
  250) — não entraram por intuição. `Instituição`, `Localidade` e `Pessoa` foram **desativadas**
  (nunca deletadas: a FK é `SET NULL`).
- [x] **Corrigido: `archive_tag_facets`** dá às tags um eixo que não é assunto. `ippuc` é
  produtor, `curitiba` é lugar, e uma tag pode ser os dois ao mesmo tempo — por isso a chave é
  composta.
- [x] **Corrigido: a classe `NENHUMA` tem dois mecanismos.** O determinístico cobre o que tem
  forma (data, placeholder, logradouro, número) e pegou **1 de 4** dos não-assuntos do gabarito;
  o resto são julgamentos (`pessoas` 166 docs, `vista aérea`, `capanema`) e ganharam o catálogo
  curado `domain_subject_exclusions`, no padrão de `domain_ner_exclusions`.
- [x] **Corrigido: o limiar de 0.40 subiu para 0.55, com fila atrás.** Medido, uma resposta
  errada tem 0.455 de média — 0.40 deixava passar quase todo erro. Abaixo do piso a tag fica
  órfã **e** entra em `archive_ai_review_queue` como `SUBJECT_LOW_CONFIDENCE`.
- [x] **Corrigido: o carimbo virou hash do conjunto de rótulos** (`worker_macro_category_v1`
  com o valor sendo o SHA-256 dos rótulos, como o `worker_embedding` faz com o texto). A V3
  expôs a falha na prática: aposentou `Instituição` enquanto suas tags mantinham `DONE`, e a
  correção nunca chegaria a elas.
- [x] **`classifier_label` existe como saída de curadoria, não como padrão.** A coluna é
  editável sem deploy e o carimbo por hash a propaga, mas o docstring registra os 0.000 medidos
  para ninguém semeá-la com frases esperando melhoria.

**O que segue aberto, e é honesto registrar:**

- [ ] **Acurácia de 0.500 (mDeBERTa) / 0.575 (xlm-roberta) em nome nu.** ~42% do topo por
  `document_count` continua errando: `alvenaria`, `casa`, `rio`, `parque iguaçu` erram nos
  **dois** modelos, com a mesma ordem — é limite do zero-shot NLI com sintagma nominal, não do
  rótulo nem de um modelo específico. Decisão do dono: **aceitar e resolver por curadoria**.
- [ ] **Trocar para `xlm-roberta-large-xnli`** (+0.075, ~3 tags em 40): medido e **descartado
  por ora** — não compensa um engine novo em produção. O gabarito e a bancada ficam prontos
  para reavaliar.
- [ ] **O acervo não foi reprocessado.** O dry-run foi encerrado por decisão do dono (ambiente
  de dev): a qualidade real fica para depois. O worker está pronto e a fila de revisão está
  configurada.

**Evidência:** `testing/evaluation/macro_category_quality.py` (bancada),
`macro_category_dry_run.py` (projeção), `macro_category_vocabulary.py` (vocabulário),
`macro_category_pairs.json` (gabarito aprovado). Análise em
`.analysis/b3-medicao-classificador.md`.

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

## 🏛️ Fase 2.5 — Hierarquia das descrições arquivísticas

> **H1, H2 e H3 ENTREGUES e verificados no acervo real (2026-10-04).** Plano de referência em
> `.analysis/roadmap-hierarquia.md`. A UI (H4/H5) e o restante (H6–H8) seguem **não iniciados por
> decisão de sequenciamento**: a tela nasce no front novo (Fase 4 / B6), e a H3 provou que ela é
> curadoria de **~52 nós**, não de 3.608 decisões.

O sistema tratava cada descrição como uma linha plana. O acervo **é** hierárquico, e a evidência
está no `reference_code` — preenchido em **100%** dos 3.608 documentos.

### ⚠️ O que a medição corrigiu no plano

| O plano dizia | Medido (2026-10-04, 3.608 documentos) | Consequência |
| --- | --- | --- |
| "3.604 órfãos; 4 têm registro-pai" | **0 documentos têm ancestral existente por prefixo exato**; os 6 registros estruturais têm **0 filhos** por prefixo. São **3.608 órfãos**. | Não muda o desenho; corrige a expectativa. O plano confundiu "existem 4 registros de 4 tokens" com "4 têm pai". |
| "a fatição por espaço é ~90% correta" | **Falsa para a família SMU (1.124 docs, 31% do acervo).** Fatiar todo prefixo cria **1.123 pais de 1 documento**: o código intercala vocabulário de arranjo e identificadores da folha. | É a descoberta que decidiu o desenho — o fatiador passou a ser **ciente de vocabulário**. |
| (implícito) árvore de milhares de nós | Descartados os identificadores: **20 rungs estruturais → 52 nós propostos**, 8 já existentes. | A Tela A é curadoria de **~52 nós**, não de 3.608. |
| "profundidade do código ≠ ordinal" como regra fixa | A profundidade **não** determina o nível: 5 tokens têm 2.466 Itens, **1 Série e 1 Seção**. | A norma passou a ser **aprendida da coleção** (maioria estrita por profundidade), não fixada no código. |

### H1 — Catálogo de níveis — ✅ FECHADA

- [x] **`ArchiveDescriptionLevel`** (`archive_description_levels`, migração `a1f2c3d4e5b6`):
  `ordinal`, `code`, `name`, `description`, `aliases`, `requires_parent`, `allows_children`,
  `is_active`. Sem `DELETE`: desativar basta, porque a FK é `SET NULL`.
- [x] **`name` é a grafia que a ORIGEM declara** (`"Item Documental"`, `"Dossiê/Processo"`), não a
  redação da norma: semear `"Item documental"` teria derrubado os 2.478 itens por caixa. A norma
  vive em `description`; `aliases` guarda as variantes aceitas no casamento.
- [x] **`requires_parent`** é o `is_required` do plano com a ambiguidade removida ("não pode ser
  raiz"), e o teto de ordinal **não** virou CHECK: o catálogo é do arquivista, não do código.
- [x] **Migração em duas etapas** — `b2c3d4e5f6a7` adiciona a FK e popula, `c3d4e5f6a7b8` dropa o
  texto — com guarda: a segunda revisão **recusa rodar** se sobrar uma única declaração não mapeada.
- [x] **Backfill medido no acervo real: 3.608/3.608 mapeados, 0 não classificados** — `Item
  Documental` 2.478 · `Dossiê/Processo` 1.124 · `Série` 3 · `Seção` 3, exatamente o declarado. O
  `downgrade` repovoa o texto a partir da FK (ida-e-volta sem perda, verificada).
- [x] **Assimetria documentada:** a carga resolve nível desconhecido → `NULL` + `UNKNOWN_LEVEL` e
  **não falha** a transferência; o `PATCH` humano recusa com **422**. Typo da origem não derruba
  carga; escolha do arquivista o catálogo tem de responder.
- [x] **Rotas:** `GET/POST /api/v1/hierarchy/levels`, `PATCH /levels/{id}`. Duplicata de ordinal,
  código ou nome → **409**; inexistente → **404**.

### H2 — Árvore — ✅ FECHADA

- [x] **`parent_id` + `path` + `level_id`** (migração `d4e5f6a7b8c9`). `path` é o caminho de **ids**
  (`"2731.2368.51931"`), materializado, com índice **`text_pattern_ops`** — sem ele o `LIKE 'x.%'`
  não usa o índice sob a collation do banco e "descendentes de X" vira varredura sequencial.
- [x] **`ON DELETE RESTRICT`** no pai, e não `SET NULL`: o `path` dos descendentes carrega o
  prefixo, então um `SET NULL` silencioso deixaria a subárvore inteira apontando para um prefixo
  que não existe mais.
- [x] **Regras puras** (`domain/hierarchy.py`): ciclo, pai obrigatório, `allows_children`, ordem na
  escada, auto-pai. A guarda de ciclo é uma linha: o alvo já vive sob o nó.
- [x] **Recálculo da subárvore em uma instrução** (`substr(path, length(old)+1)`): qualquer
  profundidade, um round trip. Invariante verificada por teste e por diagnóstico
  (`PATH_DIVERGENCE` = **0** no acervo real).
- [x] **Diagnóstico:** `ORPHAN` (**3.602** no acervo — só quem exige pai), `DOSSIER_WITHOUT_PARENT`,
  `UNKNOWN_LEVEL`, `PATH_DIVERGENCE` e `LEVEL_DEPTH_MISMATCH`.
- [x] **`LEVEL_DEPTH_MISMATCH` com norma aprendida, não fixada:** maioria estrita por profundidade.
  Empate não gera norma, então as duas Seções e duas Séries de 4 tokens **não** são sinalizadas.
  Medido: **18 casos** — 13 `Item Documental` em profundidade 6 entre 1.095 Dossiês, e 5 registros
  de arranjo que legitimamente diferem do nível modal daquela profundidade.
- [x] **Move com trilha, sem blindagem:** o antes/depois entra em `archive_document_revisions`;
  **não** força `HUMAN_APPROVED` (hierarquia é arranjo, não conteúdo, e nenhum worker de IA escreve
  essas colunas) — decisão registrada e contestável.
- [x] **A transferência não reescreve o arranjo:** `parent_id`/`path` entraram em
  `protected_columns` do `upsert_archive_document`. Sem isso, a próxima carga desligaria todo nó
  curado.
- [x] **Rotas:** `GET /tree` (flat, ordenado por `path`), `/nodes/{id}/children`,
  `/nodes/{id}/ancestors`, `POST /nodes`, `POST /nodes/{id}/move` (**200**) e `GET /diagnostics`.

### H3 — Proposta automática — ✅ FECHADA (o ponto de decisão foi exercido)

- [x] **Fatiador ciente de vocabulário** (`domain/hierarchy_code.py`): token alfabético é arranjo,
  o resto é identificador da folha. Medido nos 3.608 códigos: `BR PRADAP SMU ED AL CONSTR 2154
  1903` vira **um** rung, não 1.123 pais.
- [x] **Nunca adivinha em silêncio:** cauda que não é número puro → `UNPARSED_TAIL` (**31 códigos**
  no acervo); identificador antes do último token de vocabulário → `MID_CODE_IDENTIFIER` (**3**).
- [x] **Relatório medido no acervo real, só leitura:** 3.608 códigos → **20 rungs estruturais** →
  **52 nós propostos** · **8 existem** como registro · **43 a criar** · **1 ambíguo**; **44** com
  ordinal inferido, **8** registros sem documento algum, **7** com ordem de nível impossível (a
  família SMU tem mais níveis do que a escada de 6 comporta — achado real, não defeito do código).
- [x] **`FOTOGRAFIA` × `FOTOGRAFIAS` (2.391 itens) marcado, não decidido:** `NEAR_DUPLICATE_NODE`
  nos dois lados, o nó ausente marcado `AMBIGUOUS`, e um teste que proíbe o merge por trigramas
  sobre nós hierárquicos. A decisão é do arquivista.
- [x] **Read-only provado, não prometido:** `md5` de `archive_documents` idêntico antes e depois da
  bancada sobre o acervo real, e teste de integração equivalente.
- [x] **Bancada:** `testing/evaluation/hierarchy_proposal.py` → `.analysis/hierarchy_proposal.json`.
- [x] **Rota:** `POST /api/v1/hierarchy/proposal` (**200**, sem persistência) — a UI nova (H4)
  consome daqui. **Nada de catálogo de propostas persistido** até a H4 mostrar que precisa.

### O que segue aberto

- [ ] **H4 — Tela A (proposta).** Decidir os ~52 nós: aceitar, renomear, fundir.
- [ ] **H5 — Telas B e C** (edição individual e diagnóstico com ações).
- [ ] **H6 — Contrato de ingestão:** `parent_reference_code`/`hierarchy_path` no
  `StagingDocumentDTO` e resolução do pai na transferência. Hoje **todo documento entra como raiz**.
- [ ] **H7 — Busca e facetas hierárquicas** ("buscar dentro deste fundo/série").
- [ ] **H8 — `DocumentSummary`** com `ancestors[]` e `children_count`.
- [ ] **A árvore NÃO foi materializada.** O acervo real tem **3.602 órfãos** e 8 rungs isolados: é
  exatamente o estado que a H4 resolve. `embedding` e `search_vector` não foram tocados, então a
  baseline de `retrieval_quality.py` (Hit@10 0.625) **continua comparável** até a H7.
- [ ] **Nível 0 e Fundos ainda não existem como registro.** A proposta os sugere (`BR PRADAP` →
  Acervo, os 8 nós do 3º token → Fundos) e é a H4 que grava.

### Riscos que continuam de pé

- **A H4 escreve no acervo:** é a primeira operação que **cria** registros de arranjo. Precisa do
  mesmo cuidado da Fase E (decisão humana registrada, dry-run e undo).
- **`path` desnormalizado** pode divergir se alguém escrever por fora do serviço — o diagnóstico
  `PATH_DIVERGENCE` e o teste de invariante existem para isso, e o índice precisa continuar
  `text_pattern_ops`.
- **A árvore muda a busca inteira** quando a H7 chegar → re-medir `retrieval_quality.py`.

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

### Diagnóstico medido (acervo real, 3608 documentos — 2026-10-03/04)

| Sintoma medido | Número | Consequência |
| --- | --- | --- |
| `scope_content` preenchido, mas **12 textos distintos** | 2477 docs | **1930 docs (53%)** compartilham o mesmo bloco "Acervo de 35.327 fotografias…" |
| `admin_bio_history` distinto | **2916 valores distintos** para 3608 docs; top repetido = 22 | **correção de 2026-10-04:** o TODO dizia "682 docs com o mesmo texto". É falso hoje: esse campo é o **texto específico do documento** e era soterrado pelo bloco. A "pobreza de sinal" do embedding era do `scope_content`, não do acervo |
| `provenance` preenchido em **99,8%** | 3600 docs, **2 valores cobrem 99,5%** (IPPUC 2467 · SMU 1125) | campo de instituição; inútil como sinal por documento |
| `original_title` | 2232 distintos p/ 3608 docs | template `"Registros Fotográficos - X"` em **2467 títulos** (um título repetido 46×) |
| `document_date` ausente | **1925 docs (53%)** | **1682 são o sentinela `"00/00/0000"`** na origem (não é data perdida); só ~243 têm expressão real não parseada ("Década de 1980", "1951-1953", "Após 1996") |
| `final_title` preenchido | **0** | coluna morta (terceira do mesmo padrão) |

**Prova do efeito no embedding** (modelo real, `paraphrase-multilingual-MiniLM-L12-v2`):

| Par de documentos (assuntos **diferentes**) | Texto de hoje | Só o título |
| --- | --- | --- |
| enchente × matadouro (deveria ser baixo) | **0,4478** | **0,1038** |
| matadouro × matadouro (deveria ser alto) | 0,6537 | 0,7650 |

O bloco de boilerplate **sozinho** tem 0,95 de similaridade com o documento de enchente: ele
domina o vetor. Remover o texto repetido **melhora a separação em ~4×**.

### Fase A — Ferramenta de curadoria de boilerplate — ✅ **FECHADA (2026-10-04)**

O arquivista é quem manda; a máquina só aponta. Nada aqui altera dado do acervo.

- [x] **`DomainTextTemplate`** (`domain_text_templates`, migração `c5b784678746` + `cecb7bcf7f7d`):
  `text`, `fingerprint` (unique, SHA-256 do texto normalizado), `variants` (grafias
  quase-idênticas aprovadas como um grupo), `action` (`IGNORE`/`REPLACE`), `replacement`,
  `scope` (**`EMBEDDING`/`NER`/`TITLE`** — ver Fase B), `reason`, `source`, `status`
  (`SUGGESTED`/`APPROVED`/`REJECTED`), `occurrence_count`, `sample_document_ids`,
  `is_active`, `created_by`.
- [x] **Sugestão por frequência** (`POST /quality/text-templates/suggest`): lê o acervo e
  propõe valores inteiros, segmentos de frase e **prefixos de título**, agrupando
  quase-duplicatas e contando a **união de documentos** (nunca a soma — o prefixo
  `"Registros Fotográficos"` é prefixo da própria variante `"... -"`, e somar dobrava a
  evidência). Idempotente por fingerprint e **nunca sobrescreve decisão humana**.
- [x] **Rotas de curadoria:** `GET` (lista), `POST` (cadastro/aprovação), `PATCH`
  (editar/aprovar/desativar/rejeitar), `DELETE` (undo com expurgo retroativo).
- [x] **Dry-run obrigatório** (`POST /preview`): quantos documentos mudam, com amostras
  antes/depois por coluna. A aprovação recalcula a evidência pelo mesmo SQL.
- [x] **Undo retroativo:** ao remover ou editar um trecho, os documentos afetados têm os
  carimbos que leem texto removidos (`worker_ner_v2`, `worker_typology_classifier_v2`,
  `worker_quality_validator_v1`). O embedding não precisa de ajuda: o carimbo dele é o MD5
  do texto efetivo.
- [x] **Verificado no acervo real:** 3608 documentos → **5 candidatos** coerentes: o bloco
  (2467 docs, 2 variantes), `IPPUC…` (2467), `Registros Fotográficos -` (2467),
  `Projeto de uma` (627) e `Pesquisa: Não foram encontradas informações` (276).
- [ ] **UI:** fora de escopo por decisão explícita (o front será substituído).
- [x] **Testes:** 79 novos (unit + integração) cobrindo limiar, normalização de espaços
  (inclusive NBSP), união de variantes, pruning, idempotência, decisão humana preservada,
  dry-run, requeue e as rotas.

#### Duas armadilhas que só a execução real mostrou

1. **O piso de frequência descartava a variante de 57 documentos.** Ela sozinha ficava
   abaixo do limiar, e o bloco (2410) parecia mais raro que uma frase dentro dele (2467),
   então a frase nunca era podada. Correção: agrupar por **forma** (texto sem espaços)
   antes de aplicar o piso.
2. **`execution_log` pode conter o `null` do JSON**, não SQL NULL (o tipo mantém
   `none_as_null=False`). `coalesce` não cobre esse caso e `jsonb - text` estoura
   *"cannot delete from scalar"*. Correção: normalizar com `jsonb_typeof(...) = 'null'`.

### Fase B — Consumo do que foi aprovado (destrava a IA) — ✅ **FECHADA (2026-10-04)**

- [x] **Composição única em SQL.** `repository/text_quality_repo.py` constrói o "texto
  efetivo" (normaliza espaços + aplica os trechos aprovados) como expressão SQL. O
  embedding usa a **mesma expressão** para selecionar o texto e calcular o MD5 do carimbo —
  sem dualidade Python/SQL que possa divergir. NER e tipologia passam a **selecionar o
  texto já composto** do banco em vez de remontá-lo em Python.
- [x] **Carimbos v2** (`worker_ner_v2`, `worker_typology_classifier_v2`) para reprocessar o
  acervo com o texto limpo.
- [x] **Escopo por consumidor — descoberto pela medição, não suposto.** O `scope` existe
  porque um trecho pode ajudar um consumidor e atrapalhar outro (ver a tabela abaixo).
- [x] **Conjunto rotulado + medição antes/depois:** `testing/evaluation/retrieval_pairs.json`
  (16 consultas, relevância derivada do título — proxy documentado) e
  `testing/evaluation/retrieval_quality.py`, que recomputa os candidatos **em memória** e
  mede os dois rankings com o modelo real, sem escrever no banco.
- [x] **Registrar o ganho medido** — tabela de evidências abaixo.

#### ⚠️ O que a medição mudou no desenho

Medido com o acervo real e o MiniLM real (16 consultas, `k=10`):

| Trechos aplicados ao texto embedado | Similaridade média entre pares (separação) | Hit@10 | Recall@10 | MRR | Precisão@10 por termo |
| --- | --- | --- | --- | --- | --- |
| nenhum (antes) | 0.769 | 0.562 | 0.292 | **0.358** | 0.294 |
| só o bloco de `scope_content` | 0.545 | **0.625** | 0.287 | 0.327 | 0.375 |
| só `provenance` (IPPUC) | 0.504 | **0.625** | 0.321 | 0.339 | 0.381 |
| só o prefixo de título | 0.768 | 0.500 | 0.308 | 0.350 | 0.306 |
| só `admin_bio_history` ("Pesquisa:…") | 0.769 | 0.562 | 0.292 | 0.352 | 0.294 |
| bloco + proveniência + "Pesquisa" (**sem os prefixos**) | 0.504 | **0.625** | **0.333** | 0.339 | **0.381** |
| conjunto completo sugerido (com os prefixos) | 0.423 | 0.500 | 0.225 | 0.277 | 0.300 |

Leituras que ficam registradas:

1. **A separação dos vetores melhora muito** (0.769 → 0.504) — confirma o diagnóstico da
   sessão D: o bloco dominava o vetor.
2. **Mas separação não é recuperação.** O conjunto completo sugerido **piora** o ranking
   (Hit@10 0.562 → 0.500). Aprovar tudo o que a máquina propôs teria sido um erro — e é
   exatamente por isso que a decisão é humana.
3. **O prefixo de título é o vilão:** subtraí-lo do texto embedado derruba o Hit@10
   (0.562 → 0.500), embora seja justamente o que o `suggested_final_title` precisa. Daí o
   campo `scope`: propostas de título nascem `TITLE` e **não** entram no vetor.
4. **Com o escopo de produção** (bloco + proveniência + "Pesquisa", sem os prefixos) o
   ganho aparece: Hit@10 **+0.062**, Recall@10 **+0.042**, precisão por termo **+0.087**.
   O MRR cai 0.019 — não esconder: o topo ficou um pouco menos preciso, a cauda melhorou.
5. **Relevância é proxy derivada do título** e são 16 consultas: o número serve para
   comparar dois rankings, não para coroar modelo. Não afirmar mais do que isso.

### Fase C — Template de título, validador e curadoria humana — ✅ **FECHADA (2026-10-04)**

- [x] **Título repetido (`"Registros Fotográficos - X"`):** a máquina **propõe** a parte fixa
  (candidato com escopo `TITLE`, 2467 documentos) e o arquivista confirma. O
  `suggested_final_title` é derivado **na leitura** e desaparece quando o arquivista grava
  `final_title`.
- [x] **`final_title` — decidido com número:** o produtor é o **arquivista**. A API passou a
  aceitar **qualquer campo ISAD(G)** no `PATCH /documents/{id}` (título, data, código de
  referência, nível, produtor, histórias, procedência, idioma, notas), com `changed_by` e
  `review_note`. Cada campo que muda entra em `archive_document_revisions` (antes/depois em
  JSONB) e há rota de leitura do histórico.
- [x] **`is_anomaly` / `anomaly_reasons` — decidido:** ganharam **produtor**. O worker
  `quality-validator` (antes do `embedding` no pipeline) grava códigos (`AnomalyReason`) e
  marca `NEEDS_REVIEW`, nunca `HUMAN_APPROVED`.
- [x] **Validador estrutural:** data ausente/sentinela, data no futuro, título vazio/curto,
  título todo em maiúsculas, título apenas com o template fixo, escopo 100% boilerplate, sem
  tags/tipologia/entidades.
- [x] **Regex do arquivista:** `ArchiveCleaningRule` ganhou `rule_kind`
  (`REWRITE`/`VALIDATE`/`LLM_CHECK`) + `anomaly_reason`. O worker de limpeza filtra
  `REWRITE` explicitamente — sem isso uma regra de validação **reescreveria** o texto.
- [x] **LLM opcional e desligado por padrão:** só uma regra `LLM_CHECK` **ativa** constrói um
  modelo (`engines/title_quality/`, motor `ollama_title_check`). Sem regra, custo zero — e um
  teste garante que o motor não é instanciado.
- [x] **Regra geral aplicada:** nenhum campo ficou sem produtor nem foi removido sem número.

### Fase D — Cobertura e vocabulário — ✅ **FECHADA (2026-10-04)**

- [x] **Os 1925 sem data: investigados e resolvidos até o limite do dado.** Medido:
  **1682 são o sentinela `"00/00/0000"`** (não há data na origem) e **243 têm expressão real
  que o parser não entendia**. O parser virou função pura (`domains/staging/dates.py`) com
  sentinelas explícitas, décadas ("Década de 1980", "Anos 90"), intervalos ("1951-1953",
  "1920 a 2006") e aproximações ("Após 1996", "Meados de 1970").
  **Medido no acervo real: 201 datas recuperadas; cobertura de 47,0% → 52,6%.**
  Os 1690 restantes não têm data na origem — nenhum parser os recupera.
- [x] **O caminho até o archive foi consertado.** Dois defeitos reais impediam a correção de
  chegar lá: (1) o staging é CDC por hash do **payload cru**, então mudar o parser não
  reprocessava nada → `force` explícito no `run_staging_pipeline`; (2) o transfer reusava
  esse hash cru como chave do archive, então a mudança nunca apareceria →
  `StagingRecord.parsed_content_hash()`, o hash do que a camada **parseou**.
- [x] **Lematização: decidida como sugestão, não como reescrita.** `singular_candidates` gera
  hipóteses regulares (incluindo `-ões/-ães/-ais/-éis/-óis/-is/-ns`), que só viram sugestão
  quando o singular **já existe** como tag. Nenhuma tag é criada, renomeada ou destruída.
- [x] **Deduplicação em lote por trigramas + plural:** a sugestão agrupa clusters com canônico
  (a grafia mais usada), membros com contagem e o motivo (`TRIGRAM`, `PLURAL`, `MIXED`).
  Verificado no acervo real: `igrejas/igreja`, `casa/casas`, `alvenaria/alvenaria.`,
  `comércio/comércios` e o erro de digitação `uma casa/um casa`.
  **Re-medido em 2026-10-04** (mesmo `threshold=0.65`, sem o teto de 50 da rota antiga):
  **411 clusters**, 466 tags absorvidas, 2074 documentos tocados — a medição anterior
  registrava 200 e o `limit` padrão da rota escondia o resto. O ciclo de curadoria desses
  merges está na **Fase E**; nada é mesclado sem decisão humana registrada.

### Fase E — Ciclo de curadoria dos merges de tags — **Entrega 1 fechada (2026-10-04)**

> O buraco não era "falta lematizar": era que a máquina propunha e **nada consumia**. A rota
> de sugestão devolvia no máximo 50 clusters, sem `total`, e a única rota que efetivava era
> destrutiva, uma por vez, sem dry-run, sem undo e sem autoria. Detalhe do plano e das
> medições em `.analysis/buraco-4-plano.md`.

- [x] **Defeitos latentes do merge, reproduzidos e corrigidos.** O plano supunha "sinônimo
  órfão"; a execução mostrou que `domain_synonyms.canonical_tag_id` é `ON DELETE CASCADE`,
  então o modo de falha é a **ressurreição do termo absorvido** num merge encadeado
  (`parques → parque → área verde`): o sinônimo era apagado junto com a tag intermediária e a
  próxima ingestão recriava a tag. Correções: `repoint_synonyms()` antes do delete e
  `create_synonyms` como *upsert* (reapontar um sinônimo deixou de ser um no-op silencioso).
  Guardas: merge encadeado mantém o mapeamento; nenhum sinônimo aponta para tag morta; a
  ingestão seguinte vincula ao canônico **sem** recriar a tag absorvida.
- [x] **Catálogo de propostas durável** (`archive_tag_merge_proposals`, migração
  `acfe0e1d9f1f`): `fingerprint` único (SHA-256 do canônico + nomes ordenados), snapshot dos
  membros em JSONB, `reason`, `review_flags`, `total_documents`, `status` e autoria
  (`decided_by`/`decided_at`/`decision_note`). O *upsert* só atualiza a evidência de propostas
  ainda `SUGGESTED` — **uma decisão humana nunca é sobrescrita** (re-execução devolve
  `persisted=0`), então o arquivista não reavalia os mesmos 411 clusters toda vez.
- [x] **Rotas de curadoria:** `POST /tags/merge-proposals/suggest` (calcula e persiste),
  `GET /tags/merge-proposals` com `total`, paginação e filtros (`status`, `reason`,
  `min_documents`, `flagged_only`) e `PATCH /tags/merge-proposals/{id}` que **registra** a
  decisão. A rota antiga `GET /tags/merge-suggestions` saiu: recomputar na leitura criava duas
  fontes de verdade.
- [x] **Dry-run com definição única** (`POST /tags/merge/preview`): `plan_merge()` é puro e
  descreve o impacto (documentos, vínculos reescritos, tags absorvidas com categoria e score,
  sinônimos criados/reapontados, flags); `apply_merge()` executa exatamente o plano, e
  `merge()` passou a ser plano + aplicação. Um teste de integração fixa que **o preview e o
  merge produzem os mesmos números** — dry-run que mente é pior que nenhum.
- [x] **Flags de revisão medidas:** `MEMBER_WITH_DIGITS` (onde os falsos positivos se
  concentram: `rua 24 de maio` ← `rua 13 de maio`), `WEAK_MEMBER`,
  `CATEGORY_WOULD_BE_LOST` e `MEMBER_IS_SYNONYM`. **A flag não é veredito:** entre os 58
  clusters com dígito há `br-116 ← br 116` (correto) e `rua ← ruas, rua 7, rua 4` (errado).
- [x] **Relatório do acervo real, só leitura:** `testing/evaluation/tag_merge_review.py` →
  `.analysis/tag_merge_report.json`. Medido: 411 clusters, 466 tags absorvidas, 2074
  documentos, **350 clusters sem flag**, 58 com dígito, 3 `WEAK_MEMBER`, 0 de categoria em
  risco (nenhuma tag tem macro categoria no acervo hoje).
- [x] **Ledger reversível e undo sem perda (Entrega 2).** `archive_taxonomy_merge_log`
  (migração `63bcc576d926`), uma linha por tag absorvida, gravado **antes** de o merge tocar
  em qualquer coisa: snapshot da linha (nome, categoria, score, `execution_log`, `created_at`),
  os documentos daquela tag, os vínculos que o merge **criou** e o estado das grafias.
  `undo_merge` restaura a tag com o `tag_id` original, os vínculos, a classificação e as
  grafias. Três achados da implementação: (1) restaurar a tag não bastava — sem apagar os
  vínculos criados o documento ficaria com as **duas** grafias, daí `created_link_ids`;
  (2) **nenhum `setval` é necessário**, porque o id veio da própria sequence (a armadilha dos
  seeds com id explícito não se aplica), e há teste criando tags depois do undo; (3) grafias
  têm **três** estados (criada pelo merge, já existente apontando para outra tag, ou apontando
  para a tag absorvida) e o undo restaura cada um.
- [x] **Aplicação em lote com isolamento real.** `POST /tags/merge/batch` roda cada cluster num
  SAVEPOINT: um cluster ruim entra em `failed` e os bons são aplicados (commit único do
  `provide_unit_of_work`). Incluir um `SUGGESTED` no lote **é** a decisão (vira `APPROVED` com
  `decided_by`); `REJECTED` é recusado; um cluster já aplicado é reportado, não reescrito.
- [x] **Auditoria e undo por HTTP.** `GET /tags/merge-log` (paginado; filtros por canônico,
  autor e desfeitos) e `DELETE /tags/merge-log/{merge_id}` (single-shot: a segunda tentativa é
  **409**; id inexistente é **404**). O ledger é o recurso — único desvio de nomenclatura em
  relação ao plano, que dizia `DELETE /tags/merge/{id}`.
- [x] **Mesmos dois defeitos no caminho de entidades — corrigidos.**
  `EntityRepository.create_synonyms` virou upsert e `EntityService.merge` reaponta os sinônimos
  antes de `delete_entities` (`canonical_entity_id` também é `ON DELETE CASCADE`). Guardas:
  merge encadeado de entidade mantém o mapeamento, nenhum sinônimo aponta para entidade morta,
  e reapontar move de verdade.
- [x] **Aplicado no acervo real (decisão do arquivista, 2026-10-04).** Os **40 clusters
  `PLURAL` sem flag** foram aprovados e aplicados: **40/40 sem falha em 2,9 s**. Efeito medido:
  tags **6182 → 6142**, vínculos **41592 → 41452** (as 140 diferenças são documentos que tinham
  **as duas** grafias e ficaram com um vínculo só), sinônimos TAG **14 → 54**, documentos
  inalterados (3608) e buscas de sanidade idênticas (`historica` 2489, `enchentes` 17). O
  relatório com os `merge_id` está em `.analysis/tag_merge_applied.json`; os 371 clusters
  restantes continuam pendentes de revisão humana.
- [x] **Undo exercitado ao vivo no acervo real.** O menor cluster aplicado (`vendas ← venda`,
  merge_id 9) foi desfeito e reaplicado: a tag voltou com o `tag_id` e o vínculo originais, o
  vínculo que o merge criara saiu do canônico (41 → 40) e a reaplicação devolveu o estado
  final (41). O ledger guarda os dois eventos (9 desfeito, 41 ativo) — a trilha não some.
- [x] **Achado colateral, medido e corrigido: a busca perdia a grafia absorvida.** O eixo de
  tags casa nome por `ILIKE`, sem stemming e sem sinônimos, então os documentos alcançáveis
  **só** pela grafia absorvida sumiam da busca por ela (medido: `lojas` perdia 42 dos 54,
  `homens` 30 dos 35 — o FTS cobre quem tem a palavra no texto, não quem só tinha a tag).
  `DocumentRepository.search` passou a mapear o termo pelo `domain_synonyms` nos **dois** eixos
  (tag e entidade). Re-medido: **0 perdidos** em `casas`, `carro`, `lojas` e `homens`, com as
  buscas conhecidas inalteradas.
- [ ] **Catálogo de propostas de entidades** (228 pares similares), reusando o dry-run e o
  ledger que já existem para tags.


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

### UI nova, BFF e o repo — plano em `.analysis/roadmap-bff-curador.md`

> **Decisão de arquitetura: monorepo, duas UIs, dois BFFs.**
> Justificativa: as mudanças de backend e front são acopladas (o rótulo NLI muda o que a UI
> mostra; a hierarquia muda o contrato inteiro); o contrato OpenAPI merece cliente gerado +
> CI bloqueante; o `Procfile` e o CI já são um só.

- [ ] **B1 — Separar a superfície pública.** `PublicDocumentSummary` com **allowlist
  explícita** + controller público + teste que falha se alguém adicionar campo interno.
  *Não depende da UI; pode começar já.*
- [ ] **B2 — Definir o predicado de publicação** (produto, não código): `is_published` ou
  `review_status = HUMAN_APPROVED`? Muda índice e query — e se for `HUMAN_APPROVED`, o site
  público nasce **vazio** (o acervo tem 0 revisões humanas hoje).
- [ ] **B3 — Rota de fila de curadoria** `GET /api/v1/curation/inbox`: contagem + amostra por
  tipo (propostas de merge, conflitos, anomalias, tags órfãs, órfãos de hierarquia, docs não
  revisados). É **view de leitura** — cada número já é uma query existente. Transforma "44
  endpoints" em "um sistema que diz o que fazer".
- [ ] **B4 — Scaffold `apps/curator/`**: React + Vite + TS, TanStack Query, cliente gerado do
  OpenAPI, CI que quebra se o contrato mudar.
- [ ] **B5 — Telas essenciais:** busca/facetas, detalhe+edição, taxonomia (merge com preview),
  conflitos, qualidade.
- [ ] **B6 — Telas da hierarquia** (Fase 2.5, H4/H5).
- [ ] **B7 — Scaffold `apps/public/`** + regras de badge (Fase 1.5).
- [ ] **B8 — Desligar o Streamlit** (`src/memoria_curitibana/dashboard/` e o `web` do Procfile).
- [ ] **B9 — Auth + auditoria + CORS + rate limit** no BFF do curador. **Última etapa.**

**Por que duas UIs e não uma com auth:** o `DocumentSummary` vaza metadado interno
(`review_status`, `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`). Num site
público isso expõe o processo interno de curadoria. **Segurança por omissão de campo é
frágil; por omissão de rota é auditável.** O BFF público reusa os mesmos serviços de domínio
(zero duplicação de regra) e difere só na projeção de saída.

> **Ponto importante:** o núcleo Python **não se move** — `apps/api` é a casca HTTP que já
> existe. Isso mantém `pytest`, `alembic` e os workers intactos. **Não** mover
> `src/memoria_curitibana/api/` junto com a chegada da UI: misturar reorganização cosmética
> com feature nova multiplica o diff.

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

## 🔧 Pendências operacionais no acervo (não são código)

Descobertas na auditoria de 2026-10-04 rodando a API contra o banco de dev real.

- [ ] **Os carimbos v1→v2 nunca foram reprocessados no acervo.** O banco tem
  `worker_ner_v1` e `worker_typology_classifier_v1` em **3.608** documentos, enquanto o código
  filtra por `_v2`. O bump é **deliberado** (commit `a8ecebb`: *"so the collection is re-read
  with the clean text"*), mas a releitura **não foi executada** — ou seja, NER e tipologia do
  acervo ainda vêm do **texto sujo**, e o ganho medido (Hit@10 0.562 → 0.625) não está nos
  dados. **Ação:** rodar `ner` e `typology` no acervo.
- [ ] **Regra de limpeza de teste ativa em produção.** Existe uma `ArchiveCleaningRule`
  chamada `aaaaa` (regex `\bpalavra\b`) carimbando os 3.608 documentos. Desativar.
- [ ] **5.162 tags órfãs** de macro categoria (de 6.142) — a maioria porque o worker rodou
  antes do conserto dos rótulos. Rerodar depois de resolver o defeito 2/2 (Fase 1.5).
- [ ] **0 revisões humanas** e **0 propostas de merge decididas** (411 pendentes). O acervo
  nunca passou por curadoria humana real — relevante para a decisão B2.
- [ ] **`domain_text_templates` vazio** e **`domain_ner_exclusions` vazio**: as duas feats da
  Fase 3.5 estão implementadas e sem uso no acervo real ainda.
- [x] **O acervo real foi migrado para a Fase 2.5** (2026-10-04): `alembic upgrade head`
  aplicado no volume de dev com `pg_dump` prévio; `archive_documents.level` foi substituído por
  `level_id` (3.608/3.608), `parent_id`/`path` existem e a busca lexical segue idêntica
  (`historica` 2489, `enchentes` 17). O `pg_dump` foi escrito em `/tmp` e **não sobreviveu à
  sessão** — a via de rollback é `alembic downgrade -1` ×4, que recria o texto a partir do
  catálogo (ida-e-volta verificada sem perda).
- [ ] **A árvore não foi materializada:** 3.602 descrições órfãs e 8 rungs isolados aguardam a
  H4. A rota `POST /api/v1/hierarchy/proposal` mostra exatamente o que a decisão vai criar.

---

## ✅ Verificação executada (evidências)

Tudo abaixo foi executado contra Postgres real + engines reais, não apenas inspecionado:

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **574 passed** |
| `ruff check` / `ruff format --check` | limpos (224 arquivos) |
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
| **Catálogo de trechos verificado no acervo real** | 3608 documentos → **5 candidatos**: bloco de `scope_content` (2467 docs, 2 variantes), `IPPUC…` (2467), `Registros Fotográficos -` (2467), `Projeto de uma` (627), `Pesquisa: Não foram encontradas informações` (276) |
| **Dry-run de curadoria** | bloco: 2467 documentos afetados de 3608 varridos, `scope_content` → `''`; prefixo de título: 2467 afetados, título → parte específica |
| **Normalização SQL × Python** | idênticas em 200 valores reais de `scope_content`, incluindo tab e U+00A0 (o `[[:space:]]` do Postgres **não** cobre NBSP e o `\s` do Python cobre: por isso a classe de espaços é explícita e compartilhada) |
| **Datas recuperadas (acervo real)** | 201 documentos saíram de "sem data": 58 "Década de 1980", 34 "Década de 1990", 17 "Anos 90", 15 "Anos 1990", 13 "Década de 1960", 7 "Após 1996", 6 "1951-1953", 4 "Final da década de 1980", 3 "Meados de 1993", 1 "1929-1986"… Cobertura 47,0% → **52,6%**; 1690 seguem sem data na origem (sentinela) |
| **Sugestões de merge de tags (acervo real, re-medido)** | **411 clusters** (267 `TRIGRAM` · 101 `MIXED` · 43 `PLURAL`), 466 tags absorvidas, 2074 documentos tocados. A medição anterior registrava 200: o `limit` padrão de 50 da rota escondia o resto |
| **Ciclo de merges — Fase E (Entrega 1)** | defeitos latentes reproduzidos como teste que falha (3) e corrigidos; merge encadeado não ressuscita o termo; ingestão pós-merge vincula ao canônico sem recriar a tag |
| **Dry-run = apply (verificado)** | preview e merge produzem os mesmos números na mesma fixture (`documents_updated`, `links_rewritten`, tags deletadas) — a promessa do dry-run está presa ao que o merge faz |
| **Decisão humana preservada (verificado)** | re-executar o sugeridor depois de uma decisão devolve `persisted=0` e o status continua `REJECTED`/`APPROVED` |
| **Flags no acervo real** | 350 de 411 clusters sem nenhuma flag; 58 com `MEMBER_WITH_DIGITS` (mistos: `br-116 ← br 116` correto, `rua ← rua 7` errado); 3 `WEAK_MEMBER`; 0 `CATEGORY_WOULD_BE_LOST` |
| **Rotas ponta a ponta (HTTP, acervo real)** | `POST /tags/merge/preview` 200 com flags e impacto reais; canônica inexistente → 400; `PATCH` de proposta inexistente → 404; `limit` acima do teto → 400; nenhuma proposta ou tag foi escrita pelas rotas de leitura |
| **Migração `acfe0e1d9f1f` em banco limpo** | `upgrade head` → `check` (exit 0) → `downgrade -1` → `upgrade head` → `check` sem drift |
| **Ciclo completo por HTTP (banco descartável, Entrega 2)** | `suggest` → `preview` → `PATCH` approve → `batch` → `GET merge-log` → `DELETE merge-log/{id}`; a tag absorvida volta com o vínculo no lugar, a segunda tentativa de undo é **409** e um id inexistente é **404** |
| **Undo sem perda (testes de integração)** | restaura `tag_id`, nome, categoria, score, `execution_log` e vínculos; apaga **só** os vínculos que o merge criou (documento que já tinha as duas grafias mantém as duas); devolve grafias nos três estados; tolera documento apagado depois do merge; a sequence sobrevive (criar tag depois do undo não colide) |
| **Lote com falha isolada (teste de integração)** | um cluster com canônico inexistente entra em `failed` e é revertido pelo SAVEPOINT; o cluster bom é aplicado e gera ledger; reaplicar o mesmo cluster é reportado, não reescrito |
| **Migração `63bcc576d926` em banco limpo** | `upgrade head` → `check` → `downgrade -1` → `upgrade head` → `check` sem drift |
| **Merge encadeado de entidade (defeito irmão)** | `a→b` e `b→c` mantém `a` e `b` apontando para `c`; nenhum sinônimo de entidade aponta para entidade morta; reapontar uma grafia de entidade a move de verdade |
| **Aplicação no acervo real (40 clusters `PLURAL` sem flag)** | 40/40 sem falha em 2,9 s; tags 6182 → **6142**, vínculos 41592 → **41452**, sinônimos TAG 14 → **54**, documentos 3608 e buscas de sanidade inalteradas (`historica` 2489, `enchentes` 17) |
| **Undo ao vivo no acervo real** | `vendas ← venda` (merge_id 9) desfeito e reaplicado: tag, `tag_id` e vínculo restaurados exatamente; o vínculo criado saiu do canônico (41 → 40) e a reaplicação voltou a 41; ledger com os dois eventos |
| **Busca pela grafia absorvida (antes/depois da correção)** | antes: `lojas` perdia 42 de 54 documentos e `homens` 30 de 35; depois do mapeamento por `domain_synonyms`: **0 perdidos** nos dois eixos, e `casas`/`carro` seguem 100% alcançáveis |
| **Medição antes/depois (16 consultas, 3608 docs, MiniLM real)** | separação média entre pares 0.769 → 0.504; com o escopo de produção Hit@10 0.562 → **0.625**, Recall@10 0.292 → **0.333**, precisão@10 por termo 0.294 → **0.381**, MRR 0.358 → 0.339 |
| ⚠️ **Aprovar tudo o que a máquina sugeriu PIORA o ranking** | conjunto completo (com os prefixos de título): Hit@10 **0.500** (pior que 0.562 sem trecho nenhum). O prefixo de título derruba o ranking (0.562 → 0.500) e é exatamente o que o `suggested_final_title` precisa → nasceu o `scope` do template |

| **Bancada de rótulos (44 tags, gabarito aprovado)** | `same_format` com frase NLI: **0.000** nos 2 modelos, 2 redações, 65% numa gaveta, **0/4 controles positivos** |
| **Hipótese do arranjo misto (confirmada)** | `sentence` só sai de 0.000 para 0.450 comparada **contra nomes nus** — e ainda perde do baseline (0.500) |
| **Baseline medido (nome nu)** | mDeBERTa **0.500** · xlm-roberta-large-xnli **0.575**, com **4/4** controles positivos |
| **Calibração da confiança (corrige o TODO)** | certas **0.705** · erradas **0.455** — a confiança separa; `1924` era uma data, não um erro de confiança |
| **Vocabulário derivado do acervo** | 8 gavetas de assunto · `Saúde` e `Administração` **cortadas por zero evidência** · `igrejas` (2.467 docs) finalmente tem "Religião" |
| **Guard determinístico** | pegou **1 de 4** não-assuntos do gabarito → o resto virou catálogo curado, não regra |
| **`archive_tag_facets` + migrações novas (3)** | `upgrade head` → `check` → `downgrade -1` → `upgrade head` → `check`, **sem drift** em banco limpo |
| **Migração que aposenta gavetas (V3)** | verificada em banco com o vocabulário antigo semeado: tags desanexadas, gavetas desativadas (não deletadas), downgrade restaura |
| **Dry-run no acervo real (encerrado a pedido)** | 6.142 tags · 980 carimbos · fila de revisão **vazia** · banco **byte-idêntico** depois — confirmado que nada foi escrito |
| | **Auditoria de 2026-10-04 (acervo real, 3.608 docs)** | |
| `pytest` completo | **574 passed** |
| Gate | `ruff` limpo (224 arquivos) · `basedpyright` **0 errors** · 9 migrações sem drift |
| **API exercitada por HTTP (44 rotas)** | busca lexical 2.468 docs p/ "parque" com `rank`; semântica responde; facetas (`entity_type=ORG` → 1.873); 411 propostas de merge; preview de merge correto |
| **`suggest-macro` corrigido (verificado)** | **56 clusters** em 6.142 tags — antes quebrava com 422 no preset padrão |
| **`worker_macro_category` rodando** | 980 tags processadas, `ai_confidence_score` + carimbo gravados |
| ⚠️ **Qualidade do `macro-category` (NÃO aprovada)** | 687 de 980 tags em "Mobilidade e Transporte"; `alvenaria` (826 docs), `casa` (387), `1924` (260), `residencial` (941) no balde errado — **causa isolada: o rótulo não é proposição NLI**, não o modelo |
| ⚠️ **Carimbos v1→v2 não reprocessados** | acervo tem `worker_ner_v1`/`worker_typology_classifier_v1` em 3.608 docs; o código filtra `_v2`. O bump é deliberado, a releitura **não foi executada** |
| ⚠️ **Regra de teste ativa no acervo** | `ArchiveCleaningRule` "aaaaa" (regex `\bpalavra\b`) carimbando 3.608 documentos |
| **Forma do `reference_code` (hierarquia)** | 100% preenchido; vocabulário fechado (8 valores no 3º token); código **é** o caminho; **0 documentos com ancestral existente** (são 3.608 órfãos, não 3.604) e 6 registros estruturais com 0 filhos; armadilha `FOTOGRAFIA`×`FOTOGRAFIAS` identificada |
| **Backfill `level` texto→FK (acervo real)** | 3.608/3.608 mapeados, 0 não classificados; Item 2.478 · Dossiê 1.124 · Série 3 · Seção 3; coluna de texto removida; `downgrade` repovoa sem perda e `upgrade`+`check` voltam sem drift |
| **Invariante do `path` (acervo real)** | 0 divergências depois do backfill; índice `ix_archive_documents_path` com `text_pattern_ops` presente |
| **Bancada H3 no acervo real (só leitura)** | 3.608 códigos → 20 rungs estruturais → **52 nós propostos**: 8 existentes, 43 a criar, 1 ambíguo; 44 com ordinal inferido; 8 registros sem documento; 7 com ordem de nível impossível; 31 códigos ilegíveis e 3 com identificador no meio |
| **Proposta é read-only (provado)** | `md5(string_agg(...))` de `archive_documents` idêntico antes e depois da bancada sobre o acervo real (3608 docs) |
| **Superfície HTTP da hierarquia (acervo real)** | `GET /levels` devolve a escada com as contagens (item 2478 · dossiê 1124 · série 3 · seção 3); `POST /proposal` 200 com os 52 nós; `GET /diagnostics` ORPHAN **3602**, PATH_DIVERGENCE **0**, LEVEL_DEPTH_MISMATCH **18**; criar raiz/fundo 201, mover 200 e voltar 200, dossiê na raiz **422** |
| **Busca lexical intacta depois das migrações** | `historica` 2489 e `enchentes` 17, idênticos ao pré-migração; 6142 tags e 3608 documentos inalterados |
| **Migrações da hierarquia em banco limpo** | `upgrade head` → `check` → `downgrade -1` ×4 → `upgrade head` → `check`, sem drift |

### Bugs conhecidos e abertos

1. ~~**Ancoragem "isto é TAG" não existe**~~ — **corrigido**: catálogo
   `domain_ner_exclusions` alimentado pelo juiz e pelo curador, com undo e expurgo retroativo.
   Ver Fase 1.
2. ~~**Lematização de tags ausente**~~ — **resolvido como sugestão** (Fase 3.5-D):
   nenhuma tag é reescrita na ingestão, porque isso mudaria a identidade de toda tag nova e
   poderia inventar formas. O ciclo da sugestão foi fechado na **Fase E** (Entrega 1):
   catálogo de propostas com decisão persistida e dry-run. **O que segue aberto é aplicar as
   decisões** (Entrega 2, com ledger e undo) — hoje aprovar registra a intenção e não mescla.
3. ~~**`semantic_search_vector` nunca preenchido** — a busca híbrida prometida não existia.~~
   **Resolvido (Buraco 3):** a coluna morta foi removida e substituída por
   `search_vector` gerado pelo Postgres (Fase 3).
4. ~~**`is_anomaly`, `anomaly_reasons` sem produtor**~~ — **resolvido** (Fase 3.5-C):
   o worker `quality-validator` os preenche e marca `NEEDS_REVIEW`.
5. **Sem autenticação** — bloqueio para exposição pública — Fase 4.
6. **Busca semântica com qualidade fraca** — **parcialmente endereçado e ainda aberto.**
   O gargalo medido era o texto embedado, e a Fase 3.5-B tratou a causa: com o escopo de
   produção o Hit@10 sobe de 0.562 para 0.625 e a precisão por termo do título de 0.294 para
   0.381 (16 consultas, proxy derivada do título). **Isso não é "pronto":** a busca híbrida
   (RRF) continua pendente e o MRR caiu 0.019. A medição é o que autoriza (ou não) afirmar
   melhoria — ver a tabela de evidências.
7. ~~**A classificação de macro categoria está errada de forma sistemática**~~ — **fechado
   em 2026-10-04, com diagnóstico corrigido.** O defeito existia, mas a causa não era o formato
   do rótulo: era o **vocabulário** (faltava "Religião" para a maior tag do acervo, e
   `Instituição`/`Localidade` disputavam o eixo de assunto). Medido numa bancada de 44 tags, a
   frase NLI que o plano propunha dá **0.000**. O que ficou aberto é a acurácia de **0.575**
   (nome nu), limite do zero-shot com sintagma nominal — dívida explícita, não bug.
8. ~~**Não existe hierarquia entre descrições**~~ — **H1–H3 fechadas (Fase 2.5):** o catálogo
   de níveis existe e o `level` texto virou FK (3.608/3.608 mapeados), a árvore tem
   `parent_id`/`path` com invariante verificada, e a proposta lê os códigos e sugere 52 nós
   sem escrever nada. **O que segue aberto é a materialização** (H4–H5, com a UI nova) e o
   contrato de ingestão do pai (H6): hoje o acervo real tem 3.602 órfãos e a árvore não foi
   gravada. Plano: `.analysis/roadmap-hierarquia.md`.
9. **O acervo está desatualizado em relação ao código** em dois pontos: os carimbos
   `ner`/`typology` não foram reprocessados para `_v2`, e há uma regra de limpeza de teste
   ativa. São operações, não código — ver "Pendências operacionais no acervo".

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

---

> **Fase 3.5 fechada em 2026-10-04 (A–D, sem UI).** O sistema deixou de "só rodar": agora ele
> **identifica, propõe, mede e deixa a decisão com o arquivista**, e o dado de entrada começa a
> ser arrumado sem que nada do acervo seja apagado ou reescrito por conta própria.
>
> O que sustenta a fase, em uma frase cada:
>
> 1. **A máquina propõe; o arquivista decide** — catálogo de trechos, sugestões de merge e
>    validador de anomalias jamais escrevem no acervo; reescrevem só o **texto que a IA lê**.
> 2. **Uma única definição de texto efetivo**, em SQL, usada pelo embedding, pelo NER e pela
>    tipologia — sem dualidade Python/SQL que possa divergir.
> 3. **Nada é afirmado sem número.** A medição antes/depois contradisse a hipótese inicial
>    (aprovar tudo piorava o ranking) e foi ela que criou o `scope` do template. O ganho
>    registrado (+0.062 de Hit@10, +0.087 de precisão por termo) vale para **as 16 consultas
>    do conjunto rotulado**, que é um proxy derivado do título — não é uma promessa universal.
> 4. **A dívida ficou explícita, não maquiada:** os 1690 documentos sem data não têm data na
>    origem; a busca híbrida (RRF) segue pendente; a UI de curadoria está fora por decisão.
