# 🗺️ Roadmap & TO-DO — Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não
> apenas lido no código. `[ ]` = pendente. `[~]` = parcial.
>
> **Estado do gate (2026-10-07, após o endurecimento da autenticação — B9.3):** **1.368 testes**
> passando · `ruff` limpo · `basedpyright` **0 erros** · **32 migrações** sem drift · contrato OpenAPI
> **94 paths / 111 operações / 182 schemas**, gerado, commitado e sem drift · SPA (`tsc`, `eslint`,
> `vite build`) limpa e servida pelo próprio Litestar · **9 ADRs**. As **111 operações** estão todas
> classificadas por permissão, e a superfície aberta são três.

---

## 📊 Panorama

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança | ✅ **Fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | ✅ **Fechada** — vocabulário reprojetado e medido |
| 2 | API + Curadoria humana (HITL) | ✅ **Fechada** — backend e ações locais |
| 2.5 | Hierarquia das descrições | ✅ **Fechada** (H1–H8, com tela) |
| 3 | Descoberta, performance e observabilidade | 🟡 **Quase** — falta o agendador; `/health` e o rastreamento de erros **fechados** (ADR 0005) |
| 3.5 | Qualidade do dado de entrada | ✅ **Fechada** |
| 4 | UI, BFF e publicação | 🟡 **Curador completo** (23 telas) e **auth entregue (B9.1–B9.3)**; falta o **site público** |
| **5** | **Release 1.0** | 🟡 **Iniciada** — licença (0006), nome (0007), desacoplamento (0008) e auth (0009) fechados; falta a base de documentação |

**O sistema está funcionalmente pronto.** Ingestão → staging → archive → enriquecimento por IA →
curadoria humana → bloqueio de reprocessamento, tudo verificado ponta a ponta. O **curador tem 23
telas** cobrindo todo o sitemap mais o painel de operação, e o **Streamlit saiu do repositório**.

**O que falta para uma 1.0 é de outra natureza:** não é feature, é *produto*. Documentação,
desacoplamento institucional e autenticação — a **licença** (ADR 0006), o **nome** (ADR 0007), o
**desacoplamento** (ADR 0008) e a **autenticação** (ADR 0009, ciclos B9.1 a B9.3) foram fechados em
2026-10-07. Resta a **base de documentação**. Detalhe na seção seguinte.

> **Ciclos entregues, em uma linha cada** (o detalhe está nas fases fechadas):
> contrato + onda 1 (2026-10-05) · onda 2, o plano de arranjo (2026-10-05) · ondas 4–6 e a remoção
> do Streamlit (2026-10-06) · refino de curadoria e o painel de operação (2026-10-06) · as três
> lacunas de curadoria — colisão, faceta de anomalia, "não é assunto" (2026-10-06) · o catálogo de
> tipologias e o contrato determinístico (2026-10-06) · **a observabilidade local — `/health` de
> orquestrador, causa raiz agrupada e request id (2026-10-07)** · **a licença `AGPL-3.0-only` e a
> atribuição do autor no rodapé (2026-10-07)** · **o nome `Scrinalia` e o rename do pacote
> (2026-10-07)** · **o desacoplamento institucional — o perfil de língua `pt-BR`, os dois catálogos
> do acervo com tela, e a configuração da origem (2026-10-07)** · **a autenticação — sessão por
> cookie no banco, argon2id, três papéis e as operações classificadas, com a autoria vindo da
> sessão em vez do request (2026-10-07)** · **a gestão de contas — `/api/v1/users`, a tela
> `Configurações › Usuários` e o menu que esconde a área que o papel não alcança (2026-10-07)** ·
> **o endurecimento da autenticação — bloqueio com backoff em sessão própria, rate-limit por
> endereço e `origin_guard` nas mutações (2026-10-07)**.

---

## 🎯 Caminho para a 1.0

> **Resposta curta: falta um ciclo — a documentação.** O software está pronto, a autenticação também; o
> *produto* ainda não. Nada aqui é feature nova: é o que separa "um sistema que funciona" de "um release
> que outra instituição consegue instalar, entender e usar com segurança".

### ✅ Já pronto para um release

- Pipeline completo e verificado ponta a ponta, com governança (`HUMAN_APPROVED` bloqueia IA).
- 23 telas de curadoria + painel de operação; Streamlit removido.
- Contrato OpenAPI gerado, commitado e com CI bloqueante; cliente TS gerado do contrato.
- 1.368 testes, CI com 3 jobs (lint, testes+migrações+contrato, frontend).
- Schema 100% sob Alembic, 32 migrações sem drift.
- **Autenticação entregue (B9.1–B9.3):** sessão por cookie com a linha no banco (só o sha256 do token),
  argon2id, três papéis e **cada operação de `/api/v1` declarando a sua permissão** — com um teste que
  falha se alguma ficar sem classificação. A superfície aberta são três operações, e a difusão
  continua aberta por design. O endurecimento fecha o resto: bloqueio com backoff gravado fora da
  transação do request, rate-limit por endereço e `Origin` checado nas mutações.
- Superfície pública **já projetada** (allowlist com partição exata e teste) — falta só o app.
- **Determinismo do contrato** corrigido: o OpenAPI não depende mais do `PYTHONHASHSEED`.
- **Licença fechada** (`AGPL-3.0-only` + termo de atribuição do §7(b), com rodapé na SPA e
  metadata no `pyproject.toml`/`package.json`) — ver ADR 0006.
- **Nome definido:** o projeto é **`Scrinalia`**, cunhado de `scrinium` — livre em todos os
  registries, em todos os domínios testados e no GitHub (ADR 0007).

### 🔴 Bloqueadores — sem isto não há 1.0

- [x] **Licença** — **decidida e aplicada em 2026-10-07**: **AGPL-3.0-only** + termo adicional de
      atribuição do **§7(b)**. Entregue: `LICENSE` (texto verbatim da FSF, conferido por
      `sha256 d8a6cc31…`), `LICENSE-ADDITIONAL-TERMS.md`, campos `license` no `pyproject.toml` e
      nos dois `package.json`, e o **rodapé de atribuição** na SPA
      (`lib/attribution.ts` → `AttributionFooter`, no `AppShell`). A decisão, o mapa dos cinco
      requisitos e as alternativas rejeitadas estão no **ADR 0006**.
      - **Por que não Apache-2.0** — que era a recomendação anterior deste TODO: ele não entrega
        nem o rodapé preservado nem a proibição de fork fechado, e o dono quer os dois. O medo que
        sustentava o Apache (instituição vetar AGPL) **não se confirmou no setor**, medido por SPDX:
        **AtoM** — o comparable direto em ISAD(G) — e **Archivematica** são **AGPL-3.0**, e a
        copyleft é a maioria (Tainacan/Omeka/CollectiveAccess em GPL-3.0). O risco real é estreito
        (o **fornecedor terceirizado** com veto interno, não a instituição) e a saída é
        **licenciamento duplo** — ver o gatilho de revisão do ADR 0006.
      - **O que a licença não consegue entregar, e é preciso saber:** um deploy **não modificado**
        pode ser oferecido como SaaS e cobrado (o §13 só dispara com modificação), e ninguém pode
        ser obrigado a contribuir **de volta para este repositório** — o §13 obriga a oferecer a
        fonte aos usuários daquela instalação. O pedido de retribuição está no `README`, como
        pedido.
      - **Nome:** **decidido e aplicado em 2026-10-07** — o projeto é **`Scrinalia`** (ADR 0007, §
        abaixo). O `attribution.ts` continua sendo o ponto único da troca: renomear de novo é uma
        linha, não uma tela.
