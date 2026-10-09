# 🗺️ Roadmap & TO-DO — Scrinalia

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não só lido
> no código. `[ ]` = pendente. `[~]` = parcial. O detalhe de cada ciclo vive no histórico do Git e nos
> ADRs: aqui fica **o que falta** e o que **impede alguém de refazer ou desfazer** uma decisão medida.
>
> **Estado do gate (2026-10-09, re-medido neste checkout):** **1.395 testes** em **16,9 s** ·
> `ruff check`/`format --check` limpos · `basedpyright` **0 erros** · **32 migrações** e
> `alembic check` sem drift · contrato **95 paths / 112 operações / 182 schemas** regenerado sem
> drift · SPA (`tsc`, `eslint`, `vite build`) limpa e servida pelo próprio Litestar · **10 ADRs** ·
> site MkDocs `--strict` em inglês e português, com o relatório de frescor dizendo *every page is
> fresh*.
>
> **O repositório é público e a `v1.0.0` está publicada** (2026-10-09); o site responde em
> <https://cassiodalla.github.io/Scrinalia/> e em `/pt/`. O que falta agora é **acervo, decisão de
> produto e três itens pequenos de código** — seções 2 e 3.

---

## 🎯 O que falta

### 1. Abrir o repositório — ✅ **fechado em 2026-10-09**

Era o único bloqueador de sequência, e a ordem importou: a varredura de segredos (`gitleaks`, 232
commits) e a limpeza do acervo passaram **antes** do clique. Verificado na API do GitHub neste
checkout, não de memória:

- [x] **Repositório público.** `visibility: public`, `default_branch: main`, `homepage` apontando para
      o site, advisory privada e *push protection* ligadas, secret scanning e atualizações de
      segurança do Dependabot habilitados.
- [x] **PR `dev` → `main` mergeado.** `main` está em `6fa6f6f` e carrega o que faltava (a licença e o
      termo do §7(b), `SECURITY.md`, `CONTRIBUTING.md`, o COC, os ADRs, os templates e os workflows).
      `dev` está **2 commits à frente** (`#20`, o CodeQL dos workflows): é o fluxo normal, e o próximo
      release os leva. O badge de CI deixou de ser "no status".
- [x] **`v1.0.0` publicada.** Tag `v1.0.0` em `6fa6f6f`, release de 2026-10-09T00:23Z, com SBOM e
      proveniência do workflow `Release`.
- [x] **Site publicado** em <https://cassiodalla.github.io/Scrinalia/> — a raiz (inglês) responde
      **200** e o `/pt/` também. **O deploy foi manual** (`mkdocs gh-deploy`; o commit do `gh-pages` é
      *"Deployed e96473f with MkDocs version: 1.6.1"*, do dono): o que falta é o job de CI no item 3.
- [x] **Assinatura obrigatória** nos dois rulesets. É regra independente do DCO: a assinatura prova
      **quem criou** o commit, o trailer `Signed-off-by` declara o **direito de submetê-lo**, e o job
      `dco` confere o trailer.

O que sobrou, e é pequeno:

- [~] **`dev protect` pela metade.** O ruleset tem `deletion`, `non_fast_forward`,
      `required_signatures` e agora também `required_status_checks` — verificado na API: **três
      contextos** (`Lint & format`, `Migrations & tests`, `Curator UI (types, lint, build)`), todos
      batendo com o `name:` dos jobs do `ci.yml`. **Falta a regra de `pull_request`**, que é a que
      sustenta o `dev` como branch de integração; sem ela, o que impede um push direto é só a regra de
      checks. Ao acrescentá-la, dois detalhes do `ci.yml` continuam mandando: `Signed-off-by (DCO)` só
      roda em PR (`if: github.event_name == 'pull_request'`), então exigi-lo só faz sentido junto com a
      regra; e `Dependency advisories` tem `continue-on-error: true`, ou seja, é sempre verde e não
      serve de gate. Vale revisitar também a assinatura obrigatória no `dev`: é coerente com a `main`,
      mas um contribuidor externo sem chave não pousa nada no `dev` — e, sem ela no `dev`, a `main`
      recusaria o merge depois.
