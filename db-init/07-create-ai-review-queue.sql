
CREATE TYPE anomaly_type_enum AS ENUM ('CROSS_DOMAIN_COLLISION');


-- 2. Criação da Tabela
CREATE TABLE archive_ai_review_queue (
    id SERIAL PRIMARY KEY,
    anomaly_type anomaly_type_enum NOT NULL,
    status archive_review_status_enum NOT NULL DEFAULT 'PENDING_AI',
    context_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_decision VARCHAR(50),
    llm_confidence FLOAT,
    llm_reason TEXT
);

-- 3. Criação dos Índices (conforme index=True na model)
CREATE INDEX ix_archive_ai_review_queue_anomaly_type ON archive_ai_review_queue (anomaly_type);
CREATE INDEX ix_archive_ai_review_queue_status ON archive_ai_review_queue (status);