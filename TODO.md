# 🗺️ Roadmap & TO-DO: Motor de Enriquecimento de Arquivos (AI-Driven)

Este documento centraliza o planeamento arquitetural e as próximas etapas de desenvolvimento do sistema de curadoria e enriquecimento de dados arquivísticos, baseado em arquitetura orientada a domínio (DDD) e micro-workers.

## 🟢 Fase 1: Fundação e Core Pipeline de IA (Em Fechamento)
O objetivo desta fase é estabelecer a fundação de dados robusta e a esteira de Inteligência Híbrida (Humano + IA) descentralizada.

- [x] **Camadas Ingestion & Staging (Antigas Bronze/Silver):** Extração, limpeza e controle de linhagem (Hash CDC) do acervo base.
- [x] **Camada Archive (Antiga Gold):** Modelagem dimensional, schemas Pydantic estritos, trava de idempotência e índices GIN para alta performance.
- [x] **Infraestrutura de Testes:** Suíte completa no Pytest (Mocks, Savepoints no BD, isolamento de transações).
- [x] **Worker de Transferência (`worker_archive_transfer.py`):** Carga inicial isolada, limpeza de taxonomia via `TagService` e inicialização do `execution_log`.
- [x] **Worker NER (`worker_ner.py`):** Extração de entidades (LOC, PER, ORG) via `spaCy` com filtros de Data Quality e EntityRuler dinâmico.
- [x] **Worker Thumbnail (`worker_thumbnail.py`):** Download resiliente e upload para Object Storage (S3/MinIO) com fallback de erros.
- [x] **Worker Typology (`worker_typology.py`):** Classifica os documentos com base nas Tipologias cadastradas no Banco
  - [x] Engine mdeberta aplicando *Zero-Shot Classification* 
- [ ] **Worker Categorizador/Taxonomia (`worker_mdeberta.py`):**
  - [ ] Consumir textos pendentes e aplicar *Zero-Shot Classification* para descobrir Macro-Categorias.
  - [ ] Integrar com `TagService` para ignorar documentos que já foram classificados por heurística.
- [ ] **Worker Validador LLM (`worker_ollama.py` ou Granite):**
  - [ ] Implementar parser defensivo (Pydantic/Instructor) e *retries* para lidar com LLMs locais.
  - [ ] Avaliar coerência textual, atributos dos dados e sinalizar anomalias textuais (`is_anomaly`).
  - [ ] Configurar prompt de classificação estrita (JSON Output) focado apenas em similaridade semântica: avaliar pares de entidades e sugerir fusões (merges).
  - [ ] Criar tabela transacional no banco: `entity_merge_suggestions` para armazenar as ideias da IA.

## 🟡 Fase 2: APIs e Governança (Human-in-the-Loop)
Dar utilidade aos dados isolando o banco de dados do *Front-end* e permitindo a atuação dos arquivistas sobre as decisões da IA.

- [ ] **Camada de API (FastAPI):**
  - [ ] Desenvolver roteamento RESTful seguindo o padrão DDD (`domains/archive/routers.py`).
  - [ ] Criar *endpoints* de leitura (Paginação do Acervo) e escrita (Aprovação humana).
- [X] **Serviço de Entidades (`EntityService`):**
  - [X] Espelhar a lógica do `TagService`: criar funções para fundir (`merge`) Entidades duplicadas e popular a tabela `domain_synonyms`.
- [ ] **Painel de Curadoria (Front-end HITL):**
  - [x] Dashboard inicial em Streamlit/Gradio para visualização de metadados.
  - [X] **Ação Global:** Tela dedicada à resolução de entidades/tags. O utilizador aprova fusões (ex: "Prefeitura" -> "PMC") que alimentam os sinônimos automaticamente.
  - [ ] **Ação Local:** Botão de edição no documento individual. Ao salvar, altera o status para `HUMAN_APPROVED`, blindando o documento contra re-processamento da IA.

## 🟠 Fase 3: Descoberta e Performance (Escala)
Tornar o acervo pesquisável e otimizar a infraestrutura para lidar com grandes volumes de dados de forma rápida.

- [ ] **Motor de Busca Híbrida (Hybrid Search):**
  - [ ] *Full-Text Search:* Implementar busca léxica nativa no PostgreSQL usando o campo `semantic_search_vector` (lematizado sem stopwords).
  - [ ] *Semantic Search:* Gerar embeddings do texto e usar a extensão `pgvector` para buscas por similaridade de conceito ("procurar por desastres naturais" encontrar "enchentes").
