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
- [ ] **Serviço de Entidades (`EntityService`):**
  - [ ] Espelhar a lógica do `TagService`: criar funções para fundir (`merge`) Entidades duplicadas e popular a tabela `domain_synonyms`.
- [ ] **Painel de Curadoria (Front-end HITL):**
  - [x] Dashboard inicial em Streamlit/Gradio para visualização de metadados.
  - [ ] **Ação Global:** Tela dedicada à resolução de entidades/tags. O utilizador aprova fusões (ex: "Prefeitura" -> "PMC") que alimentam os sinônimos automaticamente.
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