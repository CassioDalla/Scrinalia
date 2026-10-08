---
translation_of: guides/data-model.md
---

# Modelo de dados

Esta página trata do que os dados **significam**: qual camada é dona de qual fato, para que serve
cada tabela e quais escritas são decisões que uma pessoa pode desfazer. Não é um guia de instalação —
para o ciclo de vida do schema veja [Instalação e implantação](install.md), para executar os workers
veja [Operação](operate.md) e para as telas sobre essas tabelas veja [Curadoria](curate.md).

O schema é propriedade do **Alembic** (`migrations/`), e os modelos SQLAlchemy em
`src/scrinalia/domains/*/models/` são a fonte única de verdade. `uv run alembic check` não pode
acusar drift; uma tabela que existe apenas em uma migration é um defeito.

## Domínios e camadas do pipeline

O sistema tem quatro domínios em `src/scrinalia/domains/`. Três deles são as camadas que um registro
atravessa, nesta ordem:

- `ingestion` — a fila de coleta e o payload intocado (`scraping_queue`, `raw_data`);
- `staging` — o payload convertido em colunas ISAD(G) tipadas e higienizadas (`staging_documents`);
- `archive` — a descrição final enriquecida, os catálogos, os ledgers da IA e a revisão humana
  (`archive_*`, `domain_*`).

O quarto domínio, `identity`, **não** é uma camada desse pipeline (ADR 0009). Ele é dono das contas,
das sessões e do mapa de papéis — as tabelas que descrevem a instalação, não o acervo. Um registro
nunca "passa por" identity.

```text
site de origem
    │  coleta              │  parse + limpeza           │  enriquecimento + revisão
    ▼                       ▼                            ▼
ingestion ───────────▶ staging ───────────────────▶ archive
(scraping_queue,        (staging_documents)          (archive_documents, …)
 raw_data)

identity ── contas, sessões, papéis (não é camada do pipeline)
```

Cada camada identifica um registro por um hash do que leu por último, para que uma nova execução
saiba se algo mudou: `raw_data.content_hash`, `staging_documents.raw_content_hash` e
`archive_documents.staging_content_hash`. A chave de staging → archive é o hash do registro
**parseado**, não do payload bruto, então uma correção no parser chega ao archive mesmo quando os
bytes da origem não mudaram.

## Tabelas

Todas as tabelas de `Base.metadata`. Para enumerá-las a partir do código:

```bash
uv run python -c "from scrinalia.core.base import Base; import scrinalia.domains.archive.models, scrinalia.domains.identity.models, scrinalia.domains.ingestion.models, scrinalia.domains.staging.models; print('\n'.join(sorted(Base.metadata.tables)))"
```

### Ingestão — o que a origem enviou, sem tratamento

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `scraping_queue` | Uma linha por identificador descoberto na origem, com seu estado de extração e contagem de tentativas. | `description_id` (chave de negócio, única), `scrape_status` (`ScrapeStatus`), `discovered_at`, `last_scraped_at`, `retry_count`, `last_error_message` |
| `raw_data` | O payload exato devolvido pelo adaptador, sem tipagem nem limpeza. | `description_id` (único), `content_hash`, `raw_title`, `payload` (JSONB) |

`scrape_status` distingue uma falha transitória (`NETWORK_ERROR`, com nova tentativa) de uma
permanente (`NOT_FOUND`, `FATAL_ERROR`). `raw_data.payload` é a evidência do que a origem realmente
enviou; nada a jusante o lê diretamente.

### Staging — o registro parseado

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `staging_documents` | A descrição higienizada e tipada antes de qualquer IA tocar nela: a fonte única de verdade higienizada. | `description_id` (chave primária), `raw_content_hash`, `title`, `document_date`, `reference_code`, `parent_reference_code`, `hierarchy_path`, `level`, as colunas de texto ISAD(G), `raw_metadata` (JSONB), `created_at`, `updated_at` |

`parent_reference_code` é opcional de propósito: uma origem que entrega um filho antes do pai deixa a
descrição órfã e *marcada* em vez de derrubar o lote. `raw_metadata` guarda as chaves que não foram
mapeadas para uma coluna.

### Archive — a descrição e tudo ao redor dela

