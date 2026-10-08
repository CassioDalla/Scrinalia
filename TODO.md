# 🗺️ Roadmap & TO-DO — Scrinalia

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não só lido
> no código. `[ ]` = pendente. `[~]` = parcial.
>
> **Estado do gate (2026-10-07, após a autenticação — B9.1 a B9.3):** **1.368 testes** passando · `ruff`
> limpo · `basedpyright` **0 erros** · **32 migrações** sem drift · contrato OpenAPI
> **94 paths / 111 operações / 182 schemas**, gerado, commitado e sem drift · SPA (`tsc`, `eslint`,
> `vite build`) limpa e servida pelo próprio Litestar · **9 ADRs**. As **111 operações** estão todas
> classificadas por permissão, e a superfície aberta são três.
>
> **Resposta curta sobre a 1.0:** o software está pronto e a autenticação está fechada. **Falta um
> ciclo — a documentação.** O resto é operação (processar o acervo de referência) e o **endurecimento
> do repositório antes de abrir o código** (seção própria, com passo a passo).

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança | ✅ **Fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | ✅ **Fechada** |
| 2 | API + Curadoria humana (HITL) | ✅ **Fechada** |
| 2.5 | Hierarquia das descrições | ✅ **Fechada** (H1–H8, com tela) |
| 3 | Descoberta, performance e observabilidade | 🟡 **Quase** — falta o agendador; `/health` e o rastreamento de erros fechados |
| 3.5 | Qualidade do dado de entrada | ✅ **Fechada** |
| 4 | UI, BFF e publicação | 🟡 **Curador completo** (23 telas) e **auth entregue (B9.1–B9.3)**; falta o **site público** |
| **5** | **Release 1.0** | 🟡 **Iniciada** — licença (0006), nome (0007), desacoplamento (0008) e auth (0009) fechados; **falta a base de documentação** |

---

## ✅ O que já foi feito (síntese)

> O detalhe de cada ciclo vive no histórico do Git e nos ADRs. Aqui fica só o que **impede alguém de
> refazer ou desfazer** uma decisão já medida.

| Ciclo | O que entregou (uma linha) |
| --- | --- |
| **Fase 1 — pipeline** | Ingestão → staging → archive com CDC por hash do **registro parseado**; 9 workers com idempotência por `execution_log` (JSONB + GIN) e carimbo versionado; governança `HUMAN_APPROVED` bloqueia IA (exceção documentada: `worker_embedding`). |
| **Fase 1.5 — macro categorias** | Vocabulário de 5 → 8 gavetas derivado das tags reais; guarda determinística recusa **1.489 de 8.155** tags como "não é assunto"; limiar 0.55 com fila; carimbo = hash do conjunto de rótulos. A frase NLI **é o colapso**, não a cura (medido). |
| **Fase 2 — API e curadoria** | Litestar + DDD por domínio; `PATCH /documents/{id}` edita ISAD(G) e grava revisão; exclusão definitiva com retrato ISAD(G) (trilha, não lixeira); autoria vinda da sessão, em duas colunas. |
| **Fase 2.5 — hierarquia** | `path` materializado (uma query indexada por nível), catálogo de níveis, plano de arranjo com decisão separada da execução, materialização por decisão humana com ledger e undo. |
| **Fase 3 — busca e observabilidade** | Lexical (coluna gerada + GIN, sem acento) e semântica (pgvector, HNSW cosseno); facetas com semântica própria; `/health/live` + `/health/ready` de orquestrador; falhas agrupadas por causa raiz em coluna gerada (ADR 0005). |
| **Fase 3.5 — qualidade do dado** | Composição do texto do AI **em SQL** (uma expressão alimenta embedding, carimbo MD5, NER e tipologia); trechos com escopo `EMBEDDING`/`NER`/`TITLE`; merges de tags com ledger e undo exato; Hit@10 **0.562 → 0.625**; +201 datas recuperadas. |
| **Contrato e determinismo** | OpenAPI gerado e commitado, cliente TS gerado dele; **`Field(description=...)` em enum compartilhado reescreve o componente** e dependia do `PYTHONHASHSEED` — por isso se documenta o **tipo**, nunca o campo. |
| **Desacoplamento (ADR 0008)** | A **língua** é código (`core/language`, perfil `pt-BR`); o **acervo** é dado (`archive_arrangement_vocabulary`, `archive_collection_terms`, com tela); a origem é parâmetro (`SourceSchema`), sem default. O que é de uma instituição não fica no meio do domínio. |
| **Licença e nome** | `AGPL-3.0-only` + termo de atribuição do §7(b) (ADR 0006); nome **Scrinalia** (ADR 0007), livre em registries/domínios. |
| **Auth (B9.1–B9.3, ADR 0009)** | Sessão por cookie no banco (só o sha256 do token), argon2id com hash-isca, três papéis, **cada operação declara a sua permissão** (teste de partição), autoria vinda da sessão; `/api/v1/users` + tela de contas; **bloqueio com backoff gravado fora da transação do request**, rate-limit por endereço e `origin_guard` nas mutações. |
| **Invariante de `path`** | Verificada **no CI pelo próprio diagnóstico** (`find_path_divergences`) depois de cada escritor, com os dois lados: árvore saudável responde vazio e a linha corrompida de propósito é encontrada. |

### 🐞 Modos de falha já aprendidos (valem para código novo)

- **Uma rota que publica um vocabulário tem de cobrir todo produtor** (`/hierarchy/flags` unia quatro
  vocabulários; publicar um só deixava a UI renderizando código cru).
- **Um campo parseado e não persistido falha em silêncio** (`access_conditions` existia no staging e
  não no archive).
- **`scope` é nome reservado do Litestar** (ASGI scope): rotas usam `axis`/`pair_kind`.
- **`%` sozinho no join de trigrama**: `name % name OR lower(name)=lower(name)` = 52,9 s → 1,4 s sem o
  OR, resultado idêntico. Prefilter de comprimento descartava 52–65% dos pares reais.
- **`UNSAFE` sem escape vira "todos os registros"** (`escape_like()` em termo digitado).
- **`Secure` no cookie quebra login em HTTP de LAN** (o browser descarta em silêncio).
- **`Date.now()` no render** faz o componente deixar de ser reprodutível — o relógio é do servidor
  (`is_locked`).

---

## 🔴 Antes do 1.0 — detalhado

### 1. Base de documentação — **o único bloqueador**

Decisão já tomada: **versionada no repositório**, publicada a partir dele (wiki externa não versiona
com o código e diverge). O que falta:

- [ ] **Escolher a ferramenta.** Recomendação: **MkDocs Material** (build estático, versionamento por
      release com `mike`, busca própria, `mkdocstrings` puxa docstrings do Python). **GitHub Docs**
      basta se o objetivo for só publicar os quatro guias abaixo, sem versionar por release. A escolha
      vira um ADR curto (`docs/adr/0010-...`) ou uma nota aqui — mas tem de ser decidida, não herdada.
- [ ] **Guia de instalação e deploy** — o que um terceiro precisa, na ordem:
      - pré-requisitos: Docker + Compose, `uv`, `bun`, espaço em disco para os modelos, RAM mínima;
      - `docker compose up -d` → `uv sync` → `uv run alembic upgrade head` →
        `bun install && bun run curator:build` → criar o primeiro admin pelo CLI;
      - **tabela completa de variáveis** (`DB_*`, `S3_*`, `OLLAMA_HOST_URL`, `ACERVO_SOURCE`,
        `ACERVO_LANGUAGE`, `AUTH_*`) e o que cada uma muda;
      - **CPU × GPU**: por que o `Procfile` roda com `CUDA_VISIBLE_DEVICES=""` e como usar GPU;
      - **HTTPS**: `AUTH_COOKIE_SECURE=true` e o que quebra se ficar `false`;
      - **premissa de processo único** (`uvicorn --workers 1`): o executor de workers e a recuperação
        de órfãos no boot assumem um processo (ADR 0004). É a armadilha nº 1 de quem instala;
      - **backup e restauração**: `pg_dump` + bucket, e o que **não** se recupera (nada além disso);
      - **operação mínima**: o que fazer quando `/health/ready` responde 503, quando o Ollama está
        fora, e quando o bucket não responde.
- [ ] **Guia de operação** — os 9 workers e a ordem do pipeline; o que cada fila significa; presets,
      overrides e a precedência (`argumento explícito > linha em archive_worker_settings > default`);
      o painel de sistema; o ledger de execuções; **como reprocessar** um documento ou um lote; o que
      fazer com execuções `INTERRUPTED`; o agendador que **não existe** (hoje é disparo manual — como
      pendurar um cron externo na CLI/rota); como ler `/system/failures`.
- [ ] **Guia de curadoria** — para cada uma das 23 telas: **que decisão o arquivista toma ali**, o que
      é reversível e o que não é. O que não tem volta precisa estar em negrito: purga de stopwords,
      `DELETE /documents/{id}`, merge de entidade (sem ledger). E o que a IA **não** pode desfazer
      depois de `HUMAN_APPROVED`.
- [ ] **Modelo de dados** — as três camadas + `identity`; o `execution_log` e os carimbos; a
      governança bidirecional (stopword de tag × exclusão de NER); os ledgers (merge, materialização,
      conflito, deleções, execuções, erros da API); as colunas geradas (`search_vector`,
      `error_fingerprint`) e por que elas são a definição única; a partição exata da superfície
      pública (`NOT_PUBLIC_FIELDS`/`NOT_PUBLIC_FACETS`).
- [ ] **Publicar**: `mkdocs.yml`, `docs/index.md` + `docs/guia/*.md`, link no `README`, e um job de CI
      que **builda o site** (falha se um link ou um bloco quebrar).

### 2. Endurecer o CI e o repositório antes de abrir o código

Passo a passo, na ordem em que faz sentido executar. **Nada aqui é feature**: é o que separa "um repo
que funciona" de "um repo que estranhos podem auditar e usar".

#### Fase 0 — antes de tornar público (obrigatório)

