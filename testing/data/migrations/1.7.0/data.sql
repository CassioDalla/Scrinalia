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
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.alembic_version VALUES ('f4ac6a4c4d09');


--
-- Data for Name: archive_ai_review_queue; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_api_errors; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_arrangement_vocabulary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: auth_users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.auth_users VALUES (1, 'admin@example.org', 'Ada Curadora', 'fixture-not-a-real-hash', 'ADMIN', true, false, 0, NULL, NULL, '2026-10-29 13:50:31.791331+00', '2026-10-29 13:50:31.791331+00', 'pt-BR');
INSERT INTO public.auth_users VALUES (2, 'viewer@example.org', 'Bruno Consulta', 'fixture-not-a-real-hash', 'VIEWER', true, false, 0, NULL, NULL, '2026-10-29 13:50:31.791331+00', '2026-10-29 13:50:31.791331+00', 'en');


--
-- Data for Name: archive_cleaning_rules; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_collection_terms; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_conflict_resolution_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_description_levels; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_description_levels VALUES (1, 0, 'acervo', 'Acervo da entidade custodiadora', 'Conjunto documental sob a guarda de uma mesma entidade custodiadora. É a raiz da árvore.', '{Acervo,"Acervo da entidade"}', false, true, true, '2026-10-29 13:49:01.693069+00');
INSERT INTO public.archive_description_levels VALUES (2, 1, 'fundo', 'Fundo', 'Fundo ou coleção: o conjunto produzido por uma mesma instituição ou pessoa.', '{"Fundo ou coleção",Coleção,"Fundo ou colecao"}', false, true, true, '2026-10-29 13:49:01.693069+00');
INSERT INTO public.archive_description_levels VALUES (3, 2, 'secao', 'Seção', 'Divisão administrativa ou funcional do fundo.', '{Secao,Seccao}', false, true, true, '2026-10-29 13:49:01.693069+00');
INSERT INTO public.archive_description_levels VALUES (4, 3, 'serie', 'Série', 'Agrupamento de descrições por afinidade de função, atividade ou tipo documental.', '{Serie,Subsérie,Subserie}', false, true, true, '2026-10-29 13:49:01.693069+00');
INSERT INTO public.archive_description_levels VALUES (5, 4, 'dossie', 'Dossiê/Processo', 'Nível obrigatório da norma: o conjunto de documentos reunidos por um mesmo assunto ou processo.', '{"Dossiê ou processo",Dossiê,Dossie,Processo}', true, true, true, '2026-10-29 13:49:01.693069+00');
INSERT INTO public.archive_description_levels VALUES (6, 5, 'item', 'Item Documental', 'Unidade documental indivisível. Não admite filhos.', '{"Item documental",Item}', true, false, true, '2026-10-29 13:49:01.693069+00');


