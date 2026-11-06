--
-- PostgreSQL database dump
--


-- Dumped from database version 15.19 (Debian 15.19-1.pgdg12+2)
-- Dumped by pg_dump version 15.19 (Debian 15.19-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: unaccent; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;


--
-- Name: EXTENSION unaccent; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION unaccent IS 'text search dictionary that removes accents';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: anomaly_type_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.anomaly_type_enum AS ENUM (
    'CROSS_DOMAIN_COLLISION',
    'SUBJECT_LOW_CONFIDENCE',
    'TYPOLOGY_LOW_CONFIDENCE'
);


--
-- Name: archive_entity_origin; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.archive_entity_origin AS ENUM (
    'AI',
    'HUMAN',
    'UNKNOWN'
);


--
-- Name: archive_review_status_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.archive_review_status_enum AS ENUM (
    'PENDING_AI',
    'AI_APPROVED',
    'NEEDS_REVIEW',
    'HUMAN_APPROVED',
    'REJECTED'
);


--
-- Name: collection_term_kind; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.collection_term_kind AS ENUM (
    'DISTRICT',
    'MUNICIPALITY',
    'STATE',
    'REGION',
    'COUNTRY',
    'PERSON'
);


--
-- Name: scrape_status_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.scrape_status_enum AS ENUM (
    'PENDING',
    'DONE',
    'NETWORK_ERROR',
    'NOT_FOUND',
    'FATAL_ERROR'
);


--
-- Name: stopwords_scope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.stopwords_scope AS ENUM (
    'TAG',
    'ENTITY',
    'ALL'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'ADMIN',
    'CURATOR',
    'VIEWER'
);


--
-- Name: worker_run_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.worker_run_status AS ENUM (
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'INTERRUPTED',
    'CANCELLED'
);


--
-- Name: worker_run_trigger; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.worker_run_trigger AS ENUM (
    'CLI',
    'API',
    'SCHEDULE'
);


--
-- Name: archive_error_fingerprint(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.archive_error_fingerprint(message text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$
  SELECT left(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(
            lower(btrim(regexp_replace(split_part(message, E'\n', 1), '\s+', ' ', 'g'))),
            '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', 'g'
          ),
          '[0-9a-f]{16,}', '<hash>', 'g'
        ),
        '[0-9]+', '<n>', 'g'
      ),
      '(/[^ /"'']+)+', '<path>', 'g'
    ),
    200
  )
$$;