- [x] **Auth (B9) — B9.1, B9.2 e B9.3 entregues em 2026-10-07.** Antes disso qualquer
      cliente que alcançasse a API aprovava fichas, apagava descrições, fundia taxonomia e **disparava
      workers**: eram **85 paths / 100 operações**, 58 delas de mutação, e **15 colunas de autoria em
      15 tabelas** guardavam texto livre (`changed_by`, `requested_by`, `decided_by`, `deleted_by`,
      `created_by`, `undone_by`). Hoje são **94 paths / 111 operações**, todas classificadas, e a
      superfície aberta são **três** operações: o login e as duas rotas de difusão.
      - **O que a execução corrigiu no plano, e vale para o próximo ciclo.** (1) O guard faz a
        **autenticação junto** com a autorização, e não um middleware: um middleware roda fora do
        `ExceptionHandlerMiddleware`, então o 401 saía **depois** da linha de acesso — a resposta que a
        frente mais vê era a única sem status e sem `X-Request-ID` ecoado. (2) O inventário de autoria
        do primeiro commit procurou cinco nomes e **esqueceu `undone_by`**: as três rotas de undo
        ficaram abertas por um commit a mais, e a migração que as corrige registra que existiu porque a
        lista era curta. (3) Duas rotas (`PATCH /documents/{id}`, `PATCH /taxonomy/tags/{id}`)
        **descartavam o autor em silêncio**, porque o campo sempre tivera default `None` e nenhum teste
        podia notar. (4) O autogerador do Alembic criou as FKs **sem nome** e o downgrade não passava —
        as migrações foram reescritas com `fk_<tabela>_<coluna>` e o round-trip downgrade/upgrade passou
        a ser verificado. (5) `EntityRepository.resolve_cross_domain_conflict` gravava
        `decided_by=source`, então "quem decidiu" respondia `JUDGE`/`HUMAN`; o teste **afirmava o
        defeito** e agora afirma a correção.
      - **B9.2 — entregue. Papéis na tela.** `/api/v1/users` (listar, criar, editar nome/papel,
        ativar/desativar, reset de senha, sessões ativas e revogação — uma ou todas) e o grupo
        **"Configurações"** no fim da sidebar, com `Usuários` primeiro, na tela
        `/configuracoes/usuarios`. Duas decisões que a execução fixou: (1) a senha criada na tela é
        **temporária** (`must_change_password=True`), como a do CLI — quem a digitou foi o
        administrador, não o dono da conta; e (2) revogar sessão de **outra conta** responde 404 e não
        200: o id sozinho não pode enumerar os acessos alheios. O menu deixou de ser o mesmo para todos
        os papéis: cada entrada declara a **área que a tela escreve** (`Permission`) e o shell esconde
        o que o papel não alcança — os **leitores puros** (acervo, árvore, diagnóstico) não declaram
        nada e continuam visíveis a todos, e o 403 com frase segue sendo a verdade para quem chega
        pela URL direta.
      - **B9.3 — entregue. Endurecimento, e a armadilha medida que ele fechou.** O contador de
        `failed_attempts`/`locked_until` **não podia** viver na transação do request: um login que
        falha levanta e o `provide_unit_of_work` faz rollback, então o contador seria apagado pela
        falha que ele conta. Agora ele é escrito por `LoginAttemptRecorder`, com **sessão própria
        commitada** como `archive_worker_runs`; o sucesso limpa o estado na transação do request (a
        assimetria é deliberada — um sucesso commita de qualquer forma). O backoff anda no próprio
        contador — o *n*-ésimo bloqueio dobra a janela até `AUTH_LOGIN_LOCKOUT_MAX_MINUTES` — e
        **só a senha correta** numa conta bloqueada ouve o motivo (`AccountLockedError`, 423); para
        quem adivinha a resposta continua `InvalidCredentialsError`, então o bloqueio não é oráculo
        de existência. Junto: rate-limit por endereço (janela deslizante **no processo**, 429 — um
        freio, não a garantia), `origin_guard` nas mutações (mesma origem ou `AUTH_TRUSTED_ORIGINS`;
        sem `Origin` passa, leitura nunca é checada) e `is_locked` calculado **no servidor** para a
        tela de contas. `last_login_at` já era escrito no B9.1; a auditoria de sessões é a lista de
        sessões por conta do B9.2, agora com o estado de bloqueio ao lado.
      - **Lacuna conhecida e registrada:** o `openapi.json` **não declara** o esquema de segurança do
        cookie. Um `security` global marcaria também as rotas de difusão e os probes como protegidos, o
        que seria pior que subdeclarar; declarar por rota é uma mudança maior que este ciclo.
      - **Decisões tomadas com o dono (2026-10-07).** (1) **Três ciclos**, não um: o mínimo
        defensável é o B9.1, e o que incha não é o login. (2) Cookie `HttpOnly` + sessão **no banco**,
        revogável — não cookie assinado stateless, não JWT no SPA. (3) Três papéis
        (`ADMIN`/`CURADOR`/`LEITOR`) com o **mapa de permissões em código**, não em tabela editável.
        (4) `changed_by` **sai** dos requests; o autor vem da sessão. (5) Primeiro admin e reset de
        senha por **CLI no pacote**. (6) O `--by` da CLI de workers continua texto livre — é operação
        de host, fora do modelo de ameaça HTTP. **OIDC/SSO descartado:** varia por instituição, e é
        exatamente o acoplamento que o ADR 0008 removeu.
      - **Correção de premissa:** não existe "BFF do curador" separado. `asgi.py` monta
        `apps/curator/dist` em `/` — mesma origem, sem CORS —, então o login são dois endpoints no
        próprio Litestar, cookie first-party e nenhum token em JS. O `apps/public`, quando existir,
        será o segundo processo, e ele só toca `/api/v1/public`, que continua aberto **por design**.
      - **B9.1 — entregue (o que segue é o desenho, verificado em execução).** Novo domínio
        `domains/identity/` — e não
        `core/`, que não tem nenhuma tabela hoje: usuário e sessão são contexto com ciclo de vida,
        não infraestrutura. `auth_users` + `auth_sessions` (só o **sha256** do token no banco, nunca
        o token), argon2id via `argon2-cffi` com parâmetros explícitos e rehash no login, e
        **hash-isca** para e-mail inexistente, para o tempo de resposta não enumerar quem existe.
        A trava é **uma policy**: tudo sob `/api/v1` exige sessão, exceto
        `POST /api/v1/auth/login` e `/api/v1/public/*` — `/health/*`, `/schema*` e os estáticos
        ficam fora por construção, então os dois probes do orquestrador não precisam de exceção.
        Autorização fina: cada handler declara `opt={"access": Permission.X}`, **um guard global**
        decide, e um teste de **partição exata** sobre o route map falha se alguma operação de
        `/api/v1` não estiver classificada — o mesmo padrão de `NOT_PUBLIC_FIELDS` e do
        `RouteMessageCode`, e o que impede "esqueci de proteger a rota nova" de virar processo.
        Endpoints: `login`, `logout`, `me` e `POST /auth/password` (a troca da própria senha entra
        **aqui**, não no B9.2: o CLI cria o admin com senha temporária e `must_change_password`, e sem
        essa rota ele fica preso num beco sem saída). **O ADR 0009 nasce neste ciclo**, não no B9.3: o
        registro pertence a quem toma a decisão.
      - **O que o B9.2 deixou armado para depois.** "Configurações" é o lugar natural para o que é
        *configuração* e não *operação* (settings de worker), deixando "Sistema" com execuções e
        diagnóstico. O que a tela ainda **não** faz é desabilitar botão a botão nas telas antigas: o
        menu esconde a área inteira, e um controle que o papel não pode usar responde 403 com frase —
        honesto, e a decidir caso a caso quando doer.
      - **O que custa mais que o login (medido).** (a) **11 campos `changed_by` em schemas de
        request** (mais o `requested_by` do runner): se a autenticação chega e o cliente continua
        podendo mandar o nome, o curador logado escreve o nome de outro e a auditoria fica **pior**
        que antes, porque passa a *parecer* confiável. O campo sai do request, o servidor preenche da
        sessão, e as 12 tabelas ganham `changed_by_user_id` (FK `SET NULL`) **preservando o texto
        antigo** — histórico não se reescreve. (b) **14 arquivos de teste de integração da API**
        sobem `create_app()` com `TestClient` e passam a precisar de sessão: uma fixture
        `logged_in_client` no `conftest.py` é o grosso mecânico do ciclo. (c) Contrato regerado no
        mesmo commit (`openapi.json` + `schema.d.ts`), com o teste de determinismo verde.
      - **Armadilhas já identificadas.** `Secure` no cookie **quebra o login em HTTP de LAN** →
        `AUTH_COOKIE_SECURE` condicional e documentado. **Guards do Litestar são cumulativos e não se
        removem por rota** (`resolve_guards` faz `extend` de controller para handler), então um guard
        de controller vazaria para os GETs que o LEITOR precisa alcançar — é por isso que a
        classificação é por handler com um guard global, e não por controller. 401/403 saem como
        `HTTPException` do Litestar, **nunca** `DomainException`: o handler de domínio mapearia para
        400 e — pior — faria uma **resposta devida ao cliente** entrar no ledger de falhas, que é
        para defeito. E 403, não 404: o 404-que-esconde é a regra da **superfície pública** para
        registro não publicado, não de recurso administrativo. `conftest.py` (que constrói o schema
        por `create_all`) e `migrations/env.py` precisam importar o pacote novo, senão as tabelas não
        existem no teste e o erro parece regressão. `last_seen_at` por request é um UPDATE por
        request → só atualizar se estiver velho.
      - **Fora do 1.0, com aviso:** OIDC/SSO, 2FA, e-mail e reset self-service. O `/schema` continua
        aberto.
      - **Ordem dos commits:** (1) `feat(identity)!` modelos, sessões, argon2id, CLI e migração;
        (2) `feat(api)!` sessão obrigatória, classificação de acesso e contrato (+ ADR 0009);
        (3) `refactor(api)!` autoria vinda da sessão + `changed_by_user_id`; (4) `feat(curator)`
        portão de login e remoção do autor livre; (5) `chore(todo)` fechar o bullet do B9.1;
        (6) `feat(identity)` contas e sessões administrativas (`/api/v1/users`); (7) `feat(curator)` a
        seção Configurações, a tela de contas e o menu por papel; (8) `test(archive)` a invariante de
        `path` verificada pelo próprio diagnóstico; (9) `feat(identity)` bloqueio com backoff, rate-limit
        e `origin_guard`; (10) `feat(curator)` o estado de bloqueio na tela de contas; (11) `docs(todo)`
        fechar o B9.3.
