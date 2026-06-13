CREATE TABLE IF NOT EXISTS domain_synonyms (
    id SERIAL PRIMARY KEY,
    -- Colunas base
    synonym_name VARCHAR(100) NOT NULL,
    category VARCHAR(10) NOT NULL, -- Valores Aceitos 'TAG', 'LOC','ORG','PER'
    canonical_tag_id INTEGER,
    canonical_entity_id INTEGER, -- Arcos Exclusivos (Chaves Estrangeiras Nulas)
    -- 1. Relacionamento com a tabela de Tags
    CONSTRAINT fk_domain_synonyms_tag FOREIGN KEY (canonical_tag_id) REFERENCES gold_tags (tag_id) ON DELETE CASCADE,
    -- 2. Relacionamento com a tabela de Entidades
    CONSTRAINT fk_domain_synonyms_entity FOREIGN KEY (canonical_entity_id) REFERENCES gold_entities (entity_id) ON DELETE CASCADE,
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

-- 5. Índices de Performance (Essenciais para buscas rápidas durante o ETL)
CREATE INDEX ix_domain_synonyms_synonym_name ON domain_synonyms (synonym_name);

CREATE INDEX ix_domain_synonyms_category ON domain_synonyms (category);