#### A descrição

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_documents` | A descrição final, limpa e enriquecida, servida aos usuários e enriquecida pelos workers de IA. | `description_id` (chave primária), `original_title`, `final_title`, `document_date`, `summary`, `staging_content_hash`, `reference_code`, `level_id`, `typology_id`, `parent_id`, `path`, `review_status`, `is_anomaly`, `anomaly_reasons`, `is_published`, `execution_log` (JSONB), `embedding` (`vector(384)`), `search_vector` (gerada), timestamps |

Três propriedades desta tabela sustentam o modelo:

- `parent_id` é uma autorreferência com `ON DELETE RESTRICT`. Um fundo é uma descrição arquivística
  como qualquer outra, então não ganha tabela própria; e um nó com filhos não é apagável de passagem,
  porque o `path` de cada descendente carrega os ids dos seus ancestrais.
- `path` é o conjunto materializado de ids dos ancestrais (`2368.2732.51931`), mantido pelo serviço e
  nunca pela IA. Ele transforma "todos os descendentes de X" em um único `LIKE 'x.%'` indexado.
- `review_status` (`ArchiveReviewStatus`) é o ciclo de vida IA/humano: `PENDING_AI`, `AI_APPROVED`,
  `NEEDS_REVIEW`, `HUMAN_APPROVED`, `REJECTED`. `HUMAN_APPROVED` bloqueia reescritas da IA.

!!! note "Difusão não é revisão"
    `is_published` é coluna própria, deliberadamente não `review_status = HUMAN_APPROVED`. Revisão é
    uma afirmação sobre o registro; publicação é uma decisão sobre o que expor. Reutilizar o status
    faria uma correção de errinho equivaler a publicar, e travaria todo documento publicado contra a
    reescrita da IA. Nada é publicado por padrão, então a superfície de difusão nasce vazia.

#### Assuntos, gavetas e entidades

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_tags` | Um termo de assunto do acervo. | `tag_id`, `name` (único), `macro_category_id`, `ai_confidence_score`, `execution_log` (JSONB) |
| `archive_macro_categories` | A gaveta de assunto (o eixo do "sobre o quê"). | `category_id`, `name` (único), `description`, `classifier_label`, `is_active` |
| `archive_tag_facets` | O eixo não-assunto de uma tag: o que ela *é* quando não é um *sobre*. | chave composta `(tag_id, facet_type)`, `value`, `created_by`, `created_by_user_id` |
| `archive_entities` | Uma entidade nomeada (pessoa, organização, lugar) encontrada por NER ou inserida à mão. | `entity_id`, `name` (único), `entity_type` |
| `archive_document_tags` | Quais tags uma descrição carrega. | chave composta `(description_id, tag_id)` |
| `archive_document_entities` | Quais entidades uma descrição carrega. | chave composta `(description_id, entity_id)` |
| `archive_ai_review_queue` | A fila de auditoria da IA; o lado da *decisão* de uma colisão tag × entidade. | `anomaly_type` (`AnomalyType`), `status` (`ArchiveReviewStatus`), `context_payload` (JSONB), `llm_decision`, `llm_confidence`, `llm_reason` |

`archive_tags.macro_category_id` guarda no máximo uma gaveta de assunto; `archive_tag_facets` é uma
tabela separada porque uma tag carrega no máximo um assunto, mas pode ser lugar *e* instituição ao
mesmo tempo. `facet_type` é restrito a `INSTITUTION` ou `PLACE`, e nada grava uma faceta
automaticamente — faceta é ato de curadoria, nunca inferência da IA.

