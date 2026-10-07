# 🗺️ Roadmap & TO-DO — Motor de Enriquecimento de Arquivos (AI-Driven)

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não
> apenas lido no código. `[ ]` = pendente. `[~]` = parcial.
>
> **Estado do gate (2026-10-07, após o desacoplamento):** **1.219 testes** passando · `ruff` limpo
> (338 arquivos) · `basedpyright` **0 erros** · **29 migrações** sem drift · contrato OpenAPI
> **85 paths / 100 operações / 173 schemas**, gerado, commitado e sem drift · SPA (`tsc`, `eslint`,
> `vite build`) limpa e servida pelo próprio Litestar · **8 ADRs**.

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
| 4 | UI, BFF e publicação | 🟡 **Curador completo** (22 telas); faltam **auth** e **site público** |
| **5** | **Release 1.0** | 🟡 **Iniciada** — licença (0006), nome (0007) e desacoplamento (0008) fechados; faltam auth e docs |

**O sistema está funcionalmente pronto.** Ingestão → staging → archive → enriquecimento por IA →
curadoria humana → bloqueio de reprocessamento, tudo verificado ponta a ponta. O **curador tem 22
telas** cobrindo todo o sitemap mais o painel de operação, e o **Streamlit saiu do repositório**.

**O que falta para uma 1.0 é de outra natureza:** não é feature, é *produto*. Documentação,
desacoplamento institucional e autenticação — a **licença** (ADR 0006), o **nome** (ADR 0007) e o
**desacoplamento** (ADR 0008) foram fechados em 2026-10-07. Restam a **autenticação** e a **base de
documentação**. Detalhe na seção seguinte.

> **Ciclos entregues, em uma linha cada** (o detalhe está nas fases fechadas):
> contrato + onda 1 (2026-10-05) · onda 2, o plano de arranjo (2026-10-05) · ondas 4–6 e a remoção
> do Streamlit (2026-10-06) · refino de curadoria e o painel de operação (2026-10-06) · as três
> lacunas de curadoria — colisão, faceta de anomalia, "não é assunto" (2026-10-06) · o catálogo de
> tipologias e o contrato determinístico (2026-10-06) · **a observabilidade local — `/health` de
> orquestrador, causa raiz agrupada e request id (2026-10-07)** · **a licença `AGPL-3.0-only` e a
> atribuição do autor no rodapé (2026-10-07)** · **o nome `Scrinalia` e o rename do pacote
> (2026-10-07)** · **o desacoplamento institucional — o perfil de língua `pt-BR`, os dois catálogos
> do acervo com tela, e a configuração da origem (2026-10-07)**.

---

## 🎯 Caminho para a 1.0

> **Resposta curta: não estamos perto — estamos a ~2 ciclos.** O software está pronto; o *produto*
> não. Nada aqui é feature nova: é o que separa "um sistema que funciona" de "um release que outra
> instituição consegue instalar, entender e usar com segurança".

### ✅ Já pronto para um release

- Pipeline completo e verificado ponta a ponta, com governança (`HUMAN_APPROVED` bloqueia IA).
- 22 telas de curadoria + painel de operação; Streamlit removido.
- Contrato OpenAPI gerado, commitado e com CI bloqueante; cliente TS gerado do contrato.
- 1.175 testes, CI com 3 jobs (lint, testes+migrações+contrato, frontend).
- Schema 100% sob Alembic, 28 migrações sem drift.
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
      - **Nome:** ainda em aberto (§ abaixo) — o `attribution.ts` é o ponto único da troca.
- [ ] **Auth (B9).** Hoje qualquer cliente que alcance a API aprova fichas, apaga descrições, funde
      taxonomia e **dispara workers**. `changed_by`/`requested_by` são texto livre.
      - Um 1.0 que outras instituições instalam **precisa** de autenticação, mesmo que mínima —
        porque o primeiro deploy exposto fica aberto. Alternativa honesta: shippar 1.0 com aviso
        explícito de "não exponha" e auth na 1.1, mas isso é pior que fazer agora.
      - Escopo mínimo defensável: usuário+senha (ou OIDC) no BFF do curador, `changed_by` vindo do
        token, e a superfície pública continuando aberta **por design**.
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
- **`path` desnormalizado** — `PATH_DIVERGENCE` = 0 hoje, mas a invariante ainda não é verificada
  automaticamente no CI.

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
| `pytest` (unit + integração) | **1.219 passed** |
| `ruff check` / `ruff format --check` | limpos (338 arquivos) |
| `basedpyright` | **0 errors, 0 warnings** |
| `alembic check` | **sem drift** (29 migrações) |
| `alembic downgrade -1` + `upgrade head` | as duas tabelas e o enum voltam, o seed reaplica (38 + 71 linhas) e `check` segue sem drift |
| `tsc` / `eslint` / `vite build` | limpos |
| Contrato OpenAPI | **85 paths / 100 operações / 173 schemas**, sem drift (cliente TS incluído) |
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
3. **Sem autenticação** — bloqueador da 1.0.
4. **O acervo de referência está parcialmente processado** — tipologia e embedding pendentes.
5. **`path` desnormalizado** — `PATH_DIVERGENCE` = 0 hoje, mas sem verificação automática no CI.
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