--
-- Data for Name: archive_document_deletions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_typologies; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_typologies VALUES (1, 'Planta Arquitetônica', 'Projetos de construção, aumento de área, projeto de muro, projeto de aumento, reformas, fachadas, alvarás de obras', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (2, 'Mapa / Croqui Urbanístico', 'Loteamentos, zoneamento, arruamento, cartografia, traçados de ruas e bairros', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (3, 'Fotografia', 'Registros fotográficos, negativos, ampliações, imagens de ruas, imagens de eventos, imagens de obras', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (4, 'Decreto / Lei / Portaria', 'Atos normativos, legislação municipal, diário oficial, regulamentações', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (5, 'Ofício / Memorando', 'Comunicação oficial interna ou externa entre secretarias, correspondências institucionais', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (6, 'Audiovisual', 'Fitas magnéticas, VHS, gravações de áudio, entrevistas, vídeos institucionais', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (7, 'Ata de Reunião', 'Registros de encontros, deliberações de conselhos, comitês ou assembleias', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (8, 'Relatório Técnico', 'Estudos de impacto, vistorias, laudos técnicos, balanços de gestão, diagnósticos', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (9, 'Processo Administrativo', 'Autos de infração, desapropriações, licitações, contratos públicos consolidados', '2026-10-29 13:49:01.693069+00', true);
INSERT INTO public.archive_typologies VALUES (10, 'Dossiê Funcional', 'Fichas de funcionários, histórico de servidores públicos, prontuários', '2026-10-29 13:49:01.693069+00', true);


--
-- Data for Name: archive_documents; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_documents VALUES ('fixture-fundo', 'Fundo Câmara Municipal', NULL, NULL, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Documentos da Câmara.', NULL, NULL, 'Câmara Municipal', '{}', NULL, 'PENDING_AI', false, NULL, '2026-10-29 13:50:31.792061+00', '2026-10-29 13:50:31.792061+00', DEFAULT, NULL, 2, NULL, 'fundo', NULL, false, 'csv', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.archive_documents VALUES ('fixture-serie', 'Série Atas', NULL, NULL, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Atas das sessões.', NULL, NULL, 'Atas da Câmara', '{"worker_ner_v2": {}}', NULL, 'HUMAN_APPROVED', false, NULL, '2026-10-29 13:50:31.792061+00', '2026-10-29 13:50:31.792061+00', DEFAULT, NULL, 4, 'fixture-fundo', 'fundo/serie', NULL, false, 'csv', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.archive_documents VALUES ('fixture-item', 'Item Ata 1890', NULL, NULL, 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'Ata manuscrita.', NULL, NULL, 'Ata de 1890', '{}', NULL, 'NEEDS_REVIEW', true, NULL, '2026-10-29 13:50:31.792061+00', '2026-10-29 13:50:31.792061+00', DEFAULT, NULL, 6, 'fixture-serie', 'fundo/serie/item', NULL, false, 'csv', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: archive_entities; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_entities VALUES (1, 'Câmara Municipal de São Paulo', 'ORGANIZATION', '2026-10-29 13:50:31.796624+00');


--
-- Data for Name: archive_document_entities; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_document_entities VALUES ('fixture-item', 1, 'HUMAN', NULL);


--
-- Data for Name: archive_document_revisions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_macro_categories; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_macro_categories VALUES (1, 'Urbanismo e Arquitetura', 'Construção, materiais, tipologia construtiva e desenho urbano.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (2, 'Mobilidade e Transporte', 'Circulação, ferrovia, veículos e transporte público.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (3, 'Religião', 'Edifícios, instituições e práticas religiosas.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (4, 'Meio Ambiente e Áreas Verdes', 'Parques, rios, vegetação e ecologia.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (5, 'Economia e Comércio', 'Comércio, serviços, indústria e abastecimento.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (6, 'Educação e Cultura', 'Escolas, museus, eventos, esporte e produção cultural.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (7, 'Patrimônio e Preservação', 'Tombamento e o patrimônio construído como política pública.', true, '2026-10-29 13:49:01.600329+00', NULL);
INSERT INTO public.archive_macro_categories VALUES (8, 'Assistência e Questões Sociais', 'População, vulnerabilidade, trabalho e ação social.', true, '2026-10-29 13:49:01.600329+00', NULL);


--
-- Data for Name: archive_tags; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_tags VALUES (1, 'Saúde', 1, NULL, '2026-10-29 13:50:31.79562+00', NULL);
INSERT INTO public.archive_tags VALUES (2, 'Educação', 2, NULL, '2026-10-29 13:50:31.79562+00', NULL);
INSERT INTO public.archive_tags VALUES (3, 'Urbanismo', NULL, NULL, '2026-10-29 13:50:31.79562+00', NULL);


--
-- Data for Name: archive_document_tags; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_document_tags VALUES ('fixture-fundo', 1);
INSERT INTO public.archive_document_tags VALUES ('fixture-item', 2);


--
-- Data for Name: archive_entity_merge_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_hierarchy_materialisation_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_hierarchy_node_plans; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_ner_purge_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_stopword_purge_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_tag_merge_proposals; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_taxonomy_merge_log; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_worker_runners; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_worker_runs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.archive_worker_runs VALUES (1, 'ner', 'SUCCESS', 'API', 'Ada Curadora', 'spacy', 'default', '{}', '2026-10-29 13:50:31.797822+00', NULL, NULL, NULL, NULL, DEFAULT, 1, '{}', '{}', NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL, false, NULL);


--
-- Data for Name: archive_worker_schedules; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_worker_settings; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: archive_worker_settings_revisions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: auth_sessions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: domain_ner_exclusions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: domain_stopwords; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: domain_subject_exclusions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: domain_synonyms; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: domain_text_templates; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: ingestion_origins; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.ingestion_origins VALUES ('manual', true, '{}', '{}', NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-10-29 13:49:01.798834+00', '2026-10-29 13:49:01.798834+00');
INSERT INTO public.ingestion_origins VALUES ('csv', true, '{}', '{}', NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-10-29 13:49:01.798834+00', '2026-10-29 13:49:01.798834+00');


--
-- Data for Name: raw_data; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.raw_data VALUES (1, 'fixture-item', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'Ata 1890', '{"title": "Ata 1890"}', '2026-10-29 13:50:31.797145+00', '2026-10-29 13:50:31.797145+00', 'csv', 'Ada Curadora', 1);


--
-- Data for Name: scraping_queue; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.scraping_queue VALUES (1, 'fixture-item', 'DONE', '2026-10-29 13:50:31.797615+00', NULL, 0, NULL, 'csv');


--
-- Data for Name: staging_documents; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.staging_documents VALUES ('fixture-item', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'Ata de 1890', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{}', '2026-10-29 13:50:31.797434+00', '2026-10-29 13:50:31.797434+00', NULL, NULL, 'csv', NULL);


--
-- Name: archive_ai_review_queue_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_ai_review_queue_id_seq', 1, false);


--
-- Name: archive_api_errors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_api_errors_id_seq', 1, false);


--
-- Name: archive_arrangement_vocabulary_term_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_arrangement_vocabulary_term_id_seq', 1, false);


--
-- Name: archive_cleaning_rules_rule_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_cleaning_rules_rule_id_seq', 1, false);


--
-- Name: archive_collection_terms_term_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_collection_terms_term_id_seq', 1, false);


--
-- Name: archive_conflict_resolution_log_resolution_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_conflict_resolution_log_resolution_id_seq', 1, false);


--
-- Name: archive_description_levels_level_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_description_levels_level_id_seq', 6, true);


--
-- Name: archive_document_deletions_deletion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_document_deletions_deletion_id_seq', 1, false);


--
-- Name: archive_document_revisions_revision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_document_revisions_revision_id_seq', 1, false);


--
-- Name: archive_entities_entity_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_entities_entity_id_seq', 1, false);


--
-- Name: archive_entity_merge_log_merge_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_entity_merge_log_merge_id_seq', 1, false);


--
-- Name: archive_hierarchy_materialisation_log_materialisation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_hierarchy_materialisation_log_materialisation_id_seq', 1, false);


--
-- Name: archive_hierarchy_node_plans_plan_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_hierarchy_node_plans_plan_id_seq', 1, false);


--
-- Name: archive_macro_categories_category_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_macro_categories_category_id_seq', 8, true);


--
-- Name: archive_ner_purge_log_purge_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_ner_purge_log_purge_id_seq', 1, false);


--
-- Name: archive_stopword_purge_log_purge_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_stopword_purge_log_purge_id_seq', 1, false);


--
-- Name: archive_tag_merge_proposals_proposal_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_tag_merge_proposals_proposal_id_seq', 1, false);


--
-- Name: archive_tags_tag_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_tags_tag_id_seq', 1, false);


--
-- Name: archive_taxonomy_merge_log_merge_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_taxonomy_merge_log_merge_id_seq', 1, false);


--
-- Name: archive_typologies_typology_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_typologies_typology_id_seq', 10, true);


--
-- Name: archive_worker_runs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_worker_runs_id_seq', 1, false);


--
-- Name: archive_worker_settings_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.archive_worker_settings_revisions_id_seq', 1, false);


--
-- Name: auth_sessions_session_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_sessions_session_id_seq', 1, false);


--
-- Name: auth_users_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_users_user_id_seq', 1, false);


--
-- Name: domain_ner_exclusions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.domain_ner_exclusions_id_seq', 1, false);


--
-- Name: domain_stopwords_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.domain_stopwords_id_seq', 1, false);


--
-- Name: domain_subject_exclusions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.domain_subject_exclusions_id_seq', 1, false);


--
-- Name: domain_synonyms_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.domain_synonyms_id_seq', 1, false);


--
-- Name: domain_text_templates_template_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.domain_text_templates_template_id_seq', 1, false);


--
-- Name: raw_data_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.raw_data_id_seq', 1, false);


--
-- Name: scraping_queue_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.scraping_queue_id_seq', 1, false);


--
-- PostgreSQL database dump complete
--