#### O arranjo

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_description_levels` | A escada de níveis de descrição (os degraus NOBRADE/ISAD(G)), propriedade do arquivista. | `level_id`, `ordinal` (único), `code` (único), `name` (único), `description`, `aliases`, `requires_parent`, `allows_children`, `is_active` |
| `archive_hierarchy_node_plans` | Um degrau que os códigos de referência implicam, e a decisão do arquivista sobre ele: proposta, não escrita. | `plan_id`, `code` (impressão digital única), `depth`, `parent_code`, `document_count`, `declared_levels`, `flags`, `existing_description_id`, `level_id`, `title`, `reference_code`, `status`, `collapse_into_code`, `materialised_description_id`, `decided_by`, `decided_at` |
| `archive_hierarchy_materialisation_log` | O ledger de uma execução de materialização, com detalhe suficiente para revertê-la. | `materialisation_id`, `created_nodes` (JSONB), `rung_map` (JSONB), `previous_state` (JSONB), `changed_by`, `changed_by_user_id`, `undone_at`, `undone_by`, `undone_by_user_id` |

`requires_parent` significa "um nó neste nível não pode ser raiz"; `allows_children` significa "um nó
neste nível é folha". A carga de staging registra um nível desconhecido como não classificado e
segue; já uma tipologia escolhida por uma pessoa é uma afirmação que o catálogo precisa responder.

#### A trilha de curadoria da descrição

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_document_revisions` | Toda edição humana de uma descrição, antes e depois. | `revision_id`, `description_id`, `changed_by`, `changed_by_user_id`, `changes` (JSONB), `note`, `created_at` |
| `archive_document_deletions` | O ledger da única escrita destrutiva sobre o acervo. | `deletion_id`, `description_id`, `reference_code`, `title`, `level_name`, `snapshot` (JSONB), `children_count`, `deleted_by`, `deleted_by_user_id`, `note`, `deleted_at` |

O `description_id` em `archive_document_revisions` é `ON DELETE CASCADE`, então uma revisão escrita
para um documento apagado morre com ele. Por isso `archive_document_deletions` **não tem chave
estrangeira** para `archive_documents`: a linha que ela nomeia sumiu por definição, e este ledger é o
que sobrevive. Ele não é caminho de restauração — não existe código que grave o snapshot de volta.

#### Tabelas de governança

Estas tabelas se chamam `domain_*` embora vivam em `domains/archive/`: são afirmações sobre o domínio
do acervo, não sobre a instalação.

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `domain_stopwords` | Termos banidos pela curadoria, com o eixo que eles deixam. | `id`, `word` (único), `word_scope` (`StopwordsScope`: `TAG`, `ENTITY`, `ALL`) |
| `domain_ner_exclusions` | Termos que a curadoria decidiu pertencerem ao eixo TAG, não a entidades nomeadas. | `id`, `term` (único), `reason`, `source` (`JUDGE`/`HUMAN`), `tag_id` |
| `domain_subject_exclusions` | Termos que a curadoria decidiu não serem assunto de forma alguma. | `id`, `term` (único), `reason`, `source` (`HUMAN`/`RULE`) |
| `domain_synonyms` | Grafias mapeadas para uma tag ou entidade canônica. | `id`, `synonym_name`, `category` (`TAG`/`ORG`/`LOC`/`PER`), `canonical_tag_id`, `canonical_entity_id` |
| `domain_text_templates` | Trechos repetidos que a curadoria mantém fora do texto da IA. | `template_id`, `text`, `fingerprint` (único), `variants`, `action`, `replacement`, `scope`, `status`, `occurrence_count`, `sample_document_ids` |
| `archive_cleaning_rules` | Regras de regex cadastradas por um arquivista. | `rule_id`, `rule_name`, `rule_kind` (`REWRITE`/`VALIDATE`/`LLM_CHECK`), `target_column`, `regex_pattern`, `replacement_string`, `anomaly_reason`, `engine_name`, `preset`, `is_active` |

`domain_synonyms` tem uma checagem de arco exclusivo: uma linha `TAG` aponta para uma tag e não para
uma entidade, e as outras categorias apontam para uma entidade e não para uma tag. Canonicalizar uma
grafia apaga a linha antiga, e é por isso que a busca da taxonomia lê esta tabela também.

`domain_text_templates.scope` (`EMBEDDING`, `NER`, `TITLE`) diz qual consumidor deixa de ler um
trecho. A separação existe porque a medição mostrou que um trecho pode ajudar um consumidor e
prejudicar outro: remover um prefixo de título do texto *embutido* piorou o ranking, sendo exatamente
o que a sugestão de título precisa.

`archive_cleaning_rules.rule_kind` separa `REWRITE` (o worker de limpeza substitui a ocorrência) de
`VALIDATE`/`LLM_CHECK` (o validador de qualidade apenas sinaliza). O worker de limpeza filtra
`REWRITE` explicitamente; sem isso, uma regra de validação reescreveria o texto.

