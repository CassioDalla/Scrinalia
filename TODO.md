# 🗺️ Roadmap & TO-DO — Scrinalia

Documento central de planejamento: curadoria e enriquecimento de acervo arquivístico
(DDD + micro-workers + Human-in-the-Loop).

> **Como ler.** `✅` = feito **e verificado em execução real** (Postgres + engines reais), não só lido
> no código. `[ ]` = pendente. `[~]` = parcial. O detalhe de cada ciclo vive no histórico do Git e nos
> ADRs: aqui fica **o que falta** e o que **impede alguém de refazer ou desfazer** uma decisão medida.
>
> **Estado do gate (2026-10-08):** **1.395 testes** · `ruff` limpo · `basedpyright` **0 erros** ·
> **32 migrações** sem drift · contrato **95 paths / 112 operações / 182 schemas** sem drift · SPA
> (`tsc`, `eslint`, `vite build`) limpa e servida pelo próprio Litestar · **10 ADRs** · site MkDocs
> builda com `--strict` em inglês e português, com o gate de cobertura da documentação dentro da suíte.

---

## 🎯 O que falta

### 1. Abrir o repositório — o único bloqueador de sequência

Os **Settings do GitHub já estão feitos**: advisory privada, Dependabot (alerts + security updates),
secret scanning com push protection, o ruleset `Main Protect` na `main` (PR obrigatório, sem
force-push, sem deleção e **assinatura obrigatória**) e permissões de Actions em *read*. Duas coisas
que o ruleset **não** exige, e vale saber: os checks do CI (eles rodam em cada PR, mas o merge não
espera por eles) e histórico linear (os três métodos de merge estão liberados). Falta, **nesta
ordem**:

- [x] **Commitar e empurrar o working tree.** Feito: a base de documentação, os cinco consertos de
      código, a revisão do `README.md` e do `AGENTS.md` e o bump da versão — `dev` está em sincronia
      com `origin/dev`.
- [x] **Revisar o `AGENTS.md`.** Não havia caminho absoluto, nome de máquina nem nome de acervo; o
      que saiu foram as **contagens do acervo** (quantas tags, quantos pares, quantas decisões do
      juiz) — os tempos que justificam decisões ficaram.