- [x] **Renomear o projeto, o pacote e o repositório** — **feito em 2026-10-07**: o projeto agora é
      **`Scrinalia`** (`refactor(pkg)!: rename memoria_curitibana to scrinalia`), com decisão e
      etimologia no **ADR 0007**. Escopo medido antes de executar: **240 arquivos** com uma das
      variantes (`memoria_curitibana` em 241, `memoria-curitibana` em 11, `Memória Curitibana` em
      6) — os números que este TODO trazia (256/209) estavam desatualizados.
      - **O que a primeira tentativa de escolha errou — e por que isso está registrado.** A busca
        inicial olhou só PyPI e npm e recomendou `Tabularium`. A busca profunda (registries, Docker
        Hub, DNS, **marca registrada** e produto vivo) desqualificou: **`Tabularium` é um sistema de
        gestão documental do MPDFT em produção desde 2016**, com portarias e relatório de cinco anos;
        **`Cimelia` tem marca registrada viva** (EUIPO 017967984 + equivalente britânica);
        `Repertorium` é empresa de IA ativa; `Arkheion` tem app brasileiro no Docker Hub e o `kh`/`ch`
        ambíguo; `Chartularius` tem o gêmeo **Cartularius**, produto comercial de gestão documental.
        **Para este projeto a classe das palavras reais disponíveis estava vazia** — por isso o nome
        é **cunhado**: de `scrinium` (o cofre dos rolos e os ofícios de registro imperiais) + `-alia`
        (como *marginalia*, *memorabilia*), "as coisas do arquivo". Livre em **todos** os registries,
        **todos** os domínios testados (inclui `.com` e `.com.br`) e como usuário do GitHub.
      - **O que NÃO entrou, de propósito:** o banco `memoriacuritibana`, o banco legado, o bucket
        MinIO `memoria-curitibana-bronze` e os objetos `archive_*`/`domain_*`. São identidade de
        **dado**: renomear apontaria uma instalação em produção para dados vazios. Ganho: uma
        instalação existente migra com `uv sync`, **sem migração de dados**.
      - **Passos manuais que faltam** (automação não faz): renomear o diretório do checkout (o `.pth`
        do editable aponta para `src/`, então `uv sync` depois), renomear o repositório no GitHub (o
        `sourceUrl` do rodapé já aponta para `/scrinalia` e **precisa resolver** — é a oferta de fonte
        do §13, hoje um 404), e recriar os containers (`docker compose down && up -d`, **nunca `-v`**).
      - **Cuidado aprendido, que vale para o próximo rename:** o `sed` **não pode** passar por um
        documento que *descreve* o rename. Ele reescreveu este bullet (que ficou dizendo
        "`scrinalia` está em 244 arquivos") e o `ADR 0002` (que passou a dizer que se considerou
        publicar como `scrinalia` — falso). O ADR 0002 foi restaurado no mesmo commit; este bullet,
        aqui. Documentos que falam sobre o rename são a exceção à regra de substituir tudo.
- [ ] **Base de documentação.** Hoje `docs/` tem só os 5 ADRs; o `README` é a porta de entrada e
      `AGENTS.md` é convenção interna. Falta o que um terceiro precisa para *instalar e operar*:
      - [ ] **Instalação e deploy** (Docker, variáveis de ambiente, migrations, build da SPA,
            CPU × GPU, requisitos de disco para os modelos).
      - [ ] **Guia de operação** (os 9 workers, a ordem do pipeline, o painel de sistema, o que
            cada fila significa, como reprocessar).
      - [ ] **Guia de curadoria** (o que o arquivista decide em cada tela, e por quê).
      - [ ] **Modelo de dados** (as camadas, o `execution_log`, a governança, o ledger).
      - **Decidido: versionada no repositório**, publicada a partir dele (ferramenta em aberto —
            ver "Decisão de documentação"). Uma wiki externa **não versiona com o código** e
            diverge; pode ser espelho, nunca a fonte.