- [ ] **Higiene do repositório público** (medido agora): `description` está **nula** e `topics`
      **vazio** — é o que aparece na busca do GitHub e no cartão do repositório.
      `delete_branch_on_merge` é `false` e há **5 branches remotas já mergeadas**
      (`adopt-deps-pr5`, `ci-codeql-advanced-setup`, `perf-tests-argon2` e duas do Dependabot).
      `Main Protect` continua **sem** `required_status_checks` e **sem** histórico linear (os três
      métodos de merge liberados): é escolha, não esquecimento — mas é a assimetria entre os dois
      rulesets que confunde quem chega.

### 2. O acervo de referência — **operação, não código**

O software saiu na **1.0.0**; **o acervo continua parcialmente processado**. Re-medido no banco de
desenvolvimento em **2026-10-09** (`DB_NAME=memoriacuritibana`; o comando está no Handoff) — não
confie em número congelado:

| # | Medida | 2026-10-06 | **2026-10-09** |
| --- | --- | ---: | ---: |
| 1 | Descrições | 4.844 | **4.844** |
| 2 | Com pai (árvore materializada) | 4.826 | **4.826** |
| 3 | Tags / sem gaveta de assunto | 8.155 / 7.461 | **8.154 / 7.460** |
| 4 | Propostas de merge: sugeridas / aplicadas | 748 / 127 | **747 / 127** |
| 5 | Rungs decididos / total | 24 / 81 | **24 / 81** |
| 6 | Carimbos `ner_v2` / `typology_v2` | 4.826 / 0 | **4.826 / 0** |
| 7 | Carimbos `macro_category_v1` (tags) | 957 | **957** |
| 8 | Carimbos `embedding_v1` | 41 | **4.844** (vetor não nulo em todos) |
| 9 | Carimbos `quality_validator_v1` | — | **4.826** (4.596 com `anomaly_reasons`) |
| 10 | Publicados / revisões humanas | 0 / 0 | **0 / 0** |

- [ ] **Rodar a tipologia — é a única IA que falta.** `typology_v2` está em **0**, e o ledger explica:
      a execução de `typology` está **INTERRUPTED** desde 2026-10-06 ("O processo anterior terminou
      antes do fim desta execução" — o `lifespan.py` marcando o órfão). `embedding` (4.844/4.844, 76 s,
      2026-10-08) e `quality-validator` (4.826, 4.596 com anomalia) já rodaram inteiros.
- [ ] **O carimbo do `embedding` não guarda a identidade do modelo.** O bump de
      `torch`/`sentence-transformers` invalidou os vetores antigos **em silêncio**: o carimbo é o MD5
      do texto, não a versão do modelo, então o worker não recoloca ninguém na fila sozinho. Re-rodar
      resolveu desta vez (item 8), mas o próximo bump repete o problema — **incluir a identidade do
      modelo no carimbo é item de código**, não de operação.
- [ ] **Decidir a ordem:** rodar a tipologia **antes ou depois** de decidir os 81 rungs. Enquanto não
      roda, a UI mostra menos do que o sistema sabe. É decisão de produto, não de engenharia.
- [ ] **Higiene de catálogo que a medição deixou visível:** há **1 regra de limpeza, e ela está
      inativa** (`REWRITE`) — o `cleaning` não tem o que fazer, e as 41 descrições que carregam carimbo
      de limpeza vieram de quando ela estava ativa. Como não há `LLM_CHECK` ativa, o
      `quality-validator` rodou **sem etapa de LLM**. E `thumbnail` está em **0**: nenhuma descrição
      tem `storage_thumbnail_uri` (falta o endpoint S3 do operador).
- [ ] **As 18 fichas `HUMAN_APPROVED`** são os nós de arranjo (níveis 1–4, criados em 2026-10-06):
      **são exatamente as 18 sem carimbo `ner_v2`** (medido: nenhuma descrição não aprovada está sem o
      carimbo) — a janela de reprocessamento **já fechou** para elas. E **nenhuma tem linha em
      `archive_document_revisions`**, porque não passaram pelo `PATCH /documents/{id}`. Vale saber
      antes de rodar IA em lote.

**O que não pode rodar no acervo real sem decisão do dono:**

- `POST /hierarchy/materialisation/apply` — **já rodou uma vez** (4.816 descrições ganharam pai); rodar
  de novo move mais. Tem preview e undo.