#### O vocabulário do acervo (dado, não código)

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_arrangement_vocabulary` | Um token de arranjo e o nome que a proposta de hierarquia sugere para o seu degrau. | `term_id`, `token` (único, normalizado), `display_name`, `is_active` |
| `archive_collection_terms` | Um termo que o acervo carrega e que não é assunto, com o eixo para onde ele vai. | `term_id`, `(term, kind)` único, `kind` (`CollectionTermKind`), `is_active` |

`token` é tanto um token de código único (`ED`, `ALFA`) quanto um código inteiro (`ACERVO RAIZ`). A
proposta lê o código inteiro primeiro e recorre ao seu último token, então uma linha de código
completo vence uma linha de último token. `CollectionTermKind` é `DISTRICT`, `MUNICIPALITY`, `STATE`,
`REGION`, `COUNTRY` ou `PERSON`; um tipo de lugar reivindica a faceta `PLACE`, e `PERSON` não vai a
lugar nenhum — é o produtor, não um assunto.

#### Operação

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_worker_settings` | A configuração padrão persistida de um worker. | `worker_name` (chave primária), `engine_name`, `preset`, `db_batch_size`, `options` (JSONB), `updated_by`, `updated_at` |
| `archive_worker_settings_revisions` | Trilha de auditoria das escritas de configuração, uma linha por escrita. | `id`, `worker_name`, `before` (JSONB), `after` (JSONB), `changed_by`, `changed_by_user_id`, `changed_at` |
| `archive_worker_runs` | Uma linha por execução de worker, tanto pela CLI quanto pelo painel. | `id`, `worker_name`, `status` (`WorkerRunStatus`), `trigger` (`WorkerRunTrigger`), `requested_by`, `requested_by_user_id`, `engine_name`, `preset`, `config` (JSONB), `queued_at`, `started_at`, `finished_at`, `duration_ms`, `error`, `error_fingerprint` (gerada) |
| `archive_api_errors` | As falhas HTTP inesperadas da própria API. | `id`, `occurred_at`, `request_id`, `method`, `path`, `status_code`, `message`, `error_fingerprint` (gerada) |

`archive_worker_settings` é uma linha **parcial** de propósito: um campo deixado `NULL` continua
seguindo o código, então a precedência é `argumento explícito > esta linha > o default da assinatura`.
`archive_worker_runs` guarda a configuração **resolvida**, então a linha mantém o sentido quando um
preset muda no código. Deliberadamente não há chave estrangeira de nenhuma das duas para uma tabela
de workers: workers são código, não linhas. `archive_api_errors` registra apenas falhas
*inesperadas* — um 404, um 409 e um 422 são respostas que a API deve a um cliente, e registrá-las
enterra os defeitos de verdade.

### Identity — a instalação, não o acervo

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `auth_users` | Uma pessoa que pode entrar no sistema. | `user_id`, `email` (normalizado, único), `name`, `password_hash` (argon2id), `role` (`Role`), `is_active`, `must_change_password`, `failed_attempts`, `locked_until`, `last_login_at` |
| `auth_sessions` | Um login vivo, revogável. | `session_id`, `user_id`, `token_hash` (SHA-256, único), `created_at`, `last_seen_at`, `expires_at`, `revoked_at`, `user_agent`, `ip_address` |

Uma conta é desativada (`is_active`), nunca apagada: todo ledger do acervo guarda quem decidiu o quê,
e as colunas `*_user_id` são `ON DELETE SET NULL`, então apagar a conta apagaria o *quem* de decisões
que continuam valendo. `auth_sessions` guarda apenas o SHA-256 do token, nunca o token, então um dump
do banco não pode ser reexecutado como cookie. O `ON DELETE CASCADE` de `auth_sessions` para
`auth_users` é correto aqui e em nenhum outro lugar deste domínio: uma sessão não tem sentido sem a
sua conta.

## Idempotência: `execution_log` e carimbos versionados

