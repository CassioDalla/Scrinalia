---
translation_of: guides/install.md
---

# Instalação e implantação

O Scrinalia é instalado pela própria instituição que guarda o acervo, na infraestrutura dela, e
funciona ali sem serviço hospedado. Esta página é a sequência ordenada para quem instala em uma
terceira instituição: o que precisa estar instalado, o que cada variável muda e quais operações a
implantação assume depois. Ela descreve o código como ele está.

Quem opera lê esta página; as telas do arquivista estão em [Curadoria](curate.md) e o pipeline de
workers em [Operação](operate.md).

## O que você está instalando

A instalação tem quatro peças. Só as duas primeiras vêm deste repositório.

| Peça | Roda como | De onde vem |
| --- | --- | --- |
| API e interface do curador | um processo (`uvicorn`, um worker) | este repositório |
| PostgreSQL 15 com `pgvector` | um contêiner ou um servidor que você administra | o `docker-compose.yml` constrói um; um servidor próprio serve, desde que tenha a extensão |
| Armazenamento de objetos compatível com S3 | qualquer endpoint que fale S3 | **você traz** — veja [O armazenamento de objetos não vem no pacote](#o-armazenamento-de-objetos-nao-vem-no-pacote) |
| Host do Ollama | um servidor que serve os modelos de LLM | **você traz**; só os motores que usam Ollama precisam dele |

## Pré-requisitos

### Software

| Requisito | Versão usada aqui | Por quê |
| --- | --- | --- |
| Docker Engine com o plugin Compose v2 (`docker compose`) | Docker 29.1.3, Compose 2.40.3 | o PostgreSQL vem do `docker-compose.yml`, que fixa o `name:` do projeto e usa a forma `env_file: {path, required: false}` — a implementação do Compose precisa aceitá-la |
| [`uv`](https://docs.astral.sh/uv/) | 0.11.14 | administra o Python 3.12 e o lockfile; o `Dockerfile` fixa a imagem do `uv` em 0.11.14 |
| [Bun](https://bun.sh/) | 1.3.14 | instala o workspace do front e roda o `curator:build`; o Bun administra pacotes e scripts, o Vite empacota (ADR 0003) |
| Python | 3.12 | `requires-python = ">=3.12"`; o `uv` o fornece, não é preciso um Python do sistema |

As versões acima são as do repositório no momento em que ele foi construído e verificado; uma versão
mais nova de correção de qualquer uma delas deve funcionar. Todos os comandos desta página rodam da
raiz do repositório.

### Disco

O ambiente Python e os caches de modelo são os itens grandes. Medido em um checkout em uso:

| O quê | Medido | Comando |
| --- | --- | --- |
| Ambiente Python (`.venv`), incluindo torch, transformers, spaCy e o modelo `pt_core_news_lg` de 602 MB | 6,6 GB | `du -sh .venv` |
| Cache de modelos do Hugging Face depois da primeira execução de classificação e NER | 4,6 GB | `du -sh .cache-hf` |
| Dependências do front | 268 MB | `du -sh node_modules` |
| Modelos do Ollama (os presets citam `gemma4:e4b`) | não medido | baixados pelo Ollama, não por este repositório |
| Dados do PostgreSQL | depende do acervo | cresce com as descrições, não com o software |

Reserve cerca de 12 GB livres para a pilha Python, o cache de modelos e as dependências do front,
mais espaço para o banco. Se você também construir a imagem do contêiner, some a própria imagem — o
`Dockerfile` registra que só o virtualenv dela tem cerca de 6 GB.

### Memória

**Esta página não declara uma RAM mínima, porque isso não foi medido.** Como referência do que se
observou ao escrevê-la: a máquina de desenvolvimento informa 15 GiB no total e 8,3 GiB disponíveis
(`free -h`). A memória de uma execução é determinada pelos modelos mantidos no processo — os motores
de classificação e de NER carregam cada um um transformer ou um pipeline do spaCy — e pelo Ollama
mantendo o modelo dele ao mesmo tempo. Meça na máquina de destino com o modelo carregado antes de
dimensionar um servidor; uma máquina confortável para a API ainda pode ser curta para uma execução de
worker.

### Serviços externos

- Um servidor PostgreSQL 15 com `pgvector`. O Alembic cria as extensões de que o schema precisa
  (`pg_trgm`, `unaccent`, `vector`), mas não instala os *pacotes* das extensões: em um PostgreSQL sem
  pgvector, o `alembic upgrade head` falha na migration de embeddings. A imagem do
  `docker/postgres/Dockerfile` parte do pgvector e acrescenta o PostGIS, então as duas estão
  disponíveis; o PostGIS está instalado, mas nenhuma migration o habilita ainda.
- Um endpoint compatível com S3, alcançável a partir do processo da API, com um bucket que **já
  existe**.
- Um host do Ollama, se você for usar os motores que dependem dele. O `OLLAMA_HOST_URL` é onde todo
  motor baseado em preset resolve o host; `http://localhost:11434` é o padrão quando ele não é
  definido.

## O runner e a API

A API apenas enfileira desde a ADR 0014; um runner fora dela executa os workers. É por isso que a API
pode rodar com `uvicorn --workers N` — não há executor em segundo plano nem recuperação no boot — e
por que os workers precisam de um segundo processo, iniciado da raiz do repositório ou da imagem:

```bash
uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
```

`--workers` restringe o que o runner aceita (o padrão é o catálogo inteiro); `--concurrency`,
`--heartbeat-seconds`, `--lease-seconds`, `--poll-seconds`, `--sweep-seconds`, `--once` e
`--drain-seconds` estão no [guia de Operação](operate.md#o-runner). O runner reivindica uma linha
`QUEUED` com `FOR UPDATE SKIP LOCKED`, renova um lease enquanto roda e grava a configuração efetiva.
Ele recusa um schema atrás do seu código: aplique as migrações da API antes. O painel mostra o runner
e se ele aceita cada worker; uma execução enfileirada sem runner online espera.

O banco é o único canal entre a API e um runner: a API nunca chama um.

O scheduler (ADR 0015) é um terceiro processo, separado de propósito: ele transforma a agenda de cada
worker em linhas `QUEUED` e nunca executa uma. `python -m scrinalia.domains.archive.workers.scheduler`
toma um advisory lock, então uma instância por vez é decisão do banco; o serviço `scheduler` do compose
e o `bun run scheduler:dev` o iniciam. A API, o runner e o scheduler podem cada um viver na própria
máquina, e só o scheduler escreve a tabela de agendas.

## A rede e a credencial

Um runner em outra máquina alcança o mesmo PostgreSQL. Duas coisas tornam isso seguro:

1. **Um caminho privado.** WireGuard/Tailscale, ou um túnel SSH no host do runner
   (`ssh -N -L 5432:localhost:5432 user@vps`), com o `pg_hba.conf` aceitando só `hostssl` desse
   caminho; nunca exponha a `5432` publicamente.
2. **TLS.** O `DB_SSLMODE` (padrão `prefer`) entra no DSN derivado; um banco remoto usa `verify-full`
   com uma CA. Uma `RUNNER_DATABASE_URL` completa pode trazer o próprio host e `sslmode`, então o
   runner não depende do DSN da API.

A role de menor privilégio é endurecimento opcional. Ela mantém o runner fora das tabelas de
identidade sem tirar dele a escrita do acervo, que é o que um worker faz:

```sql
CREATE ROLE scrinalia_runner LOGIN PASSWORD '<segredo>';
GRANT CONNECT ON DATABASE <db> TO scrinalia_runner;
GRANT USAGE ON SCHEMA public TO scrinalia_runner;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scrinalia_runner;
REVOKE ALL ON auth_users, auth_sessions FROM scrinalia_runner;
GRANT SELECT ON alembic_version TO scrinalia_runner;
REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM scrinalia_runner;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scrinalia_runner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scrinalia_runner;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO scrinalia_runner;
```

Depois defina `RUNNER_DATABASE_URL=postgresql+psycopg2://scrinalia_runner:<segredo>@<host>:5432/<db>?sslmode=verify-full`
no ambiente do runner. Nada mais muda: a API continua com `DB_*`.

## Instalação: a sequência ordenada

### 1. Obtenha o código e declare o ambiente

```bash
git clone <url-do-repositorio> scrinalia
cd scrinalia
cp .env.example .env
# edite o .env para a sua infraestrutura
```

O `.env` é ignorado pelo git. O `Settings` o lê (`env_file=".env"`), uma variável de ambiente real
tem precedência sobre ele, e o `docker compose` lê o mesmo arquivo para a interpolação. Parta do
`.env.example`; [os dois arquivos batem](#envexample-e-coreconfigpy) e não há nada a trocar ali.

### 2. Suba o banco de dados

```bash
docker compose up -d
```

Isso sobe o PostgreSQL 15 na porta 5432 e nada mais. O serviço da aplicação fica atrás do profile
`app`, então este comando nunca o constrói nem o inicia.

### 3. Instale o ambiente Python

```bash
uv sync
uv pip install --python .venv/bin/python --require-hashes -r models/requirements.txt
```

Pesado: `torch`, `transformers`, `spacy` e `bertopic` estão no conjunto padrão de dependências. O
segundo comando instala o `pt_core_news_lg`, o pipeline português de 542 MB que o motor de NER
carrega. Ele **não** está no `uv.lock` de propósito: como fonte por URL, ele fazia todo `uv lock`
baixar o wheel, e a atualização do Dependabot morria nesse download antes de chegar ao pacote que
estava atualizando (a medição está no comentário no topo de `models/requirements.txt`). O `uv sync` é
exato e remove o que o lock não nomeia, então rode o segundo comando de novo depois de qualquer
`uv sync`.

### 4. Crie o banco de dados e o schema

```bash
bun run db:init
```

O `db:init` é aqueles dois passos em um: sobe o contêiner, cria o banco que `DB_NAME` nomeia quando ele
ainda não existe e aplica o schema. Repeti-lo é inofensivo — ele é idempotente. É também o que recupera
um banco apagado de um volume que já existia, o caso que o `docker compose up -d` não recupera sozinho:
o `POSTGRES_DB` é honrado quando o volume é *inicializado*, então um banco apagado depois continua
apagado e a migração falha em um banco que não está lá.

O schema em si é propriedade do Alembic e nada mais o cria. O `uv run alembic upgrade head` o aplica, e
o mesmo comando cria as extensões `pg_trgm`, `unaccent` e `vector` de que o schema depende. Confirme o
resultado com `uv run alembic check`, que não acusa drift em uma instalação saudável.

A ordem importa: este passo precisa de um banco alcançável, e é por isso que o contêiner vem antes.
Para jogar tudo o que há nesse banco fora e começar de um vazio, o `bun run db:recreate` imprime o que
seria destruído e pede o nome do banco antes de apagá-lo. Onde ninguém pode digitá-lo — um script de
provisionamento — a mesma operação é `uv run python -m scrinalia.core.database_cli recreate --yes`; o
`bun run` não encaminha argumentos extras para um script composto, então a flag tem de ir ao módulo.
Ele é limitado ao banco de propósito: o `docker compose down -v` destrói o volume inteiro — todos os
bancos vizinhos nele — e é a única forma de conseguir um volume *novo*, onde o `POSTGRES_DB` volta a ser
honrado.

### 5. Compile a interface do curador

```bash
bun install
bun run curator:build
```

O `bun install` roda uma vez, da raiz do repositório (é um workspace). A compilação escreve em
`apps/curator/dist`, e o `create_app()` monta esse diretório em `/` quando ele existe — é isso que
mantém o navegador na mesma origem da API e o projeto livre de CORS. Sem a compilação a API continua
respondendo; só não serve interface nenhuma.

### 6. Crie o primeiro administrador

Uma instalação vazia tem duas portas para a mesma conta: a tela de primeiro acesso na interface, ou
a CLI na máquina. Cada uma cria um `ADMIN` com uma senha que alguém escolheu, e só a primeira se
fecha atrás dela — a rota de primeiro acesso responde 409 para sempre depois que uma conta existe,
enquanto a CLI é administração da máquina e continua criando contas a qualquer momento.

```bash
uv run python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN
```

A CLI é o caminho que funciona antes de a API subir, e o que uma instalação sem interface usa. Sem
`--password` ela gera uma senha, imprime e marca a conta como **temporária**, para que a senha no
histórico do terminal deixe de ser uma credencial — a conta a troca no primeiro acesso. Os papéis
são `ADMIN`, `CURATOR` e `VIEWER`, e a CLI ainda tem `list`, `reset-password`, `activate`,
`deactivate` e `set-role`.

Com a API no ar (passo 7), uma instalação cuja `auth_users` ainda está vazia responde à primeira
visita com **Primeiro acesso da instalação** em vez do formulário de entrada: e-mail, nome e a
senha, pedida duas vezes. Ela cria o primeiro `ADMIN` e entra com essa pessoa, então não há segunda
entrada nem senha temporária. A tela pergunta a `GET /api/v1/setup/status`, que é pública porque uma
instalação sem conta nenhuma não tem segredo a proteger. O cartão carrega a logomarca do produto no
topo, a mesma placa do cartão de entrada: é a primeira tela que quem instala vê, e é o lugar onde vale
mostrar o nome inteiro.

A rota de primeiro acesso se fecha **para sempre** depois que a primeira conta existe — desativada
ou não, porque o predicado é a tabela estar vazia, e uma regra que uma desativação pudesse reabrir
seria um caminho de volta para uma porta aberta. A CLI não é uma porta que a instalação fecha: ela
roda na máquina, com o mesmo serviço que a API usa, e continua criando contas depois disso. Até lá,
quem alcançar a instância primeiro pode criar essa conta; o `POST /api/v1/setup/admin` é serializado
por um lock de tabela, então duas tentativas simultâneas não podem dar certo as duas, mas o lock não
fecha a janela (ADR 0011). **Configure a instância antes de expô-la.**

A interface abre em português. Cada conta pode passar para inglês no menu da conta; a escolha fica guardada na conta, e a API responde na língua que a requisição pede.

### 7. Suba a API

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Depois da migração, uma instalação nova tem **nenhuma origem configurada**: `ingestion_origins` guarda só as linhas manual e CSV, que são as entradas e aparecem só para leitura. A tela `/sistema/ingestao` é onde o operador adiciona uma origem do pacote — a definição `pmc` está no seletor, e as URLs acima são o fallback dela quando os campos estão vazios — e uma descrição é digitada ou importada em `/acervo/nova`.

A API fica em `http://localhost:8000/`, a interface no mesmo endereço e o documento OpenAPI em
`/schema/swagger`. O `--reload` é de desenvolvimento (`bun run api:dev`), não de uma instalação.
Antes de expor a instância, defina o `AUTH_COOKIE_SECURE` — veja [HTTPS](#https).

## Variáveis de ambiente

Cada configuração é definida uma única vez em `src/scrinalia/core/config.py` (`Settings`). Todas
têm valor padrão, então a API sobe com um `.env` vazio; o que falha rápido sem configuração é o
pipeline, não o boot — a origem é uma linha em `ingestion_origins` e os `PUBLIC_SCRAPE_*` são o fallback do adaptador de referência.

| Variável | Padrão | O que ela muda |
| --- | --- | --- |
| `DB_USER` | `admin` | usuário do banco; precisa casar com o servidor ou com o serviço `db` |
| `DB_PASS` | `admin123` | senha do banco; um segredo, revelado só onde o driver precisa |
| `DB_HOST` | `localhost` | host do banco: `db` na rede do compose, o endereço do servidor no metal |
| `DB_PORT` | `5432` | porta do banco |
| `DB_NAME` | `scrinalia` | nome do banco; o serviço do compose o cria no primeiro boot |
| `DB_SSLMODE` | `prefer` | transporte libpq acrescentado ao DSN derivado; `verify-full` com uma CA quando o banco é alcançado pela rede |
| `RUNNER_DATABASE_URL` | não definido | o DSN próprio do runner externo (um segredo); sem ele, o runner usa `DB_*`. Permite que um host de GPU tenha uma role de menor privilégio e seu próprio `sslmode` (ADR 0014) |
| `PUBLIC_SCRAPE_URL` | vazio | URL base da listagem do site de referência; fallback do `pmc` — a configuração da origem na tela de ingestão vence |
| `PUBLIC_SCRAPE_DETAIL_URL` | vazio | prefixo da página de detalhe do site de referência; fallback do `pmc`, como acima |
| `DEFAULT_TIMEZONE` | `America/Sao_Paulo` | o fuso em que a agenda de um worker é avaliada quando o operador não nomeia um; o cron roda aqui, não no fuso do servidor (ADR 0015) |
| `ACERVO_LANGUAGE` | `pt-BR` | seleciona o perfil de língua — stopwords, gramática de datas, regras de plural, o dicionário de busca textual e o modelo do spaCy. O dicionário chega a uma coluna gerada, então mudá-lo é uma **migração**, não um reinício |
| `S3_ENDPOINT_URL` | vazio | o endpoint compatível com S3 (MinIO, Ceph, SeaweedFS, um bucket na nuvem); de dentro de um contêiner, `localhost` é o próprio contêiner |
| `S3_BUCKET_NAME` | vazio | o bucket para onde vão as miniaturas; o worker o confirma uma vez, antes da execução |
| `S3_ACCESS_KEY` | vazio | credencial com leitura e escrita no bucket; um segredo |
| `S3_SECRET_KEY` | vazio | o segredo da credencial; um segredo |
| `S3_AUTO_CREATE_BUCKET` | `false` | se o worker pode criar o `S3_BUCKET_NAME` quando ele não existe; desligado, a execução é recusada com o comando que o cria |
| `OLLAMA_HOST_URL` | vazio → `http://localhost:11434` | o host do Ollama que todo motor baseado em preset resolve; um `--option host=...` explícito ainda vence |
| `AUTH_SESSION_COOKIE_NAME` | `scrinalia_session` | nome do cookie de sessão de primeira parte |
| `AUTH_SESSION_TTL_MINUTES` | `720` | quanto tempo uma sessão vive; deslizante, empurrada adiante pela atividade |
| `AUTH_SESSION_TOUCH_MINUTES` | `15` | quanto tempo uma sessão pode ficar parada antes de o vencimento ser empurrado |
| `AUTH_COOKIE_SECURE` | `false` | acrescenta `Secure` ao cookie de sessão; **mude para `true` atrás de HTTPS** — veja [HTTPS](#https) |
| `AUTH_PASSWORD_MIN_LENGTH` | `12` | tamanho mínimo da senha, cobrado no domínio para a CLI obedecer também |
| `AUTH_PASSWORD_MEMORY_KIB` | `65536` | custo de memória do argon2id (64 MiB); aumentá-lo não invalida os hashes existentes |
| `AUTH_PASSWORD_TIME_COST` | `3` | iterações do argon2id |
| `AUTH_PASSWORD_PARALLELISM` | `4` | vias do argon2id |
| `AUTH_LOGIN_MAX_ATTEMPTS` | `5` | tentativas de acesso que bloqueiam uma conta |
| `AUTH_LOGIN_LOCKOUT_MINUTES` | `15` | primeira janela de bloqueio; cada bloqueio seguinte a dobra até o teto |
| `AUTH_LOGIN_LOCKOUT_MAX_MINUTES` | `240` | teto da janela de bloqueio, para quem tenta adivinhar não ter uma agenda fixa de retentativas |
| `AUTH_LOGIN_RATE_MAX` | `20` | tentativas de acesso permitidas por endereço de cliente na janela; um freio local ao processo, não a defesa durável |
| `AUTH_LOGIN_RATE_WINDOW_SECONDS` | `300` | a janela em que essas tentativas são contadas |
| `AUTH_TRUSTED_ORIGINS` | vazio | origens extras aceitas em requisição de escrita, separadas por vírgula; necessárias quando um proxy reverso reescreve o `Host` |
| `LOG_DIR` | `logs` | diretório dos sinks do loguru (`critical.log`, `ui_stream.jsonl`); criado se não existir |
| `LOG_LEVEL` | `INFO` | nível do console e do fluxo estruturado |
| `DEBUG` | `false` | informa o sinalizador de depuração no diagnóstico do sistema; ele é exibido, não usado para trocar o log |

O `DATABASE_URL` **não** está nesta tabela: é uma propriedade derivada, que codifica as credenciais
de `DB_*` para a URL, e não um valor que você define. Ele também acrescenta o `sslmode` de
`DB_SSLMODE`.

### `.env.example` e `core/config.py`

Os dois batem, e a conferência vale a pena: todo nome do `.env.example` é um campo de `Settings`
**menos um**. O `APP_OLLAMA_HOST_URL` não é configuração da aplicação — ele existe só para o
contêiner, onde o `docker-compose.yml` o mapeia para `OLLAMA_HOST_URL`, porque uma entrada em
`environment:` tem precedência sobre o `env_file`. Ele é explicado em
[Implantação em contêiner](#implantacao-em-conteiner).

O `DB_NAME` é `scrinalia` nos três lugares — `core/config.py`, `.env.example` e a interpolação do
compose. Isso é deliberado, não cosmético: o nome era o do banco do acervo de referência, o que
fazia um clone novo apontar por omissão para o catálogo de outra pessoa — o mesmo defeito que o
ADR 0008 removeu uma camada acima. Uma implantação que queira outro nome o define no próprio
`.env`, que é onde a configuração dela mora.

## CPU e GPU

A CPU é a forma que o processo embarcado assume, não uma limitação do código, e isso é garantido em
dois lugares. O `pyproject.toml` aponta o `torch` para o **índice só-CPU do PyTorch**, então nenhum
runtime CUDA chega a ser instalado; e o `Procfile` sobe a API como `CUDA_VISIBLE_DEVICES="" uv run
uvicorn main:app --reload`, com o estágio de runtime do `Dockerfile` definindo a mesma variável como
`ENV`, então o processo não enxerga GPU nem numa máquina que tenha uma.

O índice vale mais do que parece. Medido neste lock, a roda padrão resolve **3,46 GB**, dos quais
**2,19 GB são pacotes `nvidia-*`** e 248 MB de `triton` — um runtime que um processo de CPU nunca
executa, baixado e cacheado por toda instalação e pela CI. Com o índice de CPU o mesmo lock resolve
**0,66 GB**. A variável cobre o outro sentido: impede que uma instalação re-lockada com CUDA falhe numa
máquina sem o driver da NVIDIA, e esconde a GPU das partes da pilha que chegam ao CUDA por outro
caminho (o `spaCy` só chega a uma pelo `cupy`, o extra `spacy[gpu]`, que este projeto não declara).

Para usar uma GPU em vez disso, a roda precisa estar lá primeiro:

1. Remova a linha `torch = { index = "pytorch-cpu" }` e o bloco `[[tool.uv.index]]` do `pytorch-cpu`
   do `pyproject.toml`, e rode `uv lock && uv sync`. A roda padrão do PyPI carrega o runtime CUDA no
   Linux e no Windows; o macOS mantém a build dele de qualquer jeito.
2. Não defina `CUDA_VISIBLE_DEVICES=""` para o processo; suba-o sem a variável, ou nomeie o
   dispositivo desejado (`CUDA_VISIBLE_DEVICES=0`).
3. Escolha uma configuração que use a GPU. O motor de tipologia (usado também pelo worker de
   macro-categoria) tem o preset `gpu_cloud` com `device: "cuda"`; o preset padrão do NER já é `gpu`,
   que chama `spacy.prefer_gpu()` — note que o spaCy só chega à GPU pelo runtime CUDA dele
   (`cupy`, o extra `spacy[gpu]`), que este projeto não declara, então instale-o à parte se quiser as
   entidades na GPU; o motor de embeddings tem um único preset, `multilingual_minilm`, em
   `device: "cpu"`, e aceita override.
4. Rode o runner nesse host com a build CUDA, e deixe-o aceitar os workers que usam o modelo. O
   painel enfileira e o runner da GPU reivindica; para um teste pontual no host, a CLI unificada
   continua lá:

```bash
CUDA_VISIBLE_DEVICES=0 uv run python -m scrinalia.domains.archive.workers.runner_daemon \
    --name gpu-01 --workers ner,typology,embedding
CUDA_VISIBLE_DEVICES=0 uv run python -m scrinalia.domains.archive.workers.runner typology --preset gpu_cloud
```

A consequência que importa agora: **o processo que roda um worker é o runner, não a API**. Uma
execução disparada pelo painel roda no runner que a reivindicar, com o ambiente e a build CUDA desse
runner; o `CUDA_VISIBLE_DEVICES=""` da API só esconde a GPU do processo da API. A configuração
efetiva continua seguindo `argumento explícito > override persistido > padrão da assinatura`, então um
preset escolhido no painel é o que o runner resolve — [Operação](operate.md) é dona dessa precedência.

## HTTPS

Defina `AUTH_COOKIE_SECURE=true` quando a instância for alcançada por HTTPS, e só então.

A sessão é um cookie de primeira parte cuja linha vive em `auth_sessions`; o servidor guarda apenas o
SHA-256 do token. Com o `AUTH_COOKIE_SECURE` no padrão `false`, o atributo `Secure` não existe, então
o navegador também envia o cookie por HTTP simples — em rede aberta, o token de sessão viaja em texto
claro e pode ser lido do fio. É isso que o sinalizador evita.

O padrão é `false` de propósito, e é por isso que uma instalação em rede local por `http://` não pode
ligá-lo: o navegador descarta um cookie `Secure` em HTTP simples **em silêncio**, então o acesso
pareceria ter funcionado enquanto nada foi guardado, e a requisição seguinte seria anônima de novo. O
modo de falha de inverter isso é um login que parece dar certo e nunca gruda (ADR 0009).

O `AUTH_TRUSTED_ORIGINS` é a configuração companheira. Requisições de escrita são conferidas contra
a `Origin`: a mesma origem é aceita comparando a autoridade da origem com o `Host` da requisição, e um
proxy reverso que reescreve o `Host` faz toda escrita parecer de outra origem, a menos que a origem
pública esteja listada ali, separada por vírgulas. Leituras nunca são conferidas, e uma requisição
sem `Origin` (curl, a CLI) é aceita. Como a API serve a interface da própria origem, não há CORS a
configurar; encaminhe o `Host` original pelo proxy, ou declare a origem pública aqui.

## Implantação em contêiner

O contêiner é a alternativa à sequência no metal acima, e empacota o que o código já assume: uma
imagem contendo a API **e** a interface do curador, mais um segundo serviço para o runner.

```bash
docker compose --profile app up -d --build   # API + runner + PostgreSQL
docker compose --profile app logs -f app
docker compose --profile app logs -f runner
docker compose --profile app logs -f scheduler
# → http://localhost:8000
```

O serviço `app` fica atrás do profile `app` de propósito, então o `docker compose up -d` — e
portanto o `bun run dev` — continua subindo só a infraestrutura.

O profile também traz um serviço `runner` e um `scheduler`: a mesma imagem, sem porta publicada, o
módulo dos workers como entrypoint do runner e o módulo do scheduler como entrypoint do scheduler. É o formato CPU de uma instalação de um host só; um host com GPU roda a imagem
naquela máquina com uma build CUDA e um caminho privado até o banco, como em [a rede e a
credencial](#a-rede-e-a-credencial). A API nunca o chama.

O que o entrypoint faz por você:

- O `docker/entrypoint.sh` roda `alembic upgrade head` antes de subir o servidor, tentando de novo
  enquanto o banco está inalcançável e desistindo com saída não zero depois de
  `SCRINALIA_DB_WAIT_SECONDS` (padrão 60). Defina `SCRINALIA_RUN_MIGRATIONS=false` quando as
  migrações forem um passo separado, ou quando várias réplicas subirem ao mesmo tempo: o Alembic não
  toma trava distribuída, então execuções concorrentes correm umas contra as outras. O serviço
  `runner` deliberadamente **não** usa esse entrypoint: a API é dona das migrações, e o runner
  confere o schema e tenta de novo em vez de disputar com elas.
- O comando de runtime é `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1` (o entrypoint
  mantém um processo; a API agora suporta mais, e o número de réplicas é escolha do operador), e o
  `HEALTHCHECK` da própria imagem lê o `/health/live`, que não toca em nada.

Configuração dentro do contêiner:

- O bloco `environment:` do compose reaponta o `DB_HOST` para o serviço `db` e dá
  `http://host.docker.internal:9000` como padrão do `S3_ENDPOINT_URL`.
- O `OLLAMA_HOST_URL` **dentro do contêiner** vem de outra variável:
  `OLLAMA_HOST_URL: ${APP_OLLAMA_HOST_URL:-http://host.docker.internal:11434}`. Uma entrada de
  `environment:` no compose vence o `env_file`, então definir `OLLAMA_HOST_URL` no `.env` não chega
  ao contêiner da aplicação — defina `APP_OLLAMA_HOST_URL` também. Esse nome é variável de
  interpolação do Compose, não um campo de `Settings`; ele existe só para este arquivo. Confirme o
  que o contêiner realmente vai receber com `docker compose --profile app config`, que resolve a
  interpolação antes de qualquer coisa subir.
- Os volumes `pgdata`, `app_logs` e `hf_cache` sobrevivem a uma reconstrução: o banco, os sinks do
  loguru (`LOG_DIR`) e o cache do Hugging Face para onde os modelos são baixados. O pacote da
  interface vem do estágio de build, nunca da máquina: `apps/curator/dist` é ignorado pelo git e
  fica fora do contexto de build.

O primeiro administrador é criado de dentro do contêiner:

```bash
docker compose --profile app exec app \
  python -m scrinalia.domains.identity.cli create \
  --email voce@instituicao.org --name "Seu Nome" --role ADMIN
```

Não precisa ser por aí: com o contêiner já servindo a interface, uma instalação que ainda não tem
conta nenhuma responde à primeira visita com a tela de primeiro acesso (passo 6), e a conta criada
ali é a mesma. O `exec` acima é o caminho que funciona também quando nada está acessível ainda.

### `docker-compose.test.yml` não é para produção

O `docker-compose.test.yml` descreve o banco de **teste** e nada mais: usuário `test_user`, banco
`test_db`, o diretório de dados em `tmpfs` (na memória, então perdido quando o contêiner para) e
porta publicada `${TEST_DB_PORT:-5433}`. O schema dele é construído pelo `Base.metadata.create_all`
no `testing/conftest.py`, não pelo Alembic, e a suíte o derruba no teardown. Nunca aponte uma
instalação para ele, e nunca rode `alembic upgrade head` contra ele: o `create_all` então pula as
tabelas que encontra, a suíte roda contra um schema migrado em vez dos modelos, e o resultado se lê
como regressão em vez do erro que é.

## O armazenamento de objetos não vem no pacote

O `docker compose up -d` sobe o PostgreSQL e nada mais. O projeto precisa de um endpoint compatível
com S3 e não se importa com qual produto o serve — MinIO, Ceph, SeaweedFS ou um bucket na nuvem são
infraestrutura que quem opera traz, não algo que este repositório embarca.

As configurações são `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` e
`S3_AUTO_CREATE_BUCKET`; o cliente é o boto3 com assinatura v4. Duas exigências vêm do código: a
credencial precisa de leitura e escrita no bucket, e o bucket precisa existir — o worker o confirma
uma vez, antes de tocar na fila, e só o cria quando `S3_AUTO_CREATE_BUCKET=true`. De dentro do
contêiner `app`, `localhost` é o próprio contêiner, então aponte o endpoint para o endereço do
serviço na sua rede (`host.docker.internal` alcança um serviço rodando na máquina hospedeira).

A confirmação é deliberada, e é ela que torna a falha legível. Nem todo endpoint diz "este bucket
não existe": o SeaweedFS responde **`AccessDenied`** a um envio para um bucket que nunca foi criado,
então cada documento da execução parece um problema de credencial. Com a flag desligada (o padrão) o
worker recusa a execução de antemão, nomeando o bucket e o comando que o cria; com a flag ligada ele
cria o bucket e segue. O `GET /api/v1/system/health` relata a mesma distinção e nunca cria nada — um
probe que provisiona é uma escrita escondida dentro de uma leitura.

O que vive lá hoje são os JPEGs do worker `thumbnail`, em `thumbnails/`. O banco guarda a referência
`s3://bucket/key` resultante em `storage_thumbnail_uri`.

## Backup e restauração

Duas peças de estado, e só duas: o banco e o bucket.

Dump e restauração do banco, com o `DB_USER`/`DB_NAME` que você configurou (`admin`/`scrinalia` por
padrão):

```bash
# dump, formato custom
docker exec scrinalia_db pg_dump -U admin -d scrinalia -Fc > scrinalia-$(date +%F).dump

# restauração em um banco novo, deixando o atual intacto
docker exec scrinalia_db createdb -U admin scrinalia_restore
docker exec -i scrinalia_db pg_restore -U admin -d scrinalia_restore < scrinalia-2026-10-08.dump
# depois aponte o DB_NAME para scrinalia_restore e suba a API
```

Bucket: copie-o com o que o provedor oferecer; qualquer cliente S3 serve, e a forma genérica é
`aws s3 sync --endpoint-url <url> s3://<bucket> ./bucket-backup`.

Restaure as duas **em par**. Esta é a armadilha: a fila do worker `thumbnail` é
`storage_thumbnail_uri IS NULL`, então um banco restaurado sem o bucket tem todas as referências
preenchidas e nenhum objeto atrás delas. O worker não vai reenviar nada — a fila está vazia — e a
interface serve imagens quebradas. Faça o backup das duas juntas e restaure as duas juntas.

### O que não se recupera

- Nada além dessas duas peças, e a frase é literal: a aplicação não guarda outro estado. O `LOG_DIR`
  (`logs/`) é histórico operacional, não registro arquivístico; o cache do Hugging Face e o
  `apps/curator/dist` são reconstruíveis; e o schema vem das `migrations/` no repositório. Guarde uma
  cópia do seu `.env` junto do dump; ele não está dentro dele, e uma restauração sem ele aponta para
  os padrões.
- **Tudo o que foi escrito entre o último dump e a falha.** O projeto não configura arquivamento
  contínuo nem envio de WAL; o ponto de recuperação é o dump.
- **Uma descrição excluída.** O `DELETE /api/v1/documents/{id}` é a única operação que remove um
  registro. Ele fotografa a linha inteira em `archive_document_deletions` — código de referência,
  título, nível, todo o conteúdo ISAD(G), quem excluiu e por quê —, mas a tela `Acervo › Histórico de
  exclusões` é só um registro, não uma lixeira: não há restauração. Um nó com filhos é recusado de saída, porque a
  chave estrangeira que referencia a própria tabela é `RESTRICT`.
- **As miniaturas, se o bucket se perder.** O banco continua nomeando-as, e o worker poderia
  derivar uma de novo a partir de `original_thumbnail_url` enquanto o site de origem ainda servir a
  imagem — mas não vai, porque a fila só contém documentos cujo `storage_thumbnail_uri` é `NULL`.
  Rederivá-las é uma operação deliberada, não algo que a próxima execução faça sozinha.
- Os modelos do Ollama e o cache do Hugging Face são downloads, não estado: podem ser baixados de
  novo, o que custa tempo e banda, não dados.

## Operação mínima

### Três respostas de saúde, três perguntas

| Endpoint | Pergunta que responde | O que toca | Resposta | Acesso |
| --- | --- | --- | --- | --- |
| `GET /health/live` | o processo está respondendo? | nada | 200 enquanto o processo responde | nenhum |
| `GET /health/ready` | esta instância pode receber tráfego? | um `SELECT 1` no motor próprio dela | 200, ou **503** quando o banco não responde | nenhum |
| `GET /api/v1/system/health` | qual peça está fora? | contagens de tabela, `/api/tags` do Ollama, um `HEAD` no bucket, a configuração efetiva do processo | 200 de qualquer forma, com um veredito por peça | permissão `OPERATE` (ADMIN) |

As duas probes ficam fora do `/api/v1` e fora do documento OpenAPI de propósito, para um orquestrador
não precisar conhecer a versão da API. Não as junte: uma probe de liveness que consultasse o banco
faria o orquestrador reiniciar a API toda vez que o banco reiniciasse. O painel humano é a terceira
pergunta, a cara, e é o que nomeia a peça quebrada; na interface ele é
`Configurações → Operação → Saúde do sistema`.

### O `/health/ready` responde 503

O processo está vivo e o banco não respondeu a uma consulta trivial. A probe de prontidão tem um
motor dedicado, com `connect_timeout` e `statement_timeout` de 2 segundos e nenhuma conexão em pool,
então a resposta volta rápido e não pode ser herdada de uma conexão velha; o detalhe da falha vai
para o log, não para o corpo da resposta, porque a rota não é autenticada e um erro de conexão ecoa
host e porta. Verifique se o serviço `db` está rodando (`docker compose ps`), se
`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME` apontam para ele e se o PostgreSQL aceita conexões.
Reiniciar a API é o reflexo errado: o processo está bem.

### O Ollama está fora

O `GET /api/v1/system/health` informa `ollama.ok = false` com o host que usou, se ele veio do
`OLLAMA_HOST_URL` ou do padrão, e lista os modelos que os presets exigem ao lado dos que o servidor
tem — então a lista de faltantes é a lista do conserto. Só os motores que dependem do Ollama são
afetados: o juiz de tag × entidade (`conflict-judge`, preset padrão `gemma_4b_local`), o validador
de qualidade, que tira o motor da regra de limpeza `LLM_CHECK` ativa, e o motor alternativo de
tipologia `ollama_typology`, quando você o escolhe no lugar do padrão `deberta_typology`. O resto do
pipeline — transfer, cleaning, NER, tipologia no motor padrão, thumbnail, macro-category, embedding
— roda sem Ollama. Suba o host e baixe as tags que o painel lista como faltantes; o
`OLLAMA_HOST_URL` é o que chega aos motores, e um `--option host=...` explícito ainda o sobrepõe em
uma execução isolada.

Um preset foi aposentado em vez de consertado: `granite_local` nomeava `granite4.1:3b`, que no
Ollama 0.24.0 derruba o llama runner com `signal arrived during cgo execution` e responde `500` a
todo prompt, enquanto `gemma4:e4b` responde normalmente no mesmo servidor (medido em 2026-10-18). O
nome não é mais oferecido e a sonda de saúde não exige mais o modelo. Uma linha de configuração ou
uma regra `LLM_CHECK` que ainda o nomeie é recusada ao ser gravada, e uma gravada antes da
aposentadoria resolve para `gemma_4b_local` com o motivo na tela, em vez de derrubar o painel.

### O bucket não responde

O painel distingue os dois casos: `storage.configured = false` significa endpoint, bucket ou
credenciais faltando, e `configured = true, ok = false` significa que a configuração existe e o
`HEAD` no bucket falhou. O worker `thumbnail` é o único consumidor do bucket, então o resto do
pipeline continua. Suba o bucket **antes** de rodar esse worker: um documento cujo envio levanta
exceção recebe o carimbo `thumbnail_failed`, uma marca de falha permanente que a fila respeita, então
uma indisponibilidade passageira do armazenamento durante uma execução deixa esses documentos
excluídos de toda execução seguinte. Corrija `S3_ENDPOINT_URL`/`S3_BUCKET_NAME`/`S3_ACCESS_KEY`/
`S3_SECRET_KEY`, confirme que o bucket existe e verifique o alcance a partir do processo que faz o
envio — dentro de um contêiner, `localhost` é o contêiner.

## Próximos passos

- [Operação](operate.md) — os nove workers e a ordem deles, presets e overrides, o ledger de
  execuções e como reprocessar um documento ou um lote.
- [Curadoria](curate.md) — o que o arquivista decide em cada tela e quais escritas não têm volta.
- [Modelo de dados](data-model.md) — as três camadas mais `identity`, os carimbos e os ledgers.