- Aprovar rungs e aplicar merges em massa — decisões de conteúdo, não de engenharia.
- `POST /taxonomy/tags/stopwords/purge` — **apaga tags e não tem undo** (o merge tem ledger).
- `DELETE /documents/{id}` — exclusão definitiva (trilha, não lixeira).
- Os workers de IA — **a janela de reprocessamento fecha na primeira ficha aprovada por humano**.

### 3. Pós-1.0 — o que é **código**, e é pequeno

- [ ] **Teste de fumaça `e2e`** (marcado `slow`) exercitando um pipeline com engines reais. A suíte usa
      `mock_registry` (correto) e por isso a classe de bug do `suggest-macro` fica invisível.
- [~] **Publicar o site pela CI** — o site **já está no ar** (<https://cassiodalla.github.io/Scrinalia/>),
      mas por `mkdocs gh-deploy` manual, com `build_type: legacy` sobre o branch `gh-pages`. Falta o job
      que publica a cada merge (o `docs` do CI hoje só builda com `--strict`) e a decisão de versionar
      por release (`mike`). **Não bloqueou a 1.0**: o build com `--strict` é o gate, e o site é gerado
      do repositório.
- [ ] **Adotar pandas 3 e SQLAlchemy 2.1 de propósito.** Os dois estão segurados no `pyproject.toml`
      (`pandas<3`, `sqlalchemy<2.1`) porque o Dependabot os trouxe num PR de grupo com 12 outros bumps.
      O SQLAlchemy 2.1 **troca o driver padrão de `postgresql://` de psycopg2 para psycopg (v3)**, e o
      projeto pina `psycopg2`: medido, a suíte dá **748 erros de setup** (`No module named 'psycopg'`)
      com o 2.1.4 e passa com o 2.0.54. A adoção é: tornar o driver explícito
      (`postgresql+psycopg2://`) em `core/config.py`, `testing/conftest.py` e no env do CI, ajustar a
      tipagem de `Row` (6 pontos) e a de pandas (`int(row[...])`, 2 pontos) e re-rodar a suíte. O
      pandas 3 muda a tipagem de `Series.__getitem__` e traz mudanças de comportamento (string dtype,
      copy-on-write) que a suíte atual não exercita.
- [ ] **A identidade do modelo dentro do carimbo do `embedding`** — é o item de código escondido na
      seção 2: hoje o carimbo é só o MD5 do texto, então uma troca de modelo não invalida vetor nenhum.

---

## 📊 Panorama das fases

| Fase | Escopo | Estado |
| --- | --- | --- |
| 1 | Fundação, pipeline de IA e governança | ✅ **Fechada** |
| 1.5 | Macro Categorias (eixo de Assuntos) | ✅ **Fechada** |
| 2 | API + Curadoria humana (HITL) | ✅ **Fechada** |
| 2.5 | Hierarquia das descrições | ✅ **Fechada** (H1–H8, com tela) |
| 3 | Descoberta, performance e observabilidade | 🟡 **Quase** — `/health` e o rastreamento de erros fechados; o agendador é pós-1.0 |
| 3.5 | Qualidade do dado de entrada | ✅ **Fechada** |
| 4 | UI, BFF e publicação | 🟡 **Curador completo** (24 telas) e **auth entregue (B9.1–B9.3)**; falta o **site público** (o `/api/v1/public/*` já existe; **0 de 4.844** publicados) |
| **5** | **Release 1.0** | ✅ **Fechada em 2026-10-09** — licença (0006), nome (0007), desacoplamento (0008), auth (0009), documentação (0010), repositório público e **`v1.0.0` publicada**. Sobra `dev protect` (regra de PR), higiene do repositório e o deploy do site pela CI |

---

## ✅ O que já está pronto

> Uma linha por área, com o ADR que guarda o porquê e as alternativas descartadas. O detalhe de
> implementação vive no histórico do Git — não se refaz o que já foi medido.

| Área | Entrega | Decisão |
| --- | --- | --- |
| Pipeline (Fase 1) | Ingestão → staging → archive com CDC por hash do **registro parseado**; 9 workers com idempotência por `execution_log` (JSONB + GIN) e carimbo versionado; `HUMAN_APPROVED` bloqueia a IA (exceção documentada: `worker_embedding`). | ADR 0002, 0004 |
| Macro categorias (1.5) | 8 gavetas derivadas das tags reais; guarda determinística recusa **1.489 de 8.155** tags como "não é assunto"; limiar 0.55 com fila; carimbo = hash do conjunto de rótulos. A frase NLI **é o colapso**, não a cura (medido). | `AGENTS.md` |
| API e curadoria (2) | Litestar + DDD por domínio; `PATCH /documents/{id}` edita ISAD(G) e grava revisão; exclusão definitiva com retrato ISAD(G) (trilha, não lixeira); autoria vinda da sessão, em duas colunas. | ADR 0001 |
| Hierarquia (2.5) | `path` materializado, catálogo de níveis, plano de arranjo com a decisão separada da execução, materialização com ledger e undo; **invariante verificada no CI pelo próprio diagnóstico**, com a linha corrompida de propósito como contraprova. | — |
| Busca e observabilidade (3) | Lexical (coluna gerada + GIN, sem acento) e semântica (pgvector, HNSW cosseno); facetas com semântica própria; `/health/live` + `/health/ready`; falhas agrupadas por causa raiz em coluna gerada. | ADR 0005 |
| Qualidade do dado (3.5) | Composição do texto da IA **em SQL** (uma expressão alimenta embedding, carimbo MD5, NER e tipologia); trechos com escopo `EMBEDDING`/`NER`/`TITLE`; merges de tags com ledger e undo exato. | — |
| Contrato e determinismo | OpenAPI gerado e commitado, cliente TS gerado dele; **`Field(description=...)` em enum compartilhado reescreve o componente** e dependia do `PYTHONHASHSEED` — por isso se documenta o **tipo**, nunca o campo. | ADR 0003 |
| Desacoplamento | A **língua** é código (`core/language`); o **acervo** é dado (`archive_arrangement_vocabulary`, `archive_collection_terms`, com tela); a origem é parâmetro (`SourceSchema`), **sem default**. | ADR 0008 |
| Licença e nome | `AGPL-3.0-only` + termo de atribuição do §7(b); nome **Scrinalia**, livre em registries e domínios. | ADR 0006, 0007 |
| Autenticação | Sessão por cookie no banco (só o sha256 do token), argon2id com hash-isca, três papéis, **cada operação declara a sua permissão** (teste de partição); `/api/v1/users` com tela; bloqueio com backoff gravado **fora** da transação do request, rate-limit por endereço e `origin_guard` nas mutações. | ADR 0009 |
| Documentação | Quatro guias em inglês e português, índice, ADRs, **cobertura como gate** (worker/setting/tela/tabela/ADR) e **frescor como relatório** com ledger de triagem; job `docs` no CI com `--strict`. | ADR 0010 |
| Endurecimento do repositório | CI com lint, testes, front, docs, segredos, auditoria, `zizmor` e DCO; Actions pinadas por SHA e imagens por digest; CodeQL; Dependabot; SBOM e proveniência no release; comunidade completa (`CONTRIBUTING`, COC, templates, `CHANGELOG`, `CITATION`). | — |
| **Repositório público e `v1.0.0`** | **Aberto em 2026-10-09**: `main` recebeu o `dev` (eram **206 commits** de distância, medidos antes do merge), a tag `v1.0.0` saiu pelo workflow `Release` com SBOM e proveniência, o site está no ar em <https://cassiodalla.github.io/Scrinalia/> (com `/pt/`), e os dois rulesets exigem assinatura — o `dev` também exige os três checks do CI. | ADR 0006, 0007 |
| Curadoria de código | Os quatro itens que a escrita da documentação abriu, mais o `thumbnail`: reativação da regra de limpeza, `suggest-macro` como leitura, caixa de entrada abrindo as telas que existem, e `validate_engine_choice` valendo também no CLI. | ADR 0010 |

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
- **Uma recusa que só o painel faz não é garantia** (`--engine` passava pelo CLI e vencia a regra
  `LLM_CHECK` em silêncio); a validação tem de morar onde a configuração é resolvida.
- **Uma ação reversível que a tela não alcança não é reversível** (desativar a regra de limpeza não
  tinha volta *nem forma de ver a regra desativada*).
- **Um teste que prende a assinatura antiga falha quando o contrato melhora** — foi o caso do
  `thumbnail` recusando `force`; atualizar o teste é parte da correção.
- **Um bump de major pode trocar o driver padrão, não só a tipagem.** O SQLAlchemy 2.1 manda
  `postgresql://` para o psycopg **v3**; com `psycopg2` pinado, toda conexão falha. O `basedpyright`
  pegou 13 diagnósticos e **não** pegou isso — verde no type check não é sinal de runtime, e o passo
  `Run tests` do CI só roda depois dele.
- **Um grupo do Dependabot com `patterns: ["*"]` transforma três decisões de major num `chore(deps)`**
  (pandas 3, SQLAlchemy 2.1 e transformers 5.18 no mesmo PR). Major se adota de propósito, com o
  lock rebaseado e a suíte rodada — o lock que o Dependabot testou não é o que o rebase produz
  (o PR trazia SQLAlchemy 2.1.3; o rebase resolveu 2.1.4).
- **Um carimbo que não identifica o produtor não invalida nada.** O `worker_embedding` grava o **MD5 do
  texto**, então trocar `torch`/`sentence-transformers` deixa 4.844 vetores velhos com o carimbo em
  dia: a fila fica vazia e a busca semântica serve um vetor que nenhum modelo atual geraria. Um carimbo
  de worker tem de nomear **o que o produziu** (versão do modelo/preset), não só a entrada.

---

## 📈 Medições que mudaram decisões (preservadas)

| Verificação | Resultado |
| --- | --- |
| Trigrama com e sem o `OR lower()` | **52,9 s → 1,42 s**, resultado idêntico |
| Prefilter de comprimento | descartava **52–65%** dos pares reais; removido |
| Qualidade do texto de entrada | separação 0.769 → 0.504; Hit@10 0.562 → **0.625**; aprovar tudo piora (0.500) |
| Hierarquia em escala | `apply` 1,7 s; 1 raiz; profundidade 5; `undo` com 3.619 linhas restauradas |
| Undo de merge ao vivo | `vendas ← venda` desfeito e reaplicado: tag, id e vínculo restaurados exatamente |
| Worker `embedding` | 3.608/3.608 em ~1 min; `cos(guardado, recalculado) = 1.0` |
| `embedding` sobre o acervo inteiro | **4.844/4.844 em 76,5 s** (2026-10-08, pelo ledger; vetor não nulo em todos) |
| `quality-validator` sobre o acervo | **4.826 em 6,3 s**, 4.596 com `anomaly_reasons` (2026-10-08) |
| Tipologia interrompida | a única IA em falta: `typology_v2 = 0` e a execução **INTERRUPTED** desde 2026-10-06 |
| Banco reconstruído | 15 tabelas copiadas; `alembic check` sem drift |
| Execução real da auth | sessão de outra conta responde 404; 3 falhas de senha → a senha **correta** responde **423**; rate-limit 429; mutação de origem estranha **403** e leitura **200** |
| `/health/live` e `/health/ready` | 200 com o banco de pé, **503** com o banco parado |

---

## 🧭 Backlog pós-1.0

### Limites conhecidos e aceitos

| Limite | O que custa |
| --- | --- |
| Acurácia de assunto em **0.500/0.575** | limite do zero-shot NLI com sintagma nominal; a decisão foi aceitar e resolver por curadoria |
| Busca semântica fraca (MRR **−0.019**) | o ranking híbrido (RRF) é o próximo passo — item 5 |
| `path` desnormalizado | o banco **não** garante a invariante: um `UPDATE` manual fora do serviço diverge, e é o `PATH_DIVERGENCE` que encontra |
| Observabilidade **sem alerta** | ninguém é avisado de uma causa nova; alguém precisa abrir a tela (custo aceito no ADR 0005) |
| Auth com limites conscientes | rate-limit **por processo**, sessão revogada não registra **quem** revogou, e 2FA/SSO/recuperação por e-mail estão fora de propósito (ADR 0009) |
| **7 nós** com `LEVEL_NOT_ALLOWED_AS_CHILD` | a família SMU não cabe na escada de 6 níveis sem repetir ordinal |
| Premissa de **processo único** | o executor na API e a recuperação de órfãos assumem `uvicorn --workers 1` (ADR 0004); `--workers > 1` corrompe o estado das execuções |
| Acervo parcialmente processado | **a tipologia** é a IA que falta (`typology_v2 = 0`), e **0 de 4.844** publicados — seção 2 acima |

### 1. Processamento fora da API, agendador e IA em outra máquina

Tirar os workers do processo da API, criar agendador (cron/retry) e permitir rodar a IA numa máquina
com GPU que devolve os dados para a API numa VPS.

- **O que fazer primeiro:** definir o **protocolo runner↔API** num ADR próprio. A semântica de
  `POST /system/workers/{name}/runs` muda de "executa agora, neste processo" para "enfileira para um
  runner" — o schema não muda se a resposta continuar sendo `WorkerRun`; o que muda é o *tempo* e a
  *garantia*.
- **Interage com versionamento?** Não quebra o contrato, muda a semântica.

### 2. Site público (`apps/public/`)

- **O que já está pronto:** a superfície `/api/v1/public/*` com projeção por allowlist
  (`NOT_PUBLIC_FIELDS` + `NOT_PUBLIC_FACETS`, partição exata com teste), `published_only` no servidor e
  o 404-que-esconde.
- **O que falta:** o app em si (segundo processo, mesmo contrato) e a decisão de qual framework serve
  o site.
- **Bloqueio real, e é de produto:** o predicado é `is_published` e **0 de 4.844** estão publicados. O
  site nasce vazio; o trabalho é de curadoria, não de código.
- **Interage com versionamento?** Não — aditivo por construção.

### 3. Internacionalização (i18n)

- **No servidor já é aditivo:** todo desfecho responde `code` (estável, em inglês) + `message`
  (português), e o front lê tudo por `routeMessage()` (`lib/messages.ts`). Encher o mapa de traduções é
  o que torna a interface multilíngue, sem tocar em tela.
- **Na SPA:** ~334 strings PT hardcoded nas rotas + os `lib/` (`format.ts` formata data/número em
  pt-BR). Não há infra de i18n hoje (`i18n`/`useTranslation`/`intl`: zero).
- **O que NÃO se traduz:** prompts de LLM (raciocinam sobre português) e os **rótulos de campo da
  origem** (são chaves do payload; traduzir esvazia a coluna) — eles moram no `SourceSchema`.

### 4. Dívidas de curadoria já registradas

- **Entidades sem catálogo de propostas** — os defeitos de merge foram corrigidos (upsert de sinônimos
  + `repoint_synonyms` antes de deletar), mas não há proposta, ledger nem undo como nas tags. A tela
  **avisa** que unificar não tem desfazer.
- **Colisão tag × entidade em lote** — os ~5.050 nomes idênticos são uma decisão *por categoria*
  ("logradouro é entidade"), e a tela ainda pede uma por par. `pair_kind` já separa as duas populações.
- **Purga de stopwords é a única escrita destrutiva sem undo** — tem preview; torná-la reversível
  (ledger, como o merge) é decisão em aberto.
- **Lematização de tags** ficou como **sugestão**, não reescrita.

### 5. Busca híbrida (RRF)

A semântica funciona (pgvector, `vector(384)`, HNSW cosseno) mas o ranking é fraco: o **MRR caiu
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

---

## ▶️ Handoff — como rodar

### O sistema

```bash
bun run dev            # docker compose up -d + API :8000 + SPA :5173 (proxy /api -> :8000)
# peças soltas: bun run db:up | bun run api:dev | bun run curator:dev
```

Um **502 em `/api`** quer dizer que a API não está no ar — a SPA responde 200 e o sintoma parece bug
de front.

### Os gates (o que rodar antes de commitar)

```bash
# banco de teste deste checkout está na porta 5434
TEST_DATABASE_URL=postgresql://test_user:test_password@localhost:5434/test_db .venv/bin/pytest -q
.venv/bin/basedpyright && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/alembic check
bun run --cwd apps/curator typecheck && bun run --cwd apps/curator lint && bun run --cwd apps/curator build
uv run mkdocs build --strict
```

### Construir e servir a documentação

```bash
uv sync --group docs                     # grupo opcional: mkdocs-material + mkdocs-static-i18n
uv run mkdocs serve -a 127.0.0.1:8080    # preview com reload — a 8000 é da API
uv run mkdocs build --strict             # gera site/ (gitignored); --strict falha em link quebrado
uv run python -m http.server -d site 8080   # servir o build estático
```

- O site em **inglês** sai na raiz e o **português** em `site/pt/`; o `serve` publica os dois.
- O build imprime o **relatório de frescor** (o hook do ADR 0010). Para só o relatório:
  `uv run python docs/_hooks/freshness.py` — e `--all` ignora o piso do ledger de triagem.
- Sem instalar o projeto, que é o que o CI faz:
  `uvx --from mkdocs==1.6.1 --with mkdocs-material==9.7.7 --with mkdocs-static-i18n==1.3.1 mkdocs build --strict`.

> **Neste sandbox** o `~/.cache` é somente-leitura: exporte os caches para o workspace antes de
> commitar, e use o `mkdocs` do venv (o grupo `docs` já está instalado aqui).
>
> ```bash
> export PRE_COMMIT_HOME=.cache-pre-commit UV_CACHE_DIR=.cache-uv
> .venv/bin/mkdocs serve -a 127.0.0.1:8080
> ```
>
> **E o cache somente-leitura já custou um arquivo:** `bun run contract` redireciona com `>` para
> `packages/api-contract/openapi.json`, então o redirect **trunca o arquivo antes de o `uv` falhar** —
> o `openapi.json` fica com **0 byte** e o `git status` mostra `M`, como se fosse uma mudança de
> conteúdo. O `git checkout --` restaura (426 KB); com `UV_CACHE_DIR` exportado, não acontece.

**Nunca** rode `alembic upgrade head` no banco de **teste**: o `create_all` do conftest pula o que já
existe e a suíte passa a rodar contra o schema migrado (53 falhas + 42 erros que parecem regressão).

### Medir o acervo (não confie em número congelado)

O banco de desenvolvimento deste checkout é o `memoriacuritibana` (é o nome que está no `.env`;
`scrinalia` **não existe** mais — a versão antiga vive em `memoriacuritibana_legacy`).

```bash
docker exec scrinalia_db psql -U admin -d memoriacuritibana -t -A -F' | ' -c "
SELECT 'descrições', count(*)::text FROM archive_documents
UNION ALL SELECT 'com pai', count(*)::text FROM archive_documents WHERE parent_id IS NOT NULL
UNION ALL SELECT 'sem nível', count(*)::text FROM archive_documents WHERE level_id IS NULL
UNION ALL SELECT 'tags', count(*)::text FROM archive_tags
UNION ALL SELECT 'tags sem gaveta', count(*)::text FROM archive_tags WHERE macro_category_id IS NULL
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
UNION ALL SELECT 'revisões humanas', count(*)::text FROM archive_document_revisions
UNION ALL SELECT 'HUMAN_APPROVED', count(*)::text FROM archive_documents WHERE review_status='HUMAN_APPROVED';"
```

Os carimbos dizem **o que rodou**, mas não com que modelo: `embedding_v1` é o MD5 do texto. Para saber
o que executou e quando, o ledger é a fonte (`archive_worker_runs`, com `status`, `engine_name`,
`preset`, `duration_ms` e `error`) — é lá que está o `typology` **INTERRUPTED** que explica o
`typology_v2 = 0`.

---

## 📚 Referências

- `AGENTS.md` — convenções e as regras arquiteturais fáceis de errar (**leia antes de mexer**).
- `README.md` — porta de entrada (o que é, como rodar).
- `docs/guides/` — os quatro guias (instalação, operação, curadoria, modelo de dados), em inglês e
  português; `docs/log.md` é o ledger de triagem da documentação.
- `docs/adr/` — decisões aceitas: Litestar (0001), layout `src/` (0002), monorepo e stack do curador
  (0003), execução de workers pela API (0004), observabilidade sem serviço externo (0005), licença e
  atribuição (0006), nome (0007), língua × acervo (0008), autenticação e autorização (0009) e
  **documentação com cobertura e frescor (0010)**.
- `.analysis/` — **gitignored**, notas de trabalho deste checkout (planos, sitemap, refino de UI). O que
  precisa sobreviver a um clone está **aqui** e no `AGENTS.md`.
