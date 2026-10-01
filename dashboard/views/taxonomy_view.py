import pandas as pd
import streamlit as st

from dashboard.services.taxonomy_api import TaxonomyApiService

st.title("🏷️ Governança de Tags e Assuntos")
st.markdown(
    "Audite a relevância dos termos indexados, unifique sinônimos e gerencie as stopwords para otimização do acervo arquivístico."
)

aba_analise, aba_similaridade, aba_macro = st.tabs(
    ["📊 Análise de Relevância", "🔍 Unificação de Duplicatas", "🧠 Macro Categorização por IA"]
)

# ==========================================
# ABA 1: ANÁLISE DE RELEVÂNCIA
# ==========================================
with aba_analise:
    st.subheader("Métricas de Relevância de Assuntos")
    col1, col2 = st.columns([2, 1])
    with col1:
        metodo = st.radio(
            "Método de Análise Estatística:",
            ["TF-IDF (Recomendado)", "Frequência Simples"],
            horizontal=True,
            help="Selecione o motor matemático para ordenação dos assuntos principais.",
        )
    with col2:
        limite = st.slider(
            "Quantidade de Tags na Amostra:",
            10,
            500,
            30,
            help="Ajuste o tamanho do lote para visualização de relatórios.",
        )

    with st.spinner("Calculando métricas..."):
        df_relevancia = TaxonomyApiService.fetch_tag_relevance(metodo, limite)

        if not df_relevancia.empty:
            st.dataframe(df_relevancia, use_container_width=True, hide_index=True)
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
            lista_palavras = [w.strip() for w in stopwords_input.split(",") if w.strip()]

            with st.spinner("Processando exclusão relacional em background..."):
                sucesso, qtd_apagadas = TaxonomyApiService.purge_stopwords(lista_palavras)

                if sucesso:
                    st.success(
                        f"✅ Sucesso! Novas stopwords registradas e **{qtd_apagadas}** tags foram apagadas do acervo."
                    )