- [x] **Desacoplar o que é específico de uma instituição** — **fechado em 2026-10-07** (ADR 0008),
      com a divisão por **natureza** em vez de por "onde guardar": a **língua** virou código
      (`core/language`, um perfil por idioma, `ACERVO_LANGUAGE` seleciona) e o **acervo** virou dado
      (duas tabelas + rotas + tela). O que foi entregue, medido:
  - [x] **Config morta removida.** `ARQDOC_BASE_URL`/`ARQDOC_VIEW_ENDPOINT` e o campo
        `arqdoc_configured` do `ProcessHealthDTO` saíram — com o contrato e o cliente TS regerados.
  - [x] **Vocabulário hardcoded virou catálogo.** `VOCABULARY_BY_CODE`/`VOCABULARY_BY_TOKEN`
        (38 entradas: IPPUC, SMU, SMMA, SEPLAD, CMC, FAS, SGM, SMCS, SMDS, OUVIDORIA e as siglas de
        arranjo) agora são linhas de `archive_arrangement_vocabulary`, semeadas pela migração
        `b3d6f1a2c4e7` e editáveis em `/vocabulario`. O serviço de proposta recebe o catálogo por
        repositório; o código inteiro continua tendo precedência sobre o último token.
  - [x] **`_PLACE_NAME` e `_PERSON_SUFFIX` viraram gazetteer tipado.** 71 termos
        (`archive_collection_terms`, `CollectionTermKind`: bairro, município, estado, região, país,
        pessoa) substituem as duas regex de Curitiba. O guarda continua **puro**: recebe um
        `CollectionVocabulary`, e um catálogo vazio não recusa nada — **sem fallback** para o acervo
        de referência, senão toda outra instituição seria Curitiba em silêncio.
  - [x] **`PUBLIC_SCRAPE_*` é declarado pelo adapter.** `SourceConfig` (`ingestion/ports.py`) é o
        que o adapter precisa para alcançar a origem; `build_scraper_adapter()` é o único ponto que
        lê o ambiente e falha rápido quando falta a URL.
  - [x] **O vocabulário de campos da origem saiu do domínio de staging.** Achado depois do resto, e
        era o último acoplamento: `map_raw_to_staging` carregava um mapa de **28 rótulos do site**
        (`Código de Referência`, `Âmbito e Conteúdo`…) para as colunas ISAD(G), mais as chaves
        privadas do adapter e os dois campos de data — o domínio de staging, que não pertence a
        instituição nenhuma, conhecia o vocabulário de um site. Virou `SourceSchema`, declarado ao
        lado do adapter (`PMC_SOURCE_SCHEMA`), selecionado por `ACERVO_SOURCE` e entregue ao
        transform como **contexto de validação do Pydantic**. Os rótulos continuam **não
        traduzidos** — são chaves do payload, e traduzir uma esvazia a coluna em silêncio. Sem
        default de origem: `get_source_schema()` levanta em vez de assumir o site de referência.
  - [x] **"O originário escreveu nada" tinha quatro definições.** Estava no parser de datas, na
        regex do guarda de assunto, no limpador de texto do staging e no validador de título —
        `não informado` sozinho vivia em três. Agora as grafias são `PT_BR.false_null_values` e os
        outros três são **views declaradas**: o conjunto de datas é o núcleo + os placeholders com
        forma de data, e o padrão do guarda é construído a partir de um **subconjunto declarado**
        (o veredito do guarda é comportamento medido — 1.489 de 8.155 tags — e alargá-lo mudaria
        quais tags chegam ao classificador, que é decisão de classificação, não limpeza).
  - [x] **Defeito corrigido de tabela:** um documento cujo título era um placeholder (`não
        informado`) era **rejeitado** pelo staging, porque `title` é obrigatório e a limpeza de
        false null o tornava `None` — a ficha inteira se perdia por um título ausente. Agora cai em
        `PT_BR.untitled_title` (`SEM TÍTULO`), que é o que o validador de qualidade já reconhece
        como título vazio.
  - [x] **A língua inteira saiu do meio do código.** As 573 linhas de stopwords (que estavam no
        motor de clustering e **não tinham teste nenhum**), a gramática de datas do staging, os
        prefixos de logradouro e as unidades do guarda, e as regras de plural do normalizador agora
        vêm de `PT_BR`. Dois acoplamentos que o TODO não listava entraram no mesmo passe: o
        dicionário `'portuguese'` do full-text (numa **coluna gerada**, então trocar de idioma é
        migração, não reboot) e o modelo `pt_core_news_lg` dos presets de NER.
  - **Os seletores e os nomes de campo em português ficam dentro do adapter** de propósito: são o
        contrato com *aquele* site, e nenhum valor de configuração abstrai um layout de HTML.
- [x] **`/health` de orquestrador** — **fechado em 2026-10-07** por `/health/live` +
      `/health/ready` (fora de `/api/v1` e do contrato), cada um com seu timeout e engine próprio.
      O `/system/health` continua sendo o painel humano: um responde *qual peça caiu*, o outro
      *esta instância recebe tráfego*. Ver ADR 0005.

### 🟡 Recomendados antes da 1.0

- [ ] **Documentar (ou resolver) a premissa de processo único.** O executor de workers roda
      **dentro da API** e a recuperação de órfãos no boot (`api/lifespan.py`) **assume um único
      processo** — `uvicorn --workers 4` corrompe o estado das execuções. Já está no ADR 0004, mas
      precisa estar no guia de deploy em letras grandes. **Não é quebra de versionamento** (é
      constraint de operação), mas é a armadilha nº 1 de quem instalar.
- [ ] **Rodar a IA pendente no acervo de referência** antes de declarar 1.0 "com IA": hoje
      `typology_v2` está em **0** e `embedding_v1` em **41** de 4.844. Ver "Pendências operacionais".
- [ ] **Teste de fumaça `e2e`** (marcado `slow`) que exercite um pipeline com engines reais. A
      suíte usa `mock_registry` (correto) e por isso a classe de bug do `suggest-macro` fica
      invisível.
- [x] **`.env.example` revisado** — o bloco `ARQDOC_*` saiu e o `ACERVO_LANGUAGE` entrou, com a
      nota de que trocar de idioma é migração (o dicionário do full-text alimenta uma coluna gerada).

### ✅ A decisão que interagia com versionamento — **fechada**

**Era a única do backlog que precisava vir antes da 1.0 por motivo de contrato.** Fechada em
2026-10-06 com a saída aditiva.

- ✅ **A API responde `code` **e** `message`.** Todo schema de resposta que carrega uma frase
  herda `RouteResponse` (`domains/archive/schemas/responses.py`), que pareia um
  `RouteMessageCode` com a sentença em português. São **21 códigos** cobrindo os 18 schemas.
  - **`code` é a identidade do desfecho** — estável, em inglês, e é por ele que um catálogo de
    tradução vai ser indexado. `message` **fica**: um cliente que não conhece códigos continua
    funcionando, e um código ainda sem tradução tem o que mostrar em vez de uma linha vazia.
  - **Aditivo, não incompatível:** um código novo é um membro novo no enum, e o cliente antigo
    cai no `message`. Era exatamente o que se queria evitar — trocar prosa por código depois da
    1.0 seria mudança de contrato.
  - **O front lê por uma costura única:** `routeMessage()` (`apps/curator/src/lib/messages.ts`).
    Os 13 pontos que imprimiam `.message` direto passaram a chamar a função; o mapa de traduções
    está **vazio de propósito** (o produto é em português hoje), então nada do que o arquivista lê
    mudou. Encher esse mapa é o que torna a interface multilíngue, sem tocar em tela nenhuma.
  - **Convenção presa por teste:** `testing/unit/api/test_route_message_codes.py` varre os dois
    pacotes de schema e falha se uma resposta com `message` ficar sem `code`. **Verificado
    reintroduzindo o defeito de propósito** — e a primeira versão do teste passou com o defeito,
    porque filtrava `obj.__module__` contra o **pacote** enquanto os modelos vivem nos
    submódulos; a correção foi varrer os submódulos, e o motivo está no docstring.
  - Registrado no `AGENTS.md` para as rotas que vierem.