- [x] **Varrer o histórico por segredos — feito, sem achados.** O gitleaks não está instalado, mas não
      precisa estar: a imagem oficial roda com Docker e o resultado foi **232 commits, nenhum
      vazamento**. O comando (também é o job de CI, com o digest pinado):
      `docker run --rm -v "$PWD:/repo" zricethezav/gitleaks@sha256:c00b… detect --source /repo --log-opts="--all" --redact --no-banner`.
      Se um dia achar: rotacione **e** reescreva o histórico (`git filter-repo`) — rotacionar sozinho
      não remove o commit do clone de quem já baixou.
- [x] **Nada sensível versionado** — `git ls-files | grep -E '\.env$|logs/|\.analysis/|\.cache'` é
      vazio, e o `.env` **nunca** esteve no histórico (`git log --all -- .env` vazio).
- [x] **Decisão: dado do acervo não vai para o repositório público.** Nada que descreva a coleção de
      referência é versionado — nem descrições, nem IDs, nem nomes de fundos e bairros, nem os
      conjuntos rotulados. Consequência de projeto: **o sistema tem de subir e operar com banco
      zerado**, e o dono vai testar exatamente assim.
      - [x] **Os dois conjuntos de avaliação saíram.** `retrieval_pairs.json` (IDs de descrição reais
        e títulos) e `macro_category_pairs.json` (tags reais com veredictos de curador) vivem agora
        em `Data/evaluation/`, que é ignorado. `testing/evaluation/dataset.py` é o ponto único que os
        carrega — de `Data/` ou de `SCRINALIA_EVALUATION_DATA` — e falha **com a instrução** em vez
        de `FileNotFoundError`, porque o reflexo diante de um fixture ausente é recriá-lo a partir do
        código, que é o que não pode acontecer. O **formato** ficou versionado em
        `testing/evaluation/README.md`: a forma é método, as linhas são acervo. Nenhum teste dependia
        deles.
      - [x] **A semente do vocabulário saiu do repo.** Os 38 tokens de arranjo e os 71 termos de
        coleção saíram de `domain/collection_vocabulary.py` **e** da migração `b3d6f1a2c4e7`, que
        agora só cria as tabelas. Editar uma revisão aplicada é normalmente errado e aqui é o certo
        pelo motivo que importa: **não é mudança de schema**, e manter a semente significaria embarcar
        o acervo no único lugar onde um `git clone` sempre traz. Quem já rodou a forma antiga **mantém
        as linhas** — elas passaram a ser dado daquela instalação — e quem clona começa vazio; os dois
        convergem no comportamento, porque nada lê a semente em runtime.
        - O vocabulário virou **arquivo carregável**: `python -m scrinalia.domains.archive.cli
          export|import` (`Data/vocabulary/collection_vocabulary.json`, ignorado). O `import` é
          idempotente e assimétrico — cria o que falta (respeitando `is_active`, para um termo
          aposentado não ressuscitar), corrige nome e **nunca apaga**. O arquivo da instalação de
          referência já foi gerado, então não há nada para redigitar: um comando e pronto.
        - Os testes **mantêm os nomes reais**, agora em `testing/reference_vocabulary.py`: eles foram
          escritos contra este acervo, grafia por grafia, e é isso que faz o teste falhar quando a
          guarda deixa de cobrir o que ele foi escrito para cobrir. Vocabulário neutro deixaria a
          suíte verde sobre nada. Decisão do dono.
        - Verificado com **banco zerado**: 32 migrações, `alembic check` sem drift, catálogo vazio,
          `/health/ready` 200, difusão pública 200 com `total: 0`, e o `import` levando 0 → 109 linhas
          (e 0 na segunda vez).
      - [x] **O fatiador NÃO tem token do acervo em código — verificado.** Eu tinha registrado o
        contrário aqui, e a checagem desmentiu: `slice_reference_code` recebe **só** o código e
        classifica por **forma** (`str.isalpha()` = arranjo, dígito/outro = identificador) com
        `ROOT_MIN_TOKENS = 2`. O `BR PRADAP` existe apenas em comentário e em exemplo de docstring.
        Um banco zerado não faz o fatiador fatiar contra Curitiba.
      - [x] **`DB_NAME` neutro.** Era o nome do banco da coleção de referência; agora o default é
        `scrinalia` em `core/config.py` e nos dois pontos do `docker-compose.yml`. É mudança
        **quebradiça para instalação existente** — um volume já criado tem o outro nome — então quem
        já tem o banco aponta `DB_NAME` no `.env` (o desta máquina já aponta).
      - [x] **Comentários e docstrings de `src/` limpos.** 21 arquivos com exemplos que nomeavam
        fundos, secretarias e bairros passaram a usar placeholders neutros (`ACERVO RAIZ`, `ALFA`,
        `BETA`, `exemplo lugar`), mais cinco arquivos fora da primeira lista
        (`models/governance.py`, `repository/tag_repo.py`, `schemas/tag_schema.py`,
        `workers/worker_ner.py`). O contrato da API foi **regenerado** (`bun run contract`), porque
        `description=` de schema e docstring de enum chegam ao OpenAPI.
      - [x] **Números e nomes do acervo em documentação.** Linha de corte aplicada: as **medições
        agregadas** ficaram (são a evidência de por que o código é como é — "52,9 s com o OR, 1,4 s
        sem, resultados idênticos") e o **conteúdo** saiu — nome de fundo, bairro, ID. `AGENTS.md` e
        `TODO.md` atualizados, incluindo `memoriacuritibana_legacy` → `scrinalia_legacy`.
- [x] **Licença conferida**: `LICENSE` (AGPL verbatim), `LICENSE-ADDITIONAL-TERMS.md`, `license` no
      `pyproject.toml` e nos dois `package.json`, e o rodapé de atribuição na SPA.
- [x] **`SECURITY.md`** criado, com o reporte pela **advisory privada do GitHub** (decisão do dono),
      versões suportadas, prazo de resposta, escopo e a lista explícita do que **não** é vulnerabilidade.
- [ ] **Configurar no GitHub (Settings)**, ainda em repo privado — só o dono pode fazer, na ordem:
      1. **Settings → Security → Private vulnerability reporting** → *Enable*.
      2. **Settings → Code security** → ligar *Dependabot alerts*, *Dependabot security updates*,
         *Secret scanning* e *Push protection*.
      3. **Settings → Branches → Add branch protection rule** para `main`: exigir pull request, exigir
         os status checks do CI, proibir force-push e deleção, exigir histórico linear.
      4. **Settings → Actions → General → Workflow permissions** = *Read repository contents*.
      5. **Settings → General → Danger zone** → tornar público **só depois** de 1–4.
- [ ] **Só então tornar público.** A ordem importa: um segredo que entra no histórico de um repo
      público já vazou.

#### Fase 1 — CI (bloqueante no PR)

- [x] **`uvx` no job de lint** — o job usava `uvx ruff@0.16.10` sem instalar o `uv`; agora tem
      `astral-sh/setup-uv`.
- [x] **`permissions: contents: read`**, `persist-credentials: false` no checkout, `concurrency` para
      cancelar runs superados e `timeout-minutes` por job.
- [x] **`uv sync --locked`**: o `uv.lock` commitado é o contrato; uma resolução diferente falha o build.
- [x] **Actions pinadas por SHA** (`checkout` v4.4.0, `setup-uv` v5.4.2, `setup-bun` v2.2.0), com o
      comentário da versão. Tag é mutável; SHA não. **Verificado com `uvx zizmor`** — as 6 ocorrências
      de `unpinned-uses` sumiram.
- [x] **Job de segredos** — `gitleaks` no histórico completo, com a imagem pinada por digest.
- [x] **Job de lint do workflow** — `zizmor@1.30.1 --persona=pedantic` nos dois workflows: **0 achados**
      (era 6 `unpinned-uses` + a imagem sem digest).
- [x] **Imagens Docker pinadas por digest** — `pgvector` nos **três** lugares (serviço do CI,
      `docker-compose.test.yml`, `FROM` do `docker/postgres/Dockerfile`). O MinIO **saiu** do compose:
      o projeto só pede um endpoint S3-compatível, e o storage é infraestrutura do operador.
- [x] **CodeQL** (Python + JS/TS) em PR, `main` e semanal — é o único scanner que segue o dado, não a
      lista de dependências.
- [x] **Dependabot** para `github-actions` e `uv`, com PRs agrupadas e prefixo `chore(deps)`.
      **O front ficou de fora de propósito**: um entry `npm` mudaria `package.json` sem tocar
      `bun.lock`, e o CI instala com `--frozen-lockfile` — toda PR quebraria. Precisa de um updater que
      entenda `bun.lock` (o Renovate entende; o suporte do Dependabot ainda é parcial).
- [x] **DCO** — documentado no `CONTRIBUTING` e verificado por um job no CI (ver Fase 2).
- [x] **Pre-commit no CI** — desnecessário por enquanto: os três hooks são `ruff`, `ruff format` e
      `basedpyright`, que o CI já roda. Um job de `pre-commit` só acrescentaria valor no dia em que um
      hook **novo** entrar; aí ele entra junto.
- [x] **Auditoria de dependências — advisories do runtime resolvidos.** O job audita o export
      **sem dev** (`--no-dev`), que é o que embarca na instalação; pra ele, `pip-audit` e `bun audit`
      respondem **"no known vulnerabilities"**. As correções foram **bumps mínimos** (o menor fix
      publicado, não o último release): `torch` 2.12→2.13, `transformers` 5.9→5.10,
      `sentence-transformers` 5.5.1→5.6, `setuptools` 81→83, `urllib3` 2.7→2.8, `pillow` 12.2→12.3,
      `anyio`, `multidict`, `soupsieve`, `fsspec`. **Ainda `continue-on-error: true`**: um advisory
      novo pode aparecer sem correção disponível, e a promoção a bloqueante é uma linha — a decisão
      fica com o dono depois de ver o job verde algumas semanas.
      - ⚠️ **Consequência do bump de `torch`/`sentence-transformers`:** os embeddings guardados no
        acervo foram calculados com a versão antiga, e o carimbo do worker é o **hash do texto**, não
        da versão do modelo — então o worker **não** recoloca esses documentos na fila sozinho.
        Antes de confiar na busca semântica: re-rodar `worker_embedding` (ou comparar os vetores,
        como no `cos = 1.0` medido no B11) e re-rodar `testing/evaluation/retrieval_quality.py`.
- [x] **SBOM e proveniência no release.** `.github/workflows/release.yml` (dispatch manual, default
      `dry_run: true`): valida a versão, **recusa re-apontar uma tag existente**, imprime no resumo o
      que os Conventional Commits sugerem (patch/minor/major), builda a SPA, gera o SBOM Python
      (`cyclonedx-bom`) e atesta a proveniência (`actions/attest-build-provenance`) **antes** de criar
      a tag e o release com `gh release create --target --generate-notes`. O primeiro release público
      é o `v1.0.0` (default do input).
      - ⚠️ **A tag sai sem assinatura.** O `gh` cria a tag pela API do GitHub, não no seu clone, então
        a regra "require signed commits" não a alcança. Se tag assinada importar, ou o workflow assina
        localmente e faz push (e aí precisa de credencial no workflow, que foi evitado de propósito),
        ou se aceita — a proveniência atesta os **artefatos**, não a tag.
- [ ] **Assinatura de commit como regra.** As chaves já são usadas por padrão
      (`commit.gpgsign=true`, formato SSH), então o ruleset da `main` pode ligar **Require signed
      commits** além do DCO. São regras independentes: a assinatura prova quem criou o commit, o
      trailer `Signed-off-by` declara o direito de submetê-lo, e o job `dco` confere o trailer.
- [x] **Badges** de licença e de CI no `README`. O de licença é estático e diz o que a licença é —
      `AGPL-3.0-only` **mais** a atribuição da seção 7(b) —, não só o identificador SPDX. O de CI
      aponta para **`main`**, o branch default: ele lê "no status" até o `dev` ser mergeado (o `main`
      ainda não tem `.github/workflows/`), o que é honesto e mais barato do que um badge seguindo um
      branch que ninguém olha.
      - Observação: o badge de CI só renderiza para terceiros **depois** do repositório virar público
        (em repo privado o endpoint exige autenticação).
- [x] **Editor e gate com a mesma régua.** O Pylance não conhece `[tool.basedpyright]` e caía no
      default dele (`standard` sobre o workspace inteiro), acusando 58 diagnósticos nos testes que o
      CI nunca checou. A régua virou **um arquivo só**, `pyrightconfig.json`, que os **dois** leem.
      Armadilha medida: um bloco `[tool.pyright]` no `pyproject.toml` faz o basedpyright ignorar a
      própria seção e cair em `recommended` sobre tudo — **661 erros onde havia zero**. Não mover.
- [x] **`testing/` dentro do type check.** Os 47 diagnósticos foram zerados e a suíte entrou no
      escopo do gate (330 arquivos, `basic`, 0 erros e 0 avisos). **Dois deles eram imprecisão na
      fonte, não no teste:** o `Protocol` `SessionContext` declarava `__exit__` com parâmetros `Any` e
      não *positional-only*, o que rejeitava todo `@contextmanager` do projeto; e
      `test_describe_config` olhava `engine.host` através de `ResolveTagEntityConflictEngine`, um
      Protocol que só promete `decide_conflict` — o atributo é do motor Ollama, e o teste agora diz
      isso. O resto foi narrowing honesto (`assert x is not None`) e `PlanStatus.APPROVED` no lugar da
      string que o `StrEnum` tolerava em runtime.

#### Fase 2 — repositório e comunidade

- [x] **`CONTRIBUTING.md`** — setup, os checks que a PR precisa, convenções (Conventional Commits,
      código em inglês, contrato gerado), o **DCO** explicado e a licença.
- [x] **`CODE_OF_CONDUCT.md`** (Contributor Covenant 2.1, contato pelo GitHub) e
      **`.github/CODEOWNERS`**.
- [x] **Templates** de bug e feature (formulários), o `config.yml` com o link para a **advisory
      privada** — um template de segurança criaria uma issue pública no primeiro caractere digitado — e
      o `PULL_REQUEST_TEMPLATE.md`.
- [x] **`CHANGELOG.md`** (Keep a Changelog) com o que `main` carrega hoje, a ser cortado em `v0.1.0`.
- [x] **`CITATION.cff`**, **`.gitattributes`** e **`.editorconfig`**.
- [x] **DCO decidido** — era a dúvida: `Signed-off-by` no commit (`git commit -s`), verificado por um
      job no CI. É a *certificação de origem*: "escrevi isto ou tenho o direito de enviar, e pode ser
      distribuído sob esta licença". **Não cede copyright** e não é um contrato. CLA só faria sentido
      se houvesse intenção de relicenciar no futuro, que não é o caso.
- [ ] **Revisar o `AGENTS.md` antes de publicar**: tirar qualquer coisa específica do dono/instituição.
- [ ] **Tags semver** (`v0.1.0`) e o primeiro Release com notas, quando a documentação fechar.
- [ ] **Publicar a documentação** (`docs/`) e linkar no README.

### 3. Recomendados antes do 1.0

- [ ] **A premissa de processo único em letras grandes** no guia de deploy (o ADR 0004 já a registra; o
      que falta é o instalador tropeçar nela antes de rodar `--workers 4`).
- [ ] **Rodar a IA pendente no acervo de referência** antes de declarar 1.0 "com IA": hoje
      `typology_v2` está em **0** e `embedding_v1` em **41** de 4.844. Enquanto isso, a busca semântica
      serve vetores antigos para 3.608 e nenhum para os ~1.218 do re-parse.
- [ ] **Teste de fumaça `e2e`** (marcado `slow`) exercitando um pipeline com engines reais. A suíte usa
      `mock_registry` (correto) e por isso a classe de bug do `suggest-macro` fica invisível.

### 4. Pendências operacionais no acervo (não são código)

O código está pronto; **o acervo de referência está parcialmente processado**. Medido em
**2026-10-06** — **re-meça antes de confiar** (o comando está no Handoff):

| # | Medida | Valor |
| --- | --- | ---: |
| 1 | Descrições | **4.844** |
| 2 | Com pai (árvore materializada) | **4.826** |
| 3 | Tags / sem gaveta de assunto | **8.155 / 7.461** |
| 4 | Propostas de merge: sugeridas / aplicadas | **748 / 127** |
| 5 | Rungs decididos / total | **24 / 81** |
| 6 | Carimbos `ner_v2` / `typology_v2` | **4.826 / 0** |
| 7 | Carimbos `macro_category_v1` (tags) / `embedding_v1` | **957 / 41** |
| 8 | Publicados / revisões humanas | **0 / 0** |

**O que não pode rodar no acervo real sem decisão do dono:**

- `POST /hierarchy/materialisation/apply` — **já rodou uma vez** (4.816 descrições ganharam pai); rodar
  de novo move mais. Tem preview e undo.
- Aprovar rungs e aplicar merges em massa — decisões de conteúdo, não de engenharia.
- `POST /taxonomy/tags/stopwords/purge` — **apaga tags e não tem undo** (o merge tem ledger).
- `DELETE /documents/{id}` — exclusão definitiva (trilha, não lixeira).
- Os workers de IA — **a janela de reprocessamento fecha na primeira ficha aprovada por humano**.

> **Decisão de produto pendente:** rodar a IA (tipologia, embedding, quality-validator) **antes ou
> depois** de decidir os 81 rungs? Enquanto não rodar, a UI mostra menos do que o sistema sabe.

---

## 🧭 Backlog pós-1.0 — detalhado

### 1. Processamento fora da API, agendador e IA em outra máquina

Tirar os workers do processo da API, criar agendador (cron/retry) e permitir rodar a IA numa máquina
com GPU que devolve os dados para a API numa VPS.

- **Por que hoje não dá:** o executor roda **dentro da API**, um worker por vez, e a recuperação de
  órfãos no boot (`api/lifespan.py`) assume **um único processo**. `uvicorn --workers > 1` corrompe o
  estado das execuções.
- **O que fazer primeiro:** definir o **protocolo runner↔API** num ADR próprio. A semântica de
  `POST /system/workers/{name}/runs` muda de "executa agora, neste processo" para "enfileira para um
  runner" — o schema não muda se a resposta continuar sendo `WorkerRun`; o que muda é o *tempo* e a
  *garantia*. Desenhar a rota já pensando nisso.
- **Interage com versionamento?** **Não quebra o contrato**, muda a semântica.

### 2. Site público (`apps/public/`)

- **O que já está pronto:** a superfície `/api/v1/public/*` com projeção por allowlist
  (`NOT_PUBLIC_FIELDS` + `NOT_PUBLIC_FACETS`, partição exata com teste), `published_only` no servidor e
  o 404-que-esconde.
- **O que falta:** o app em si (segundo processo, mesmo contrato) e a decisão de qual framework serve
  o site.
- **Bloqueio real, e é de produto:** o predicado é `is_published` e **0 de 4.844** estão publicados. O
  site nasce vazio; o trabalho é de curadoria, não de código.
- **Interage com versionamento?** **Não** — aditivo por construção.

### 3. Internacionalização (i18n)

- **No servidor:** já é **aditivo** — todo desfecho responde `code` (estável, em inglês) + `message`
  (português), e o front lê tudo por `routeMessage()` (`lib/messages.ts`). Encher o mapa de traduções
  é o que torna a interface multilíngue, sem tocar em tela.
- **Na SPA:** ~334 strings PT hardcoded nas rotas + os `lib/` (`format.ts` formata data/número em
  pt-BR). Não há infra de i18n hoje (`i18n`/`useTranslation`/`intl`: zero).
- **O que NÃO se traduz:** prompts de LLM (raciocinam sobre português) e os **rótulos de campo da
  origem** (são chaves do payload; traduzir esvazia a coluna). Eles moram no `SourceSchema`.
- **Interage com versionamento?** **Sim, e era o item crítico** — resolvido: o `code` já existe, então
  traduzir depois é aditivo.

### 4. Dívidas de curadoria já registradas

- **Entidades sem catálogo de propostas** — os defeitos de merge foram corrigidos (upsert de sinônimos
  + `repoint_synonyms` antes de deletar), mas não há proposta, ledger nem undo como nas tags. A tela
  **avisa** que unificar não tem desfazer.
- **Colisão tag × entidade em lote** — os ~5.050 nomes idênticos são uma decisão *por categoria*
  ("logradouro é entidade"), e a tela ainda pede uma por par. `pair_kind` já separa as duas populações.
- **Purga de stopwords é a única escrita destrutiva sem undo** — tem preview; torná-la reversível
  (ledger, como o merge) é decisão em aberto.
- **Lematização de tags** ficou como **sugestão**, não reescrita.

### 5. Busca híbrida (RRF) e qualidade semântica

- A semântica funciona (pgvector, `vector(384)`, HNSW cosseno) mas o ranking é fraco: o **MRR caiu
  0.019** enquanto o Hit@10 subiu. Combinar lexical + semântica por RRF é o próximo passo; a bancada de
  medição é `testing/evaluation/retrieval_quality.py`.

### 6. Ingestões plurais — configuração por origem

Tratar a origem como objeto de primeira classe: scraper do PMC contínuo, ingestão manual por CSV e um
scraper de outra instituição, cada um com ciclo de vida, periodicidade e **configuração própria**
(colunas lidas, limpeza, limiares, talvez o preset).

- **O primeiro passo já foi dado** pelo ADR 0008: o adapter **declara o que precisa** (`SourceConfig`) e
  o vocabulário de campos é `SourceSchema` — não há default de origem.
- **Consequência no painel:** um eixo a mais ("de qual origem é esta fila?") e a origem no ledger de
  execuções.
- **Interage com versionamento?** **Não** — é aditivo (coluna/tabela + filtro).

### 7. Outras dívidas menores

- **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU não cabe na escada de 6 níveis sem repetir
  ordinal.
- **Observabilidade sem alerta** — o agrupamento por causa raiz é local e ninguém é avisado de uma
  causa nova: alguém precisa abrir a tela. É o custo aceito da decisão local (ADR 0005), com gatilho de
  revisão registrado.
- **Auth — limites conscientes:** rate-limit **por processo** (não distribuído; a garantia durável é o
  bloqueio por conta), sessão revogada guarda `revoked_at` mas **não quem** revogou, e 2FA/SSO/
  recuperação por e-mail estão fora de propósito.

---

## ✅ Verificação executada (evidências)

### Gate no estado atual (2026-10-07)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **1.368 passed** |
| `ruff check` / `ruff format --check` | limpos (377 arquivos) |
| `basedpyright` | **0 errors, 0 warnings** |
| `alembic check` | **sem drift** (32 migrações) |
| `tsc` / `eslint` / `vite build` | limpos |
| Contrato OpenAPI | **94 paths / 111 operações / 182 schemas**, sem drift (cliente TS incluído) |
| `zizmor --persona=pedantic` nos workflows | **0 achados** (era 6 `unpinned-uses` + a imagem sem digest) |
| `gitleaks` no histórico completo | **232 commits, nenhum segredo** |
| `pip-audit` / `bun audit` | rodam; o Python acusa advisories transitivos (`tornado`, `transformers`, `urllib3`) — job **não bloqueante** até triar |
| `/api/v1/users` em execução real | criar, editar, desativar, resetar senha, listar e revogar sessões; sessão de outra conta responde 404 |
| Bloqueio em execução real | 3 falhas → a senha **correta** responde **423** mesmo com o rollback de cada request |
| Rate-limit e `Origin` em execução real | 429 ao estourar a janela; **403** em mutação de origem estranha, **200** na leitura, e o proxy do Vite (Host preservado) aceita a origem do dev |
| `/health/live` e `/health/ready` em execução real | 200 com o banco de pé, **503** com o banco parado |
| Invariante de `path` no CI | verificada pelo próprio diagnóstico depois de cada escritor, com o caso corrompido como contraprova |

### Medições que mudaram decisões (preservadas)

| Verificação | Resultado |
| --- | --- |
| Trigrama com e sem o `OR lower()` | **52,9 s → 1,42 s**, resultado idêntico |
| Prefilter de comprimento | descartava **52–65%** dos pares reais; removido |
| Qualidade do texto de entrada | separação 0.769 → 0.504; Hit@10 0.562 → **0.625**; aprovar tudo piora (0.500) |
| Hierarquia em escala | `apply` 1,7 s; 1 raiz; profundidade 5; `undo` com 3.619 linhas restauradas |
| Undo de merge ao vivo | `vendas ← venda` desfeito e reaplicado: tag, id e vínculo restaurados exatamente |
| Worker `embedding` | 3.608/3.608 em ~1 min; `cos(guardado, recalculado) = 1.0` |
| Banco reconstruído | 15 tabelas copiadas; `alembic check` sem drift |

---

## 🐞 Bugs e limites conhecidos

1. **Acurácia de assunto em 0.500/0.575** — limite do zero-shot NLI com sintagma nominal. Decisão:
   aceitar e resolver por curadoria.
2. **Busca semântica com qualidade fraca** — a híbrida (RRF) continua pendente; o MRR caiu 0.019.
3. **Autenticação entregue (B9.1–B9.3), com limites conscientes** — 2FA, SSO/OIDC e recuperação por
   e-mail não existem (o CLI no host é o caminho de volta); o rate-limit é por processo; a sessão
   revogada não registra quem revogou.
4. **O acervo de referência está parcialmente processado** — tipologia e embedding pendentes.
5. **`path` desnormalizado** — a invariante é mantida pelo serviço e verificada no CI pelo próprio
   diagnóstico. O limite que resta é que o banco **não** a garante: um `UPDATE` manual fora do serviço
   ainda pode divergir, e é o `PATH_DIVERGENCE` que o encontra.
6. **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU não cabe na escada de 6 níveis.
7. **Premissa de processo único** — o executor na API + a recuperação de órfãos assumem
   `uvicorn --workers 1`. Documentado no ADR 0004; **precisa estar no guia de deploy**.
8. **Entidades sem ledger de merge** — unificar entidade não tem desfazer; a tela avisa.
9. **Purga de stopwords sem undo** — é a única escrita destrutiva que não é reversível.
10. **Observabilidade sem alerta** — o agrupamento por causa raiz é local e ninguém é avisado de uma
    causa nova (ADR 0005).

---

## ▶️ Handoff — como rodar

```bash
bun run dev            # docker compose up -d + API :8000 + SPA :5173 (proxy /api -> :8000)
# peças soltas: bun run db:up | bun run api:dev | bun run curator:dev
```

Um **502 em `/api`** quer dizer que a API não está no ar — a SPA responde 200 e o sintoma parece bug
de front.

```bash
# banco de teste deste checkout está na porta 5434
TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_db .venv/bin/pytest -q
.venv/bin/basedpyright && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/alembic check
bun run --cwd apps/curator typecheck && bun run --cwd apps/curator lint && bun run --cwd apps/curator build
```

> **Neste sandbox** o `~/.cache` é somente-leitura e o hook do git faz *stash* dentro do
> `PRE_COMMIT_HOME`: exporte os dois caches para o workspace antes de commitar (detalhe no `README`).
>
> ```bash
> export PRE_COMMIT_HOME=.cache-pre-commit UV_CACHE_DIR=.cache-uv
> ```

**Nunca** rode `alembic upgrade head` no banco de **teste**: o `create_all` do conftest pula o que já
existe e a suíte passa a rodar contra o schema migrado (53 falhas + 42 erros que parecem regressão).

### Medir o acervo (não confie em número congelado)

```bash
docker exec scrinalia_db psql -U admin -d scrinalia -c "
SELECT 'descrições' AS medida, count(*)::text AS valor FROM archive_documents
UNION ALL SELECT 'com pai', count(*)::text FROM archive_documents WHERE parent_id IS NOT NULL
UNION ALL SELECT 'sem nível', count(*)::text FROM archive_documents WHERE level_id IS NULL
UNION ALL SELECT 'tags', count(*)::text FROM archive_tags
UNION ALL SELECT 'tags sem gaveta', count(*)::text FROM archive_tags WHERE macro_category_id IS NULL
UNION ALL SELECT 'propostas sugeridas', count(*)::text FROM archive_tag_merge_proposals WHERE status='SUGGESTED'
UNION ALL SELECT 'propostas aplicadas', count(*)::text FROM archive_tag_merge_proposals WHERE status='APPLIED'
UNION ALL SELECT 'rungs decididos', count(*)::text FROM archive_hierarchy_node_plans WHERE status <> 'SUGGESTED'
UNION ALL SELECT 'rungs no total', count(*)::text FROM archive_hierarchy_node_plans
UNION ALL SELECT 'carimbos ner/tipo/macro/emb', (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_ner_v2')::text || '/' || (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_typology_classifier_v2')::text || '/' || (SELECT count(*) FROM archive_tags WHERE execution_log ? 'worker_macro_category_v1')::text || '/' || (SELECT count(*) FROM archive_documents WHERE execution_log ? 'worker_embedding_v1')::text
UNION ALL SELECT 'publicados', count(*)::text FROM archive_documents WHERE is_published;"
```

---

## 📚 Referências

- `AGENTS.md` — convenções e as regras arquiteturais fáceis de errar (**leia antes de mexer**).
- `README.md` — porta de entrada (o que é, como rodar).
- `docs/adr/` — decisões aceitas: Litestar (0001), layout `src/` (0002), monorepo e stack do curador
  (0003), execução de workers pela API (0004), observabilidade sem serviço externo (0005), licença e
  atribuição (0006), nome (0007), língua × acervo (0008), autenticação e autorização (0009).
- `.analysis/` — **gitignored**, notas de trabalho deste checkout (planos, sitemap, refino de UI). O que
  precisa sobreviver a um clone está **aqui** e no `AGENTS.md`.
