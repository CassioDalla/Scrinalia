---
translation_of: guides/operate.md
---

# Operação

Esta página é para quem opera a máquina no dia a dia: quais workers existem, em que ordem rodam,
como subir o runner ou disparar uma execução pontual, como a configuração efetiva é resolvida, o que
o painel de sistema mostra e o que fazer quando algo quebra. Instalar e configurar o sistema está em
[Instalação e implantação](install.md); as decisões arquivísticas de cada tela estão em
[Curadoria](curate.md).

## Os workers e a ordem do pipeline

`src/scrinalia/domains/archive/workers/catalogue.py` é a definição única de um worker: a posição
dele no pipeline, a unidade que a fila conta, se ele respeita a governança de revisão e o carimbo
que escreve. O catálogo não importa nenhum worker — resolve cada módulo sob demanda —, então lê-lo
é barato.

Nove workers, na ordem do pipeline:

| # | Nome | Módulo | Unidade | Governança | Engine efetiva vem de |
| --- | --- | --- | --- | --- | --- |
| 1 | `transfer` | `worker_archive_transfer` | registro de staging | não | — |
| 2 | `cleaning` | `worker_cleaning_regex` | documento | sim | — |
| 3 | `ner` | `worker_ner` | documento | sim | assinatura |
| 4 | `typology` | `worker_typology` | documento | sim | assinatura |
| 5 | `thumbnail` | `worker_thumbnail` | documento | sim | — |
| 6 | `conflict-judge` | `worker_resolve_tag_entity_conflict` | par tag × entidade | não | assinatura |
| 7 | `macro-category` | `worker_macro_category` | tag | não | assinatura |
| 8 | `quality-validator` | `worker_quality_validator` | documento | sim | regra `LLM_CHECK` ativa |
| 9 | `embedding` | `worker_embedding` | documento | não | assinatura |

A ordem é a ordem em que as etapas liberam umas às outras, e é a ordem que a seção de pipeline do
painel mostra:

```text
transfer -> cleaning -> ner -> typology -> thumbnail -> conflict-judge -> macro-category -> quality-validator -> embedding
```