### 🟡 Decisão de documentação — **encaminhada**

- ✅ **Documentação versionada, não wiki.** Decisão do dono em 2026-10-06: o conteúdo vive no
  repositório e é publicado a partir dele. Motivo registrado: uma wiki externa **não versiona com
  o código** e diverge — foi o que aconteceu com afirmações deste `TODO` e dos ADRs que ficaram
  falsas sem ninguém notar.
- [ ] **Escolher a ferramenta:** GitHub Docs (renderiza Markdown do próprio repo, zero build) ou
      **MkDocs Material** (build estático, versionamento por release, busca própria, `mkdocstrings`
      para puxar docstrings do Python).
      - **Recomendação: MkDocs Material**, se a documentação for crescer além de uns poucos guias:
        dá versionamento por release (`mike`), busca e referência de API gerada do código. GitHub
        Docs basta se o objetivo for só publicar os guias que já existem.
- [ ] **Escrever os quatro guias** (instalação/deploy, operação, curadoria, modelo de dados) —
      ver o bloqueador de documentação acima.

---

## 🧭 Backlog pós-1.0

> Registrado a pedido do dono. Cada item diz se interage com versionamento.

### 1. Processamento fora da API, agendador e IA em outra máquina

Tirar os workers do processo da API, criar um agendador (cron/retry) e permitir rodar a IA numa
máquina com GPU que devolve os dados para a API numa VPS.

- **Interage com versionamento?** **Não quebra o contrato**, mas muda a **semântica** de
  `POST /system/workers/{name}/runs`: de "executa agora, neste processo" para "enfileira para um
  runner". Se a resposta continuar sendo `WorkerRun`, o schema não muda; o que muda é o *tempo* e a
  *garantia*. Vale desenhar a rota já pensando nisso.
- **O que fazer na 1.0:** apenas **documentar a premissa de processo único** (§ acima). O
  desenho do protocolo runner↔API é um ADR próprio quando chegar a hora.

### 2. Internacionalização (i18n)

Extrair todas as strings das páginas para um arquivo de idioma.

- **Interage com versionamento?** **Sim, e é o item crítico** — ver "A decisão que interage com
  versionamento". Se a 1.0 adicionar `code` ao lado de `message`, a tradução depois é **aditiva**;
  se não, vira mudança incompatível.
- **Na SPA:** ~255 strings PT hardcoded nas rotas, mais os `lib/` (`format.ts` formata data e
  número em pt-BR). Não há nenhuma infra de i18n hoje (`i18n`/`useTranslation`/`intl`: zero).
- **No servidor:** prompts de LLM em português **não devem ser traduzidos** (eles raciocinam sobre
  texto em português — está no `AGENTS.md`), e os **rótulos de campo da origem** tampouco: são as
  chaves do payload, e traduzir uma esvazia a coluna em silêncio. Eles moram no `SourceSchema` da
  origem, não no domínio de staging.

### 3. Site público (`apps/public/`)

- **Interage com versionamento?** **Não.** É um app novo consumindo rotas que já existem
  (`/api/v1/public/*`), com a projeção e a allowlist prontas e testadas. Aditivo por construção.
- **Bloqueio real, e é de produto:** o predicado é `is_published` e **0 de 4.844** estão
  publicados. O site nasce vazio; o trabalho é de curadoria, não de código.

### 4. Desacoplamento institucional completo — ✅ **antecipado para a 1.0 e fechado**

Estava aqui como continuação pós-1.0; o dono decidiu fazer **tudo antes do release**, e o ciclo foi
fechado em 2026-10-07 pelo **ADR 0008**. O que a medição do backlog registrava, e o destino de cada
artefato:

| Artefato | Tamanho | Destino |
| --- | ---: | --- |
| `engines/clustering/stopwords.py` | 573 linhas | **Língua** → `core/language/pt_br_stopwords.py`, no perfil `pt-BR` |
| `domains/staging/dates.py` | 124 linhas | **Língua** (a gramática) → perfil; o algoritmo (a ordem das tentativas) ficou |
| `domain/vocabulary.py` | 235 linhas | **Partido:** as regras de PT foram para o perfil; os bairros e nomes de pessoa viraram `archive_collection_terms` |
| `hierarchy_proposal_service.py` | 42 linhas de mapa | **Acervo** → `archive_arrangement_vocabulary` |
| `domains/staging/schemas.py` | — | **Achado depois:** os 28 rótulos da origem saíram do transform e viraram `SourceSchema` (`PMC_SOURCE_SCHEMA`) — continuam **não traduzidos**, mas deixaram de ser constante do domínio de staging |
| `models/document.py` + `document_repo.py` | — | **Língua** (não estava na lista): o dicionário `'portuguese'` do full-text |
| `engines/NER/registry.py` | — | **Língua** (não estava na lista): o modelo `pt_core_news_lg` dos presets |

- **A pergunta de desenho ("banco ou arquivo?") foi respondida por natureza, não por conveniência:**
  língua é código (um perfil por idioma, testável, sem bootstrap) e acervo é banco (o curador edita
  sem deploy). O ADR 0008 registra as alternativas rejeitadas — inclusive "tudo no banco", que
  esbarraria na coluna **gerada** do full-text.
- **Não há tenant, e o ADR diz isso em vez de inventar um.** Medido nas 30 tabelas: nenhum
  `institution_id`/`collection_id`. A instalação **é** a instituição, então os catálogos são globais
  — e o gatilho de revisão do ADR é exatamente o dia em que isso deixar de valer.
- **O que continua fora, de propósito:** os prompts de LLM em português (raciocinam sobre texto em
  português), os **rótulos de campo da origem** (chaves do payload; moram no `SourceSchema`, não no
  domínio) e as ~334 strings PT da SPA (item 2, i18n, com `routeMessage()` como costura). O nome do
  banco `memoriacuritibana` também fica: é identidade de dado, decidido no ADR 0007.

### 5. Ingestões plurais — configuração por origem

Tratar a origem como objeto de primeira classe: scraper do PMC contínuo, ingestão manual por CSV e
um scraper de outra instituição, cada um com ciclo de vida, periodicidade e **configuração
própria** (colunas lidas, limpeza, limiares, talvez o preset). Consequência no painel: um eixo a
mais ("de qual origem é esta fila?") e a origem no ledger de execuções.

- **Interage com versionamento?** **Não** — é aditivo (uma coluna/tabela de origem e um filtro).
- **Relação com a 1.0:** o item "desacoplar `PUBLIC_SCRAPE_*`" é o primeiro passo disto. Fazer o
  adapter **declarar o que precisa** (em vez de ler `settings` global) é o que permite N origens.

### 6. Outras dívidas já registradas

- **Entidades sem catálogo de propostas** — os defeitos de merge foram corrigidos, mas não há
  proposta, ledger nem undo como nas tags. A tela **avisa** que unificar não tem desfazer.
- **Colisão tag × entidade em lote** — os 5.050 nomes idênticos são uma decisão *por categoria*
  ("logradouro é entidade"), e a tela ainda pede uma por par.
- **Purga de stopwords é a única escrita destrutiva sem undo** — tem preview; torná-la reversível
  (ledger, como o merge) é decisão em aberto.
- **Busca híbrida (RRF)** e **qualidade semântica** (o MRR caiu 0.019 enquanto o Hit@10 subiu).
- **Sentry / agregação de falhas** — ✅ **resolvido em 2026-10-07 pela metade local**: a causa raiz
  é uma coluna gerada, compartilhada pelos dois ledgers, e a tela agrupa. O encaminhamento para um
  serviço hospedado continua possível **sem tocar no caminho de escrita** — o gatilho e o custo
  aceito (sem alerta nem paging) estão no ADR 0005.
