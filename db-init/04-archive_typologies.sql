-- Cria a tabela de domínio das tipologias (Ex: Fotografia, Planta, Ofício)
CREATE TABLE IF NOT EXISTS archive_typologies (
    typology_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    context_description TEXT, --usado para dar mais contexto para o classificador
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Adiciona a referência na tabela principal de documentos
ALTER TABLE archive_documents
ADD COLUMN typology_id INT,
ADD CONSTRAINT fk_archive_documents_typology FOREIGN KEY (typology_id) REFERENCES archive_typologies (typology_id) ON DELETE SET NULL;

CREATE INDEX idx_archive_documents_typology ON archive_documents (typology_id);

--Exemplos
INSERT INTO
    archive_typologies (name, context_description)
VALUES (
        'Planta Arquitetônica',
        'Projetos de construção, aumento de área, projeto de muro, projeto de aumento, reformas, fachadas, alvarás de obras'
    ),
    (
        'Mapa / Croqui Urbanístico',
        'Loteamentos, zoneamento, arruamento, cartografia, traçados de ruas e bairros'
    ),
    (
        'Fotografia',
        'Registros fotográficos, negativos, ampliações, imagens de ruas,imagens de eventos, imagens de obras'
    ),
    (
        'Audiovisual',
        'Fitas magnéticas, VHS, gravações de áudio, entrevistas, vídeos institucionais'
    ),
    (
        'Decreto / Lei / Portaria',
        'Atos normativos, legislação municipal, diário oficial, regulamentações'
    ),
    (
        'Ofício / Memorando',
        'Comunicação oficial interna ou externa entre secretarias, correspondências institucionais'
    ),
    (
        'Ata de Reunião',
        'Registros de encontros, deliberações de conselhos, comitês ou assembleias'
    ),
    (
        'Relatório Técnico',
        'Estudos de impacto, vistorias, laudos técnicos, balanços de gestão, diagnósticos'
    ),
    (
        'Processo Administrativo',
        'Autos de infração, desapropriações, licitações, contratos públicos consolidados'
    ),
    (
        'Dossiê Funcional',
        'Fichas de funcionários, histórico de servidores públicos, prontuários'
    )
ON CONFLICT (name) DO
UPDATE
SET
    context_description = EXCLUDED.context_description;