- [ ] **Observabilidade e CI/CD:**
  - [ ] Configurar GitHub Actions para rodar a suíte do `pytest` automaticamente a cada *commit*.
  - [ ] Adicionar rastreamento de erros nos *workers* (ex: Sentry) para monitorizar falhas de IA silenciosas em produção.

## 🔴 Fase 4: Agentes Ativos e Interoperabilidade (v2.0) - IDÉIAS
Transformar o repositório numa ferramenta open-source inteligente e capaz de dialogar com sistemas externos.

- [ ] **Sistema de Adapters (Plugins Ingestion):**
  - [ ] Criar uma interface padrão (Abstract Base Class) para que qualquer instituição possa plugar os seus próprios *scrapers* sem alterar o *Core Engine*.
- [ ] **Worker de Visão Computacional (OCR / VLM):**
  - [ ] Extrair texto bruto diretamente de URLs de imagens históricas armazenadas no MinIO e injetar na tabela fato.
- [ ] **Chatbot Arquivista (RAG - Retrieval-Augmented Generation):**
  - [ ] Permitir que o utilizador converse com o acervo ("Quais foram as obras públicas mencionadas em Curitiba na década de 50?"), cruzando dados da tabela de Entidades com o LLM.
- [ ] **Exportação para Preservação (OAIS):**
  - [ ] Criar rotinas de empacotamento de dados estruturados (DIPs) para envio a sistemas de guarda permanente (ex: Archivematica).






  --



  📝 TODO: Pipeline de Macro Categorias e Classificação de Tags
1. Banco de Dados (Modelagem e Migrações)

    [x] Criar a Model ArchiveMacroCategory:
        Definir colunas: category_id, name (unique), description, is_active, created_at.
        Definir relationship tags apontando para ArchiveTag.
    [x] Atualizar a Model ArchiveTag:
        Adicionar a Foreign Key macro_category_id (com ondelete="SET NULL").
        Manter/Adicionar a coluna ai_confidence_score (pois a classificação da IA ocorre na Tag, não no documento).
        Definir relationship macro_category apontando para a model correspondente.


2. Helper Exploratório (Descoberta de "Gavetas" com BERTopic)
    [x] Criar a Lógica do BERTopic:
        Desenvolver o helper que busca as infinitas tags "soltas" do acervo.
        Processar os embeddings das tags e clusterizá-las semanticamente.
    [ ] Criar o Controller / Endpoint:
        Criar a rota no API para acionar o helper manualmente quando necessário.
    [ ] Ação Humana:
        Analisar os clusters gerados pelo BERTopic e cadastrar oficialmente as Macro Categorias (Assuntos) na tabela archive_macro_categories (ex: Urbanismo, Legislação, Administração).

3. Worker de Classificação (Bibliotecário de Tags com mDeBERTa)

    [ ] Criar worker_macro_category.py (ou worker_tag_classifier.py):
        Implementar o padrão de loop que criamos no NER (while True, paginação com limit, etc).
        A Query: Buscar na tabela ArchiveTag apenas as tags órfãs (WHERE macro_category_id IS NULL).

    [ ] Integração com a IA Genérica:
        Instanciar o motor: engine = get_engine("deberta_typology", preset="gpu_local").
        Enviar o nome da Tag para a IA classificar de acordo com a lista de Macro Categorias cadastradas.

    [ ] Persistência Segura:
        Atualizar a Tag com o macro_category_id escolhido e o ai_confidence_score.
        Usar blocos try/except com db.rollback() e limpeza de memória (db.expunge_all()) para evitar vazamentos e locks.
        Gravar logs de execução para evitar reprocessamento de tags com erro.

4. Backend (API Payload)

    [ ] Ajustar as Queries de Leitura de Documentos:
        Ao carregar um documento, fazer o JOIN das suas Tags com as suas respectivas Macro Categorias.
    [ ] Lógica de "Voto Majoritário" no Backend:
        Agrupar as Macro Categorias encontradas no documento.
        Contar o número de tags que pertencem a cada uma.
    [ ] Modelar o Schema Pydantic:
        Devolver o payload enriquecido com a lista ordenada (quem tem mais tags primeiro):
        JSON
        "macro_categories": [
          {"id": 1, "name": "Urbanismo", "tag_count": 3},
          {"id": 2, "name": "Legislação", "tag_count": 1}
        ]

