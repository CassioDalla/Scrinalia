CREATE TYPE stopwords_scope as ENUM (
    'TAG', -- Stopwords apenas para as tags
    'ENTITY',
    'ALL'
);

Alter TABLE domain_stopwords
ADD COLUMN word_scope stopwords_scope DEFAULT 'TAG' NOT NULL;

CREATE INDEX idx_stopwords_scope ON domain_stopwords (word_scope);