import pandas as pd
import streamlit as st

from dashboard.services.taxonomy_api import TaxonomyApiService

st.title("🏷️ Governança de Tags e Assuntos")
st.markdown(
    "Audite a relevância dos termos indexados, unifique sinônimos e gerencie as stopwords para otimização do acervo arquivístico."
)

analysis_tab, similarity_tab, macro_tab = st.tabs(
    ["📊 Análise de Relevância", "🔍 Unificação de Duplicatas", "🧠 Macro Categorização por IA"]
)

# ==========================================
# TAB 1: RELEVANCE ANALYSIS
# ==========================================
with analysis_tab:
    st.subheader("Métricas de Relevância de Assuntos")
    col1, col2 = st.columns([2, 1])
    with col1:
        method = st.radio(
            "Método de Análise Estatística:",
            ["TF-IDF (Recomendado)", "Frequência Simples"],
            horizontal=True,
            help="Selecione o motor matemático para ordenação dos assuntos principais.",
        )
    with col2:
        limit = st.slider(
            "Quantidade de Tags na Amostra:",
            10,
            500,
            30,
            help="Ajuste o tamanho do lote para visualização de relatórios.",
        )

    with st.spinner("Calculando métricas..."):
        relevance_df = TaxonomyApiService.fetch_tag_relevance(method, limit)

        if not relevance_df.empty:
            st.dataframe(relevance_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma tag localizada para os parâmetros informados.")

    st.subheader("🧹 Limpeza Sistemática de Ruídos (Stopwords)")
    with st.popover("❔ O que são Stopwords de Assunto?"):
        st.markdown("""
        São termos genéricos, jargões documentais ou ruídos de digitação (ex: *foto*, *ofício*, *página*, *cópia*)
        que não agregam valor histórico ou semântico à indexação.

        Ao registrar uma palavra como stopword, o sistema **exclui** essa tag de todos os documentos atuais e
        instrui os próximos Workers a ignorarem este termo para sempre.
        """)

    stopwords_input = st.text_area(
        "Digitar Stopwords para Exclusão (Separadas por vírgula):",
        placeholder="Exemplo: documento, folha, rasgado, xerox",
    )

    if st.button("Executar Exclusão de Tags e Salvar Stopwords", type="primary", use_container_width=True):
        if not stopwords_input.strip():
            st.warning("Por favor, informe ao menos uma palavra para prosseguir com a exclusão.")
        else:
            word_list = [w.strip() for w in stopwords_input.split(",") if w.strip()]

            with st.spinner("Processando exclusão relacional em background..."):
                success, deleted_count = TaxonomyApiService.purge_stopwords(word_list)

                if success:
                    st.success(
                        f"✅ Sucesso! Novas stopwords registradas e **{deleted_count}** tags foram apagadas do acervo."
                    )

# ==========================================
# TAB 2: SIMILARITY (PRE-MERGE)
# ==========================================
with similarity_tab:
    st.subheader("Consolidação Semântica")
    st.markdown("Remova variações ortográficas ou abreviações inconsistentes fundindo registros duplicados.")
    search_mode = st.radio(
        "Estratégia de Captura de Erros:",
        ["Varrer Banco em Busca de Duplicatas (Pares)", "Buscar Termo Específico"],
        horizontal=True,
        help="Escolha entre investigar o acervo completo de forma automatizada ou focar em uma palavra suspeita.",
    )
    threshold = st.slider(
        "Tolerância de Similaridade (Métrica Levenshtein):",
        0.1,
        1.0,
        0.4,
        step=0.05,
        help="Valores baixos encontram termos mais distantes (ex: obras e cobras). Valores altos exigem grafia muito próxima.",
    )

    # ==========================================
    # MODE 1: SPECIFIC SEARCH
    # ==========================================
    if search_mode == "Buscar Termo Específico":
        st.markdown(
            "🔍 **Instruções:** 1. Busque o termo; 2. Selecione as caixas das tags duplicadas; 3. Eleja o termo correto no painel."
        )
        target_tag = st.text_input(
            "Investigar Palavra-Chave:",
            placeholder="Ex: prefeitura",
            help="Digite uma palavra para ver as suas variantes.",
        )

        if target_tag.strip():
            similar_tags = TaxonomyApiService.find_similar_tags(target_tag, threshold)

            if similar_tags:
                # The API JSON should already have clear keys, we map it to the DataFrame
                df_sim = pd.DataFrame(similar_tags)
                df_sim = df_sim.rename(columns={"tag_id": "ID da Tag", "name": "Termo", "similarity": "Score"})

                st.markdown("### Selecione as tags para Merge:")
                event = st.dataframe(
                    df_sim,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row",
                )

                selected_rows = event.selection.rows  # type: ignore

                if len(selected_rows) >= 2:
                    st.divider()
                    st.markdown("### 👑 Eleger Termo Canônico")
                    st.info(
                        "O termo eleito abaixo permanecerá ativo. Os restantes serão desativados e os seus documentos transferidos"
                    )

                    selected_df = df_sim.iloc[selected_rows]
                    options_dict = {row["ID da Tag"]: row["Termo"] for _, row in selected_df.iterrows()}

                    canonical_id = st.radio(
                        "Qual grafia padrão deve sobreviver?",
                        options=options_dict.keys(),
                        format_func=lambda x: options_dict[x],
                    )

                    ids_to_merge = [id_tag for id_tag in options_dict if id_tag != canonical_id]
                    merged_names = [options_dict[id_tag] for id_tag in ids_to_merge]

                    st.warning(
                        f"⚠️ **Confirmação:** Os assuntos **{', '.join(merged_names)}** serão permanentemente aglutinados dentro de **{options_dict[canonical_id]}**."
                    )

                    if st.button("Executar Fusão de Tags", type="primary", use_container_width=True):
                        with st.spinner("Processando fusão no banco de dados..."):
                            success = TaxonomyApiService.merge_tags(canonical_id, ids_to_merge)
                            if success:
                                st.success("Tags unificadas com sucesso!")
                                st.rerun()

                elif len(selected_rows) == 1:
                    st.caption("💡 Selecione pelo menos **duas linhas** na tabela acima para abrir o painel de fusão.")
            else:
                st.info("Nenhuma variação fonética ou ortográfica localizada para este termo.")
    # ------------------------------------------------------------------
    # MODE 2: FULL SCAN
    # ------------------------------------------------------------------
    else:
        if st.button("Executar Varredura", type="primary", use_container_width=True):
            st.session_state["tag_pairs_found"] = TaxonomyApiService.find_all_similar_pairs(threshold)

        if st.session_state.get("tag_pairs_found"):
            pairs_df = pd.DataFrame(st.session_state["tag_pairs_found"])
            pairs_df = pairs_df.rename(
                columns={
                    "id_1": "ID 1",
                    "name_1": "Termo A",
                    "id_2": "ID 2",
                    "name_2": "Termo B",
                    "sim_score": "Proximidade",
                }
            )

            st.markdown("### Conflitos Identificados na Base de Dados")
            st.caption("Clique em uma linha para abrir o painel de resolução imediata.")

            pairs_event = st.dataframe(
                pairs_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )

            selected_rows = pairs_event.selection.rows  # type: ignore

            if len(selected_rows) == 1:
                st.divider()
                row = pairs_df.iloc[selected_rows[0]]
                id1, term1 = int(row["ID 1"]), row["Termo A"]
                id2, term2 = int(row["ID 2"]), row["Termo B"]

                st.markdown(f"### 👑 Resolver Conflito: **{term1}** vs **{term2}**")

                pair_options = {id1: term1, id2: term2}
                canonical_id = st.radio(
                    "Qual termo deve ser preservado como oficial?",
                    options=pair_options.keys(),
                    format_func=lambda x: pair_options[x],
                    horizontal=True,
                )

                id_to_merge = id2 if canonical_id == id1 else id1
                dead_term = pair_options[id_to_merge]
                live_term = pair_options[canonical_id]

                st.warning(
                    f"⚠️ **Confirmação:** A tag **{dead_term}** será removida e todos os seus vínculos passarão a apontar para **{live_term}**."
                )

                if st.button("Fundir Par de Tags", type="primary", use_container_width=True):
                    with st.spinner("Salvando transação..."):
                        if TaxonomyApiService.merge_tags(canonical_id, [id_to_merge]):
                            st.success("Par de tags consolidado!")
                            del st.session_state["tag_pairs_found"]
                            st.rerun()

        elif "tag_pairs_found" in st.session_state:
            st.success("✨ Varredura concluída! Nenhuma anomalia de duplicidade localizada no limiar selecionado.")

# ======================================================================
# TAB 3: MACRO CATEGORIZATION BY AI
# ======================================================================
with macro_tab:
    st.subheader("Sugestão de Macro Categorias Semânticas (IA)")
    st.markdown(
        "Agrupe automaticamente assuntos pulverizados em clusters lógicos usando processamento de linguagem natural."
    )
    # Future implementation of semantic clustering...
    st.info("Esta funcionalidade está aguardando o carregamento dos vetores de embeddings do acervo.")
