---
translation_of: guides/operate.md
---

# Operação

Esta página é para quem opera a máquina no dia a dia: quais workers existem, em que ordem rodam,
como disparar um, como a configuração efetiva é resolvida, o que o painel de sistema mostra e o que
fazer quando algo quebra. Instalar e configurar o sistema está em
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
| 2 | `cleaning` | `worker_cleaning_regex` | documento × regra `REWRITE` ativa | sim | — |
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
- **`thumbnail`** baixa a imagem original e guarda uma miniatura no storage de objetos.
- **`conflict-judge`** compara o vocabulário de tags com o de entidades e consulta o LLM local para
  decidir se o termo ambíguo é assunto ou nome próprio. Todo veredicto, automático ou enviado a uma
  pessoa, deixa uma linha em `archive_ai_review_queue`.
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
`execute`. O painel nunca o re-deriva. `pending` é quantas unidades a próxima execução leria;
`processed` é quantas carregam o carimbo do worker; `failed` conta os carimbos que registram falha
(`ERROR`, ou a marca `thumbnail_failed`).

| Worker | O que está pendente | Carimbo de idempotência |
| --- | --- | --- |
| `transfer` | registros de staging sem linha no Acervo, ou cujo hash do conteúdo interpretado difere do gravado — exceto descrições que uma pessoa aprovou ou rejeitou | nenhum; um hash do registro de staging, mais `hierarchy_parent_v1` para um pai declarado |
| `cleaning` | documentos que as regras `REWRITE` ativas ainda não carimbaram; um documento pendente para duas regras conta duas vezes | `cleaning_rule_{rule_id}` |
| `ner` | documentos sem o carimbo que têm texto em ao menos uma coluna extraída | `worker_ner_v2` |
| `typology` | documentos sem tipologia e sem o carimbo que têm texto | `worker_typology_classifier_v2` |
| `thumbnail` | documentos com imagem de origem, sem URI no storage e sem marca de falha — todos os marcados, com `force` | nenhum; a coluna `storage_thumbnail_uri`, mais a marca `thumbnail_failed` |
| `conflict-judge` | **não é mensurável barato**: a fila é o produto trigram de tags × entidades, medido em 53 s no acervo real. O painel mostra o que já foi julgado | nenhum; a linha em `archive_ai_review_queue` |
| `macro-category` | tags sem categoria de assunto cujo carimbo não carrega o conjunto de rótulos atual | `worker_macro_category_v1` (na tag; o valor é o hash do conjunto de rótulos) |
| `quality-validator` | documentos sem o carimbo, a menos que `force` esteja ligado | `worker_quality_validator_v1` |
| `embedding` | documentos cujo carimbo difere do MD5 do texto efetivo — a primeira execução e toda mudança de texto posterior | `worker_embedding_v1` (o valor é o MD5 do texto embedado) |

O contador do `transfer` é o mais pesado: valida a tabela de staging inteira pelo mesmo port que o
transfer usa. É lido uma vez por carga do painel e não é consultado em laço.

## Executando um worker

### O runner unificado

Prefira o runner unificado, que expõe todos os workers por uma interface só. Rode da raiz do
repositório:

```bash
uv run python -m scrinalia.domains.archive.workers.runner <name> \
    [--engine X --preset Y --batch N --option key=value --by "quem"]
```

Por exemplo:

```bash
# Classifica a tipologia de toda descrição pendente, em lotes de 100.
uv run python -m scrinalia.domains.archive.workers.runner typology \
    --engine deberta_typology --preset cpu_local --batch 100 --by "ana"

# Força o embedding de toda descrição, ignorando o hash do texto.
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true

# Aponta o juiz de conflito para outro host Ollama só nesta execução.
uv run python -m scrinalia.domains.archive.workers.runner conflict-judge \
    --option host=http://ollama.interno:11434 --by "ana"
```

| Flag | Significado |
| --- | --- |
| `<name>` | um dos nove nomes acima; qualquer outro valor é recusado com a lista de opções |
| `--engine X` | uma engine registrada do eixo do worker, por exemplo `spacy_ner`, `deberta_typology`, `ollama_judge` |
| `--preset Y` | um preset desse eixo, por exemplo `gpu`, `lemmatizer`, `cpu_local`, `gpu_cloud`, `granite_local`, `multilingual_minilm` |
| `--batch N` | tamanho do lote por transação, repassado aos workers que declaram `db_batch_size` |
| `--option key=value` | parâmetro extra, repetível; `key` sem `=` é recusado |
| `--by "quem"` | texto livre com quem está executando; a CLI roda no host e não tem sessão, então isso continua sendo um nome sem conta por trás |