Todo worker de IA é reexecutável. Em vez de deixar uma coluna de negócio nula e torcer, cada worker
grava uma **chave versionada** em um `execution_log` JSONB, e sua consulta de pendentes filtra pela
*ausência* (ou diferença) dessa chave:

- workers de documento carimbam `archive_documents.execution_log`;
- `worker_macro_category` carimba `archive_tags.execution_log`, porque sua unidade de trabalho é a tag.

As chaves canônicas, definidas uma única vez em `worker_stamp.py`:

| Chave do carimbo | Gravada em | Significado |
| --- | --- | --- |
| `worker_ner_v2` | `archive_documents` | Extração NER feita |
| `worker_typology_classifier_v2` | `archive_documents` | Classificação de tipologia feita |
| `cleaning_rule_{id}` | `archive_documents` | A regra dinâmica de limpeza com aquele id já rodou |
| `worker_macro_category_v1` | `archive_tags` | A decisão de gaveta da tag foi tentada |
| `worker_quality_validator_v1` | `archive_documents` | Validação estrutural feita |
| `worker_embedding_v1` | `archive_documents` | O valor é o MD5 do texto embutido |

As consultas de polling são servidas por índices GIN sobre a coluna JSONB: `ix_archive_exec_log` em
`archive_documents` e `ix_archive_tags_exec_log` em `archive_tags`. Um worker altera o dicionário e
precisa chamar `flag_modified` para que o SQLAlchemy perceba a mudança em vigor; esquecer isso é como
um carimbo é gravado em memória e nunca no banco.

A maioria dos carimbos guarda um status (`DONE`, `ERROR`). Dois são **chaveados por valor**:

- `worker_embedding_v1` guarda o **MD5 do texto embutido**, calculado pelo PostgreSQL (`func.md5(...)`
  sobre o texto efetivo) e gravado com `WorkerStamp.mark_value`. Seu predicado de pendência é
  `execution_log[key] IS DISTINCT FROM <md5>`, então uma mudança de texto — inclusive uma edição
  humana — devolve o documento à fila sozinho.
- `worker_macro_category_v1` guarda o hash do conjunto de rótulos contra o qual a tag foi
  classificada, então reescrever o rótulo de um curador reenfileira a tag.

!!! note "Uma exceção documentada"
    `worker_embedding` deliberadamente não usa `ai_writable_documents()`. O embedding é um índice
    derivado do texto, e não conteúdo arquivístico, então um documento `HUMAN_APPROVED` cujo texto
    mudou precisa ser re-embutido, ou a busca semântica serviria um vetor velho. Ele grava apenas a
    coluna `embedding` e o seu próprio carimbo, e documentos `REJECTED` são pulados.

## Governança bidirecional

Uma colisão tag × entidade tem dois veredictos possíveis, e as duas direções são guardadas em
**tabelas diferentes de propósito**.

| Veredicto | Onde a decisão é guardada | O que significa |
| --- | --- | --- |
| A favor da **entidade** | `domain_stopwords` (escopo de tag) | O nome da tag é ruído no eixo de assunto e é retirado dele |
| A favor da **tag** | `domain_ner_exclusions` | O termo é um assunto legítimo; uma extração NER dele é falso positivo |

`domain_stopwords.word` é **único**, então um termo vive em exatamente um eixo. Banir de novo um termo
o *move* (`save_stopwords` é um upsert em `word`) em vez de deixar a tela mostrando um eixo do qual o
arquivista acabou de sair. `word_scope` é `TAG`, `ENTITY` ou `ALL`.

`TagRepository.get_stopwords()` lê **somente** o escopo `TAG`/`ALL`. Um veto com escopo `ENTITY` é um
banimento da extração NER, não uma afirmação sobre o eixo de assunto; lê-lo ali já fez a purga da
curadoria apagar tags que o curador tinha mantido de propósito. É por isso que as duas direções não
podem ser colapsadas em uma tabela ou um escopo só.

`domain_ner_exclusions` é uma *decisão*, não ruído: carrega `reason`, `source` (`JUDGE` para o juiz
de conflito por LLM, `HUMAN` para um curador) e o `tag_id` que a justifica. O `tag_id` é
`ON DELETE SET NULL`, então apagar a tag não reabre silenciosamente o falso positivo que esta linha
existe para evitar.

