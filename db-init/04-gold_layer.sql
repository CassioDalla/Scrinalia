-- 1. Criação do ENUM de Status de Revisão
CREATE TYPE gold_review_status_enum AS ENUM (
    'PENDING_AI',       -- Aguardando processamento dos modelos de IA
    'AI_APPROVED',      -- Validado automaticamente pela IA com alta confiança
    'NEEDS_REVIEW',     -- Anomalia detectada ou baixa confiança (Gatilho HITL)
    'HUMAN_APPROVED',   -- Validado/Corrigido por humano (Bloqueia re-escrita da IA)
    'REJECTED'          -- Marcado como lixo/descarte por um humano
);

-- 2. Tabela de Dimensão: Entidades Nomeadas (NER)
CREATE TABLE IF NOT EXISTS gold_entities (
    entity_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- 'PER' (Pessoa), 'ORG' (Organização), 'LOC' (Local)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uix_entity_name UNIQUE (name)
);

-- Índices para buscas textuais e filtros por categoria de entidade
CREATE INDEX IF NOT EXISTS idx_gold_entities_name ON gold_entities (name);

CREATE INDEX IF NOT EXISTS idx_gold_entities_type ON gold_entities (entity_type);

-- 3. Tabela de Dimensão: Tags e Taxonomias (Zero-Shot / Clustering)
CREATE TABLE IF NOT EXISTS gold_tags (
    tag_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    macro_category VARCHAR(100), -- Categoria mãe definida via Classificação Semântica
    ai_confidence_score DOUBLE PRECISION, -- Score de certeza do modelo (0 a 100)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uix_tag_name UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_gold_tags_name ON gold_tags (name);

CREATE INDEX IF NOT EXISTS idx_gold_tags_macro ON gold_tags (macro_category);

-- 4. Tabela Fato: Descrições
CREATE TABLE IF NOT EXISTS gold_descriptions (
    description_id VARCHAR(50) PRIMARY KEY, -- Mantém o 1:1 rigoroso com a Camada Silver
    original_title TEXT NOT NULL,
    document_date DATE,
    summary TEXT,
    silver_content_hash VARCHAR(64) NOT NULL, -- Identifica se o dado mudou na Silver
    original_thumbnail_url VARCHAR,
    storage_thumbnail_uri VARCHAR,
    -- Metadados da Norma ISAD(G)
    reference_code TEXT,
    level TEXT,
    producers TEXT,
    admin_bio_history TEXT,
    admin_archival_history TEXT,
    provenance TEXT,
    scope_content TEXT,
    language_name TEXT,
    archivist_notes TEXT,

-- Dados de Enriquecimento
final_title TEXT, -- Título definitivo (IA ou Humano)
semantic_search_vector TEXT, -- Texto limpo via spaCy (sem stopwords/lematizado) para NLP
execution_log JSONB NOT NULL DEFAULT '{}'::jsonb,

-- Governança e Qualidade Data-Driven


review_status gold_review_status_enum NOT NULL DEFAULT 'PENDING_AI',
    is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_reasons TEXT[], -- ARRAY para acumular múltiplos erros do LLM
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gold_desc_status ON gold_descriptions (review_status);

CREATE INDEX IF NOT EXISTS idx_gold_desc_anomaly ON gold_descriptions (is_anomaly);

-- 5. Tabela de Ligação (Ponte N:N): Documentos <-> Entidades
CREATE TABLE IF NOT EXISTS gold_description_entities (
    description_id VARCHAR(50) NOT NULL,
    entity_id INT NOT NULL,
    PRIMARY KEY (description_id, entity_id),
    CONSTRAINT fk_desc_entities_doc FOREIGN KEY (description_id) REFERENCES gold_descriptions (description_id) ON DELETE CASCADE,
    CONSTRAINT fk_desc_entities_ent FOREIGN KEY (entity_id) REFERENCES gold_entities (entity_id) ON DELETE CASCADE,
    CONSTRAINT uix_description_entity UNIQUE (description_id, entity_id)
);

-- 6. Tabela de Ligação (Ponte N:N): Documentos <-> Tags
CREATE TABLE IF NOT EXISTS gold_description_tags (
    description_id VARCHAR(50) NOT NULL,
    tag_id INT NOT NULL,
    PRIMARY KEY (description_id, tag_id),
    CONSTRAINT fk_desc_tags_doc FOREIGN KEY (description_id) REFERENCES gold_descriptions (description_id) ON DELETE CASCADE,
    CONSTRAINT fk_desc_tags_tag FOREIGN KEY (tag_id) REFERENCES gold_tags (tag_id) ON DELETE CASCADE,
    CONSTRAINT uix_description_tag UNIQUE (description_id, tag_id)
);

-- 7. Automação do campo 'updated_at' via Trigger nativa do PostgreSQL
CREATE OR REPLACE FUNCTION update_gold_descriptions_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_gold_descriptions ON gold_descriptions;

CREATE TRIGGER trg_update_gold_descriptions
    BEFORE UPDATE ON gold_descriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_gold_descriptions_timestamp();