O `--option` converte exatamente dois valores: `true` e `false` viram booleanos. Qualquer outro valor
continua string, então uma opção que espera número ou lista não é configurável pela linha de comando.
A flag é validada contra a assinatura do `execute` do worker: uma opção que o worker não declara é
recusada, a menos que o worker termine em `**engine_kwargs`, que é a forma documentada de
sobrescrever `device`, `host` e parâmetros parecidos da engine em uma execução.

Duas coisas são sempre recusadas:

- `config` é recusado porque é um dataclass do runner (`NerRunnerConfig` e os irmãos), não um valor
  que uma linha de comando ou um corpo JSON possa carregar; um dicionário chegando ao `execute`
  falharia com erro de atributo em vez de uma frase. Passe os campos individuais.
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
`available_engines` com seus presets e uma `note`. Esse dicionário vem do `describe_config` de cada
registro de engine, o **gêmeo somente-leitura do `get_engine`**: resolve o preset e os overrides e
devolve o dicionário sem instanciar a engine, então o painel consegue responder "com qual modelo
isto vai rodar?" para um worker que nunca rodou — sem carregar o modelo.

Para `quality-validator`, o `engine_source` é `llm_check_rule`: a engine e o preset vêm da regra
`LLM_CHECK` ativa, e as rotas de configuração e de disparo recusam defini-las ali, porque um segundo
lugar para escolher a mesma engine seria uma segunda fonte de verdade. Sem regra ativa, o worker roda
apenas a validação determinística, e o painel diz isso na `note`.

## O painel de operação

O painel é a superfície `/api/v1/system/*` e os três cartões de `/configuracoes`, sob *Operação*, na
SPA: o menu não os carrega mais (issue #22).

| Rota | Método | Permissão | O que faz |
| --- | --- | --- | --- |
| `/api/v1/system/workers` | `GET` | autenticado | os nove workers com configuração, números de fila e última execução/execução ativa, numa requisição só |
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
| `/sistema/workers` | os nove workers: engine, preset e modelo, a fila, o padrão persistido e um botão de execução |
| `/sistema/execucoes` | o ledger de execuções e as falhas dos últimos 30 dias agrupadas por causa raiz; clicar numa causa filtra o ledger para as ocorrências dela |
| `/sistema/diagnostico` | banco, modelos do Ollama, storage das miniaturas e a configuração efetiva do processo |

A tela só fica consultando enquanto algo está rodando, porque o contador do `transfer` faz uma
chamada a `/system/workers` custar cerca de dois segundos no acervo real.

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
ou `API`), `requested_by` (e `requested_by_user_id`), `engine_name`, `preset`, o `config` resolvido,
`queued_at`, `started_at`, `finished_at`, `duration_ms`, `error` e o `error_fingerprint` gerado.

Os status são `QUEUED`, `RUNNING`, `SUCCESS`, `FAILED` e `INTERRUPTED`. A linha `QUEUED` é comitada
pela **sessão própria do ledger antes** de a thread do executor receber o id; uma linha ainda dentro
da transação da requisição ficaria invisível para essa thread e a execução ficaria em `QUEUED` para
sempre.