- [ ] **Mergear o PR `dev` → `main`.** O PR está aberto e o branch **default é o `main`**, que está
      **206 commits atrás**: medido, ele **não tem `LICENSE`** nem `LICENSE-ADDITIONAL-TERMS.md`, e
      também não tem `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, os ADRs, os templates nem
      os workflows do CI. O merge — que a branch protection exige com os checks verdes, e os commits
      já carregam `Signed-off-by`, então o job `dco` passa — põe o `main` em dia e tira o badge de CI
      do "no status".
- [x] **Assinatura obrigatória.** Já está ligada: o ruleset `Main Protect` carrega a regra
      `required_signatures`, e os commits do PR estão assinados (`commit.gpgsign=true`, formato SSH).
      É regra independente do DCO: a assinatura prova **quem criou** o commit, o trailer
      `Signed-off-by` declara o **direito de submetê-lo**, e o job `dco` confere o trailer.
- [ ] **Tornar público.** É o último passo, e a ordem importou: um segredo que entra no histórico de
      um repositório público já vazou. A varredura (`gitleaks`, 232 commits) e a limpeza do acervo já
      passaram; o que falta é o clique.

### 2. Fechar a 1.0 — o que é **operação**, não código

O software está pronto; **o acervo de referência está parcialmente processado**. Medido em
**2026-10-06** — re-meça antes de confiar (o comando está no Handoff):

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

- [ ] **Rodar a IA pendente.** `typology_v2` está em **0** e `embedding_v1` em **41** de 4.844;
      enquanto isso, a busca semântica serve vetores antigos para 3.608 e nenhum para os ~1.218 do
      re-parse. E o bump de `torch`/`sentence-transformers` já invalidou os vetores antigos **em
      silêncio** — o carimbo do worker é o hash do texto, não da versão do modelo, então ele não
      recoloca esses documentos na fila sozinho.
- [ ] **Decidir a ordem:** rodar a IA (tipologia, embedding, quality-validator) **antes ou depois** de
      decidir os 81 rungs. Enquanto não rodar, a UI mostra menos do que o sistema sabe. É decisão de
      produto, não de engenharia.
- [ ] **Cortar o primeiro Release.** A versão já está em **1.0.0** (`pyproject.toml`, `uv.lock`,
      `CITATION.cff`, `CHANGELOG.md`, `apps/curator/package.json` e `README.md`), então falta rodar o
      workflow (`Actions → Release`): com `dry_run: true` ele valida e builda **sem** criar a tag, e
      imprime no resumo o que os Conventional Commits sugerem.

**O que não pode rodar no acervo real sem decisão do dono:**

- `POST /hierarchy/materialisation/apply` — **já rodou uma vez** (4.816 descrições ganharam pai); rodar
  de novo move mais. Tem preview e undo.
- Aprovar rungs e aplicar merges em massa — decisões de conteúdo, não de engenharia.
- `POST /taxonomy/tags/stopwords/purge` — **apaga tags e não tem undo** (o merge tem ledger).
- `DELETE /documents/{id}` — exclusão definitiva (trilha, não lixeira).
- Os workers de IA — **a janela de reprocessamento fecha na primeira ficha aprovada por humano**.

### 3. Fechar a 1.0 — o que é **código**, e é pequeno

- [ ] **Teste de fumaça `e2e`** (marcado `slow`) exercitando um pipeline com engines reais. A suíte usa
      `mock_registry` (correto) e por isso a classe de bug do `suggest-macro` fica invisível.
- [ ] **Publicar o site** e decidir se versiona por release (`mike`). **Não bloqueia a 1.0**: o build
      com `--strict` já é o gate e o site é gerado do repositório; hospedagem é uma decisão separada.
- [ ] **Adotar pandas 3 e SQLAlchemy 2.1 de propósito.** Os dois estão segurados no `pyproject.toml`
      (`pandas<3`, `sqlalchemy<2.1`) porque o Dependabot os trouxe num PR de grupo com 12 outros bumps.
      O SQLAlchemy 2.1 **troca o driver padrão de `postgresql://` de psycopg2 para psycopg (v3)**, e o
      projeto pina `psycopg2`: medido, a suíte dá **748 erros de setup** (`No module named 'psycopg'`)
      com o 2.1.4 e passa com o 2.0.54. A adoção é: tornar o driver explícito
      (`postgresql+psycopg2://`) em `core/config.py`, `testing/conftest.py` e no env do CI, ajustar a
      tipagem de `Row` (6 pontos) e a de pandas (`int(row[...])`, 2 pontos) e re-rodar a suíte. O
      pandas 3 muda a tipagem de `Series.__getitem__` e traz mudanças de comportamento (string dtype,
      copy-on-write) que a suíte atual não exercita.

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
| 4 | UI, BFF e publicação | 🟡 **Curador completo** (24 telas) e **auth entregue (B9.1–B9.3)**; falta o **site público** |
| **5** | **Release 1.0** | 🟡 **Iniciada** — licença (0006), nome (0007), desacoplamento (0008), auth (0009) e **documentação (0010)** fechados; falta **abrir o repositório** e publicar o site |

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
| Acervo parcialmente processado | tipologia e embedding pendentes — seção 2 acima |

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
- `docs/guides/` — os quatro guias (instalação, operação, curadoria, modelo de dados), em inglês e
  português; `docs/log.md` é o ledger de triagem da documentação.
- `docs/adr/` — decisões aceitas: Litestar (0001), layout `src/` (0002), monorepo e stack do curador
  (0003), execução de workers pela API (0004), observabilidade sem serviço externo (0005), licença e
  atribuição (0006), nome (0007), língua × acervo (0008), autenticação e autorização (0009) e
  **documentação com cobertura e frescor (0010)**.
- `.analysis/` — **gitignored**, notas de trabalho deste checkout (planos, sitemap, refino de UI). O que
  precisa sobreviver a um clone está **aqui** e no `AGENTS.md`.
