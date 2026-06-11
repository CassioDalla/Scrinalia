CREATE TABLE
    nlp_dictionary (
        id SERIAL PRIMARY KEY,
        pattern VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        canonical_name VARCHAR NOT NULL
    );

CREATE EXTENSION IF NOT EXISTS pg_trgm;

INSERT INTO
    nlp_dictionary (pattern, label, canonical_name)
VALUES
    (
        'SMOP',
        'ORG',
        'Secretaria Municipal de Obras Públicas'
    ),
    ('PMC', 'ORG', 'Prefeitura Municipal de Curitiba'),
    (
        'Pref.',
        'ORG',
        'Prefeitura Municipal de Curitiba'
    ),
    (
        'IPPUC',
        'ORG',
        'Instituto de Pesquisa e Planejamento Urbano de Curitiba'
    ),
    ('SMU', 'ORG', 'Secretaria Municipal do Urbanismo');