--
-- Name: immutable_unaccent(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.immutable_unaccent(txt text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, txt) $$;


--
-- Name: update_archive_documents_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_archive_documents_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: archive_ai_review_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_ai_review_queue (
    id integer NOT NULL,
    anomaly_type public.anomaly_type_enum NOT NULL,
    status public.archive_review_status_enum NOT NULL,
    context_payload jsonb NOT NULL,
    llm_decision character varying(100),
    llm_confidence double precision,
    llm_reason text
);


--
-- Name: archive_ai_review_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_ai_review_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_ai_review_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_ai_review_queue_id_seq OWNED BY public.archive_ai_review_queue.id;


--
-- Name: archive_api_errors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_api_errors (
    id integer NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL,
    request_id character varying(64),
    method character varying(10) NOT NULL,
    path character varying(400) NOT NULL,
    status_code integer NOT NULL,
    message text NOT NULL,
    error_fingerprint text GENERATED ALWAYS AS (public.archive_error_fingerprint(message)) STORED
);


--
-- Name: archive_api_errors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_api_errors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_api_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_api_errors_id_seq OWNED BY public.archive_api_errors.id;


--
-- Name: archive_arrangement_vocabulary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_arrangement_vocabulary (
    term_id integer NOT NULL,
    token character varying(100) NOT NULL,
    display_name character varying(200) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_arrangement_vocabulary_term_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_arrangement_vocabulary_term_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_arrangement_vocabulary_term_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_arrangement_vocabulary_term_id_seq OWNED BY public.archive_arrangement_vocabulary.term_id;


--
-- Name: archive_cleaning_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_cleaning_rules (
    rule_id integer NOT NULL,
    rule_name character varying(150) NOT NULL,
    target_column character varying(50) NOT NULL,
    regex_pattern text NOT NULL,
    replacement_string text DEFAULT ''::text NOT NULL,
    is_active boolean NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    rule_kind character varying(20) DEFAULT 'REWRITE'::character varying NOT NULL,
    anomaly_reason text,
    engine_name character varying(50),
    preset character varying(50),
    created_by_user_id integer,
    CONSTRAINT chk_cleaning_rule_kind CHECK (((rule_kind)::text = ANY ((ARRAY['REWRITE'::character varying, 'VALIDATE'::character varying, 'LLM_CHECK'::character varying])::text[])))
);


--
-- Name: archive_cleaning_rules_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_cleaning_rules_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_cleaning_rules_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_cleaning_rules_rule_id_seq OWNED BY public.archive_cleaning_rules.rule_id;


--
-- Name: archive_collection_terms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_collection_terms (
    term_id integer NOT NULL,
    term character varying(200) NOT NULL,
    kind public.collection_term_kind NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_collection_terms_term_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_collection_terms_term_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_collection_terms_term_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_collection_terms_term_id_seq OWNED BY public.archive_collection_terms.term_id;


--
-- Name: archive_conflict_resolution_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_conflict_resolution_log (
    resolution_id integer NOT NULL,
    winner character varying(10) NOT NULL,
    source character varying(10) DEFAULT 'HUMAN'::character varying NOT NULL,
    tag_id integer NOT NULL,
    tag_name character varying(100) NOT NULL,
    entity_id integer NOT NULL,
    entity_name character varying(100) NOT NULL,
    entity_type character varying(20) NOT NULL,
    loser_snapshot jsonb NOT NULL,
    transferred_document_ids jsonb NOT NULL,
    created_link_ids jsonb NOT NULL,
    ban_kind character varying(20),
    ban_term character varying(255),
    ban_created boolean DEFAULT false NOT NULL,
    decided_by character varying(100),
    decided_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    decided_by_user_id integer,
    undone_by_user_id integer,
    synonym_names jsonb NOT NULL,
    CONSTRAINT chk_conflict_resolution_ban_kind CHECK (((ban_kind IS NULL) OR ((ban_kind)::text = ANY ((ARRAY['NER_EXCLUSION'::character varying, 'STOPWORD'::character varying])::text[])))),
    CONSTRAINT chk_conflict_resolution_source CHECK (((source)::text = ANY ((ARRAY['JUDGE'::character varying, 'HUMAN'::character varying])::text[]))),
    CONSTRAINT chk_conflict_resolution_winner CHECK (((winner)::text = ANY ((ARRAY['TAG'::character varying, 'ENTITY'::character varying])::text[])))
);


--
-- Name: archive_conflict_resolution_log_resolution_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_conflict_resolution_log_resolution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_conflict_resolution_log_resolution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_conflict_resolution_log_resolution_id_seq OWNED BY public.archive_conflict_resolution_log.resolution_id;


--
-- Name: archive_description_levels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_description_levels (
    level_id integer NOT NULL,
    ordinal integer NOT NULL,
    code character varying(20) NOT NULL,
    name character varying(60) NOT NULL,
    description text,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    requires_parent boolean DEFAULT false NOT NULL,
    allows_children boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_description_level_ordinal CHECK ((ordinal >= 0))
);


--
-- Name: archive_description_levels_level_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_description_levels_level_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_description_levels_level_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_description_levels_level_id_seq OWNED BY public.archive_description_levels.level_id;


--
-- Name: archive_document_deletions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_document_deletions (
    deletion_id integer NOT NULL,
    description_id character varying(50) NOT NULL,
    reference_code text,
    title text NOT NULL,
    level_name text,
    snapshot jsonb NOT NULL,
    children_count integer DEFAULT 0 NOT NULL,
    deleted_by character varying(100),
    note text,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_by_user_id integer
);


--
-- Name: archive_document_deletions_deletion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_document_deletions_deletion_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_document_deletions_deletion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_document_deletions_deletion_id_seq OWNED BY public.archive_document_deletions.deletion_id;


--
-- Name: archive_document_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_document_entities (
    description_id character varying(50) NOT NULL,
    entity_id integer NOT NULL,
    origin public.archive_entity_origin NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: archive_document_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_document_revisions (
    revision_id integer NOT NULL,
    description_id character varying(50) NOT NULL,
    changed_by character varying(100),
    changes jsonb NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    changed_by_user_id integer
);


--
-- Name: archive_document_revisions_revision_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_document_revisions_revision_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_document_revisions_revision_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_document_revisions_revision_id_seq OWNED BY public.archive_document_revisions.revision_id;


--
-- Name: archive_document_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_document_tags (
    description_id character varying(50) NOT NULL,
    tag_id integer NOT NULL
);


--
-- Name: archive_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_documents (
    description_id character varying(50) NOT NULL,
    original_title text NOT NULL,
    document_date date,
    summary text,
    staging_content_hash character varying(64) NOT NULL,
    original_thumbnail_url character varying,
    storage_thumbnail_uri character varying,
    reference_code text,
    producers text,
    admin_bio_history text,
    admin_archival_history text,
    provenance text,
    scope_content text,
    language_name text,
    archivist_notes text,
    final_title text,
    execution_log jsonb NOT NULL,
    typology_id integer,
    review_status public.archive_review_status_enum NOT NULL,
    is_anomaly boolean NOT NULL,
    anomaly_reasons text[],
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS ((setweight(to_tsvector('portuguese'::regconfig, public.immutable_unaccent(((COALESCE(final_title, ''::text) || ' '::text) || COALESCE(original_title, ''::text)))), 'A'::"char") || setweight(to_tsvector('portuguese'::regconfig, public.immutable_unaccent(((((COALESCE(scope_content, ''::text) || ' '::text) || COALESCE(admin_bio_history, ''::text)) || ' '::text) || COALESCE(provenance, ''::text)))), 'B'::"char"))) STORED,
    embedding public.vector(384),
    level_id integer,
    parent_id character varying(50),
    path text NOT NULL,
    access_conditions text,
    is_published boolean DEFAULT false NOT NULL,
    origin_code character varying(50),
    date_expression text,
    original_url text,
    dimension_support text,
    appraisal_destruction text,
    accruals text,
    arrangement text,
    reproduction_conditions text,
    physical_characteristics text,
    finding_aids text,
    originals_location text,
    copies_location text,
    related_units text,
    publication_notes text,
    conservation_notes text,
    general_notes text,
    rules_conventions text,
    description_dates text,
    parent_reference_code text
);


--
-- Name: archive_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_entities (
    entity_id integer NOT NULL,
    name character varying(255) NOT NULL,
    entity_type character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_entities_entity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_entities_entity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_entities_entity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_entities_entity_id_seq OWNED BY public.archive_entities.entity_id;


--
-- Name: archive_entity_merge_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_entity_merge_log (
    merge_id integer NOT NULL,
    canonical_id integer,
    canonical_name character varying(255) NOT NULL,
    canonical_entity_type character varying(50) NOT NULL,
    absorbed_entity_id integer,
    absorbed_name character varying(255),
    absorbed_snapshot jsonb,
    document_ids jsonb NOT NULL,
    created_link_ids jsonb NOT NULL,
    synonym_created boolean DEFAULT true NOT NULL,
    synonym_previous_entity_id integer,
    repointed_synonym_names jsonb NOT NULL,
    canonical_renamed_from character varying(255),
    renamed_from_synonym_created boolean DEFAULT false NOT NULL,
    renamed_from_synonym_previous_entity_id integer,
    changed_by character varying(100),
    changed_by_user_id integer,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    undone_by_user_id integer,
    kind character varying(20) DEFAULT 'MERGE'::character varying NOT NULL,
    CONSTRAINT chk_entity_merge_log_kind CHECK (((kind)::text = ANY ((ARRAY['MERGE'::character varying, 'RENAME'::character varying])::text[])))
);


--
-- Name: archive_entity_merge_log_merge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_entity_merge_log_merge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_entity_merge_log_merge_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_entity_merge_log_merge_id_seq OWNED BY public.archive_entity_merge_log.merge_id;


--
-- Name: archive_hierarchy_materialisation_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_hierarchy_materialisation_log (
    materialisation_id integer NOT NULL,
    created_nodes jsonb NOT NULL,
    rung_map jsonb NOT NULL,
    previous_state jsonb NOT NULL,
    changed_by character varying(100),
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    changed_by_user_id integer,
    undone_by_user_id integer
);


--
-- Name: archive_hierarchy_materialisation_log_materialisation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_hierarchy_materialisation_log_materialisation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_hierarchy_materialisation_log_materialisation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_hierarchy_materialisation_log_materialisation_id_seq OWNED BY public.archive_hierarchy_materialisation_log.materialisation_id;


--
-- Name: archive_hierarchy_node_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_hierarchy_node_plans (
    plan_id integer NOT NULL,
    code character varying(500) NOT NULL,
    depth integer NOT NULL,
    parent_code character varying(500),
    document_count integer DEFAULT 0 NOT NULL,
    declared_levels text[] DEFAULT '{}'::text[] NOT NULL,
    flags character varying(40)[] DEFAULT '{}'::character varying[] NOT NULL,
    sample_description_ids jsonb NOT NULL,
    existing_description_id character varying(50),
    level_id integer,
    title character varying(300),
    reference_code character varying(500),
    status character varying(20) DEFAULT 'SUGGESTED'::character varying NOT NULL,
    collapse_into_code character varying(500),
    decided_by character varying(100),
    decided_at timestamp with time zone,
    decision_note text,
    materialised_description_id character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_by_user_id integer,
    CONSTRAINT chk_hierarchy_plan_status CHECK (((status)::text = ANY ((ARRAY['SUGGESTED'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying])::text[])))
);


--
-- Name: archive_hierarchy_node_plans_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_hierarchy_node_plans_plan_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_hierarchy_node_plans_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_hierarchy_node_plans_plan_id_seq OWNED BY public.archive_hierarchy_node_plans.plan_id;


--
-- Name: archive_macro_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_macro_categories (
    category_id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    classifier_label text
);


--
-- Name: archive_macro_categories_category_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_macro_categories_category_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_macro_categories_category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_macro_categories_category_id_seq OWNED BY public.archive_macro_categories.category_id;


--
-- Name: archive_ner_purge_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_ner_purge_log (
    purge_id integer NOT NULL,
    excluded_term character varying(255) NOT NULL,
    purged_entity_id integer NOT NULL,
    purged_name character varying(255) NOT NULL,
    purged_snapshot jsonb NOT NULL,
    document_ids jsonb NOT NULL,
    synonym_names jsonb NOT NULL,
    changed_by character varying(100),
    changed_by_user_id integer,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    undone_by_user_id integer
);


--
-- Name: archive_ner_purge_log_purge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_ner_purge_log_purge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_ner_purge_log_purge_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_ner_purge_log_purge_id_seq OWNED BY public.archive_ner_purge_log.purge_id;


--
-- Name: archive_stopword_purge_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_stopword_purge_log (
    purge_id integer NOT NULL,
    purged_tag_id integer NOT NULL,
    purged_name character varying(100) NOT NULL,
    purged_snapshot jsonb NOT NULL,
    document_ids jsonb NOT NULL,
    synonym_names jsonb NOT NULL,
    changed_by character varying(100),
    changed_by_user_id integer,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    undone_by_user_id integer
);


--
-- Name: archive_stopword_purge_log_purge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_stopword_purge_log_purge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_stopword_purge_log_purge_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_stopword_purge_log_purge_id_seq OWNED BY public.archive_stopword_purge_log.purge_id;


--
-- Name: archive_tag_merge_proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_tag_merge_proposals (
    proposal_id integer NOT NULL,
    fingerprint character varying(64) NOT NULL,
    canonical_id integer,
    canonical_name character varying(100) NOT NULL,
    members jsonb NOT NULL,
    reason character varying(10) DEFAULT 'MIXED'::character varying NOT NULL,
    review_flags character varying(40)[] DEFAULT '{}'::character varying[] NOT NULL,
    total_documents integer DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'SUGGESTED'::character varying NOT NULL,
    decided_by character varying(100),
    decided_at timestamp with time zone,
    decision_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_by_user_id integer,
    CONSTRAINT chk_tag_merge_proposal_reason CHECK (((reason)::text = ANY ((ARRAY['TRIGRAM'::character varying, 'PLURAL'::character varying, 'MIXED'::character varying])::text[]))),
    CONSTRAINT chk_tag_merge_proposal_status CHECK (((status)::text = ANY ((ARRAY['SUGGESTED'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'APPLIED'::character varying])::text[])))
);


--
-- Name: archive_tag_merge_proposals_proposal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_tag_merge_proposals_proposal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_tag_merge_proposals_proposal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_tag_merge_proposals_proposal_id_seq OWNED BY public.archive_tag_merge_proposals.proposal_id;


--
-- Name: archive_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_tags (
    tag_id integer NOT NULL,
    name character varying(100) NOT NULL,
    macro_category_id integer,
    ai_confidence_score double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    execution_log jsonb
);


--
-- Name: archive_tags_tag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_tags_tag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_tags_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_tags_tag_id_seq OWNED BY public.archive_tags.tag_id;


--
-- Name: archive_taxonomy_merge_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_taxonomy_merge_log (
    merge_id integer NOT NULL,
    cluster_fingerprint character varying(64),
    canonical_id integer,
    canonical_name character varying(100) NOT NULL,
    absorbed_tag_id integer NOT NULL,
    absorbed_name character varying(100) NOT NULL,
    absorbed_snapshot jsonb NOT NULL,
    document_ids jsonb NOT NULL,
    created_link_ids jsonb NOT NULL,
    synonym_created boolean DEFAULT true NOT NULL,
    synonym_previous_tag_id integer,
    repointed_synonym_names jsonb NOT NULL,
    changed_by character varying(100),
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    note text,
    undone_at timestamp with time zone,
    undone_by character varying(100),
    changed_by_user_id integer,
    undone_by_user_id integer
);


--
-- Name: archive_taxonomy_merge_log_merge_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_taxonomy_merge_log_merge_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_taxonomy_merge_log_merge_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_taxonomy_merge_log_merge_id_seq OWNED BY public.archive_taxonomy_merge_log.merge_id;


--
-- Name: archive_typologies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_typologies (
    typology_id integer NOT NULL,
    name character varying(100) NOT NULL,
    context_description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: archive_typologies_typology_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_typologies_typology_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_typologies_typology_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_typologies_typology_id_seq OWNED BY public.archive_typologies.typology_id;


--
-- Name: archive_worker_runners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_worker_runners (
    runner_id character varying(120) NOT NULL,
    name character varying(120) NOT NULL,
    hostname character varying(255) NOT NULL,
    version character varying(50),
    capabilities character varying[] DEFAULT '{}'::text[] NOT NULL,
    concurrency integer DEFAULT 1 NOT NULL,
    heartbeat_seconds integer DEFAULT 15 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    last_heartbeat_at timestamp with time zone DEFAULT now() NOT NULL,
    stopped_at timestamp with time zone
);


--
-- Name: archive_worker_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_worker_runs (
    id integer NOT NULL,
    worker_name character varying(50) NOT NULL,
    status public.worker_run_status NOT NULL,
    trigger public.worker_run_trigger NOT NULL,
    requested_by character varying(120),
    engine_name character varying(50),
    preset character varying(50),
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    queued_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    duration_ms integer,
    error text,
    error_fingerprint text GENERATED ALWAYS AS (public.archive_error_fingerprint(error)) STORED,
    requested_by_user_id integer,
    options jsonb DEFAULT '{}'::jsonb NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    runner_id character varying(120),
    heartbeat_at timestamp with time zone,
    lease_expires_at timestamp with time zone,
    attempt integer DEFAULT 1 NOT NULL,
    retry_of integer,
    not_before timestamp with time zone,
    cancel_requested_at timestamp with time zone,
    cancel_requested_by character varying(120),
    cancel_requested_by_user_id integer,
    origin_code character varying(50),
    trial boolean DEFAULT false NOT NULL,
    trial_result jsonb
);


--
-- Name: archive_worker_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_worker_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_worker_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_worker_runs_id_seq OWNED BY public.archive_worker_runs.id;


--
-- Name: archive_worker_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_worker_schedules (
    worker_name character varying(120) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    cron character varying(120) NOT NULL,
    timezone character varying(64) NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    next_run_at timestamp with time zone,
    last_enqueued_at timestamp with time zone,
    last_skipped_at timestamp with time zone,
    updated_by character varying(120),
    updated_by_user_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_worker_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_worker_settings (
    worker_name character varying(50) NOT NULL,
    engine_name character varying(50),
    preset character varying(50),
    db_batch_size integer,
    options jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_by character varying(120),
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: archive_worker_settings_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_worker_settings_revisions (
    id integer NOT NULL,
    worker_name character varying(50) NOT NULL,
    before jsonb,
    after jsonb,
    changed_by character varying(120),
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    changed_by_user_id integer
);


--
-- Name: archive_worker_settings_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_worker_settings_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_worker_settings_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_worker_settings_revisions_id_seq OWNED BY public.archive_worker_settings_revisions.id;


--
-- Name: auth_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_sessions (
    session_id integer NOT NULL,
    user_id integer NOT NULL,
    token_hash character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    user_agent character varying(300),
    ip_address character varying(45)
);


--
-- Name: auth_sessions_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_sessions_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_sessions_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_sessions_session_id_seq OWNED BY public.auth_sessions.session_id;


--
-- Name: auth_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_users (
    user_id integer NOT NULL,
    email character varying(320) NOT NULL,
    name character varying(120) NOT NULL,
    password_hash text NOT NULL,
    role public.user_role NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    failed_attempts integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    locale character varying(8),
    CONSTRAINT chk_auth_users_locale CHECK (((locale IS NULL) OR ((locale)::text = ANY ((ARRAY['pt-BR'::character varying, 'en'::character varying])::text[]))))
);


--
-- Name: auth_users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auth_users_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auth_users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auth_users_user_id_seq OWNED BY public.auth_users.user_id;


--
-- Name: domain_ner_exclusions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_ner_exclusions (
    id integer NOT NULL,
    term character varying(255) NOT NULL,
    reason text,
    source character varying(20) DEFAULT 'HUMAN'::character varying NOT NULL,
    tag_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_ner_exclusion_source CHECK (((source)::text = ANY ((ARRAY['JUDGE'::character varying, 'HUMAN'::character varying])::text[])))
);


--
-- Name: domain_ner_exclusions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.domain_ner_exclusions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domain_ner_exclusions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.domain_ner_exclusions_id_seq OWNED BY public.domain_ner_exclusions.id;


--
-- Name: domain_stopwords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_stopwords (
    id integer NOT NULL,
    word character varying(255) NOT NULL,
    word_scope public.stopwords_scope NOT NULL,
    source character varying(20) DEFAULT 'HUMAN'::character varying NOT NULL,
    match_mode character varying(8) DEFAULT 'TOKEN'::character varying NOT NULL,
    CONSTRAINT chk_stopword_match_mode CHECK (((match_mode)::text = ANY ((ARRAY['TOKEN'::character varying, 'EXACT'::character varying])::text[]))),
    CONSTRAINT chk_stopword_source CHECK (((source)::text = ANY ((ARRAY['HUMAN'::character varying, 'CONFLICT'::character varying, 'EXCLUSION'::character varying])::text[])))
);


--
-- Name: domain_stopwords_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.domain_stopwords_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domain_stopwords_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.domain_stopwords_id_seq OWNED BY public.domain_stopwords.id;


--
-- Name: domain_subject_exclusions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_subject_exclusions (
    id integer NOT NULL,
    term character varying(255) NOT NULL,
    reason text,
    source character varying(20) DEFAULT 'HUMAN'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    ban_created boolean DEFAULT false NOT NULL,
    CONSTRAINT chk_subject_exclusion_source CHECK (((source)::text = ANY ((ARRAY['HUMAN'::character varying, 'RULE'::character varying])::text[])))
);


--
-- Name: domain_subject_exclusions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.domain_subject_exclusions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domain_subject_exclusions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.domain_subject_exclusions_id_seq OWNED BY public.domain_subject_exclusions.id;


--
-- Name: domain_synonyms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_synonyms (
    id integer NOT NULL,
    synonym_name character varying(100) NOT NULL,
    category character varying(10) NOT NULL,
    canonical_tag_id integer,
    canonical_entity_id integer,
    CONSTRAINT chk_exclusive_synonym_target CHECK (((((category)::text = 'TAG'::text) AND (canonical_tag_id IS NOT NULL) AND (canonical_entity_id IS NULL)) OR (((category)::text = ANY ((ARRAY['ORG'::character varying, 'LOC'::character varying, 'PER'::character varying])::text[])) AND (canonical_entity_id IS NOT NULL) AND (canonical_tag_id IS NULL))))
);


--
-- Name: domain_synonyms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.domain_synonyms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domain_synonyms_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.domain_synonyms_id_seq OWNED BY public.domain_synonyms.id;


--
-- Name: domain_text_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_text_templates (
    template_id integer NOT NULL,
    text text NOT NULL,
    fingerprint character varying(64) NOT NULL,
    variants text[] DEFAULT '{}'::text[] NOT NULL,
    action character varying(10) DEFAULT 'IGNORE'::character varying NOT NULL,
    replacement text DEFAULT ''::text NOT NULL,
    reason text,
    source character varying(20) DEFAULT 'HUMAN'::character varying NOT NULL,
    status character varying(20) DEFAULT 'SUGGESTED'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    occurrence_count integer DEFAULT 0 NOT NULL,
    sample_document_ids character varying(50)[] DEFAULT '{}'::character varying[] NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    scope character varying(20)[] DEFAULT '{EMBEDDING,NER}'::character varying[] NOT NULL,
    created_by_user_id integer,
    CONSTRAINT chk_text_template_action CHECK (((action)::text = ANY ((ARRAY['IGNORE'::character varying, 'REPLACE'::character varying])::text[]))),
    CONSTRAINT chk_text_template_scope CHECK (((array_length(scope, 1) >= 1) AND (scope <@ ARRAY['EMBEDDING'::character varying, 'NER'::character varying, 'TITLE'::character varying]))),
    CONSTRAINT chk_text_template_source CHECK (((source)::text = ANY ((ARRAY['SUGGESTED'::character varying, 'HUMAN'::character varying])::text[]))),
    CONSTRAINT chk_text_template_status CHECK (((status)::text = ANY ((ARRAY['SUGGESTED'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying])::text[])))
);


--
-- Name: domain_text_templates_template_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.domain_text_templates_template_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domain_text_templates_template_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.domain_text_templates_template_id_seq OWNED BY public.domain_text_templates.template_id;


--
-- Name: ingestion_origins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_origins (
    code character varying(50) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    options jsonb DEFAULT '{}'::jsonb NOT NULL,
    cron character varying(120),
    timezone character varying(64),
    next_run_at timestamp with time zone,
    last_enqueued_at timestamp with time zone,
    last_skipped_at timestamp with time zone,
    updated_by character varying(120),
    updated_by_user_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: raw_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_data (
    id integer NOT NULL,
    description_id character varying(60) NOT NULL,
    content_hash character varying(64) NOT NULL,
    raw_title character varying(500),
    payload jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    origin_code character varying(50),
    created_by character varying(120),
    created_by_user_id integer
);


--
-- Name: raw_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.raw_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: raw_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.raw_data_id_seq OWNED BY public.raw_data.id;


--
-- Name: scraping_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scraping_queue (
    id integer NOT NULL,
    description_id character varying(60) NOT NULL,
    scrape_status public.scrape_status_enum NOT NULL,
    discovered_at timestamp with time zone DEFAULT now() NOT NULL,
    last_scraped_at timestamp with time zone,
    retry_count integer NOT NULL,
    last_error_message text,
    origin_code character varying(50)
);


--
-- Name: scraping_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scraping_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scraping_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scraping_queue_id_seq OWNED BY public.scraping_queue.id;


--
-- Name: staging_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.staging_documents (
    description_id character varying(50) NOT NULL,
    raw_content_hash character varying(64) NOT NULL,
    title text NOT NULL,
    document_date date,
    original_url text,
    attachment_link text,
    thumb_down_link text,
    reference_code text,
    level text,
    dimension_support text,
    producers text,
    admin_bio_history text,
    admin_archival_history text,
    provenance text,
    scope_content text,
    appraisal_destruction text,
    accruals text,
    arrangement text,
    access_conditions text,
    reproduction_conditions text,
    language_name text,
    physical_characteristics text,
    finding_aids text,
    originals_location text,
    copies_location text,
    related_units text,
    publication_notes text,
    conservation_notes text,
    general_notes text,
    archivist_notes text,
    rules_conventions text,
    description_dates text,
    indexing_points text,
    raw_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    parent_reference_code text,
    hierarchy_path text,
    origin_code character varying(50),
    date_expression text
);


--
-- Name: archive_ai_review_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ai_review_queue ALTER COLUMN id SET DEFAULT nextval('public.archive_ai_review_queue_id_seq'::regclass);


--
-- Name: archive_api_errors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_api_errors ALTER COLUMN id SET DEFAULT nextval('public.archive_api_errors_id_seq'::regclass);


--
-- Name: archive_arrangement_vocabulary term_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_arrangement_vocabulary ALTER COLUMN term_id SET DEFAULT nextval('public.archive_arrangement_vocabulary_term_id_seq'::regclass);


--
-- Name: archive_cleaning_rules rule_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_cleaning_rules ALTER COLUMN rule_id SET DEFAULT nextval('public.archive_cleaning_rules_rule_id_seq'::regclass);


--
-- Name: archive_collection_terms term_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_collection_terms ALTER COLUMN term_id SET DEFAULT nextval('public.archive_collection_terms_term_id_seq'::regclass);


--
-- Name: archive_conflict_resolution_log resolution_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_conflict_resolution_log ALTER COLUMN resolution_id SET DEFAULT nextval('public.archive_conflict_resolution_log_resolution_id_seq'::regclass);


--
-- Name: archive_description_levels level_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_description_levels ALTER COLUMN level_id SET DEFAULT nextval('public.archive_description_levels_level_id_seq'::regclass);


--
-- Name: archive_document_deletions deletion_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_deletions ALTER COLUMN deletion_id SET DEFAULT nextval('public.archive_document_deletions_deletion_id_seq'::regclass);


--
-- Name: archive_document_revisions revision_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_revisions ALTER COLUMN revision_id SET DEFAULT nextval('public.archive_document_revisions_revision_id_seq'::regclass);


--
-- Name: archive_entities entity_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entities ALTER COLUMN entity_id SET DEFAULT nextval('public.archive_entities_entity_id_seq'::regclass);


--
-- Name: archive_entity_merge_log merge_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entity_merge_log ALTER COLUMN merge_id SET DEFAULT nextval('public.archive_entity_merge_log_merge_id_seq'::regclass);


--
-- Name: archive_hierarchy_materialisation_log materialisation_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_materialisation_log ALTER COLUMN materialisation_id SET DEFAULT nextval('public.archive_hierarchy_materialisation_log_materialisation_id_seq'::regclass);


--
-- Name: archive_hierarchy_node_plans plan_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_node_plans ALTER COLUMN plan_id SET DEFAULT nextval('public.archive_hierarchy_node_plans_plan_id_seq'::regclass);


--
-- Name: archive_macro_categories category_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_macro_categories ALTER COLUMN category_id SET DEFAULT nextval('public.archive_macro_categories_category_id_seq'::regclass);


--
-- Name: archive_ner_purge_log purge_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ner_purge_log ALTER COLUMN purge_id SET DEFAULT nextval('public.archive_ner_purge_log_purge_id_seq'::regclass);


--
-- Name: archive_stopword_purge_log purge_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_stopword_purge_log ALTER COLUMN purge_id SET DEFAULT nextval('public.archive_stopword_purge_log_purge_id_seq'::regclass);


--
-- Name: archive_tag_merge_proposals proposal_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tag_merge_proposals ALTER COLUMN proposal_id SET DEFAULT nextval('public.archive_tag_merge_proposals_proposal_id_seq'::regclass);


--
-- Name: archive_tags tag_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tags ALTER COLUMN tag_id SET DEFAULT nextval('public.archive_tags_tag_id_seq'::regclass);


--
-- Name: archive_taxonomy_merge_log merge_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy_merge_log ALTER COLUMN merge_id SET DEFAULT nextval('public.archive_taxonomy_merge_log_merge_id_seq'::regclass);


--
-- Name: archive_typologies typology_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_typologies ALTER COLUMN typology_id SET DEFAULT nextval('public.archive_typologies_typology_id_seq'::regclass);


--
-- Name: archive_worker_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runs ALTER COLUMN id SET DEFAULT nextval('public.archive_worker_runs_id_seq'::regclass);


--
-- Name: archive_worker_settings_revisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_settings_revisions ALTER COLUMN id SET DEFAULT nextval('public.archive_worker_settings_revisions_id_seq'::regclass);


--
-- Name: auth_sessions session_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions ALTER COLUMN session_id SET DEFAULT nextval('public.auth_sessions_session_id_seq'::regclass);


--
-- Name: auth_users user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_users ALTER COLUMN user_id SET DEFAULT nextval('public.auth_users_user_id_seq'::regclass);


--
-- Name: domain_ner_exclusions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_ner_exclusions ALTER COLUMN id SET DEFAULT nextval('public.domain_ner_exclusions_id_seq'::regclass);


--
-- Name: domain_stopwords id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_stopwords ALTER COLUMN id SET DEFAULT nextval('public.domain_stopwords_id_seq'::regclass);


--
-- Name: domain_subject_exclusions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_subject_exclusions ALTER COLUMN id SET DEFAULT nextval('public.domain_subject_exclusions_id_seq'::regclass);


--
-- Name: domain_synonyms id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_synonyms ALTER COLUMN id SET DEFAULT nextval('public.domain_synonyms_id_seq'::regclass);


--
-- Name: domain_text_templates template_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_text_templates ALTER COLUMN template_id SET DEFAULT nextval('public.domain_text_templates_template_id_seq'::regclass);


--
-- Name: raw_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_data ALTER COLUMN id SET DEFAULT nextval('public.raw_data_id_seq'::regclass);


--
-- Name: scraping_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraping_queue ALTER COLUMN id SET DEFAULT nextval('public.scraping_queue_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: archive_ai_review_queue archive_ai_review_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ai_review_queue
    ADD CONSTRAINT archive_ai_review_queue_pkey PRIMARY KEY (id);


--
-- Name: archive_api_errors archive_api_errors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_api_errors
    ADD CONSTRAINT archive_api_errors_pkey PRIMARY KEY (id);


--
-- Name: archive_arrangement_vocabulary archive_arrangement_vocabulary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_arrangement_vocabulary
    ADD CONSTRAINT archive_arrangement_vocabulary_pkey PRIMARY KEY (term_id);


--
-- Name: archive_cleaning_rules archive_cleaning_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_cleaning_rules
    ADD CONSTRAINT archive_cleaning_rules_pkey PRIMARY KEY (rule_id);


--
-- Name: archive_collection_terms archive_collection_terms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_collection_terms
    ADD CONSTRAINT archive_collection_terms_pkey PRIMARY KEY (term_id);


--
-- Name: archive_conflict_resolution_log archive_conflict_resolution_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_conflict_resolution_log
    ADD CONSTRAINT archive_conflict_resolution_log_pkey PRIMARY KEY (resolution_id);


--
-- Name: archive_description_levels archive_description_levels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_description_levels
    ADD CONSTRAINT archive_description_levels_pkey PRIMARY KEY (level_id);


--
-- Name: archive_document_deletions archive_document_deletions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_deletions
    ADD CONSTRAINT archive_document_deletions_pkey PRIMARY KEY (deletion_id);


--
-- Name: archive_document_entities archive_document_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_entities
    ADD CONSTRAINT archive_document_entities_pkey PRIMARY KEY (description_id, entity_id);


--
-- Name: archive_document_revisions archive_document_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_revisions
    ADD CONSTRAINT archive_document_revisions_pkey PRIMARY KEY (revision_id);


--
-- Name: archive_document_tags archive_document_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_tags
    ADD CONSTRAINT archive_document_tags_pkey PRIMARY KEY (description_id, tag_id);


--
-- Name: archive_documents archive_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_documents
    ADD CONSTRAINT archive_documents_pkey PRIMARY KEY (description_id);


--
-- Name: archive_entities archive_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entities
    ADD CONSTRAINT archive_entities_pkey PRIMARY KEY (entity_id);


--
-- Name: archive_entity_merge_log archive_entity_merge_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entity_merge_log
    ADD CONSTRAINT archive_entity_merge_log_pkey PRIMARY KEY (merge_id);


--
-- Name: archive_hierarchy_materialisation_log archive_hierarchy_materialisation_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_materialisation_log
    ADD CONSTRAINT archive_hierarchy_materialisation_log_pkey PRIMARY KEY (materialisation_id);


--
-- Name: archive_hierarchy_node_plans archive_hierarchy_node_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_node_plans
    ADD CONSTRAINT archive_hierarchy_node_plans_pkey PRIMARY KEY (plan_id);


--
-- Name: archive_macro_categories archive_macro_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_macro_categories
    ADD CONSTRAINT archive_macro_categories_pkey PRIMARY KEY (category_id);


--
-- Name: archive_ner_purge_log archive_ner_purge_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ner_purge_log
    ADD CONSTRAINT archive_ner_purge_log_pkey PRIMARY KEY (purge_id);


--
-- Name: archive_stopword_purge_log archive_stopword_purge_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_stopword_purge_log
    ADD CONSTRAINT archive_stopword_purge_log_pkey PRIMARY KEY (purge_id);


--
-- Name: archive_tag_merge_proposals archive_tag_merge_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tag_merge_proposals
    ADD CONSTRAINT archive_tag_merge_proposals_pkey PRIMARY KEY (proposal_id);


--
-- Name: archive_tags archive_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tags
    ADD CONSTRAINT archive_tags_pkey PRIMARY KEY (tag_id);


--
-- Name: archive_taxonomy_merge_log archive_taxonomy_merge_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy_merge_log
    ADD CONSTRAINT archive_taxonomy_merge_log_pkey PRIMARY KEY (merge_id);


--
-- Name: archive_typologies archive_typologies_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_typologies
    ADD CONSTRAINT archive_typologies_name_key UNIQUE (name);


--
-- Name: archive_typologies archive_typologies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_typologies
    ADD CONSTRAINT archive_typologies_pkey PRIMARY KEY (typology_id);


--
-- Name: archive_worker_runners archive_worker_runners_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runners
    ADD CONSTRAINT archive_worker_runners_pkey PRIMARY KEY (runner_id);


--
-- Name: archive_worker_runs archive_worker_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runs
    ADD CONSTRAINT archive_worker_runs_pkey PRIMARY KEY (id);


--
-- Name: archive_worker_schedules archive_worker_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_schedules
    ADD CONSTRAINT archive_worker_schedules_pkey PRIMARY KEY (worker_name);


--
-- Name: archive_worker_settings archive_worker_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_settings
    ADD CONSTRAINT archive_worker_settings_pkey PRIMARY KEY (worker_name);


--
-- Name: archive_worker_settings_revisions archive_worker_settings_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_settings_revisions
    ADD CONSTRAINT archive_worker_settings_revisions_pkey PRIMARY KEY (id);


--
-- Name: auth_sessions auth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: auth_sessions auth_sessions_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_token_hash_key UNIQUE (token_hash);


--
-- Name: auth_users auth_users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_users
    ADD CONSTRAINT auth_users_email_key UNIQUE (email);


--
-- Name: auth_users auth_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_users
    ADD CONSTRAINT auth_users_pkey PRIMARY KEY (user_id);


--
-- Name: domain_ner_exclusions domain_ner_exclusions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_ner_exclusions
    ADD CONSTRAINT domain_ner_exclusions_pkey PRIMARY KEY (id);


--
-- Name: domain_stopwords domain_stopwords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_stopwords
    ADD CONSTRAINT domain_stopwords_pkey PRIMARY KEY (id);


--
-- Name: domain_subject_exclusions domain_subject_exclusions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_subject_exclusions
    ADD CONSTRAINT domain_subject_exclusions_pkey PRIMARY KEY (id);


--
-- Name: domain_synonyms domain_synonyms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_synonyms
    ADD CONSTRAINT domain_synonyms_pkey PRIMARY KEY (id);


--
-- Name: domain_text_templates domain_text_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_text_templates
    ADD CONSTRAINT domain_text_templates_pkey PRIMARY KEY (template_id);


--
-- Name: ingestion_origins ingestion_origins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_origins
    ADD CONSTRAINT ingestion_origins_pkey PRIMARY KEY (code);


--
-- Name: raw_data raw_data_description_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_data
    ADD CONSTRAINT raw_data_description_id_key UNIQUE (description_id);


--
-- Name: raw_data raw_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_data
    ADD CONSTRAINT raw_data_pkey PRIMARY KEY (id);


--
-- Name: scraping_queue scraping_queue_description_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraping_queue
    ADD CONSTRAINT scraping_queue_description_id_key UNIQUE (description_id);


--
-- Name: scraping_queue scraping_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraping_queue
    ADD CONSTRAINT scraping_queue_pkey PRIMARY KEY (id);


--
-- Name: staging_documents staging_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.staging_documents
    ADD CONSTRAINT staging_documents_pkey PRIMARY KEY (description_id);


--
-- Name: domain_synonyms uix_synonym_category; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_synonyms
    ADD CONSTRAINT uix_synonym_category UNIQUE (synonym_name, category);


--
-- Name: archive_arrangement_vocabulary uq_archive_arrangement_vocabulary_token; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_arrangement_vocabulary
    ADD CONSTRAINT uq_archive_arrangement_vocabulary_token UNIQUE (token);


--
-- Name: archive_collection_terms uq_archive_collection_terms_term_kind; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_collection_terms
    ADD CONSTRAINT uq_archive_collection_terms_term_kind UNIQUE (term, kind);


--
-- Name: archive_description_levels uq_description_level_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_description_levels
    ADD CONSTRAINT uq_description_level_code UNIQUE (code);


--
-- Name: archive_description_levels uq_description_level_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_description_levels
    ADD CONSTRAINT uq_description_level_name UNIQUE (name);


--
-- Name: archive_description_levels uq_description_level_ordinal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_description_levels
    ADD CONSTRAINT uq_description_level_ordinal UNIQUE (ordinal);


--
-- Name: archive_hierarchy_node_plans uq_hierarchy_plan_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_node_plans
    ADD CONSTRAINT uq_hierarchy_plan_code UNIQUE (code);


--
-- Name: idx_archive_entities_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_archive_entities_name_trgm ON public.archive_entities USING gin (name public.gin_trgm_ops);


--
-- Name: idx_archive_tags_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_archive_tags_name_trgm ON public.archive_tags USING gin (name public.gin_trgm_ops);


--
-- Name: ix_api_error_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_fingerprint ON public.archive_api_errors USING btree (error_fingerprint);


--
-- Name: ix_api_error_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_error_occurred_at ON public.archive_api_errors USING btree (occurred_at);


--
-- Name: ix_archive_ai_review_queue_anomaly_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_ai_review_queue_anomaly_type ON public.archive_ai_review_queue USING btree (anomaly_type);


--
-- Name: ix_archive_ai_review_queue_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_ai_review_queue_status ON public.archive_ai_review_queue USING btree (status);


--
-- Name: ix_archive_cleaning_rules_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_cleaning_rules_is_active ON public.archive_cleaning_rules USING btree (is_active);


--
-- Name: ix_archive_cleaning_rules_rule_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_cleaning_rules_rule_kind ON public.archive_cleaning_rules USING btree (rule_kind);


--
-- Name: ix_archive_collection_terms_term; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_collection_terms_term ON public.archive_collection_terms USING btree (term);


--
-- Name: ix_archive_conflict_resolution_log_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_conflict_resolution_log_entity_id ON public.archive_conflict_resolution_log USING btree (entity_id);


--
-- Name: ix_archive_conflict_resolution_log_tag_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_conflict_resolution_log_tag_id ON public.archive_conflict_resolution_log USING btree (tag_id);


--
-- Name: ix_archive_conflict_resolution_log_winner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_conflict_resolution_log_winner ON public.archive_conflict_resolution_log USING btree (winner);


--
-- Name: ix_archive_document_deletions_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_document_deletions_deleted_at ON public.archive_document_deletions USING btree (deleted_at);


--
-- Name: ix_archive_document_deletions_description_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_document_deletions_description_id ON public.archive_document_deletions USING btree (description_id);


--
-- Name: ix_archive_document_revisions_description_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_document_revisions_description_id ON public.archive_document_revisions USING btree (description_id);


--
-- Name: ix_archive_documents_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_embedding ON public.archive_documents USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: ix_archive_documents_is_anomaly; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_is_anomaly ON public.archive_documents USING btree (is_anomaly);


--
-- Name: ix_archive_documents_is_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_is_published ON public.archive_documents USING btree (is_published);


--
-- Name: ix_archive_documents_level_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_level_id ON public.archive_documents USING btree (level_id);


--
-- Name: ix_archive_documents_origin_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_origin_code ON public.archive_documents USING btree (origin_code);


--
-- Name: ix_archive_documents_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_parent_id ON public.archive_documents USING btree (parent_id);


--
-- Name: ix_archive_documents_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_path ON public.archive_documents USING btree (path text_pattern_ops);


--
-- Name: ix_archive_documents_review_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_review_status ON public.archive_documents USING btree (review_status);


--
-- Name: ix_archive_documents_search_vector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_search_vector ON public.archive_documents USING gin (search_vector);


--
-- Name: ix_archive_documents_typology_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_documents_typology_id ON public.archive_documents USING btree (typology_id);


--
-- Name: ix_archive_entities_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_entities_entity_type ON public.archive_entities USING btree (entity_type);


--
-- Name: ix_archive_entities_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_archive_entities_name ON public.archive_entities USING btree (name);


--
-- Name: ix_archive_entity_merge_log_absorbed_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_entity_merge_log_absorbed_entity_id ON public.archive_entity_merge_log USING btree (absorbed_entity_id);


--
-- Name: ix_archive_entity_merge_log_canonical_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_entity_merge_log_canonical_id ON public.archive_entity_merge_log USING btree (canonical_id);


--
-- Name: ix_archive_exec_log; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_exec_log ON public.archive_documents USING gin (execution_log);


--
-- Name: ix_archive_hierarchy_node_plans_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_hierarchy_node_plans_code ON public.archive_hierarchy_node_plans USING btree (code);


--
-- Name: ix_archive_hierarchy_node_plans_level_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_hierarchy_node_plans_level_id ON public.archive_hierarchy_node_plans USING btree (level_id);


--
-- Name: ix_archive_hierarchy_node_plans_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_hierarchy_node_plans_status ON public.archive_hierarchy_node_plans USING btree (status);


--
-- Name: ix_archive_macro_categories_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_archive_macro_categories_name ON public.archive_macro_categories USING btree (name);


--
-- Name: ix_archive_ner_purge_log_excluded_term; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_ner_purge_log_excluded_term ON public.archive_ner_purge_log USING btree (excluded_term);


--
-- Name: ix_archive_ner_purge_log_purged_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_ner_purge_log_purged_entity_id ON public.archive_ner_purge_log USING btree (purged_entity_id);


--
-- Name: ix_archive_stopword_purge_log_purged_tag_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_stopword_purge_log_purged_tag_id ON public.archive_stopword_purge_log USING btree (purged_tag_id);


--
-- Name: ix_archive_tag_merge_proposals_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_archive_tag_merge_proposals_fingerprint ON public.archive_tag_merge_proposals USING btree (fingerprint);


--
-- Name: ix_archive_tag_merge_proposals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_tag_merge_proposals_status ON public.archive_tag_merge_proposals USING btree (status);


--
-- Name: ix_archive_tags_exec_log; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_tags_exec_log ON public.archive_tags USING gin (execution_log);


--
-- Name: ix_archive_tags_macro_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_tags_macro_category_id ON public.archive_tags USING btree (macro_category_id);


--
-- Name: ix_archive_tags_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_archive_tags_name ON public.archive_tags USING btree (name);


--
-- Name: ix_archive_taxonomy_merge_log_absorbed_tag_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_taxonomy_merge_log_absorbed_tag_id ON public.archive_taxonomy_merge_log USING btree (absorbed_tag_id);


--
-- Name: ix_archive_taxonomy_merge_log_canonical_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_taxonomy_merge_log_canonical_id ON public.archive_taxonomy_merge_log USING btree (canonical_id);


--
-- Name: ix_archive_taxonomy_merge_log_cluster_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_taxonomy_merge_log_cluster_fingerprint ON public.archive_taxonomy_merge_log USING btree (cluster_fingerprint);


--
-- Name: ix_archive_worker_runs_origin_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_worker_runs_origin_code ON public.archive_worker_runs USING btree (origin_code);


--
-- Name: ix_archive_worker_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_worker_runs_status ON public.archive_worker_runs USING btree (status);


--
-- Name: ix_archive_worker_runs_worker_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_worker_runs_worker_name ON public.archive_worker_runs USING btree (worker_name);


--
-- Name: ix_archive_worker_settings_revisions_worker_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_archive_worker_settings_revisions_worker_name ON public.archive_worker_settings_revisions USING btree (worker_name);


--
-- Name: ix_auth_sessions_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_expires_at ON public.auth_sessions USING btree (expires_at);


--
-- Name: ix_auth_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auth_sessions_user_id ON public.auth_sessions USING btree (user_id);


--
-- Name: ix_conflict_resolution_pair; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conflict_resolution_pair ON public.archive_conflict_resolution_log USING btree (tag_id, entity_id);


--
-- Name: ix_domain_ner_exclusions_tag_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_ner_exclusions_tag_id ON public.domain_ner_exclusions USING btree (tag_id);


--
-- Name: ix_domain_ner_exclusions_term; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_domain_ner_exclusions_term ON public.domain_ner_exclusions USING btree (term);


--
-- Name: ix_domain_stopwords_word; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_domain_stopwords_word ON public.domain_stopwords USING btree (word);


--
-- Name: ix_domain_stopwords_word_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_stopwords_word_scope ON public.domain_stopwords USING btree (word_scope);


--
-- Name: ix_domain_subject_exclusions_term; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_domain_subject_exclusions_term ON public.domain_subject_exclusions USING btree (term);


--
-- Name: ix_domain_synonyms_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_synonyms_category ON public.domain_synonyms USING btree (category);


--
-- Name: ix_domain_synonyms_synonym_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_synonyms_synonym_name ON public.domain_synonyms USING btree (synonym_name);


--
-- Name: ix_domain_text_templates_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_domain_text_templates_fingerprint ON public.domain_text_templates USING btree (fingerprint);


--
-- Name: ix_ingestion_origin_next_run_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_origin_next_run_at ON public.ingestion_origins USING btree (next_run_at);


--
-- Name: ix_raw_data_origin_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_raw_data_origin_code ON public.raw_data USING btree (origin_code);


--
-- Name: ix_raw_data_origin_description; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_raw_data_origin_description ON public.raw_data USING btree (origin_code, description_id);


--
-- Name: ix_scraping_queue_origin_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scraping_queue_origin_code ON public.scraping_queue USING btree (origin_code);


--
-- Name: ix_scraping_queue_origin_last_scraped; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scraping_queue_origin_last_scraped ON public.scraping_queue USING btree (origin_code, last_scraped_at);


--
-- Name: ix_staging_documents_origin_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staging_documents_origin_code ON public.staging_documents USING btree (origin_code);


--
-- Name: ix_worker_run_error_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_error_fingerprint ON public.archive_worker_runs USING btree (error_fingerprint);


--
-- Name: ix_worker_run_lease; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_lease ON public.archive_worker_runs USING btree (lease_expires_at) WHERE (status = 'RUNNING'::public.worker_run_status);


--
-- Name: ix_worker_run_queue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_queue ON public.archive_worker_runs USING btree (queued_at) WHERE (status = 'QUEUED'::public.worker_run_status);


--
-- Name: ix_worker_run_queued_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_queued_at ON public.archive_worker_runs USING btree (queued_at);


--
-- Name: ix_worker_run_retry_of; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_retry_of ON public.archive_worker_runs USING btree (retry_of);


--
-- Name: ix_worker_run_runner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_run_runner ON public.archive_worker_runs USING btree (runner_id) WHERE (status = 'RUNNING'::public.worker_run_status);


--
-- Name: ix_worker_runner_last_heartbeat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_runner_last_heartbeat ON public.archive_worker_runners USING btree (last_heartbeat_at);


--
-- Name: ix_worker_schedule_next_run_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_worker_schedule_next_run_at ON public.archive_worker_schedules USING btree (next_run_at);


--
-- Name: uix_archive_entities_name_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uix_archive_entities_name_normalized ON public.archive_entities USING btree (lower(btrim((name)::text)));


--
-- Name: uix_archive_tags_name_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uix_archive_tags_name_normalized ON public.archive_tags USING btree (lower(btrim((name)::text)));


--
-- Name: uq_worker_run_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_worker_run_active ON public.archive_worker_runs USING btree (worker_name, COALESCE(origin_code, ''::character varying)) WHERE (status = ANY (ARRAY['QUEUED'::public.worker_run_status, 'RUNNING'::public.worker_run_status]));


--
-- Name: archive_documents trg_update_archive_documents; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_update_archive_documents BEFORE UPDATE ON public.archive_documents FOR EACH ROW EXECUTE FUNCTION public.update_archive_documents_timestamp();


--
-- Name: archive_document_entities archive_document_entities_description_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_entities
    ADD CONSTRAINT archive_document_entities_description_id_fkey FOREIGN KEY (description_id) REFERENCES public.archive_documents(description_id) ON DELETE CASCADE;


--
-- Name: archive_document_entities archive_document_entities_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_entities
    ADD CONSTRAINT archive_document_entities_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.archive_entities(entity_id) ON DELETE CASCADE;


--
-- Name: archive_document_revisions archive_document_revisions_description_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_revisions
    ADD CONSTRAINT archive_document_revisions_description_id_fkey FOREIGN KEY (description_id) REFERENCES public.archive_documents(description_id) ON DELETE CASCADE;


--
-- Name: archive_document_tags archive_document_tags_description_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_tags
    ADD CONSTRAINT archive_document_tags_description_id_fkey FOREIGN KEY (description_id) REFERENCES public.archive_documents(description_id) ON DELETE CASCADE;


--
-- Name: archive_document_tags archive_document_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_tags
    ADD CONSTRAINT archive_document_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.archive_tags(tag_id) ON DELETE CASCADE;


--
-- Name: archive_documents archive_documents_typology_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_documents
    ADD CONSTRAINT archive_documents_typology_id_fkey FOREIGN KEY (typology_id) REFERENCES public.archive_typologies(typology_id) ON DELETE SET NULL;


--
-- Name: archive_hierarchy_node_plans archive_hierarchy_node_plans_level_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_node_plans
    ADD CONSTRAINT archive_hierarchy_node_plans_level_id_fkey FOREIGN KEY (level_id) REFERENCES public.archive_description_levels(level_id) ON DELETE SET NULL;


--
-- Name: archive_ner_purge_log archive_ner_purge_log_changed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ner_purge_log
    ADD CONSTRAINT archive_ner_purge_log_changed_by_user_id_fkey FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_ner_purge_log archive_ner_purge_log_undone_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_ner_purge_log
    ADD CONSTRAINT archive_ner_purge_log_undone_by_user_id_fkey FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_stopword_purge_log archive_stopword_purge_log_changed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_stopword_purge_log
    ADD CONSTRAINT archive_stopword_purge_log_changed_by_user_id_fkey FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_stopword_purge_log archive_stopword_purge_log_undone_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_stopword_purge_log
    ADD CONSTRAINT archive_stopword_purge_log_undone_by_user_id_fkey FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_tags archive_tags_macro_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tags
    ADD CONSTRAINT archive_tags_macro_category_id_fkey FOREIGN KEY (macro_category_id) REFERENCES public.archive_macro_categories(category_id) ON DELETE SET NULL;


--
-- Name: archive_worker_runs archive_worker_runs_retry_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runs
    ADD CONSTRAINT archive_worker_runs_retry_of_fkey FOREIGN KEY (retry_of) REFERENCES public.archive_worker_runs(id) ON DELETE SET NULL;


--
-- Name: archive_worker_schedules archive_worker_schedules_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_schedules
    ADD CONSTRAINT archive_worker_schedules_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: auth_sessions auth_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_sessions
    ADD CONSTRAINT auth_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.auth_users(user_id) ON DELETE CASCADE;


--
-- Name: domain_ner_exclusions domain_ner_exclusions_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_ner_exclusions
    ADD CONSTRAINT domain_ner_exclusions_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.archive_tags(tag_id) ON DELETE SET NULL;


--
-- Name: domain_synonyms domain_synonyms_canonical_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_synonyms
    ADD CONSTRAINT domain_synonyms_canonical_entity_id_fkey FOREIGN KEY (canonical_entity_id) REFERENCES public.archive_entities(entity_id) ON DELETE CASCADE;


--
-- Name: domain_synonyms domain_synonyms_canonical_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_synonyms
    ADD CONSTRAINT domain_synonyms_canonical_tag_id_fkey FOREIGN KEY (canonical_tag_id) REFERENCES public.archive_tags(tag_id) ON DELETE CASCADE;


--
-- Name: archive_cleaning_rules fk_archive_cleaning_rules_created_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_cleaning_rules
    ADD CONSTRAINT fk_archive_cleaning_rules_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_conflict_resolution_log fk_archive_conflict_resolution_log_decided_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_conflict_resolution_log
    ADD CONSTRAINT fk_archive_conflict_resolution_log_decided_by_user_id FOREIGN KEY (decided_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_conflict_resolution_log fk_archive_conflict_resolution_log_undone_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_conflict_resolution_log
    ADD CONSTRAINT fk_archive_conflict_resolution_log_undone_by_user_id FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_document_deletions fk_archive_document_deletions_deleted_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_deletions
    ADD CONSTRAINT fk_archive_document_deletions_deleted_by_user_id FOREIGN KEY (deleted_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_document_revisions fk_archive_document_revisions_changed_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_document_revisions
    ADD CONSTRAINT fk_archive_document_revisions_changed_by_user_id FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_documents fk_archive_documents_level_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_documents
    ADD CONSTRAINT fk_archive_documents_level_id FOREIGN KEY (level_id) REFERENCES public.archive_description_levels(level_id) ON DELETE SET NULL;


--
-- Name: archive_documents fk_archive_documents_parent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_documents
    ADD CONSTRAINT fk_archive_documents_parent_id FOREIGN KEY (parent_id) REFERENCES public.archive_documents(description_id) ON DELETE RESTRICT;


--
-- Name: archive_entity_merge_log fk_archive_entity_merge_log_changed_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entity_merge_log
    ADD CONSTRAINT fk_archive_entity_merge_log_changed_by_user_id FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_entity_merge_log fk_archive_entity_merge_log_undone_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_entity_merge_log
    ADD CONSTRAINT fk_archive_entity_merge_log_undone_by_user_id FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_hierarchy_materialisation_log fk_archive_hierarchy_materialisation_log_changed_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_materialisation_log
    ADD CONSTRAINT fk_archive_hierarchy_materialisation_log_changed_by_user_id FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_hierarchy_materialisation_log fk_archive_hierarchy_materialisation_log_undone_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_materialisation_log
    ADD CONSTRAINT fk_archive_hierarchy_materialisation_log_undone_by_user_id FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_hierarchy_node_plans fk_archive_hierarchy_node_plans_decided_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_hierarchy_node_plans
    ADD CONSTRAINT fk_archive_hierarchy_node_plans_decided_by_user_id FOREIGN KEY (decided_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_tag_merge_proposals fk_archive_tag_merge_proposals_decided_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_tag_merge_proposals
    ADD CONSTRAINT fk_archive_tag_merge_proposals_decided_by_user_id FOREIGN KEY (decided_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_taxonomy_merge_log fk_archive_taxonomy_merge_log_changed_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy_merge_log
    ADD CONSTRAINT fk_archive_taxonomy_merge_log_changed_by_user_id FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_taxonomy_merge_log fk_archive_taxonomy_merge_log_undone_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy_merge_log
    ADD CONSTRAINT fk_archive_taxonomy_merge_log_undone_by_user_id FOREIGN KEY (undone_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_worker_runs fk_archive_worker_runs_cancel_requested_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runs
    ADD CONSTRAINT fk_archive_worker_runs_cancel_requested_by_user_id FOREIGN KEY (cancel_requested_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_worker_runs fk_archive_worker_runs_requested_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_runs
    ADD CONSTRAINT fk_archive_worker_runs_requested_by_user_id FOREIGN KEY (requested_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: archive_worker_settings_revisions fk_archive_worker_settings_revisions_changed_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_worker_settings_revisions
    ADD CONSTRAINT fk_archive_worker_settings_revisions_changed_by_user_id FOREIGN KEY (changed_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: domain_text_templates fk_domain_text_templates_created_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_text_templates
    ADD CONSTRAINT fk_domain_text_templates_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: raw_data fk_raw_data_created_by_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_data
    ADD CONSTRAINT fk_raw_data_created_by_user_id FOREIGN KEY (created_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- Name: ingestion_origins ingestion_origins_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_origins
    ADD CONSTRAINT ingestion_origins_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public.auth_users(user_id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--