# ==========================================
# ABA 2: SIMILARIDADE (PRÉ-MERGE)
# ==========================================
with aba_similaridade:
    st.subheader("Consolidação Semântica")
    st.markdown("Remova variações ortográficas ou abreviações inconsistentes fundindo registros duplicados.")
    modo_busca = st.radio(
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
    # MODO 1: BUSCA ESPECÍFICA
    # ==========================================
    if modo_busca == "Buscar Termo Específico":
        st.markdown(
            "🔍 **Instruções:** 1. Busque o termo; 2. Selecione as caixas das tags duplicadas; 3. Eleja o termo correto no painel."
        )
        tag_alvo = st.text_input(
            "Investigar Palavra-Chave:",
            placeholder="Ex: prefeitura",
            help="Digite uma palavra para ver as suas variantes.",
        )

        if tag_alvo.strip():
            similares = TaxonomyApiService.find_similar_tags(tag_alvo, threshold)

            if similares:
                # O JSON da API já deve ter chaves claras, mapeamos para o DataFrame
                df_sim = pd.DataFrame(similares)
                df_sim = df_sim.rename(columns={"tag_id": "ID da Tag", "name": "Termo", "similarity": "Score"})

                st.markdown("### Selecione as tags para Merge:")
                evento = st.dataframe(
                    df_sim,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row",
                )

                linhas_selecionadas = evento.selection.rows  # type: ignore

                if len(linhas_selecionadas) >= 2:
                    st.divider()
                    st.markdown("### 👑 Eleger Termo Canônico")
                    st.info(
                        "O termo eleito abaixo permanecerá ativo. Os restantes serão desativados e os seus documentos transferidos"
                    )

                    df_selecionado = df_sim.iloc[linhas_selecionadas]
                    opcoes_dict = {row["ID da Tag"]: row["Termo"] for _, row in df_selecionado.iterrows()}

                    id_canonico = st.radio(
                        "Qual grafia padrão deve sobreviver?",
                        options=opcoes_dict.keys(),
                        format_func=lambda x: opcoes_dict[x],
                    )

                    ids_para_mesclar = [id_tag for id_tag in opcoes_dict if id_tag != id_canonico]
                    nomes_mesclados = [opcoes_dict[id_tag] for id_tag in ids_para_mesclar]

                    st.warning(
                        f"⚠️ **Confirmação:** Os assuntos **{', '.join(nomes_mesclados)}** serão permanentemente aglutinados dentro de **{opcoes_dict[id_canonico]}**."
                    )

                    if st.button("Executar Fusão de Tags", type="primary", use_container_width=True):
                        with st.spinner("Processando fusão no banco de dados..."):
                            sucesso = TaxonomyApiService.merge_tags(id_canonico, ids_para_mesclar)
                            if sucesso:
                                st.success("Tags unificadas com sucesso!")
                                st.rerun()

                elif len(linhas_selecionadas) == 1:
                    st.caption("💡 Selecione pelo menos **duas linhas** na tabela acima para abrir o painel de fusão.")
            else:
                st.info("Nenhuma variação fonética ou ortográfica localizada para este termo.")
    # ------------------------------------------------------------------
    # MODO 2: VARREDURA COMPLETA
    # ------------------------------------------------------------------
    else:
        if st.button("Executar Varredura", type="primary", use_container_width=True):
            st.session_state["pares_tags_encontrados"] = TaxonomyApiService.find_all_similar_pairs(threshold)

        if st.session_state.get("pares_tags_encontrados"):
            df_pares = pd.DataFrame(st.session_state["pares_tags_encontrados"])
            df_pares = df_pares.rename(
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

            evento_pares = st.dataframe(
                df_pares,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )

            linhas_selecionadas = evento_pares.selection.rows  # type: ignore

            if len(linhas_selecionadas) == 1:
                st.divider()
                linha = df_pares.iloc[linhas_selecionadas[0]]
                id1, termo1 = int(linha["ID 1"]), linha["Termo A"]
                id2, termo2 = int(linha["ID 2"]), linha["Termo B"]

                st.markdown(f"### 👑 Resolver Conflito: **{termo1}** vs **{termo2}**")

                opcoes_par = {id1: termo1, id2: termo2}
                id_canonico = st.radio(
                    "Qual termo deve ser preservado como oficial?",
                    options=opcoes_par.keys(),
                    format_func=lambda x: opcoes_par[x],
                    horizontal=True,
                )

                id_para_mesclar = id2 if id_canonico == id1 else id1
                termo_morto = opcoes_par[id_para_mesclar]
                termo_vivo = opcoes_par[id_canonico]

                st.warning(
                    f"⚠️ **Confirmação:** A tag **{termo_morto}** será removida e todos os seus vínculos passarão a apontar para **{termo_vivo}**."
                )

                if st.button("Fundir Par de Tags", type="primary", use_container_width=True):
                    with st.spinner("Salvando transação..."):
                        if TaxonomyApiService.merge_tags(id_canonico, [id_para_mesclar]):
                            st.success("Par de tags consolidado!")
                            del st.session_state["pares_tags_encontrados"]
                            st.rerun()

        elif "pares_tags_encontrados" in st.session_state:
            st.success("✨ Varredura concluída! Nenhuma anomalia de duplicidade localizada no limiar selecionado.")

# ======================================================================
# ABA 3: MACRO CATEGORIZAÇÃO POR IA
# ======================================================================
with aba_macro:
    st.subheader("Sugestão de Macro Categorias Semânticas (IA)")
    st.markdown(
        "Agrupe automaticamente assuntos pulverizados em clusters lógicos usando processamento de linguagem natural."
    )
    # Implementação futura do clustering semântico...
    st.info("Esta funcionalidade está aguardando o carregamento dos vetores de embeddings do acervo.")