`domain_subject_exclusions` tem a mesma forma para o outro eixo: um termo que a curadoria decidiu não
ser assunto de forma alguma. O guardião determinístico cobre o que tem forma reconhecível (um ano
solto, um placeholder, uma rua, uma medida); a metade semântica (`pessoas`, `vista aérea`) é uma
decisão, e vive aqui com `source` (`HUMAN` ou `RULE`). Um termo excluído continua sendo uma tag do
acervo, alcançável pela busca — a exclusão silencia o classificador de assunto, não o termo.

## Os ledgers, um a um

Um ledger é uma tabela cujo trabalho é tornar uma escrita explicável ou reversível. Eles não são
intercambiáveis, e só alguns têm desfazer.

| Ledger | O que registra | O seu desfazer |
| --- | --- | --- |
| `archive_taxonomy_merge_log` | Uma linha **por tag absorvida**, fotografada antes de qualquer mudança. | `undo_merge` restaura a linha, os seus vínculos, a sua classificação e o estado das grafias. |
| `archive_hierarchy_materialisation_log` | Uma linha por execução de materialização: os nós que ela criou e o pai/caminho anterior de cada linha que ela mudou. | O desfazer restaura `previous_state` e então remove `created_nodes`. |
| `archive_conflict_resolution_log` | Uma linha por resolução tag × entidade: o snapshot do perdedor, os vínculos transferidos, o banimento que ela plantou. | `DELETE /conflicts/resolutions/{id}`. |
| `archive_document_deletions` | Uma linha por descrição apagada, com todo o snapshot ISAD(G). | **Sem desfazer.** O snapshot é evidência; nada o grava de volta. |
| `archive_worker_runs` | Uma linha por execução de worker, CLI e painel igualmente. | **Sem desfazer** — é um histórico de execução, não uma mudança no acervo. |
| `archive_api_errors` | Uma linha por falha HTTP inesperada. | **Sem desfazer** — um ledger de erros é um rastro. |

Dois detalhes tornam os ledgers reversíveis exatos em vez de aproximados. `created_link_ids` registra
os vínculos que a operação *criou*; tanto o merge quanto a resolução de conflito vinculam com
`ON CONFLICT DO NOTHING`, então um desfazer que apagasse todo vínculo removeria vínculos que já
existiam antes dele. `ban_created` cumpre o mesmo papel para a escrita de governança: o desfazer só
pode remover o banimento quando esta resolução é a que o plantou, senão reverter uma decisão levantaria
um banimento que uma decisão anterior fez. Para o merge, `synonym_created` e `synonym_previous_tag_id`
capturam o estado das grafias antes do merge, e `repointed_synonym_names` registra as grafias que
apontavam para a tag absorvida e foram movidas para a canônica. `undone_at` mantém o desfazer de uso
único e mantém o rastro legível depois: a linha nunca é apagada.

`archive_ai_review_queue` é a companheira de `archive_conflict_resolution_log`, não um ledger de
escritas: ela guarda a *decisão* (o veredicto do juiz ou o do humano), enquanto o log de resolução
guarda a *escrita*. Ela também carrega `AnomalyType.SUBJECT_LOW_CONFIDENCE` para tags que o
classificador de assunto não conseguiu posicionar.

`archive_worker_settings_revisions` é um ledger de revisão no mesmo espírito: a decisão e a escrita
são fatos diferentes, e toda mudança de configuração deixa uma linha `before`/`after`.

## Colunas geradas: uma definição, no banco

Duas colunas são calculadas pelo PostgreSQL e nunca escritas pelo código da aplicação.

| Coluna | Tabela(s) | Definição |
| --- | --- | --- |
| `search_vector` | `archive_documents` | `setweight(to_tsvector(<dicionário>, public.immutable_unaccent(colunas de título)), 'A')` concatenado com o corpo no peso `'B'` |
| `error_fingerprint` | `archive_worker_runs` (sobre `error`), `archive_api_errors` (sobre `message`) | `public.archive_error_fingerprint(<coluna>)` |