As duas etapas **à frente** dessa tabela — ler a origem para o `raw_data` e estruturá-lo em
`staging_documents` — não são workers deste catálogo, porque não carregam engine nem gravam carimbo
de IA. São comandos de linha de comando próprios, descritos em
[a leitura da origem e o transform](#a-leitura-da-origem-e-o-transform).

- **`transfer`** copia o registro estruturado do staging para a descrição do Acervo, tendo como
  chave o hash do registro interpretado (`staging_content_hash`). É a única etapa que reescreve
  conteúdo: quando o hash muda, o `execution_log` gravado é zerado e os enriquecimentos de IA
  precisam rodar de novo. Uma descrição que uma pessoa já aprovou nunca é sobrescrita, e um
  registro de staging com o mesmo hash não é gravado.
- **`cleaning`** aplica as regras de limpeza ativas do tipo `REWRITE`, uma passada por regra. Uma
  regra do tipo `VALIDATE` ou `LLM_CHECK` nunca substitui nada — sinalizar é papel do validador de
  qualidade.
- **`ner`** extrai nomes próprios, lugares e instituições do texto composto da descrição.
- **`typology`** classifica cada descrição contra o catálogo de tipologias ativas por zero-shot.
  Uma descrição cujo melhor score fica abaixo do piso mantém `typology_id` NULL — a coluna diz
  isso tanto quando o classificador recusou quanto quando nenhuma execução chegou à descrição —
  então a recusa é gravada: uma linha em `archive_ai_review_queue` com o **score que a execução
  viu**.
- **`thumbnail`** baixa a imagem original e guarda uma miniatura no storage de objetos. Ele confirma
  que o bucket existe antes do primeiro documento — criando-o só quando
  `S3_AUTO_CREATE_BUCKET=true` — então um bucket ausente derruba a execução uma vez, com uma frase,
  em vez de carimbar a fila inteira com o `AccessDenied` enganoso do endpoint. O `--limit N` limita
  os documentos de uma execução, que é o que torna barato um teste local.
- **`conflict-judge`** compara o vocabulário de tags com o de entidades e consulta o LLM local para
  decidir se o termo ambíguo é assunto ou nome próprio. Todo veredicto, automático ou enviado a uma
  pessoa, deixa uma linha em `archive_ai_review_queue`. Uma chamada que o motor não conseguiu fazer
  levanta em vez de virar veredicto, então o par **não** deixa linha e é perguntado de novo na
  execução seguinte: ele continua pendente, e o número de "já julgados" do painel não o conta.
- **`macro-category`** arquiva cada tag numa categoria de assunto. A unidade dele é a **tag**, não a
  descrição, então o carimbo vive no `execution_log` da própria tag; uma tag que o curador arquivou
  à mão está fora do alcance dele.
- **`quality-validator`** marca anomalias estruturais, títulos repetidos e regras `VALIDATE`. Nunca
  reescreve um campo. O modelo de linguagem só é construído quando existe uma regra `LLM_CHECK`
  ativa.
- **`embedding`** grava o vetor usado pela busca semântica e lê o texto por último, porque toda
  mudança de texto precisa acontecer antes dele.

!!! note "O embedding é a exceção de governança documentada"
    `embedding` de propósito não usa a proteção de `HUMAN_APPROVED`. O vetor é um índice derivado do
    texto, não conteúdo arquivístico, então uma descrição aprovada cujo texto mudou precisa ser
    re-embedada, ou a busca semântica serviria um vetor desatualizado. Ele grava apenas a coluna
    `embedding` e o próprio carimbo, e pula descrições em `REJECTED`.

### O que cada fila significa

Uma fila não é uma tabela: é o predicado que o próprio `count_pending` do worker compartilha com o
`execute`. O painel nunca o re-deriva. `pending` é quantas unidades a próxima execução leria.

Para os cinco workers cujo livro é um carimbo, o painel abre o carimbo em vez de mostrar um número
só, porque um slot de identidade pode guardar três coisas diferentes e apenas uma delas atribui a
resposta: **com produtor** é um valor que o próprio padrão do slot aceita, uma impressão digital que
realmente nomeia o modelo; **sem produtor conhecido** é um valor legado — o `"DONE"` gravado antes de
a impressão digital existir, ou o `PRODUCER_UNKNOWN` que uma migração deixou no lugar dele; **sem
registro** é a chave ausente, ou seja, nada registrou execução alguma. `processed` é os dois
primeiros mais as falhas, e `failed` conta os carimbos que registram uma (`ERROR`; a falha do
thumbnail vive sob a chave `thumbnail_failed`, porque o livro dele não é um carimbo).

Os quatro números aparecem em **Carimbos (descrições)**, ao lado da fila e não embaixo dela, porque
respondem a uma pergunta diferente da de `pending`: o detalhamento é sobre o **livro inteiro** do
worker, enquanto `pending` é o predicado da fila, e os dois conjuntos não são o mesmo. Na coleção de
referência o card do NER lê **4.831** carimbados contra **4.813** na fila, e a diferença são as
**18** descrições que uma pessoa aprovou — a fila aplica `ai_writable_documents()`, então uma
descrição curada é contada no livro e nunca na fila. Quem lêsse o detalhamento como decomposição da
fila via 4.831 onde a fila dizia 4.813 e não tinha onde pôr a diferença.

Cinco dos nove carimbos carregam a **identidade do produtor** em vez de um status: uma impressão
digital da engine, do preset, de toda a configuração resolvida da engine, das versões instaladas das
bibliotecas daquele eixo e das opções comportamentais declaradas (`force`, `limit` e o `config`
reservado ficam de fora). A consequência é o ponto do desenho: mudar qualquer uma dessas coisas
devolve as unidades afetadas à fila **sozinho**, o que um `DONE` nunca poderia fazer — um bump do
`torch` invalidava todos os vetores enquanto o carimbo continuava atual e a fila continuava vazia. O
embedding compõe a identidade com o MD5 do texto efetivo, então uma edição humana também o
re-enfileira; o macro-category compõe com o hash do conjunto de rótulos. Dois produtores ficam
deliberadamente fora da identidade, porque lê-los custaria um import pesado ou uma chamada de rede no
caminho do painel: a versão do pacote do modelo spaCy (`pt_core_news_lg`) e o digest do modelo que o
servidor Ollama serve. Rode esses dois casos com `force`.

| Worker | O que está pendente | Carimbo de idempotência |
| --- | --- | --- |
| `transfer` | registros de staging sem linha no Acervo, ou cujo hash do conteúdo interpretado difere do gravado — exceto descrições que uma pessoa aprovou ou rejeitou | nenhum; um hash do registro de staging, mais `hierarchy_parent_v1` para um pai declarado |
| `cleaning` | documentos que as regras `REWRITE` ativas ainda não carimbaram; um documento pendente para duas regras conta duas vezes | `cleaning_rule_{rule_id}` |
| `ner` | documentos com texto em ao menos uma coluna extraída e sem o carimbo do produtor atual | `worker_ner_v2` (o valor é a identidade do produtor) |
| `typology` | documentos com texto e sem o carimbo do produtor atual — o carimbo assina o conjunto de tipologias ativas, então acrescentar, renomear ou aposentar uma tipologia alcança os documentos já classificados | `worker_typology_classifier_v2` (o valor é a identidade do produtor) |
| `thumbnail` | documentos com imagem de origem, sem URI no storage e sem marca de falha — todos os marcados, com `force` | nenhum; a coluna `storage_thumbnail_uri`, mais a marca `thumbnail_failed` |
| `conflict-judge` | **não é mensurável barato**: a fila é o produto trigram de tags × entidades, medido em 53 s no acervo real. O painel mostra o que já foi julgado | nenhum; a linha em `archive_ai_review_queue` |
| `macro-category` | tags sem categoria de assunto cujo carimbo não é o produtor atual (o conjunto de rótulos e o modelo estão nos dois) | `worker_macro_category_v1` (na tag; o valor é o conjunto de rótulos composto com a identidade do produtor) |
| `quality-validator` | documentos sem o carimbo do produtor atual, a menos que `force` esteja ligado | `worker_quality_validator_v1` (o valor é a identidade da regra `LLM_CHECK` ativa, ou de "sem modelo" — inclusive quando a engine da regra não pode ser construída, que é a execução que o validador de fato faz) |
| `embedding` | documentos cujo carimbo difere do MD5 do texto efetivo **mais** a identidade do produtor — a primeira execução, toda mudança de texto posterior e todo bump de modelo ou dependência | `worker_embedding_v1` (o valor é o MD5 seguido de `:` e da identidade) |

Um documento que o worker marcou como `ERROR` fica fora da fila comum: `force` é o caminho de volta,
e ele limpa a marca nas unidades que processa. Uma unidade carimbada por um produtor que não está
mais configurado volta a estar pendente — incluindo todo valor legado, leia ele ainda `"DONE"` ou o
`PRODUCER_UNKNOWN` para o qual a migração o renomeou. Essas linhas estavam pendentes antes da
renomeação e continuam pendentes depois dela, então a migração mudou o que o livro **diz** e não o que
a fila **faz**: a próxima execução as cura gravando uma impressão digital de verdade. É esse o ponto
da distinção — atribuição e relato, não a fila. A identidade da tipologia também assina o conjunto de
tipologias ativas, então depois desta atualização **toda** descrição carimbada fica pendente uma vez,
com ou sem tipologia: o acervo inteiro editável pela IA na primeira execução e, daí em diante, só o
que uma mudança de catálogo, modelo, coluna ou piso realmente moveu. A pré-visualização abaixo é como
medir isso antes de pagar.

O contador do `transfer` é o mais pesado: valida a tabela de staging inteira pelo mesmo port que o
transfer usa. É lido uma vez por carga do painel e não é consultado em laço.

## O runner

Desde a ADR 0014 os workers rodam no próprio processo; a API apenas enfileira. O runner reivindica as
linhas `QUEUED` e as executa:

```bash
uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
```

| Flag | Significado |
| --- | --- |
| `--name` | o nome humano no painel; o identificador é gerado (`name:<uuid curto>`) a menos que `--id` seja dado |
| `--workers` | os workers que este runner aceita, separados por vírgula; o padrão é o catálogo inteiro |
| `--concurrency` | quantas execuções ele executa de uma vez; 1 por padrão, porque os modelos são limitados por CPU/GPU |
| `--heartbeat-seconds`, `--lease-seconds` | o lease que ele renova e quanto tempo uma reivindicação sobrevive sem ele; 15/60 por padrão, e o heartbeat precisa ser menor |
| `--poll-seconds`, `--sweep-seconds` | de quanto em quanto procura trabalho e expira reivindicações; 2/30 por padrão |
| `--once` | reivindica e executa no máximo uma execução, e sai |
| `--drain-seconds` | espera até esse tempo pelas execuções em andamento antes de sair; o lease cobre o resto |

O runner se registra em `archive_worker_runners`, renova a própria linha com o mesmo heartbeat e
recusa um schema atrás do seu código. O painel o mostra — online/offline, o host, a versão, as
capacidades — e marca **sem runner** os workers que nenhum runner online aceita; uma execução
enfileirada para um deles espera. O banco é o único canal: a API nunca chama um runner.

## Executando um worker

### O runner unificado

Prefira o runner unificado, que expõe todos os workers por uma interface só. Rode da raiz do
repositório:

```bash
uv run python -m scrinalia.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --limit N --option key=value --engine-option key=value --by "quem"]
```

Por exemplo:

```bash
# Classifica a tipologia de toda descrição pendente, em lotes de 100.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --engine deberta_typology --preset cpu_local --batch 100 --by "ana"

# Testa um limiar medido pelo bench só nas primeiras 200 descrições.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --option confidence_threshold=0.6 --limit 200 --by "ana"

# Força o embedding de toda descrição, ignorando o hash do texto.
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true

# Sobrescreve o device da engine só nesta execução: um repasse ao construtor da engine.
uv run python -m scrinalia.domains.archive.workers.runner ner \
    --engine spacy_ner --engine-option device=cpu --by "ana"
```

| Flag | Significado |
| --- | --- |
| `<name>` | um dos nove nomes acima; qualquer outro valor é recusado com a lista de opções |
| `--engine X` | uma engine registrada do eixo do worker, por exemplo `spacy_ner`, `deberta_typology`, `ollama_judge` |
| `--preset Y` | um preset desse eixo, por exemplo `gpu`, `lemmatizer`, `cpu_local`, `gpu_cloud`, `xlm_roberta_local`, `gemma_4b_local`, `multilingual_minilm` |
| `--batch N` | tamanho do lote por transação, repassado aos workers que declaram `db_batch_size`; um worker sem isso registra no log que o valor foi ignorado |
| `--limit N` | teto de unidades desta execução, para os workers que declaram `limit` (`embedding`, `macro-category`, `ner`, `quality-validator`, `thumbnail`, `typology`); recusado nos demais, porque um teto que não faz nada em silêncio é pior do que nenhum teto. Ele conta tentativas, então uma fila de falhas ainda termina, e nunca é persistido |
| `--option key=value` | uma opção **declarada** do worker, repetível; uma chave que o worker não declara é recusada com a lista de opções dele, e `key` sem `=` é recusado |
| `--engine-option key=value` | repasse cru ao construtor da engine, repetível, para uma execução; nunca persistido, e as chaves não são enumeradas (a engine valida o valor) |
| `--by "quem"` | texto livre com quem está executando; a CLI roda no host e não tem sessão, então isso continua sendo um nome sem conta por trás |

O `--option` é validado contra a assinatura do `execute` do worker e convertido pelo tipo que ele
declara ali: `true`/`false` viram booleanos, um default inteiro faz o valor virar `int`, um default
float faz virar `float`. `--option confidence_threshold=0.6` portanto chega como número e alcança a
comparação; um valor que não pode ser lido (`0.6x` para um float, `talvez` para um booleano) é
recusado com uma frase antes de a execução começar, em vez de falhar no fundo dela. Uma chave que o
worker não declara é recusada: `--option colunas_to_classify=…` — o typo medido na #120 — vira uma
frase de `422` com as opções que o worker aceita, e não um padrão que falha depois no contador da
fila. Uma lista de colunas é conferida contra as colunas que o texto da IA tem (abaixo).

O `--engine-option` é a **exceção nomeada**: vai direto ao construtor da engine, para quem conhece a
biblioteca. Vale por execução e nunca é persistido, então um ajuste não vira padrão da instalação; as
chaves que o próprio eixo repassa são oferecidas como dica (`model`, `device`, `host`, `batch_size`,
`dimensions`, `disable`), e uma chave fora delas continua sendo repassada — a engine é quem valida o
valor. Só um worker cujo `execute` termina em `**engine_kwargs` tem a porta; `transfer`, `cleaning`,
`thumbnail` e `conflict-judge` não declaram repasse, e a execução é recusada se um for dado. O
`conflict-judge`, portanto, tira o host da configuração `OLLAMA_HOST_URL` (ou do default local), não
de uma flag.

Cinco coisas são sempre recusadas:

- `config` é um dataclass do runner (`NerRunnerConfig` e os irmãos), não um valor que uma linha de
  comando ou um corpo JSON possa carregar; um dicionário chegando ao `execute` falharia com erro de
  atributo em vez de uma frase. Passe os campos individuais.
- `source` e `storage` são **portas** (a origem do staging, o armazenamento de objetos), e
  `db`/`db_session` é a sessão que o runner abre: nenhuma delas viaja por JSON.
- `engine_name`, `preset` e `db_batch_size` têm campo próprio. São recusados dentro de `options`
  porque o runner aplica o mapa de extras *depois* do argumento resolvido, e um valor ali era uma
  segunda definição silenciosa do mesmo campo.
- `limit` é recusado como **padrão persistido** (`PUT …/settings`): ele limita uma execução, e um teto
  que sobrevivesse ao comando pararia toda execução seguinte em N unidades. `force` é um padrão
  legítimo — é o caminho de volta de uma marca que uma queda passageira deixou.
- `--engine`/`--preset` só fazem sentido para os workers cuja configuração vem da própria assinatura
  (`ner`, `typology`, `conflict-judge`, `macro-category`, `embedding`). `transfer`, `cleaning` e
  `thumbnail` não carregam modelo, e `quality-validator` tira a engine da regra `LLM_CHECK` ativa.

Toda execução pelo runner grava uma linha em `archive_worker_runs` (veja
[o ledger de execuções](#o-ledger-de-execucoes)).

### Executando o módulo de um worker diretamente

Cada `worker_*.py` também traz uma função `execute(db, ...)` e um bloco `__main__`, então um worker
isolado pode ser rodado durante o desenvolvimento:

```bash
uv run python -m scrinalia.domains.archive.workers.worker_ner
```

Uma execução direta é ferramenta de depuração, não o caminho de operação. Ela ignora o ledger, os
overrides persistidos, a trava de concorrência e a conversão de `--option`, e usa o `engine_name` e
o `preset` que o bloco `__main__` do módulo fixa (para `ner`, `db_batch_size=100` e, no resto, os
padrões da assinatura). Nada aparece no histórico de execuções, então nada avisa que ela aconteceu.

### A leitura da origem e o transform

As duas etapas à frente do Acervo não estão no runner nem no painel, e os comandos delas são o
caminho de operação dessas camadas, não um atalho de depuração:

```bash
# Lista os identificadores da origem na fila, percorrendo no máximo dez páginas.
uv run python -m scrinalia.domains.ingestion.worker discover --pages 10

# Lê a página de detalhe de no máximo cem dos identificadores que a fila guarda.
uv run python -m scrinalia.domains.ingestion.worker scrape --limit 100

# As duas fases num processo, que é o que um agendador rodaria.
uv run python -m scrinalia.domains.ingestion.worker run --pages 10 --limit 100

# Estrutura no máximo cem registros brutos no staging.
uv run python -m scrinalia.domains.staging.worker --limit 100
```

Os dois aceitam `--origin` para nomear a origem daquela execução; sem ele, o código é o que
`ACERVO_SOURCE` nomeia, e continua não havendo padrão. O `scrape` também aceita `--audit-ttl-days N`
para reler as descrições concluídas há mais de N dias, `--force-retry-fatal` para incluir as linhas
marcadas como `FATAL_ERROR`, `--ignore-sliding-window` para descartar as janelas de descoberta e de
TTL, e `--max-retries`, `--discovery-window-days` e `--scraped-ttl-days` para sobrepor a política
daquela execução.

**Uma execução limitada retoma sozinha.** A fila é ordenada por `last_scraped_at`, com as nunca
tentadas na frente, e todo desfecho — concluída, falha transitória, falha fatal — carimba esse
campo, então o lote que acabou de rodar vai para trás dos que ainda não rodaram. O transform tem
como chave o hash do payload bruto, então o que uma execução estruturou deixa de estar pendente.
`--limit 100` sobre uma fila de milhares pega os próximos cem na execução seguinte, e os dois
comandos registram no log quanto ainda falta quando terminam. A única exceção é uma leitura cuja
gravação sofre rollback: a linha mantém seu lugar e ocupa uma vaga em toda execução até que a
gravação dê certo.

`--force` reinterpreta todos os registros brutos, que é o que uma correção de parser exige, e
também ignora a comparação de hash da qual o transform avança, então uma execução forçada e
limitada não retoma sozinha. É para isso que existe `--after <description_id>`: a execução registra
no log o id em que a janela terminou e o comando para continuar dali. Não use `--after` sem
`--force`: sob a comparação de hash, pular à frente pularia registros pendentes em vez de registros
já estruturados.

Nenhum dos dois comandos escreve em `archive_worker_runs` — o ledger é do runner — e nenhum dos
dois aparece no painel de sistema, o que é uma mudança à parte.

## Configuração: o que uma execução realmente usa

A configuração efetiva segue uma precedência:

```text
argumento explícito  >  linha em archive_worker_settings  >  o padrão da assinatura do worker
```

A linha persistida (`archive_worker_settings`, uma por worker, com chave `worker_name`) é **parcial
de propósito**: um campo deixado `NULL` continua seguindo o código, então um preset renomeado numa
versão nova ainda alcança todo worker que ninguém sobrescreveu. Seus campos são `engine_name`,
`preset`, `db_batch_size`, `options`, `updated_by` e `updated_at`.

Toda escrita deixa uma revisão em `archive_worker_settings_revisions` (`before`, `after`,
`changed_by`, `changed_by_user_id`, `changed_at`), gravada na mesma transação da linha. Você pode
lê-las em `GET /api/v1/system/workers/{worker_name}/settings/revisions`. Apagar a linha
(`DELETE /api/v1/system/workers/{worker_name}/settings`) faz o worker voltar a seguir o código, e é
idempotente.

`GET /api/v1/system/workers` é a forma de ver a configuração efetiva sem rodar nada. Cada worker
traz o `engine_name`, o `preset`, o `db_batch_size` e as `options` resolvidos, o `overridden` (se
existe linha — um campo pode ser `None` de propósito), o dicionário `config` resolvido, os
`available_engines` com seus presets, o `declared_options` que o worker aceita e o
`engine_option_names` que o eixo dele sabe repassar, e uma `note`. Esse dicionário vem do
`describe_config` de cada registro de engine, o **gêmeo somente-leitura do `get_engine`**: resolve o preset e os overrides e
devolve o dicionário sem instanciar a engine, então o painel consegue responder "com qual modelo
isto vai rodar?" para um worker que nunca rodou — sem carregar o modelo.

Para `quality-validator`, o `engine_source` é `llm_check_rule`: a engine e o preset vêm da regra
`LLM_CHECK` ativa, e as rotas de configuração e de disparo recusam defini-las ali, porque um segundo
lugar para escolher a mesma engine seria uma segunda fonte de verdade. Sem regra ativa, o worker roda
apenas a validação determinística, e o painel diz isso na `note`.

### O que um worker aceita

O que um worker aceita é a assinatura do `execute` dele, e a API publica isso: `GET
/api/v1/system/workers` e `/workers/settings` trazem `declared_options` — o nome, o tipo de controle
(`boolean`, `integer`, `number`, `text`, `list`, `columns`), o default da assinatura, se a opção é um
padrão persistido ou de uma execução (`scope: "run"` para `limit`) e, para uma lista de colunas, os
valores que ela admite. As telas de configuração e de execução renderizam essa lista como campos, então
o formulário não pode oferecer uma chave que a escrita recusaria, e o arquivista não precisa saber que
o parâmetro se chama `columns_to_classify`.

Dois nomes de opção carregam o texto que um worker de IA lê: **`columns_to_extract`** (`ner`) e
**`columns_to_classify`** (`typology`). Os valores deles são as colunas de `AI_TEXT_COLUMNS`:

`original_title`, `final_title`, `scope_content`, `admin_bio_history`, `provenance`.

Essa tupla é a definição única do que a IA pode ler: é o que a composição em SQL compõe, o que os
benches de avaliação conferem em `--config engine:preset:colunas` e o que a escrita confere na opção.
Um nome fora dela é recusado quando o padrão é salvo, com as conhecidas na frase; uma lista vazia
também é recusada, porque um worker sem coluna não tem texto para ler. Deixar o campo vazio mantém o
default do código (`NerRunnerConfig.columns_to_extract`,
`TypologyRunnerConfig.columns_to_classify`), que é o valor que o ledger da execução registra.

Uma linha salva antes desta regra não é um erro novo: a leitura ignora a opção que não consegue mais
honrar e põe o motivo em `note` ("Padrão salvo ignorado — …"), então o painel responde com o default
do código em vez de derrubar o contador da fila. Salvar a tela de novo cura a linha.

### Testar uma configuração antes de salvá-la

Um padrão salvo não é só uma preferência: como a fila é chaveada pela identidade do produtor, mudar a
engine, o preset ou uma opção declarada (um `confidence_threshold`, as colunas lidas) devolve
unidades à fila sozinho. `POST /api/v1/system/workers/{worker_name}/queue/preview` responde quantas,
para uma configuração que nunca foi escrita, com a mesma precedência que uma execução usa. O corpo é o
corpo da configuração, então a tela pré-visualiza exatamente o que salvaria, e a resposta é `pending`
mais um `pending_reason` para o worker cuja fila não é mensurável (`conflict-judge`).

Medido no acervo de referência, com os documentos da tipologia carimbados pelo produtor que está no
código: a configuração padrão responde `0 na fila`, e propor `{"confidence_threshold": 0.9}` responde
`4.465` — o limiar faz parte da identidade, então os documentos que o limiar de 0.40 settleou estão
pendentes sob o de 0.90, e nada foi salvo. Esse número é também o que a próxima execução custaria, e é
por isso que a tela de configuração o coloca atrás de *Conferir impacto* em vez de deixá-lo ser
descoberto depois da escrita.

A CLI não tem rota de pré-visualização; `--limit N` numa execução é a outra forma de limitar o mesmo
custo.

## O painel de operação

O painel é a superfície `/api/v1/system/*` e os quatro cartões de `/configuracoes`, sob *Operação*, na
SPA: o menu não os carrega mais (issue #22).

| Rota | Método | Permissão | O que faz |
| --- | --- | --- | --- |
| `/api/v1/system/workers` | `GET` | autenticado | os nove workers com configuração, números de fila, última execução/execução ativa e o registro de runners, numa requisição só |
| `/api/v1/system/workers/settings` | `GET` | autenticado | os padrões persistidos dos nove workers, sem os contadores de fila (issue #53) |
| `/api/v1/system/workers/{worker_name}/queue/preview` | `POST` | autenticado | o pendente de uma configuração **proposta**, calculado sem escrever |
| `/api/v1/system/workers/{worker_name}/runs` | `POST` | `OPERATE` | enfileira uma execução com overrides só para ela e responde `201` na hora |
| `/api/v1/system/workers/{worker_name}/settings` | `PUT` | `OPERATE` | persiste o padrão de engine/preset/batch/options |
| `/api/v1/system/workers/{worker_name}/settings` | `DELETE` | `OPERATE` | apaga o override para o worker voltar a seguir o código |
| `/api/v1/system/workers/{worker_name}/settings/revisions` | `GET` | autenticado | quem mudou o quê, quando |
| `/api/v1/system/runs` | `GET` | autenticado | o ledger de execuções, mais recente primeiro; filtros `worker`, `status`, `fingerprint`, `limit`, `offset` |
| `/api/v1/system/failures` | `GET` | autenticado | as causas raiz agrupadas; filtros `days` (padrão 30), `worker`, `limit` |
| `/api/v1/system/health` | `GET` | `OPERATE` | banco, modelos do Ollama, storage de objetos e o processo |

Só o `ADMIN` carrega `OPERATE`; `CURATOR` e `VIEWER` leem os workers, o ledger e as falhas, mas não
disparam execução nem mudam padrão.

A SPA espelha isso, como cartões de `/configuracoes` sob *Operação*:

| Tela | Mostra |
| --- | --- |
| `/sistema/workers` | os nove workers: engine, preset e modelo, a fila, o que o carimbo de cada um nomeia (com produtor, sem produtor conhecido, sem registro) e um botão **Enfileirar execução**; acima deles, os cartões dos runners (online, host, versão, concorrência, capacidades, último sinal) e um aviso quando nenhum está online. Um worker que nenhum runner online aceita aparece como **sem runner** — a linha ainda enfileira e espera. A configuração efetiva aqui é só leitura |
| `/configuracoes/workers` | o padrão persistido de cada worker e suas revisões, com salvar e remover — a escrita que o painel carregava |
| `/sistema/execucoes` | o ledger de execuções e as falhas dos últimos 30 dias agrupadas por causa raiz; clicar numa causa filtra o ledger para as ocorrências dela |
| `/sistema/diagnostico` | banco, modelos do Ollama, storage das miniaturas e a configuração efetiva do processo |

A tela consulta a cada 5 s enquanto uma execução está rodando e a cada 15 s enquanto uma está na fila,
porque o contador do `transfer` faz uma chamada a `/system/workers` custar cerca de dois segundos no
acervo real; ociosa, ela não consulta. A `/configuracoes/workers` lê `/system/workers/settings`, que
resolve a mesma configuração e não conta fila nenhuma — a separação existe para que uma tela que não
mostra números não pague por eles.

### Saúde: três endpoints, três perguntas

Eles não são intercambiáveis, e juntá-los é o erro a evitar.

| Endpoint | Pergunta | Comportamento |
| --- | --- | --- |
| `GET /health/live` | o processo está vivo? | não toca em nada, sempre `200` enquanto o processo responde; fora do documento OpenAPI |
| `GET /health/ready` | esta instância pode receber tráfego? | roda `SELECT 1`; `200`, ou `503` quando o banco não responde; também fora de `/api/v1` e fora do contrato |
| `GET /api/v1/system/health` | qual peça está fora? | o painel humano: contagens do banco, os modelos do Ollama que os presets exigem e quais faltam, o bucket do storage e a configuração efetiva do processo — segredos como presença, nunca como valor |

Uma sonda de liveness que consulta o banco reiniciaria a API sempre que o banco reiniciasse, e é por
isso que `live` não toca em nada. A sonda de readiness tem engine própria, com timeout de conexão e
de statement, então uma sonda contra um host inalcançável falha rápido em vez de pendurar pelo
timeout de TCP do sistema operacional.

## O ledger de execuções

`archive_worker_runs` tem uma linha por execução, tanto da CLI quanto do painel: o ledger é sobre o
worker, não sobre o botão que o iniciou. Uma linha carrega `worker_name`, `status`, `trigger` (`CLI`
ou `API`), `requested_by` (e `requested_by_user_id`), `engine_name`, `preset`, o `request` validado
(o que um runner reproduz), o `config` resolvido, as **`options` efetivas do worker**, `queued_at`,
`runner_id`, `started_at`, `heartbeat_at`, `lease_expires_at`, `finished_at`, `duration_ms`, `error`
e o `error_fingerprint` gerado.

O `config` responde "com qual modelo?" e as `options` respondem "sobre qual texto, com qual limiar?" —
as duas metades de uma execução. As `options` são resolvidas **quando a execução começa**, porque o
default de uma lista de colunas vive no dataclass do runner do próprio worker e só ele sabe quais
colunas leu; uma linha enfileirada e ainda não iniciada, ou escrita antes de a coluna existir, carrega
o default vazio e a tela do ledger diz "opções não registradas nesta execução". A identidade do
produtor faz o hash dos mesmos valores no carimbo, então a linha é a metade legível desse hash.

Os status são `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED` e `INTERRUPTED`. A linha `QUEUED` é comitada
pela **sessão própria do ledger antes de a requisição retornar**, para que um runner externo possa
reivindicá-la; a reivindicação é uma instrução (`FOR UPDATE SKIP LOCKED`) que também grava `runner_id`,
`started_at`, `heartbeat_at` e `lease_expires_at`. Uma linha `QUEUED` é o item de trabalho; a API
apenas enfileira.

`uq_worker_run_active` é um **índice único parcial** sobre `(worker_name)` quando o status é `QUEUED`
ou `RUNNING`. É ele, e não um lock de processo, a trava de concorrência: no máximo uma execução por
worker em andamento, entre processos e através de um reload. Um segundo envio vira um
`IntegrityError` que a API transforma em `409` com uma frase ("Já existe uma execução em andamento
para o worker '…'"). A CLI chega ao mesmo erro, mas não tem tratamento para ele, então termina com o
traceback em vez da frase.

Um runner reivindica uma linha `QUEUED` e renova o lease enquanto roda; `--concurrency` decide quantas
executa de uma vez, e os workers são limitados por CPU/GPU, então o padrão é um. Ele **não é um
agendador**: sem retry, sem cron, sem prioridade. A fila é um slot por worker, então uma segunda
execução espera no ledger ou responde `409`.

## Reprocessar um documento ou um lote

Rodar um worker de novo é seguro e incremental: a fila dele é a ausência do carimbo do produtor
atual, então uma segunda execução toca só o que ainda está pendente. O que devolve uma unidade à fila:

- **o texto mudou** — uma edição humana ou um trecho de texto aprovado/editado/desfeito. O
  `embedding` se re-enfileira sozinho, porque o carimbo dele carrega o MD5 do texto efetivo; os
  carimbos dependentes do texto (`worker_ner_v2`, `worker_typology_classifier_v2`,
  `worker_quality_validator_v1`) são invalidados pelo serviço de qualidade de texto.
- **o produtor mudou** — outra engine, outro preset, outro `confidence_threshold`, outro conjunto de
  colunas, uma atualização de `torch`/`transformers`/`sentence-transformers`/`spaCy`, ou a regra
  `LLM_CHECK` de onde o validador de qualidade tira a engine. Tudo isso está dentro da identidade,
  então as unidades afetadas voltam sozinhas; a pré-visualização acima diz quantas antes de a mudança
  ser salva.
- **a origem mudou** — o `transfer` reescreve a descrição quando o hash do conteúdo interpretado
  muda, e a escrita zera os carimbos de IA, então os enriquecimentos precisam rodar de novo.
- **o catálogo mudou** — reescrever um rótulo de assunto muda o hash do conjunto de rótulos, então as
  tags afetadas voltam à fila do `macro-category`, e acrescentar, renomear ou aposentar uma tipologia
  faz o mesmo com as descrições: a identidade da tipologia assina o conjunto de rótulos ativas e o
  carimbo é o único portão do lado da resposta, então uma descrição que já carrega tipologia volta
  quando o catálogo se move. Uma execução que então recusa **limpa** a resposta que encontrou — uma
  resposta escrita por outro produtor não sobrevive a uma recusa deste, ou subir o piso releria o
  acervo sem mudar rótulo nenhum. Os motivos do validador de qualidade também dependem do catálogo, e
  é para esse caso que o `force` existe.
- **`force=true`** — `embedding`, `macro-category`, `ner`, `quality-validator`, `thumbnail` e
  `typology` aceitam e ignoram o próprio carimbo; o `macro-category` continua sem tocar numa tag que
  já tem categoria, enquanto o `typology` relê uma descrição que já carrega tipologia, porque quem
  decide é o carimbo e não a resposta. É o caminho
  de volta de um motivo que um hash não vê — uma regra de sinônimos editada, uma exclusão curada, um
  prompt — e de uma marca de falha: as unidades que ele processa são carimbadas com o produtor atual,
  o que limpa o `ERROR`. No `thumbnail` ele também traz de volta os documentos marcados como
  `thumbnail_failed`, que é a saída de um bucket que estava fora durante uma execução: a marca existe
  para um link morto não ficar em laço, não para tornar a queda permanente. Uma execução forçada
  avança por cursor, então termina; `--limit N` limita ainda mais.

```bash
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true
uv run python -m scrinalia.domains.archive.workers.runner typology --option force=true --limit 200
uv run python -m scrinalia.domains.archive.workers.runner quality-validator --option force=true
uv run python -m scrinalia.domains.archive.workers.runner thumbnail --option force=true
```

!!! warning "A janela de reprocessamento fecha no primeiro registro aprovado por uma pessoa"
    `HUMAN_APPROVED` é a proteção: `ai_writable_documents()` a exclui, e `cleaning`, `ner`,
    `typology`, `thumbnail` e `quality-validator` filtram por ela — `force` incluído, e é por isso que
    uma execução forçada relê todo documento *gravável pela IA*, não todo documento. O `transfer` se
    recusa a sobrescrever uma descrição aprovada mesmo quando o hash da origem mudou. As duas exceções
    documentadas são o trabalho derivado — o `embedding`, que re-embeda um texto mudado, e o
    `macro-category`, cuja unidade é a tag e cuja fila é "ainda sem categoria", então a categoria de um
    curador nunca é reescrita.

Não há **rota nem flag que limpe um carimbo** para os workers que não aceitam `force` (`transfer`,
`cleaning`, `conflict-judge`): para devolver um documento à fila ali, é preciso remover aquela chave do
`execution_log` dele no banco. Trate isso como reparo, não como operação de rotina.

## Execuções INTERRUPTED

Uma execução fica `RUNNING` sob um lease. O runner o renova a cada `--heartbeat-seconds`; quando o
lease vence — o runner morreu, ou o sinal parou — o próximo runner (ou a próxima CLI, que tem o mesmo
lease) marca a linha como `INTERRUPTED`, com `finished_at` e o texto "O runner parou de enviar sinal
antes do fim desta execução." O boot da API não repara nada, então vários processos da API são
seguros. A varredura toca só as linhas vencidas: a reivindicação viva de um irmão nunca é fechada.

Nada é retentado automaticamente. Depois de uma execução `INTERRUPTED`:

1. Leia `GET /api/v1/system/runs?status=INTERRUPTED` (ou o painel) e abra o erro da linha.
2. Corrija a causa — um modelo do Ollama faltando, um bucket inalcançável, um banco que estava fora.
3. Dispare o worker de novo. Os carimbos por unidade são o que torna isso seguro: a nova execução lê
   só o que a interrompida não terminou.

A execução enfileirada sem runner online espera, e o painel diz isso. O cancelamento é a #72 e a
política de retry é a #43: a ADR 0014 fixa o vocabulário, as issues o implementam.

## Agendamento

Hoje não existe agendador. Na prática, isso significa que um cron externo — ou qualquer orquestrador
que você já opere — tem de pendurar em uma das duas entradas:

```bash
# No host, a partir da raiz do repositório.
uv run python -m scrinalia.domains.archive.workers.runner embedding --by "cron"

# Ou pela API, que enfileira a execução e retorna na hora.
curl -sS -X POST "http://localhost:8000/api/v1/system/workers/embedding/runs" \
    -H "Content-Type: application/json" -H "Origin: http://localhost:8000" \
    -b "scrinalia_session=<cookie>" \
    -d '{"db_batch_size": 100}'
```

Dois avisos que o desenho deixa explícitos:

- **Uma execução pode durar mais que o intervalo do cron.** A rota responde `201` assim que a
  execução entra na fila, então o cron não tem como saber se a anterior terminou. Agende num período
  maior que uma execução, ou leia o ledger antes de disparar.
- **A concorrência é recusada pelo banco, não por um lock.** O índice único parcial rejeita a segunda
  execução em andamento do mesmo worker; a API responde `409` e a CLI levanta a mesma recusa. Nada no
  processo serializa as chamadas, então a garantia vale entre processos, através de um reload e mesmo
  quando a CLI e o painel discordam sobre quem manda. Disparar um worker **diferente** é aceito
  mesmo com outro rodando — a linha fica na fila e um runner a reivindica quando tem folga — porque o
  índice limita a uma execução por worker; o `--concurrency` do runner decide quantas ele executa de
  uma vez.

A rota da API é uma mutação, então também exige sessão de `ADMIN` autenticada e cabeçalho `Origin` de
mesma origem. Um cron em host remoto é mais simples pela CLI.

## Lendo as falhas

`GET /api/v1/system/failures` agrupa **os dois** ledgers de erro pela mesma chave: a coluna gerada
`error_fingerprint`, calculada pelo PostgreSQL a partir do texto de erro em `archive_worker_runs` e
em `archive_api_errors`. Uma causa raiz que quebrou uma execução de worker e uma requisição HTTP
aparece uma vez, com `sources` (`WORKER`, `API` ou os dois) dizendo onde foi vista.

| Campo | Significado |
| --- | --- |
| `fingerprint` | a identidade do grupo e o filtro que leva de volta às ocorrências |
| `sample` | a ocorrência mais recente, sem normalização — o fingerprint lê como chave, não como frase |
| `occurrences` | quantas vezes aconteceu na janela |
| `first_seen`, `last_seen` | a janela em que aconteceu |
| `sources` | de qual(is) ledger(s) veio |
| `worker_names` | os workers que quebrou, quando houver |
| `last_path`, `last_request_id` | a rota e a referência da requisição da última ocorrência de **API** do grupo |

O `total` da resposta é o número de **grupos** na janela, não a soma das ocorrências. De propósito
**não há total geral** entre os grupos: uma execução de worker e uma requisição HTTP são unidades
diferentes, e somá-las produziria um número sobre o qual ninguém age.

Os dois detalhes que tornam a leitura útil:

- `last_path`/`last_request_id` vêm da última ocorrência de **API** do grupo, não da última
  ocorrência de qualquer tipo. Um grupo misto cuja linha mais nova é uma execução de worker ainda
  tem uma rota e uma referência que vale mostrar.
- O filtro `worker` recorta as **linhas**, não os grupos. Um grupo que também quebrou a API mantém só
  as ocorrências de worker, que é o sentido de "este worker falhou"; um grupo só de API sai fora.

O `last_request_id` é a costura com o log: o mesmo valor está no registro de `ui_stream.jsonl` da
requisição, então um grupo leva ao traceback.

## Logs

O logging é configurado por dois ajustes:

| Ajuste | Padrão | Significado |
| --- | --- | --- |
| `LOG_DIR` | `logs` | o diretório onde os sinks de arquivo são escritos |
| `LOG_LEVEL` | `INFO` | o nível do sink de console e do stream estruturado |

Três sinks são instalados:

- o terminal, em `LOG_LEVEL`;
- `logs/critical.log`, em `ERROR`, rotacionado em 10 MB e mantido por 30 dias — o arquivo de
  post-mortem;
- `logs/ui_stream.jsonl`, em `LOG_LEVEL`, JSON serializado, rotacionado em 50 MB e mantido por 7
  dias — o stream estruturado que carrega o id da requisição em todo registro.

Toda requisição sai com um `X-Request-ID`: o que o cliente mandou (aceito só quando tem no máximo 64
caracteres de `[A-Za-z0-9._:-]`) ou um gerado. Ele é devolvido no cabeçalho da resposta e amarrado ao
contexto de log, então todo registro escrito enquanto aquela requisição era servida o carrega —
inclusive o que o handler de exceção não tratada escreve. A SPA o mostra como "referência" ao lado de
um erro.

A linha de acesso é escrita pelo mesmo middleware, não pelo uvicorn, porque o registro do uvicorn não
tem id de requisição:

```text
↔️ GET /api/v1/system/workers -> 200 em 1842.3 ms
❌ POST /api/v1/system/workers/ner/runs -> 500 em 12.4 ms
```

Um `5xx` é aviso, o resto é linha de informação. As duas sondas do orquestrador (`/health/live` e
`/health/ready`) ficam fora da linha de acesso — um orquestrador pergunta a cada poucos segundos e
rotacionaria um arquivo de 50 MB só com "200 OK" — mas não ficam fora da correlação.

## Recuperar acesso

A recuperação de senha é guiada pelo administrador, e qual porta se aplica é a única pergunta:

- **Alguém esqueceu a senha e um administrador consegue entrar.** O administrador abre
  *Configurações → Usuários*, encontra a conta e usa **redefinir senha** — um botão na própria linha
  da conta, então a redefinição é alcançada sem expandir a ficha. A senha digitada ali é
  **temporária**: a conta a troca no primeiro acesso. A redefinição também **encerra todas as sessões**
  dessa conta e **destrava um bloqueio**, que é o único caso que a tela sozinha resolve. Ela não tem
  desfazer.
- **Nenhum administrador consegue entrar** — o último ativo está bloqueado, desativado ou não existe
  mais. Aí a operação que resolveria é justamente a que ninguém alcança, e a entrada é o terminal do
  servidor:

```bash
# Quais contas existem e qual está ativa. O endereço é o que os comandos abaixo recebem.
uv run python -m scrinalia.domains.identity.cli list

# Uma senha explícita. Ela é gravada como veio; a conta não é obrigada a trocá-la no primeiro acesso.
uv run python -m scrinalia.domains.identity.cli reset-password --email pessoa@instituicao.org --password 'a nova senha'

# Sem --password, ele gera uma, imprime uma vez e marca a conta como temporária.
uv run python -m scrinalia.domains.identity.cli reset-password --email pessoa@instituicao.org

# Uma conta desativada é reativada antes de conseguir entrar de novo.
uv run python -m scrinalia.domains.identity.cli activate --email pessoa@instituicao.org
```

O CLI roda no host contra o mesmo banco e chama **o mesmo serviço** que a API chama, então a política
de senha, a revogação de sessões e a guarda de último administrador por trás de `deactivate` e
`set-role` são o mesmo código, e não uma segunda implementação com menos verificações. Ele também é
como a primeira conta de administrador é criada ([Instalação e implantação](install.md)).

Duas coisas deliberadamente não existem, e a tela de entrada diz isso em vez de fingir o contrário:
não há **redefinição por e-mail** (nada configura SMTP, e a ADR 0009 deixa a recuperação de
autosserviço fora de escopo), e não há **tabela de tokens de redefinição** para guardar, expirar ou
vazar. O *Esqueci minha senha* da tela declara esses dois caminhos e não promete mensagem nenhuma.

## Medir o acervo

Duas tabelas respondem a duas perguntas diferentes, e um número tirado da tabela errada engana.

`execution_log` diz **se um worker passou por uma unidade**: é o carimbo de onde a fila é construída.
`archive_worker_runs` diz **o que rodou, quando, com que engine e preset, sobre quais opções, quanto
demorou e como
terminou** (`SUCCESS`, `FAILED`, `INTERRUPTED`). Uma contagem de carimbo vazia é um fato sobre a fila;
a linha no ledger é o fato sobre a execução que explica a fila — uma etapa em zero e uma execução
interrompida na subida são o mesmo evento visto de duas tabelas.

Esta é a consulta com que o acervo de referência foi medido. Rode no banco da própria instalação e
trate todo número como uma medição com data, não como uma constante:

```bash
docker exec <container> psql -U <user> -d <database> -t -A -F' | ' -c "
SELECT 'descrições', count(*)::text FROM archive_documents
UNION ALL SELECT 'com pai', count(*)::text FROM archive_documents WHERE parent_id IS NOT NULL
UNION ALL SELECT 'sem nível', count(*)::text FROM archive_documents WHERE level_id IS NULL
UNION ALL SELECT 'tags', count(*)::text FROM archive_tags
UNION ALL SELECT 'tags sem categoria', count(*)::text FROM archive_tags WHERE macro_category_id IS NULL
UNION ALL SELECT 'propostas sugeridas', count(*)::text FROM archive_tag_merge_proposals WHERE status='SUGGESTED'
UNION ALL SELECT 'propostas aplicadas', count(*)::text FROM archive_tag_merge_proposals WHERE status='APPLIED'
UNION ALL SELECT 'rungs decididos', count(*)::text FROM archive_hierarchy_node_plans WHERE status <> 'SUGGESTED'
UNION ALL SELECT 'rungs no total', count(*)::text FROM archive_hierarchy_node_plans
UNION ALL SELECT 'ner_v2', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_ner_v2'
UNION ALL SELECT 'typology_v2', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_typology_classifier_v2'
UNION ALL SELECT 'macro_v1 (tags)', count(*)::text FROM archive_tags WHERE execution_log ? 'worker_macro_category_v1'
UNION ALL SELECT 'embedding_v1', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_embedding_v1'
UNION ALL SELECT 'quality_validator_v1', count(*)::text FROM archive_documents WHERE execution_log ? 'worker_quality_validator_v1'
UNION ALL SELECT 'publicados', count(*)::text FROM archive_documents WHERE is_published
UNION ALL SELECT 'revisões humanas', count(*)::text FROM archive_document_revisions;"
```

Uma armadilha vale saber antes de ler esses números: `?` diz que a chave **existe**, não que ela está
atual. Como os carimbos chaveados por identidade carregam o produtor, um documento carimbado por outro
modelo, por uma dependência mais antiga ou por outro limiar conta aqui e continua pendente para a
configuração que está no código — a coluna `pending` do painel e a pré-visualização de fila são o que
responde *essa* pergunta. As contagens cruas servem para "este worker já passou por este acervo".

## O site da documentação

Estes guias são publicados em <https://cassiodalla.github.io/Scrinalia/> — inglês na raiz, português
em `/pt/` — e **quem publica é a CI; não é uma pessoa.** O job `docs` constrói o site com
`mkdocs build --strict` sobre o histórico completo (o relatório de freshness é um relatório *contra o
git*, ADR 0010), envia `site/` como artefato do Pages, e o job `docs-publish` publica exatamente esse
artefato. A decisão, e as alternativas que ela recusou, estão na
[ADR 0012](../adr/0012-the-documentation-site-is-published-by-ci.md).

Três consequências valem antes de mexer num workflow ou no tema:

- **Só um push para `main` publica.** Um merge em `dev` constrói o site e não publica nada: o site é
  a documentação da **versão**, e `main` é o ramo que se move numa versão. O ambiente `github-pages`
  confia em `main` — e no ramo `gh-pages` que a publicação manual usava — então um deploy a partir de
  `dev` exigiria mudar essa política antes.
- **Repetir a execução do workflow é a recuperação.** O deploy pega o artefato que a mesma execução
  construiu, então uma falha passageira se resolve com "re-run jobs". Não existe passo
  `mkdocs gh-deploy` e `gh-pages` não é mais a origem do site: publicar à mão deixou de ser um
  caminho, que é o que impede o site publicado de ser uma versão mais velha que a tag.
- **O tema é a identidade do sistema**, e vive em dois lugares presos um ao outro: `docs/assets/` (a
  marca, o favicon, a PT Serif auto-hospedada com a licença) e
  `docs/assets/stylesheets/scrinalia.css`, que carrega os tokens de `apps/curator/src/styles.css`.
  `testing/unit/docs/test_docs_brand.py` falha quando falta um arquivo que o `mkdocs.yml` nomeia — o
  `--strict` **não** pega isso — ou quando uma cópia se afasta do arquivo original do curador.

## Limites conhecidos e trade-offs aceitos

São medidos, aceitos e não estão esperando correção. Estão aqui para o operador saber que
comportamento esperar, e para um limite já pago não ser lido como defeito.

- **Ninguém é avisado.** A observabilidade é o painel, o ledger de execuções e os grupos de falha; um
  serviço externo de alerta está deliberadamente fora do sistema (ADR 0005). Uma causa raiz nova é
  encontrada por quem abre a tela, não por uma notificação.
- **O runner alcança o banco.** Um runner em outra máquina precisa de um caminho privado até o
  PostgreSQL e de uma credencial; o `DB_*` da API pode ficar local (ADR 0014). A role de menor
  privilégio opcional e o túnel estão no [guia de instalação](install.md#a-rede-e-a-credencial).
- **O lease não é um fencing token.** Um runner que perdeu o lease ainda pode escrever o acervo até o
  worker parar; os carimbos tornam a re-execução idempotente e a linha do ledger é cercada, mas uma
  execução duplicada depois de um lease vencido é possível. Um fence rígido é trabalho futuro.
- **A fila é um slot por worker.** Uma segunda execução de um worker com uma em andamento responde
  `409`, e um agendamento precisa coalescer; backlog ou prioridade não é o que esta fila é.
- **Ainda não há retry nem cancelamento.** Uma execução que falhou continua falha e uma em andamento
  não pode ser parada pelo painel até a #43/#72; uma interrompida é visível e um novo disparo é seguro.
- **O `path` do arranjo não é garantido pelo banco.** A coluna é materializada pelo serviço, então um
  `UPDATE` escrito à mão pode divergi-la da árvore; o diagnóstico `PATH_DIVERGENCE` é o que encontra.
  Não escreva `path` diretamente — passe pelas rotas que são donas da movimentação.
- **A autenticação tem limites conscientes.** O limitador de tentativas de login é **por processo** e
  zera no restart, e é por isso que a defesa durável é a coluna de bloqueio por conta; revogar uma
  sessão registra que ela foi revogada, não **quem** revogou; e OIDC/SSO, segundo fator e recuperação
  de senha por e-mail estão fora de escopo (ADR 0009). A recuperação é o administrador ou o CLI no
  host (veja [Recuperar acesso](#recuperar-acesso)). **A primeira conta é uma janela.** Enquanto a `auth_users` estiver vazia, o
  `POST /api/v1/setup/admin` é público e quem alcançar a instância primeiro pode criar o
  administrador; o lock de tabela torna duas tentativas simultâneas seguras, e nada torna a janela
  segura (ADR 0011). Configure a instância antes de expô-la, e leia o `GET /api/v1/setup/status` —
  `{"needs_setup": true}` numa instância acessível é um convite.
- **O contrato não declara o cookie de sessão.** O documento OpenAPI não carrega um esquema
  `security` para ele, porque uma exigência global também marcaria as rotas de difusão e as sondas de
  saúde como protegidas (ADR 0009). Um cliente gerado não consegue descobrir a exigência; ele recebe
  401 como qualquer requisição anônima.
- **A ordenação depende do modo, e essa é uma decisão do arquivista.** Uma busca semântica que
  **encontra mais** não é uma busca que **ordena melhor**: a ordem lexical ganha quando o termo é
  exato, a semântica quando o assunto é conhecido mas o vocabulário do fundo não, e o modo híbrido
  funde as duas para que a escolha não seja necessária. Os três modos e quando preferir cada um estão
  no guia de curadoria, e `testing/evaluation/retrieval_modes.py` mede os três por estrato de consulta.
