import pandas as pd
import streamlit as st

from dashboard.services.taxonomy_api import TaxonomyApiService

st.title("🧹 Gestão de Taxonomia e Limpeza")
st.markdown("Analise a relevância das tags, unifique termos e gerencie as stopwords do acervo.")

aba_analise, aba_similaridade, aba_limpeza = st.tabs(
    ["📊 Análise de Relevância", "🔍 Similaridade (Pré-Merge)", "🗑️ Limpeza de Stopwords"]
)

# ==========================================
# ABA 1: ANÁLISE DE RELEVÂNCIA
# ==========================================
with aba_analise:
    st.subheader("Análise de Tags")

    col1, col2 = st.columns([2, 1])
    with col1:
        metodo = st.radio("Método de Cálculo:", ["TF-IDF (Recomendado)", "Frequência Simples"], horizontal=True)
    with col2:
        limite = st.slider("Quantidade de tags para exibir:", 10, 100, 30)

    with st.spinner("Buscando métricas na API..."):
        df_relevancia = TaxonomyApiService.fetch_tag_relevance(metodo, limite)

        if not df_relevancia.empty:
            st.dataframe(df_relevancia, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma tag encontrada ou falha de comunicação.")

# ==========================================
# ABA 2: SIMILARIDADE (PRÉ-MERGE)
# ==========================================
with aba_similaridade:
    st.subheader("Análise de Similaridade e Mesclagem (Merge)")
    st.markdown("1. Busque por um termo. 2. Selecione as tags que deseja unificar. 3. Escolha a tag principal.")

    tag_alvo = st.text_input("Digite a tag que deseja investigar:", placeholder="Ex: prefeitura")
    threshold = st.slider("Limiar de Similaridade:", 0.1, 1.0, 0.4, step=0.05)

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
                st.info("O termo canônico será mantido. Os outros serão apagados e seus documentos transferidos.")

                df_selecionado = df_sim.iloc[linhas_selecionadas]
                opcoes_dict = {row["ID da Tag"]: row["Termo"] for _, row in df_selecionado.iterrows()}

                id_canonico = st.radio(
                    "Qual termo deve sobreviver?",
                    options=opcoes_dict.keys(),
                    format_func=lambda x: opcoes_dict[x],
                )

                ids_para_mesclar = [id_tag for id_tag in opcoes_dict if id_tag != id_canonico]
                nomes_mesclados = [opcoes_dict[id_tag] for id_tag in ids_para_mesclar]

                st.warning(
                    f"⚠️ Atenção: **{', '.join(nomes_mesclados)}** serão mesclados para dentro de **{opcoes_dict[id_canonico]}**."
                )

                if st.button("Unificar Tags", type="primary"):
                    with st.spinner("Enviando requisição para a API..."):
                        sucesso = TaxonomyApiService.merge_tags(id_canonico, ids_para_mesclar)
                        if sucesso:
                            st.success("Tags fundidas com sucesso!")
                            st.rerun()  # Recarrega a tela para limpar a tabela após o merge

            elif len(linhas_selecionadas) == 1:
                st.caption("Selecione pelo menos duas tags na tabela acima para habilitar a fusão.")

# ==========================================
# ABA 3: LIMPEZA E STOPWORDS
# ==========================================
with aba_limpeza:
    st.subheader("Remover Tags Inúteis")
    st.markdown("Digite as palavras que deseja banir do acervo.")

    stopwords_input = st.text_area("Stopwords (separadas por vírgula):", placeholder="Exemplo: foto, documento, cópia")

    if st.button("Limpar Tags e Salvar Stopwords", type="primary"):
        if not stopwords_input.strip():
            st.warning("Por favor, digite pelo menos uma palavra.")
        else:
            lista_palavras = [w.strip() for w in stopwords_input.split(",") if w.strip()]

            with st.spinner("Comunicando com a API..."):
                sucesso, qtd_apagadas = TaxonomyApiService.purge_stopwords(lista_palavras)

                if sucesso:
                    st.success(f"✅ Sucesso! Novas stopwords registradas e **{qtd_apagadas}** tags apagadas do acervo.")
