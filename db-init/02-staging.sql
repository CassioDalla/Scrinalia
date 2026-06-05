CREATE TYPE staging_status_enum AS ENUM (
    'PENDING',
    'REVIEW_REQUIRED',
    'APPROVED',
    'NETWORK_ERROR',
    'FATAL_ERROR'
);

CREATE TABLE
    validation_rules (
        id SERIAL PRIMARY KEY,
        code VARCHAR(50) UNIQUE NOT NULL,
        description VARCHAR(255) NOT NULL,
        severity VARCHAR(20) DEFAULT 'WARNING'
    );

CREATE TABLE
    IF NOT EXISTS staging_descriptions (
        id SERIAL PRIMARY KEY,
        description_id VARCHAR(60) UNIQUE NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        raw_title VARCHAR(500),
        suggested_title VARCHAR(500),
        status staging_status_enum DEFAULT 'PENDING',
        payload JSONB,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

-- Tabela que liga o documento aos erros encontrados
CREATE TABLE
    staging_flags (
        id SERIAL PRIMARY KEY,
        staging_id INT REFERENCES staging_descriptions (id) ON DELETE CASCADE,
        rule_id INT REFERENCES validation_rules (id) ON DELETE CASCADE,
        error_context VARCHAR(255) -- Ex: "Palavra encontrada: Pavimentasão"
    );

-- Populando o banco com algumas regras padrão para você já começar
INSERT INTO
    validation_rules (code, description, severity)
VALUES
    (
        'TYPO_TITLE',
        'Erro ortográfico detectado no título',
        'WARNING'
    ) ON CONFLICT (code) DO NOTHING;