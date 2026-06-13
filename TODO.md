# 🗺️ Roadmap & TO-DO: Motor de Enriquecimento de Arquivos (AI-Driven)

Este documento centraliza o planeamento arquitetural e as próximas etapas de desenvolvimento do sistema de curadoria e enriquecimento de dados arquivísticos.

## 🟢 Fase 1: Conclusão do Core Pipeline (Curto Prazo)
O objetivo desta fase é fechar a esteira de Inteligência Híbrida (Humano + IA) nos dados já existentes na Camada Ouro.

- [x] **Camadas Bronze & Silver:** Extração e limpeza do acervo base.
- [x] **Camada Gold (Fato/Dimensão):** Modelagem dimensional, testes Pytest, DTOs estritos e trava de idempotência via Hash.
- [x] **Worker de Migração (`worker_load_gold.py`):** Carga inicial, Data Quality de tags legadas e logs JSONB.
- [x] **Worker NER (`worker_ner.py`):**
  - [x] Implementar script utilizando `spaCy` (`pt_core_news_lg`).
  - [x] Extrair entidades (LOC, PER, ORG) dos metadados.
  - [x] Salvar progressão no `execution_log` (checkpoint).
- [ ] **Worker LLM Gerador/Validador (`worker_ollama.py`):**
  - [ ] Implementar parser defensivo e retries para lidar com respostas instáveis de LLMs locais.
  - [ ] Expandir tags não documentadas pelo arquivista original.
  - [ ] Sinalizar anomalias textuais (`is_anomaly`).
- [ ] **Worker Categorizador (`worker_mdeberta.py`):**
  - [ ] Agrupar tags soltas em Macro Categorias para facilitar a filtragem no front-end.
- [x] **Worker Thumbnail Downloader**

## 🟡 Fase 2: Camada de Acesso e Descoberta (Médio Prazo)
Dar utilidade imediata aos dados enriquecidos na Camada Ouro através de uma interface visual simples.

- [ ] **Motor de Busca Semântica:**
  - [ ] Implementar queries otimizadas no PostgreSQL filtrando por tags, categorias e entidades.
  - [ ] (Opcional) Gerar embeddings com pgvector para busca por similaridade de contexto.
- [x] **Interface Web Leve (MVP):**
  - [x] Desenvolver um front-end rápido em Python (Streamlit ou Gradio).
  - [x] Criar dashboard simples exibindo os metadados ISAD(G) e as entidades descobertas pela IA.

## 🟠 Fase 3: Refatoração Arquitetural (Ports & Adapters)
Preparar o repositório para ser uma ferramenta open-source agnóstica, separando o "Motor de IA" da origem dos dados.

- [ ] **Isolamento do Core:** Separar a lógica das Camadas Prata/Ouro e dos Workers numa pasta/módulo independente (ex: `core_engine/`).
- [ ] **Sistema de Adapters (Plugins):** - [ ] Mover o scraper específico atual para um módulo de *Adapters* (ex: `adapters/scrapers/curitiba_scraper.py`).
  - [ ] Criar uma interface padrão (Abstract Base Class) para que qualquer instituição possa plugar os seus próprios scrapers ou conectores de banco sem alterar o Core.

## 🔴 Fase 4: Expansão de Capacidades (Longo Prazo - v2.0)
Adicionar novos "operários" de IA à esteira industrial para lidar com dados não-estruturados e criação ativa.

- [ ] **Worker de Visão Computacional (OCR):**
  - [ ] Consumir URLs de imagens/PDFs salvos na Bronze.
  - [ ] Extrair texto bruto de documentos históricos e injetar na Ouro para indexação.
- [ ] **Worker de Geração de Descrições (LLM Avançado):**
  - [ ] Criar textos descritivos no padrão ISAD(G) (ex: `scope_content`) do zero, a partir da leitura de documentos onde o arquivista não deixou resumo.
- [ ] **Integração com Sistemas de Preservação:**
  - [ ] Criar pipelines de exportação (DIPs) que conversem com sistemas de guarda permanente e pacotes OAIS.


### 🧹 Governança e Resolução de Entidades (Entity Resolution)

Este documento mapeia a evolução da curadoria humana e automatizada sobre os dados extraídos pelo motor de NLP.

#### Fase 1: Exploração e Limpeza Tática (Manual via Jupyter/SQL)
- [x] Ativar extensão `pg_trgm` no PostgreSQL.
- [x] Criar query de similaridade de strings (Fuzzy Matching) para agrupar entidades suspeitas de duplicação.
- [x] Mapear os erros mais comuns do spaCy (ex: divisão de siglas institucionais).
- [ ] Inserir manualmente os mapeamentos corrigidos na tabela `nlp_dictionary` para blindar o motor.
  - `nlp_dictionary` possivelmente está deprecated agora com a tabela `domain_synonyms`

#### Fase 2: O Revisor Silencioso (Background AI)
- [ ] Criar worker assíncrono para o Granite (ou outro modelo local leve).
- [ ] Configurar prompt de classificação estrita (JSON Output) focado apenas em similaridade semântica: avaliar pares de entidades e sugerir fusões (merges).
- [ ] Criar tabela transacional no banco: `entity_merge_suggestions` para armazenar as ideias da IA.

#### Fase 3: Módulo de Curadoria no Streamlit (Human-in-the-Loop)
- [ ] **Ação Global (Merge de Entidades):** - Criar tela onde o usuário não-técnico aprova/rejeita as sugestões da IA.
  - Implementar transação SQL que: (1) Remapeia as chaves estrangeiras na tabela associativa para o ID Canônico. (2) Apaga as entidades duplicadas. (3) Salva a regra permanentemente no `nlp_dictionary`.
- [ ] **Ação Local (Override de Documento):**
  - Adicionar botão de exclusão/edição de entidades na visualização individual do documento.
  - Alterar o `review_status` do documento para `HUMAN_APPROVED` ao salvar, travando futuras sobresscritas dos Workers.