`uq_worker_run_active` é um **índice único parcial** sobre `(worker_name)` quando o status é `QUEUED`
ou `RUNNING`. É ele, e não um lock de processo, a trava de concorrência: no máximo uma execução por
worker em andamento, entre processos e através de um reload. Um segundo envio vira um
`IntegrityError` que a API transforma em `409` com uma frase ("Já existe uma execução em andamento
para o worker '…'"), e que a CLI expõe do mesmo jeito.

O executor do painel roda **um worker por vez** (`WORKER_RUNTIME_MAX_WORKERS`, padrão 1) porque os
workers são limitados por CPU — dois modelos torch na mesma CPU se atrasam sem produzir mais. Ele
**não é um agendador**: sem retry, sem cron, sem prioridade. Existe para uma pessoa apertar um botão.

## Reprocessar um documento ou um lote

Rodar um worker de novo é seguro e incremental: a fila dele é a ausência do carimbo, então uma
segunda execução toca só o que ainda está pendente. O que devolve uma unidade à fila:

- **o texto mudou** — uma edição humana ou um trecho de texto aprovado/editado/desfeito. O
  `embedding` se re-enfileira sozinho, porque o carimbo dele *é* o MD5 do texto efetivo; os carimbos
  dependentes do texto (`worker_ner_v2`, `worker_typology_classifier_v2`,
  `worker_quality_validator_v1`) são invalidados pelo serviço de qualidade de texto.
- **a origem mudou** — o `transfer` reescreve a descrição quando o hash do conteúdo interpretado
  muda, e a escrita zera os carimbos de IA, então os enriquecimentos precisam rodar de novo.
- **o catálogo mudou** — reescrever um rótulo de assunto muda o hash do conjunto de rótulos, então
  as tags afetadas voltam à fila do `macro-category`. Os motivos do validador de qualidade também
  dependem do catálogo.
- **`force=true`** — `embedding`, `macro-category`, `thumbnail` e `quality-validator` aceitam e
  ignoram o próprio carimbo; o `macro-category` continua sem tocar numa tag que já tem categoria. No
  `thumbnail` ele também traz de volta os documentos marcados como `thumbnail_failed`, que é a saída
  de um bucket que estava fora durante uma execução: a marca existe para um link morto não ficar em
  laço, não para tornar a queda permanente.

```bash
uv run python -m scrinalia.domains.archive.workers.runner embedding --option force=true
uv run python -m scrinalia.domains.archive.workers.runner quality-validator --option force=true
uv run python -m scrinalia.domains.archive.workers.runner thumbnail --option force=true
```

!!! warning "A janela de reprocessamento fecha no primeiro registro aprovado por uma pessoa"
    `HUMAN_APPROVED` é a proteção: `ai_writable_documents()` a exclui, e `cleaning`, `ner`,
    `typology`, `thumbnail` e `quality-validator` filtram por ela. O `transfer` se recusa a
    sobrescrever uma descrição aprovada mesmo quando o hash da origem mudou. As duas exceções
    documentadas são o trabalho derivado — o `embedding`, que re-embeda um texto mudado, e o
    `macro-category`, cuja unidade é a tag e cuja fila é "ainda sem categoria", então a categoria de um
    curador nunca é reescrita.

Não há **rota nem flag que limpe um carimbo**: para devolver um documento à fila de um worker que não
aceita `force`, é preciso remover aquela chave do `execution_log` dele no banco. Trate isso como
reparo, não como operação de rotina.

## Execuções INTERRUPTED

Uma execução deixada em `QUEUED` ou `RUNNING` por um processo que morreu é pior que uma errada: o
índice único parcial bloquearia aquele worker para sempre. No boot, `api/lifespan.py` marca toda
linha assim como `INTERRUPTED`, com `finished_at` e o texto de erro "O processo anterior terminou
antes do fim desta execução."

Nada é retentado automaticamente. Depois de uma execução `INTERRUPTED`:

1. Leia `GET /api/v1/system/runs?status=INTERRUPTED` (ou o painel) e abra o erro da linha.
2. Corrija a causa — um modelo do Ollama faltando, um bucket inalcançável, um banco que estava fora.
3. Dispare o worker de novo. Os carimbos por unidade são o que torna isso seguro: a nova execução lê
   só o que a interrompida não terminou.

A recuperação assume **um único processo da API**. Com `uvicorn --workers > 1`, o boot de um processo
marcaria a execução viva de um irmão como interrompida, então escalar exige tirar o executor (e a
recuperação) de dentro da API antes. O índice único parcial continua válido nos dois casos.

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
  mesmo com outro rodando — ele entra na fila atrás dos demais — porque o índice limita a uma
  execução por worker; `WORKER_RUNTIME_MAX_WORKERS` decide quantos o painel mesmo roda de uma vez.

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

# Uma senha explícita. A conta fica marcada como temporária e a troca no primeiro acesso.
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
`archive_worker_runs` diz **o que rodou, quando, com que engine e preset, quanto demorou e como
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

Um carimbo tem uma armadilha que vale saber antes de ler o número: `embedding_v1` é o **MD5 do texto
efetivo**, não a identidade do modelo, então ele fica em dia mesmo quando os vetores não estão —
trocar `torch`, `sentence-transformers` ou o preset não devolve uma única descrição para a fila.
Quando o modelo de embedding muda, o vetor precisa ser reconstruído de propósito.

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
- **O executor assume um único processo da API.** A API roda um worker por vez
  (`WORKER_RUNTIME_MAX_WORKERS`) e a recuperação no `api/lifespan.py` marca o que um processo morto
  deixou para trás, o que só é correto com `uvicorn --workers 1` (veja *Execuções INTERRUPTED*, acima).
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
- **Ordenar só pela semântica é pior que pelo lexical.** Os vetores funcionam e a ordem não: a
  bancada que mede isso é `testing/evaluation/retrieval_quality.py`, e combinar os dois rankings é
  trabalho aberto. Uma busca semântica que **encontra mais** não é uma busca que **ordena melhor**.