5. Frontend (Regras de UI/UX para Badges)
    [ ] Regra de Renderização Padrão (Sem Filtros):
        Quando o usuário está apenas explorando o acervo, o site lê a posição [0] do array (vencedor por votos) e exibe: [ 🏙️ Urbanismo ] [+1].
    [ ] Regra de Relevância Contextual (Com Filtro Ativo):
        Se o usuário aplicar um filtro por "Legislação", o frontend varre o array de macro_categories do documento.
        Se "Legislação" existir no array, o frontend ignora o ganhador da votação e exibe: [ ⚖️ Legislação ] no topo para gerar confiança no resultado da busca.

6. Testes (TDD/Integração)

    [ ] Testar o Repositório/DB: Garantir que atualizar uma Tag reflete em todos os documentos atrelados a ela sem precisar tocar na tabela de documentos.
    [ ] Testar o Worker: Usar o padrão de Fixture Factory parametrizada (mock_registry) para garantir que o worker lida com o batch size e salva os IDs corretos.




    Esse é um dos problemas mais complexos (e fascinantes) de se resolver quando cruzamos a Ciência da Computação com a Arquivologia. Você acabou de esbarrar no clássico conflito entre **Vocabulário Controlado (Assuntos)** e **Ontologia (Entidades)**.

A sua intuição está certíssima em ter receio de deixar a IA apagar dados baseada em suposições (como o caso de "parques").

Vamos desatar esse nó respondendo às suas duas perguntas centrais e, em seguida, montar a arquitetura do fluxo de dados ideal para o seu MVP.

### 1. Devo ignorar os pontos de acesso (tags originais) e extrair do zero com IA?

**Não.** Os pontos de acesso legados são ouro arquivístico, mesmo vindo com lixo. Eles refletem a indexação histórica e humana daquele acervo. A IA atual não tem o contexto histórico para saber por que um arquivista na década de 90 colocou determinada palavra lá. O nosso papel não é substituir a história, é higienizá-la e enriquecê-la.

### 2. Usar o mDeBERTa no texto em vez das tags gera apenas uma classificação?

**Só se você usar a função matemática errada na saída do modelo.** Se você usar o modelo com ativação *Softmax* (que força a soma das probabilidades a dar 100%), ele vai escolher apenas um vencedor (ex: Legislação 90%, Urbanismo 10%).
Porém, se você configurar a saída (ou o *pipeline* zero-shot) para **Multi-Label Classification** (usando *Sigmoid*, onde cada classe é avaliada independentemente de 0 a 100%), um decreto pode perfeitamente pontuar "Legislação (95%)" e "Urbanismo (88%)" ao mesmo tempo.

---

### A Solução Arquitetural: Separação de Poderes

O erro que gera essa confusão mental é tentar tratar tudo como "Tag". Precisamos separar o seu modelo de dados em três eixos semânticos completamente distintos:

1. **Macro Categorias (Temas do Documento):** Legislação, Urbanismo, Finanças.
2. **Entidades Nomeadas (NER):** Prefeitura (ORG), João (PER), Curitiba (LOC).
3. **Descritores (As antigas "Tags"):** IPTU, asfalto, parques, alvará.

Aqui está o fluxo de trabalho (o *Pipeline*) que resolve o paradoxo de "apagar coisas úteis":

#### Passo 1: O spaCy no Texto (O lugar certo do NER)

O seu *worker* de NER deve **continuar rodando no conteúdo original/descrição**, e não nas tags. Modelos como o spaCy dependem de contexto gramatical (sujeito, verbo, predicado) para inferir se "Parques" é um local ou um sujeito na frase. Rodar NER em tags soltas destrói a precisão do modelo. Extraia as Entidades e salve-as na tabela `ArchiveEntity`.

#### Passo 2: A Higienização Passiva das Tags

Você importa as tags originais e faz aquela limpeza básica de *stopwords* e caracteres especiais que já programamos no repositório. Salve todas elas na tabela `ArchiveTag`. Não apague nenhuma baseada no spaCy ainda.

#### Passo 3: O "Soft-Match" (Cruzamento no Banco, não Deleção)

