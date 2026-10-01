-- 1. Cria o utilizador (role) com uma senha segura
CREATE ROLE portal_reader
WITH
    LOGIN PASSWORD 'senha_super_segura_123';

-- 2. Concede permissão para o utilizador "entrar" no schema public
GRANT USAGE ON SCHEMA public TO portal_reader;

-- 3. Concede permissão APENAS DE LEITURA (SELECT) para todas as tabelas que já existem
GRANT SELECT ON ALL TABLES IN SCHEMA public TO portal_reader;

-- 4. (Opcional, mas recomendado) Garante que se o Python criar tabelas novas no futuro,
-- este utilizador também terá permissão automática de leitura nelas:
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT
SELECT ON TABLES TO portal_reader;