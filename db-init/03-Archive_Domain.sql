-- 1. Criação do ENUM de Status de Revisão
CREATE TYPE archive_review_status_enum AS ENUM (
    'PENDING_AI',       -- Aguardando processamento dos modelos de IA
    'AI_APPROVED',      -- Validado automaticamente pela IA com alta confiança
    'NEEDS_REVIEW',     -- Anomalia detectada ou baixa confiança (Gatilho HITL)
    'HUMAN_APPROVED',   -- Validado/Corrigido por humano (Bloqueia re-escrita da IA)
    'REJECTED'          -- Marcado como lixo/descarte por um humano
);

-- 2. Tabela de Dimensão: Entidades Nomeadas (NER)
CREATE TABLE IF NOT EXISTS archive_entities (
    entity_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- 'PER' (Pessoa), 'ORG' (Organização), 'LOC' (Local)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uix_entity_name UNIQUE (name)
);

-- Índices para buscas textuais e filtros por categoria de entidade
CREATE INDEX IF NOT EXISTS idx_archive_entities_name ON archive_entities (name);
CREATE INDEX IF NOT EXISTS idx_archive_entities_type ON archive_entities (entity_type);

-- 3. Tabela de Dimensão: Tags e Taxonomias (Zero-Shot / Clustering)
CREATE TABLE IF NOT EXISTS archive_tags (
    tag_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    macro_category VARCHAR(100), -- Categoria mãe definida via Classificação Semântica
    ai_confidence_score DOUBLE PRECISION, -- Score de certeza do modelo (0 a 100)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uix_tag_name UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_archive_tags_name ON archive_tags (name);
CREATE INDEX IF NOT EXISTS idx_archive_tags_macro ON archive_tags (macro_category);

-- 4. Tabela Fato: Descrições (A base principal do Acervo)
CREATE TABLE IF NOT EXISTS archive_documents (
    description_id VARCHAR(50) PRIMARY KEY, -- Mantém o 1:1 rigoroso com a Camada Staging
    original_title TEXT NOT NULL,
    document_date DATE,
    summary TEXT,
    staging_content_hash VARCHAR(64) NOT NULL, -- Identifica se o dado mudou na origem
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
    semantic_search_vector TEXT, -- Texto limpo via spaCy para buscas
    execution_log JSONB NOT NULL DEFAULT '{}'::jsonb, -- Rastreamento Assíncrono da IA

    -- Governança e Qualidade Data-Driven
    review_status archive_review_status_enum NOT NULL DEFAULT 'PENDING_AI',
    is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_reasons TEXT[], -- ARRAY para acumular múltiplos erros
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices normais
CREATE INDEX IF NOT EXISTS idx_archive_desc_status ON archive_documents (review_status);
CREATE INDEX IF NOT EXISTS idx_archive_desc_anomaly ON archive_documents (is_anomaly);
-- O Índice GIN: Permite aos Workers encontrarem JSONs pendentes em milissegundos
CREATE INDEX IF NOT EXISTS ix_archive_exec_log ON archive_documents USING GIN (execution_log);

-- 5. Tabela de Ligação (Ponte N:N): Documentos <-> Entidades
CREATE TABLE IF NOT EXISTS archive_document_entities (
    description_id VARCHAR(50) NOT NULL,
    entity_id INT NOT NULL,
    PRIMARY KEY (description_id, entity_id),
    CONSTRAINT fk_desc_entities_doc FOREIGN KEY (description_id) REFERENCES archive_documents (description_id) ON DELETE CASCADE,
    CONSTRAINT fk_desc_entities_ent FOREIGN KEY (entity_id) REFERENCES archive_entities (entity_id) ON DELETE CASCADE,
    CONSTRAINT uix_archive_document_entity UNIQUE (description_id, entity_id)
);

-- 6. Tabela de Ligação (Ponte N:N): Documentos <-> Tags
CREATE TABLE IF NOT EXISTS archive_document_tags (
    description_id VARCHAR(50) NOT NULL,
    tag_id INT NOT NULL,
    PRIMARY KEY (description_id, tag_id),
    CONSTRAINT fk_desc_tags_doc FOREIGN KEY (description_id) REFERENCES archive_documents (description_id) ON DELETE CASCADE,
    CONSTRAINT fk_desc_tags_tag FOREIGN KEY (tag_id) REFERENCES archive_tags (tag_id) ON DELETE CASCADE,
    CONSTRAINT uix_archive_document_tag UNIQUE (description_id, tag_id)
);

-- 7. Automação do campo 'updated_at' via Trigger nativa do PostgreSQL
CREATE OR REPLACE FUNCTION update_archive_documents_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_archive_documents ON archive_documents;

CREATE TRIGGER trg_update_archive_documents
    BEFORE UPDATE ON archive_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_archive_documents_timestamp();

-- 8. Dicionário do Domínio: Stopwords
CREATE TABLE IF NOT EXISTS domain_stopwords (
    id SERIAL PRIMARY KEY,
    word VARCHAR(255) UNIQUE NOT NULL
);

-- 9. Dicionário do Domínio: Sinônimos
CREATE TABLE IF NOT EXISTS domain_synonyms (
    id SERIAL PRIMARY KEY,
    -- Colunas base
    synonym_name VARCHAR(100) NOT NULL,
    category VARCHAR(10) NOT NULL, -- Valores Aceitos 'TAG', 'LOC','ORG','PER'
    canonical_tag_id INTEGER,
    canonical_entity_id INTEGER, -- Arcos Exclusivos (Chaves Estrangeiras Nulas)
    
    -- 1. Relacionamento com a tabela de Tags
    CONSTRAINT fk_domain_synonyms_tag FOREIGN KEY (canonical_tag_id) REFERENCES archive_tags (tag_id) ON DELETE CASCADE,
    -- 2. Relacionamento com a tabela de Entidades
    CONSTRAINT fk_domain_synonyms_entity FOREIGN KEY (canonical_entity_id) REFERENCES archive_entities (entity_id) ON DELETE CASCADE,
    -- 3. Restrição de Unicidade Composta
    CONSTRAINT uix_synonym_category UNIQUE (synonym_name, category),
    -- 4. Restrição de Integridade do Arco Exclusivo (O coração da tabela)
    CONSTRAINT chk_exclusive_synonym_target CHECK (
        (
            category = 'TAG'
            AND canonical_tag_id IS NOT NULL
            AND canonical_entity_id IS NULL
        )
        OR (
            category IN ('ORG', 'LOC', 'PER')
            AND canonical_entity_id IS NOT NULL
            AND canonical_tag_id IS NULL
        )
    )
);

-- Índices de Performance para o dicionário
CREATE INDEX ix_domain_synonyms_synonym_name ON domain_synonyms (synonym_name);
CREATE INDEX ix_domain_synonyms_category ON domain_synonyms (category);