`search_vector` é contra o que a busca lexical roda, com o índice GIN
`ix_archive_documents_search_vector`. O dicionário vem do perfil de idioma
(`get_language().fts_dictionary`), e `immutable_unaccent` o torna insensível a acento, então `gaucho`
encontra `Gaúcho`. Como a coluna é **armazenada**, mudar `ACERVO_LANGUAGE` é uma migration que a
reconstrói, não um reboot — e `alembic check` relata exatamente esse drift em vez de deixar o modelo
e a expressão armazenada discordarem em silêncio.

`archive_error_fingerprint(text)` é `IMMUTABLE` e reduz uma mensagem de erro à sua causa raiz: a
primeira linha, em minúsculas, com uuids, hashes, números e caminhos substituídos por placeholders.
Ela é criada pela migration `fe7fcab37207` e **espelhada em `testing/conftest.py`**, porque o schema
de teste é construído por `Base.metadata.create_all` e a função precisa existir antes de `create_all`
emitir a coluna gerada que a chama — exatamente como `immutable_unaccent`. O prefixo `public.` faz
parte da expressão porque é assim que o PostgreSQL a reflete de volta.

A razão de as duas serem geradas e não escritas pela aplicação é que uma coluna gerada preenche as
linhas existentes com a mesma expressão que as novas recebem. Existe exatamente uma definição, ela
não pode divergir do código que escreve a mensagem, e o texto do erro é gravado com a sua classe de
exceção (`KeyError: 'nome'`) justamente para que a impressão digital distinga duas falhas.

## Propostas que sobrevivem ao que nomeiam

| Tabela | Para que serve | Colunas principais |
| --- | --- | --- |
| `archive_tag_merge_proposals` | Um agrupamento de tags que a rotina propõe unificar, e a decisão humana sobre ele. | `proposal_id`, `fingerprint` (único), `canonical_id`, `canonical_name`, `members` (JSONB), `reason`, `review_flags`, `total_documents`, `status`, `decided_by`, `decided_by_user_id`, `decided_at`, `decision_note` |
| `archive_hierarchy_node_plans` | Um degrau que os códigos de referência implicam, e a decisão do arquivista sobre ele. | veja "O arranjo" acima |

Uma proposta é **evidência mais decisão, nunca uma escrita**. A escada de status é
`SUGGESTED → APPROVED/REJECTED → APPLIED`: um veredicto humano é uma intenção durável que a execução
de sugestão nunca sobrescreve (`fingerprint` torna a sugestão idempotente), e aplicar o agrupamento
grava `APPLIED` no mesmo savepoint que absorve as tags. `decided_by`/`decided_at` guardam o
*veredicto*; o ledger de merge guarda o *quando*.

`canonical_id` e `members` são **snapshots sem chave estrangeira**, de propósito: aplicar a proposta
apaga aquelas tags, e a proposta precisa sobreviver como o registro do que foi decidido. O
agrupamento é identificado pelas suas grafias, não pelos seus ids. Como os membros podem morrer, a
leitura calcula `members_alive`, `canonical_alive` e `applicable` (canônica viva **e** mais de um
membro vivo) em uma consulta por página; `applicable` é a definição única de "ainda há trabalho".

## Catálogos se aposentam, não se apagam

Os três catálogos que o arquivista estende sem deploy são `archive_description_levels` (a escada de
níveis), `archive_macro_categories` mais `archive_tags` (as gavetas de assunto) e `archive_typologies`
(as tipologias documentais — a *forma diplomática*: ata, ofício, planta). O vocabulário do acervo
acrescenta `archive_arrangement_vocabulary` e `archive_collection_terms`. Todos são tabelas em vez de
enums para que um nome possa mudar sem uma release.

Nenhum deles apaga. As chaves estrangeiras são `SET NULL` (`archive_documents.level_id`,
`archive_documents.typology_id`, `archive_tags.macro_category_id`), então remover uma linha
desclassificaria toda descrição que aponta para ela e ainda apagaria o registro de que um dia ela
existiu. Uma linha se aposenta com `is_active=false`, e essa é também a única alavanca que alcança o
classificador: aposentar uma tipologia a remove dos rótulos candidatos sem tocar em nenhuma descrição
classificada, então a tela do catálogo continua mostrando o peso das aposentadas.

