CREATE TABLE archive_cleaning_rules (
    rule_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    target_column VARCHAR(50) NOT NULL,
    regex_pattern TEXT NOT NULL,
    replacement_string TEXT DEFAULT '' NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- O SQLAlchemy gera este índice separadamente devido ao parâmetro index=True
CREATE INDEX ix_archive_cleaning_rules_is_active ON archive_cleaning_rules (is_active);