- **`path` desnormalizado** — ✅ **resolvido em 2026-10-07**: a invariante é verificada no CI pelo
  **próprio diagnóstico** que a tela usa. Os dois testes que reescreviam a comparação em SQL
  (`test_hierarchy_service.py`, `test_hierarchy_materialisation_service.py`) passaram a perguntar a
  `find_path_divergences` — a query que serve `PATH_DIVERGENCE` — e não uma segunda definição que
  poderia continuar verde enquanto a rota divergisse. A verificação cobre os **três escritores**
  (criar, mover a subárvore, materializar e desfazer) e os **dois lados**: uma árvore saudável
  responde vazio, incluindo o *early return* do total zero, e a linha corrompida de propósito
  continua sendo encontrada — sem esse par, um diagnóstico que sempre respondesse "nada errado"
  passaria despercebido.

---

## ✅ Fases fechadas (síntese)

### Fase 1 — Fundação e Core Pipeline

- ✅ **Ingestion & Staging** com hash CDC; staging converte payload cru em colunas ISAD(G) tipadas,
  parseia datas em 3 formatos, normaliza pontos de acesso; o não mapeado cai em `raw_metadata`.
- ✅ **Archive** com schemas estritos, idempotência por `execution_log` (JSONB, GIN) e governança.
- ✅ **9 workers** no runner: `transfer → cleaning → ner → typology → thumbnail → conflict-judge →
  macro-category → quality-validator → embedding`.
- ✅ **Governança nos 9 workers.** `ai_writable_documents()` bloqueia `HUMAN_APPROVED`/`REJECTED`.
  **Uma exceção documentada:** `worker_embedding` (índice derivado do texto, não conteúdo
  arquivístico) — escreve só `embedding` + carimbo, e pula `REJECTED`.
- ✅ **Governança bidirecional** em lugares distintos de propósito: vitória da entidade → nome da
  tag em `DomainStopwords` (escopo TAG); vitória da tag → `domain_ner_exclusions` (decisão de
  curadoria com `reason`/`source`/`tag_id`). **Não colapsar as duas.**
- ✅ **Bloqueio de NER por limite de token**, não por nome exato: o spaCy funde tokens vizinhos e
  devolve `"IPTU do Batel"` como uma entidade. Um teste com `mock_registry` não pegaria isso.

### Fase 1.5 — Macro Categorias

- ✅ **O diagnóstico do plano estava errado, e a medição corrigiu.** O plano dizia que a frase NLI
  consertaria a classificação; medido numa bancada de 44 tags (3 formatos × 3 arranjos × 2 modelos),
  a frase dá **0.000** de acurácia com 65% das tags numa gaveta — **ela é o colapso**, não a cura.
  O ganho que o plano media era artefato de comparar frase contra nome nu.
- ✅ **A causa real tinha duas metades:** o vocabulário não cobria o acervo (`igrejas` alcança 2.474
  documentos e não havia "Religião"), e `Instituição`/`Localidade` **nunca foram assuntos** (são
  proveniência e geografia).
- ✅ **Vocabulário de 5 → 8 gavetas** derivadas das tags reais; `Saúde` e `Administração` cortadas
  por falta de evidência. As três antigas **desativadas** (nunca deletadas: FK `SET NULL`).
- ✅ **`archive_tag_facets`** dá às tags um eixo que não é assunto (chave composta).
- ✅ **`NENHUMA` com dois mecanismos:** guarda determinística (data, placeholder, logradouro,
  número — recusa **1.489 de 8.155** tags reais) + catálogo curado `domain_subject_exclusions`.
  `subject_exclusion_signal` explica *por que* o guarda recusou, na mesma ordem de predicados.
- ✅ **Limiar 0.40 → 0.55 com fila atrás** (`SUBJECT_LOW_CONFIDENCE`).
- ✅ **Carimbo = hash do conjunto de rótulos** (a V3 expôs a falha: aposentou uma gaveta enquanto
  suas tags mantinham `DONE`).
- **Aberto:** acurácia de 0.500 (mDeBERTa) / 0.575 (xlm-roberta) — limite do zero-shot NLI com
  sintagma nominal, decidido **resolver por curadoria**. `xlm-roberta` medido e descartado por ora.

### Fase 2 — API e Curadoria humana

- ✅ **79 paths / 94 operações**, controllers em `api/controllers/`, composição por request
  (`provide_unit_of_work` é dono da transação).
- ✅ **Curadoria humana:** `PATCH /documents/{id}` edita qualquer campo ISAD(G), grava antes/depois
  em `archive_document_revisions` e marca `HUMAN_APPROVED`. `POST/DELETE /documents/{id}/tags[/{id}]`
  e o par de entidades fazem o mesmo para os assuntos de **uma** descrição.
- ✅ **As duas capacidades que faltavam ganharam botão:** criar um nível que o código não implica
  (`POST /hierarchy/nodes`) e unificar duas tags escolhidas pelo arquivista
  (`POST /taxonomy/tags/merge` + preview).
- ✅ **Exclusão definitiva** (`DELETE /documents/{id}`) com duas guardas (recusa nó com filhos;
  exige o código de referência digitado) e retrato ISAD(G) em `archive_document_deletions` —
  **trilha, não lixeira**.

### Fase 2.5 — Hierarquia

- ✅ **H1–H8 entregues e verificados em escala.** Catálogo de níveis (seed NOBRADE, migração em
  duas etapas, backfill 3.608/3.608); árvore com `parent_id`/`path`/`level_id`, `RESTRICT` no pai,
  recálculo de subárvore em uma instrução; proposta read-only; **materialização por decisão humana**
  (`archive_hierarchy_node_plans`, `collapse_into_code`, preview pelo mesmo planejador, ledger
  reversível); contrato de ingestão (`parent_reference_code`); busca por ramo (`ancestor_id`);
  `ancestors[]`/`children_count` no read view.
- ✅ **O que a medição corrigiu no plano:** a fatição ingênua criaria **1.123 pais de 1 documento**
  na família SMU (o fatiador virou ciente de vocabulário); a profundidade do código **não**
  determina o nível (5 tokens têm 2.466 Itens, 1 Série e 1 Seção); eram **20 rungs → 81 nós**
  propostos, não milhares.
- ✅ **O caso que define a feat:** `BR PRADAP SMU ED AL` e `... ED AL CONSTR` são **um único nível**,
  e nenhum fatiador pode saber isso — por isso a materialização é decisão registrada, não script.
- **Aberto:** 24 de 81 rungs decididos; 7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD` (a família SMU não
  cabe na escada de 6 sem repetir ordinal).

### Fase 3.5 — Qualidade do dado de entrada

- ✅ **O maior ganho medido do projeto.** 53% do acervo compartilhava o mesmo bloco de
  `scope_content`; 2.467 tinham o prefixo `Registros Fotográficos -`. Isso dominava os embeddings.
- ✅ **A composição do texto vive em SQL** (`text_quality_repo.py`): o Postgres normaliza espaços e
  subtrai os trechos aprovados, e a **mesma expressão** alimenta o texto do embedding, o MD5 do seu
  carimbo, o NER e a tipologia. **Não reintroduzir composição em Python.**
- ✅ **`scope` por trecho** (`EMBEDDING`/`NER`/`TITLE`) — nasceu porque a medição mostrou que o
  prefixo de título **ajuda** o título derivado e **prejudica** o vetor. **Aprovar tudo o que a
  máquina sugere piora o ranking** (Hit@10 0.562 → 0.500).
- ✅ **Merges de tags:** decisão durável separada da escrita, dry-run pelo mesmo planejador,
  ledger por tag absorvida **antes** de qualquer mudança, e **undo** que restaura linha, vínculos,
  classificação e estado de grafia. `repoint_synonyms()` **antes** de `delete_tags()` (a FK é
  `ON DELETE CASCADE`).
- ✅ **`repoint_synonyms` também no eixo de entidades** (mesmo defeito, mesma correção).
- ✅ **Datas recuperadas:** +201 documentos saíram de "sem data" (47,0% → 52,6%).
- **Aberto:** busca híbrida (RRF); lematização de tags ficou como **sugestão**, não reescrita.

---

## 🟡 Fase 3 — o que segue aberto

- [ ] **Busca híbrida (RRF)** — combinar lexical + semântica. A semântica funciona (pgvector,
  `vector(384)`, HNSW cosseno) mas o ranking é fraco: o MRR caiu 0.019 enquanto o Hit@10 subiu.
- [x] **Rastreamento de erros** — **fechado em 2026-10-07** por agregação local, não por Sentry: a
  causa raiz é uma coluna **gerada** em `archive_worker_runs` e em `archive_api_errors`, calculada
  pela **mesma** função SQL `archive_error_fingerprint`, e `GET /api/v1/system/failures` agrupa os
  dois ledgers. Motivo da escolha local (e o custo aceito: **sem alerta nem paging**) no ADR 0005.
- [ ] **Agendamento e retry** — o disparo manual existe (CLI e tela, com guarda de concorrência no
  banco) e uma execução interrompida vira `INTERRUPTED` no próximo boot. **Não há cron nem retry.**
- [x] **`/health` de orquestrador** — **fechado em 2026-10-07**: `/health/live` (sem I/O) e
  `/health/ready` (`SELECT 1` com timeout curto → 200/503), fora do versionamento e do contrato.
- [ ] **Teste de fumaça `e2e`** com engines reais.

### Observabilidade (entregue 2026-10-07)

Decisão em `docs/adr/0005-observability-without-an-external-service.md`. Duas superfícies, dois
públicos: o **orquestrador** recebe um status code e nada mais; o **curador** lê a causa agrupada.

| Capacidade | Como funciona |
| --- | --- |
| Vivo ou morto | `GET /health/live` não toca em nada — um probe que consulta o banco reinicia a API quando o banco reinicia |
| Pronto para tráfego | `GET /health/ready` roda `SELECT 1` em engine próprio (`NullPool`, `connect_timeout`, `statement_timeout`) e responde **503** |
| Fora do contrato | As duas rotas ficam **fora** de `/api/v1` e do OpenAPI (`include_in_schema=False`), como o `/schema` do Litestar |
| Agrupar falhas | `GET /api/v1/system/failures` une os dois ledgers pelo **mesmo** fingerprint, com ocorrências, primeira/última vez e as fontes |
| A causa raiz | Coluna **gerada** por `archive_error_fingerprint`, `IMMUTABLE`: o `ALTER TABLE` preencheu o passado com a expressão que o futuro usa — uma definição só |
| Separar causas | O texto gravado passa a levar a classe (`KeyError: 'nome'`); sem ela, duas falhas com a mesma frase viram uma causa só |
| 500 da API | Handler próprio registrado pela **chave de status 500** (não por `Exception`, que sombrearia o 404) grava em `archive_api_errors` com sessão própria |
| Correlacionar | `X-Request-ID` aceito ou gerado, no header, no `scope` e no contexto do loguru; a tela mostra a referência, o log tem a linha |
| Não inundar o log | Os dois probes ficam fora do log de acesso — um orquestrador pergunta a cada poucos segundos |

**O que ficou de fora, de propósito:** alerta e paging. Sem um serviço externo ninguém é avisado de
uma causa nova; é o preço da decisão local e está registrado como gatilho de revisão no ADR 0005.

### Painel de operação (entregue 2026-10-06)

`/sistema/workers`, `/sistema/execucoes`, `/sistema/diagnostico`, servidos por `/api/v1/system/*`.
Decisão em `docs/adr/0004-worker-execution-from-the-api.md`.

| Capacidade | Como funciona |
| --- | --- |
| Ver os workers | `workers/catalogue.py` é a definição única (ordem, eixo, governança, carimbo, contador); **importa nenhum worker**, resolvendo por caminho pontilhado com cache — subir a API não paga spaCy (~1,7 s) |
| Ver preset e modelo | `describe_config` em cada registry é o gêmeo de leitura do `get_engine` (não instancia); um teste compara os dois |
| Ver a fila | Cada worker expõe `count_pending` com o **mesmo** predicado do `execute`; `conflict-judge` é explicitamente não mensurável |
| Configurar | `archive_worker_settings` (linha parcial: `NULL` segue o código) + revisões; precedência `argumento explícito > override > default` |
| Rodar | `POST /system/workers/{name}/runs`; o executor roda **um worker por vez** (são CPU-bound) |
| Concorrência | Índice único **parcial** `uq_worker_run_active` — a guarda é do banco, não de um lock de processo que `--reload` derrubaria |
| Histórico | `archive_worker_runs`, gravado pelo runner para **CLI e tela**, com configuração resolvida, duração e resultado |
| Recuperação | `api/lifespan.py` marca `INTERRUPTED` o que um processo morto deixou em voo (tolerante a banco fora) |
| Diagnóstico | Banco, Ollama (modelos exigidos × instalados), bucket e config; **nenhum segredo** é devolvido |

Corrigiu um defeito real: os presets de LLM **fixavam** `http://localhost:11434` e ignoravam
`OLLAMA_HOST_URL` — o painel mostraria um host que não era o efetivo.

---

## 🔧 Pendências operacionais no acervo (não são código)

O código está pronto; **o acervo de referência está parcialmente processado**. Medido em
**2026-10-06** (o comando de medição está no handoff — **re-meça antes de confiar**):

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

**Leitura:** o NER **já rodou** (4.826), mas **tipologia e embedding estão pendentes** — a
tipologia em zero e o embedding em 41 de 4.844. Enquanto isso, a busca semântica serve vetores
antigos para 3.608 documentos e **nenhum** para os ~1.218 que entraram no re-parse.

### O que **não** pode rodar no acervo real sem decisão do dono

- `POST /hierarchy/materialisation/apply` — **já rodou uma vez** (4.816 descrições ganharam pai).
  Rodar de novo move mais; tem preview e undo.
- Aprovar rungs e aplicar merges em massa — decisões de conteúdo, não de engenharia.
- `POST /taxonomy/tags/stopwords/purge` — **apaga tags e não tem undo** (o merge tem ledger).
- `DELETE /documents/{id}` — exclusão definitiva (trilha, não lixeira).
- Os workers de IA — **a janela de reprocessamento fecha na primeira ficha aprovada por humano**.

> **Decisão de produto pendente:** rodar a IA (tipologia, embedding, quality-validator) **antes ou
> depois** de decidir os 81 rungs? Enquanto não rodar, a UI mostra menos do que o sistema sabe.

---

## ✅ Verificação executada (evidências)

### Gate no estado atual (2026-10-07)

| Verificação | Resultado |
| --- | --- |
| `pytest` (unit + integração) | **1.368 passed** |
| `ruff check` / `ruff format --check` | limpos (372 arquivos) |
| `basedpyright` | **0 errors, 0 warnings** |
| `alembic check` | **sem drift** (32 migrações) |
| `alembic downgrade -1` + `upgrade head` | as duas tabelas e o enum voltam, o seed reaplica (38 + 71 linhas) e `check` segue sem drift |
| `tsc` / `eslint` / `vite build` | limpos |
| Contrato OpenAPI | **94 paths / 111 operações / 182 schemas**, sem drift (cliente TS incluído) |
| `/api/v1/users` em execução real (teste de integração) | criar, editar, desativar, resetar senha, listar e revogar sessões — com a permissão `ADMIN` e a sessão de outra conta respondendo 404 |
| Tela `Configurações › Usuários` | `tsc`/`eslint`/`vite build` limpos; o menu esconde a área que o papel não alcança |
| Bloqueio em execução real (teste de integração) | 3 falhas → a senha **correta** responde **423** mesmo com o rollback de cada request; a conta lê `failed_attempts`/`locked_until` |
| Rate-limit e `Origin` em execução real | 429 ao estourar a janela por endereço; **403** em mutação de origem estranha, **200** na leitura, e o **proxy do Vite** (Host preservado) aceita a origem do dev |
| `/health/live` e `/health/ready` em execução real | 200 com o banco de pé, **503** com o banco parado |
| `/api/v1/vocabulary` em execução real | 38 nomes de arranjo e 71 termos semeados, com `tag_count` por grafia |
| Tela `/vocabulario` renderizada no browser | duas seções, tema aplicado, **zero erro de console** |
| `SourceSchema` da origem em execução real | 28 rótulos + 2 campos de data; o mapa é conferido contra `StagingDocumentDTO.model_fields` e a origem resolve por `ACERVO_SOURCE=pmc` |
| Título placeholder no staging | `não informado` deixa de ser rejeitado e vira `SEM TÍTULO` (antes: documento perdido) |

### Ciclos anteriores (preservados)

| Verificação | Resultado |
| --- | --- |
| **Banco reconstruído** | 15 tabelas copiadas; `alembic check` sem drift |
| **Worker `embedding`** | 3.608/3.608 em ~1 min; `cos(guardado, recalculado) = 1.0` |
| **Catálogo de trechos** | 3.608 docs → 5 candidatos (bloco 2.467, prefixo 2.467…) |
| **Medição antes/depois (16 consultas)** | separação 0.769 → 0.504; Hit@10 0.562 → **0.625**; **aprovar tudo piora** (0.500) |
| **Sugestões de merge** | 411 clusters (267 `TRIGRAM`, 101 `MIXED`, 43 `PLURAL`) |
| **Undo ao vivo** | `vendas ← venda` desfeito e reaplicado: tag, id e vínculo restaurados exatamente |
| **Hierarquia em escala** | `apply` 1,7 s; 1 raiz; profundidade 5; `undo` com 3.619 linhas restauradas |
| **Bancada do classificador** | 44 tags × 3 formatos × 3 arranjos × 2 modelos |
| **`GET /conflicts/cross-domain`** | **52,9 s → 1,42 s**, resultado idêntico (o `OR lower()` era redundante) |
| **Prefilter de comprimento** | descartava **52–65%** dos pares reais; removido |
| **Escrita pela UI no browser** | 8 de 8 checagens contra a API (DevTools Protocol) |

---

## 🐞 Bugs e limites conhecidos

1. **Acurácia de assunto em 0.500/0.575** — limite do zero-shot NLI com sintagma nominal.
   Decisão: aceitar e resolver por curadoria.
2. **Busca semântica com qualidade fraca** — a híbrida (RRF) continua pendente; o MRR caiu 0.019.
3. **Autenticação entregue (B9.1–B9.3), com limites conscientes** — sessão, papéis, guard por operação,
   gestão de contas, bloqueio com backoff, rate-limit e `Origin`. O que **não** existe, de propósito:
   2FA, SSO/OIDC e recuperação de senha por e-mail (o CLI no host é o caminho de volta). Dois limites
   técnicos registrados: o rate-limit é **por processo** (não distribuído — a garantia durável é o
   bloqueio por conta) e a sessão revogada guarda `revoked_at` mas **não quem** a revogou.
4. **O acervo de referência está parcialmente processado** — tipologia e embedding pendentes.
5. **`path` desnormalizado** — a invariante é mantida pelo serviço e **verificada no CI** pelo próprio
   diagnóstico depois de cada escritor (criar, mover, materializar/desfazer). O limite que resta é que
   o banco **não** a garante: um `UPDATE` manual fora do serviço ainda pode divergir, e é o
   `PATH_DIVERGENCE` que o encontra.
6. **7 nós com `LEVEL_NOT_ALLOWED_AS_CHILD`** — a família SMU não cabe na escada de 6 níveis.
7. **Premissa de processo único** — o executor na API + a recuperação de órfãos assumem
   `uvicorn --workers 1`. Documentado no ADR 0004; **precisa estar no guia de deploy**.
8. **Entidades sem ledger de merge** — unificar entidade não tem desfazer; a tela avisa.
9. **Purga de stopwords sem undo** — é a única escrita destrutiva que não é reversível.
10. **Observabilidade sem alerta** — o agrupamento por causa raiz é local e ninguém é avisado de uma
    causa nova: alguém precisa abrir a tela. É o custo aceito da decisão local (ADR 0005), e o
    gatilho de revisão está lá.

### Modos de falha a vigiar (aprendidos, valem para código novo)

- **Uma rota que publica um vocabulário tem de cobrir todo produtor.** `/hierarchy/flags`
  anunciava só `ProposalFlag` e o front renderizava código cru — as rungs carregam flags de
  **quatro** origens. Um teste preso aos produtores vale mais que a leitura do código.
- **Um campo parseado e não persistido falha em silêncio.** `access_conditions` existia no staging
  e não no archive, sem erro nenhum.
- **`scope` é nome reservado do Litestar** (ASGI scope): um handler com esse parâmetro recebe o
  request cru. As rotas usam `axis`/`pair_kind`.
- **`Field(description=...)` num campo de enum compartilhado reescreve o schema do enum** para
  todo o documento, e qual campo vence depende do `PYTHONHASHSEED` — o contrato saía diferente de
  código idêntico e o CI falhava ao acaso. Documente o **tipo**, nunca o campo.
- **Um `ILIKE` sobre texto digitado tem de escapar curingas** (`escape_like()`), senão um `%` vira
  "todos os registros" e a consulta abandona o índice de trigrama.

---

## ▶️ Handoff — como rodar

```bash
bun run dev            # docker compose up -d + API :8000 + SPA :5173 (proxy /api -> :8000)
# peças soltas: bun run db:up | bun run api:dev | bun run curator:dev
```

Um **502 em `/api`** quer dizer que a API não está no ar — a SPA responde 200 e o sintoma parece
bug de front.

```bash
# banco de teste deste checkout está na porta 5434
TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_db .venv/bin/pytest -q
.venv/bin/basedpyright && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/alembic check
bun run --cwd apps/curator typecheck && bun run --cwd apps/curator lint && bun run --cwd apps/curator build
```

**Nunca** rode `alembic upgrade head` no banco de **teste**: o `create_all` do conftest pula o que
já existe e a suíte passa a rodar contra o schema migrado (53 falhas + 42 erros que parecem
regressão).

### Medir o acervo (não confie em número congelado)

```bash
docker exec scrinalia_db psql -U admin -d memoriacuritibana -c "
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
- `docs/adr/` — decisões aceitas: Litestar (0001), layout `src/` (0002), monorepo e stack do
  curador (0003), execução de workers pela API (0004), observabilidade sem serviço externo (0005).
- `.analysis/` — **gitignored**, notas de trabalho deste checkout (planos, sitemap, refino de UI).
  O que precisa sobreviver a um clone está **aqui** e no `AGENTS.md`.