Aqui está o pulo do gato para o seu problema do "Parques".
Você cria uma query ou *worker* simples que compara os nomes que caíram na tabela de Entidades com os nomes da tabela de Tags.

* Se a Tag "Curitiba" existir na tabela de Tags e também existir "Curitiba" na tabela de Entidades como LOC, você **não apaga a Tag**.
* Você cria um campo booleano na sua tabela de tags chamado `is_potential_entity = True`.

#### Passo 4: A Decisão Humana (Streamlit)

Lá na sua página de **Governança de Taxonomia** no Streamlit, você adiciona um filtro: *"Mostrar Tags que a IA acha que são Entidades"*.
O seu usuário (curador) vai ver a lista e bater o olho:

* "Prefeitura" -> O curador clica em `Converter para Entidade`. O sistema apaga a tag e vincula o documento à Entidade.
* "Parques" -> O curador vê que o spaCy errou, clica em `Manter como Assunto`. O sistema tira o *flag* e o termo continua sendo uma tag maravilhosa para o domínio de urbanismo.

#### Passo 5: mDeBERTa no Texto (Multi-Label)

Você passa o escopo/resumo do documento (e não as tags) pelo mDeBERTa configurado para *Multi-Label*. Ele vai sugerir as **Macro Categorias**. O fato de o documento ter a tag "parques" é um detalhe; o mDeBERTa vai olhar o texto dizendo "criação de áreas de lazer" e classificar como "Urbanismo".

### Resumo do porquê isso devolve a sua paz de espírito:

Você para de tentar fazer o computador tomar a decisão final e letal (apagar dados). A sua API passa a atuar como um **motor de sugestão**.
O código extrai o melhor dos textos (com spaCy e mDeBERTa), cruza com as tags originais cheias de lixo, levanta uma "bandeira amarela" (o *flag* `is_potential_entity`) onde há dúvida semântica, e deixa a interface limpa no Litestar/Streamlit para o humano dar o clique final.






O Seu Problema Real: A Normalização de Tags

Você tocou na ferida das tags: “grafias quase idênticas” (ex: "parque" e "parques", "lei municipal" e "leis municipais").

A lematização é a ferramenta perfeita para isso, mas ela deve ser aplicada apenas nas tags soltas, como uma etapa de higienização dos pontos de acesso, e nunca no texto do documento que vai para a IA.

Como você já tem o spaCy no seu projeto, você tem o melhor lematizador do ecossistema nas mãos. O fluxo ideal no seu TagService seria:
Passo 1: Lematização das Tags Isoladas

Quando você ingere os pontos de acesso (tags originais), você passa a string da tag pelo spaCy especificamente para extrair o lemma_.
Python

import spacy

# Carrega o modelo em português (já deve estar no seu projeto)
nlp = spacy.load("pt_core_news_sm") 

def normalizar_tag(nome_da_tag: str) -> str:
    doc = nlp(nome_da_tag.lower())
    # Junta os lemmas (ex: "leis municipais" vira "lei municipal")
    return " ".join([token.lemma_ for token in doc])

Passo 2: O Agrupamento (Merge) Automático

Com essa função, você resolve 80% do lixo do seu acervo automaticamente na ingestão:

    A tag "Parques" entra no sistema. O lema dela é "parque".

    A tag "parque" entra no sistema. O lema dela é "parque".

    O seu banco de dados (que já está preparado com DDD) percebe que ambas apontam para a mesma string normalizada. Em vez de criar dois IDs diferentes, ele amarra os dois documentos ao mesmo ArchiveTag com nome "parque".

Passo 3: Distância de Levenshtein (Tratamento de Erros de Digitação)

A lematização resolve plural e conjugação, mas não resolve erro de digitação de quem cadastrou no sistema nos anos 90 (ex: "Prefeiruta" em vez de "Prefeitura").
Para isso, você não usa IA. Você usa a matemática clássica diretamente no PostgreSQL, que é incrivelmente rápido com o módulo pg_trgm (Trigramas).

Você pode criar uma query no seu repositório para o curador bater o olho na interface do Litestar/Streamlit:
"Quais tags têm 90% de semelhança na digitação, mas são IDs diferentes?"
Isso permite que o curador use aquela rota maravilhosa /tags/merge que criamos para fundir "Prefeiruta" em "Prefeitura" em um clique.