Duas regras sustentam o catálogo de tipologias: `get_active_typologies()` projeta **apenas**
`(typology_id, name)` e filtra `is_active` — o nome puro é o rótulo, porque acrescentar
`context_description` faz o modelo perder a inferência conforme o rótulo cresce — e um arquivista
escolhendo uma tipologia faz uma afirmação que o catálogo precisa responder, então um id desconhecido
é recusado com 422 em vez de gravado como `NULL`.

O idioma é **código**, não dado: `core/language/` guarda um perfil congelado por idioma (stopwords,
gramática de datas, padrões de rua e placeholder, regras de plural, o dicionário de busca textual, o
modelo spaCy) e `ACERVO_LANGUAGE` o seleciona. O vocabulário do acervo é linha justamente porque o
acervo de outra instituição carrega outros nomes. Veja o ADR 0008.

## A superfície pública: uma partição exata

A superfície de difusão reutiliza `DocumentService` e difere apenas na projeção. A visão de leitura
interna é `DocumentSummary`; a pública é `PublicDocumentSummary`, construída **campo a campo** e nunca
com `model_validate` sobre o DTO interno — validá-lo tornaria público automaticamente todo campo que a
visão interna ganhasse.

Dois frozensets em `api/schemas/public.py` tornam o padrão privado:

- `NOT_PUBLIC_FIELDS` — campos de `DocumentSummary` deliberadamente não publicados. Contém
  `review_status`, `is_anomaly`, `anomaly_reasons`, `archivist_notes`, `provenance`,
  `suggested_final_title`, `rank`, `path`, `parent_id`, `level_id`, `typology_id`, `is_published`,
  `original_thumbnail_url`, `admin_bio_history`, `admin_archival_history` e `access_conditions`.
- `NOT_PUBLIC_FACETS` — atualmente apenas `anomaly_reason`.

Junto com os campos e facetas publicados, eles precisam permanecer uma **partição exata** da leitura
interna: todo campo ou é publicado ou está listado, e nenhum é as duas coisas. Um teste falha quando
um novo campo ou faceta fica sem classificação, então o padrão para o que a visão interna ganhar a
seguir é privado.

Mais duas regras completam a superfície. `published_only` é definido **no servidor** e não é parâmetro
de cliente, então nenhuma query string pode pedir um registro não publicado. Um id não publicado
responde **404, não 403**: um status distinto confirmaria que a descrição existe. E `published_only`
é um filtro que nunca é excluído da contagem de facetas — nenhuma faceta pode levantar o portão da
difusão.

## A trilha de revisão da curadoria humana

`archive_document_revisions` é onde as edições de uma pessoa viram evidência. `PATCH
/api/v1/documents/{id}` grava uma linha com o antes/depois de cada campo que realmente mudou, em
`changes` (JSONB), e marca o documento como `HUMAN_APPROVED`. Vincular e desvincular tags e entidades
grava o mesmo tipo de linha, guardando a lista inteira de nomes de cada lado em vez de um diff de
ids; uma chamada repetida que não muda nada não grava revisão.

A autoria são **duas colunas, nunca uma**:

| Coluna | O que guarda | Ao apagar a conta |
| --- | --- | --- |
| `changed_by` | O nome que o histórico imprime — um retrato de quem a pessoa era. | Mantido; renomear alguém não reescreve o que ela decidiu. |
| `changed_by_user_id` | A conta por trás do nome, como chave estrangeira. | `SET NULL`; a decisão sobrevive com o nome do seu autor. |

O mesmo par aparece onde quer que uma pessoa decida algo: `archive_document_deletions` (`deleted_by` /
`deleted_by_user_id`), `archive_taxonomy_merge_log` (`changed_by`, `undone_by`),
`archive_conflict_resolution_log` (`decided_by`, `undone_by`), `archive_hierarchy_node_plans` e
`archive_tag_merge_proposals` (`decided_by`), `archive_tag_facets`, `archive_cleaning_rules` e
`domain_text_templates` (`created_by`), `archive_hierarchy_materialisation_log` (`changed_by`),
`archive_worker_runs` (`requested_by`) e `archive_worker_settings_revisions` (`changed_by`). O autor é
gravado por `author_columns`/`assign_author` a partir da sessão, nunca tomado da requisição.
