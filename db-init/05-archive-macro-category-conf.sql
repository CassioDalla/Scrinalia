-- Tabela de configuração do sistema para a IA
CREATE TABLE IF NOT EXISTS archive_macro_categories (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL, -- O nome exato que vai para o Zero-Shot
    description TEXT, -- Para o gestor lembrar por que criou essa categoria
    is_active BOOLEAN NOT NULL DEFAULT TRUE, -- Permite desativar sem apagar histórico
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insira alguns exemplos iniciais (que outras instituições poderão apagar depois)
INSERT INTO archive_macro_categories (name, description) VALUES 
('Pessoa', 'Nomes de figuras históricas e indivíduos'),
('Localidade', 'Nomes de bairros, ruas, praças e cidades'),
('Instituição', 'Secretarias, empresas e órgãos públicos'),
('Mobilidade e Transporte', 'Tudo relacionado a trânsito, ônibus, etc.'),
('Urbanismo e Arquitetura', 'Obras, plantas e planejamento urbano');