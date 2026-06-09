CREATE TABLE
    IF NOT EXISTS staging_descriptions (
        id SERIAL PRIMARY KEY,
        description_id VARCHAR(60) UNIQUE NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        raw_title VARCHAR(500),
        payload JSONB,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );