-- PostGIS para dados espaciais, caso um dia seja preciso usar
CREATE EXTENSION IF NOT EXISTS postgis;

-- -----------------------------------------------------
--                     QUEUE AREA
-- -----------------------------------------------------
CREATE TYPE scrape_status_enum as ENUM ('PENDING', 'DONE', 'NETWORk_ERROR', 'NOT_FOUND');

CREATE TABLE
    IF NOT EXISTS scraping_queue (
        id SERIAL PRIMARY KEY,
        description_id VARCHAR(60) UNIQUE NOT NULL,
        scrape_status scrape_status_enum DEFAULT 'PENDING',
        --Sliding Window
        discovered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- Quando o ID foi visto pela 1ª vez
        last_scraped_at TIMESTAMPTZ,
        retry_count INT DEFAULT 0,
        last_error_message TEXT
    );