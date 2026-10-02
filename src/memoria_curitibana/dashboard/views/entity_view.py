from typing import Literal, cast

import pandas as pd
import streamlit as st

from memoria_curitibana.dashboard.services.entity_service import StreamlitEntityService as service


## =========================================================================
##                 REUSABLE VIEW COMPONENTS
## =========================================================================
def render_bulk_ban_panel(selected_df: pd.DataFrame, key_prefix: str):
    """
    Component for Batch Actions (>1 selected row):
    Bans multiple entities at once.
    """
    st.divider()
    st.markdown("### 🚫 Banimento em Massa (Lista Negra)")

    target_names = selected_df["Nome da Entidade"].tolist()

    st.warning(
        f"⚠️ **Atenção:** Você selecionou **{len(target_names)} entidades** para banimento. Elas serão excluídas e o Worker será bloqueado de gerá-las novamente."
    )

    with st.expander("Ver lista de entidades que serão banidas"):
        st.write(", ".join(target_names))

    if st.button(
        "🚫 Banir Todas as Entidades Selecionadas",
        type="primary",
        use_container_width=True,
        key=f"btn_ban_lote_{key_prefix}",
    ):
        with st.spinner("Adicionando à lista negra e expurgando do banco..."):
            res = service.purge_stopwords([name.lower() for name in target_names])
            if "error" in res:
                st.error(res["error"])
            else:
                deleted_count = res.get("entities_deleted", 0)
                st.success(
                    f"🎉 {len(target_names)} palavras banidas com sucesso! {deleted_count} registros deletados do acervo."
                )
                st.rerun()


def render_individual_panel(selected_df: pd.DataFrame, key_prefix: str):
    """
    Reusable component for the Individual Actions panel (Reclassify and Delete).
    """
    st.divider()
    st.markdown("### 🛠️ Ações Individuais")
    st.write("Ajuste a classificação ou exclua pontualmente este registro.")

    target_id = int(selected_df.iloc[0]["ID"])
    target_name = selected_df.iloc[0]["Nome da Entidade"]
    current_type = selected_df.iloc[0]["Tipo"]

    col_reclass, col_delete, col_ban = st.columns(3)

    with col_reclass:
        st.markdown(f"**Reclassificar: {target_name}**")
        new_type = st.selectbox(
            "Nova Categoria",
            ["PER", "LOC", "ORG"],
            index=["PER", "LOC", "ORG"].index(current_type) if current_type in ["PER", "LOC", "ORG"] else 0,
            key=f"reclass_{key_prefix}_{target_id}",
        )
        if st.button(
            "Atualizar Categoria", type="primary", use_container_width=True, key=f"btn_reclass_{key_prefix}_{target_id}"
        ):
            if new_type == current_type:
                st.warning("A entidade já possui esta categoria.")
            else:
                with st.spinner("Atualizando banco e gerando sinônimos..."):
                    new_type = cast(Literal["PER", "ORG", "LOC"], new_type)
                    res = service.reclassify_entity(target_id, new_type)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success(f"Categoria alterada para {new_type}!")
                        st.rerun()

    with col_delete:
        st.markdown("**Exclusão**")
        st.caption("Remove apenas este ID específico.")
        if st.button(
            "🗑️ Excluir Entidade", type="secondary", use_container_width=True, key=f"btn_del_{key_prefix}_{target_id}"
        ):
            with st.spinner("Excluindo registro..."):
                res = service.delete_entity(target_id)
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.success("Entidade excluída com sucesso!")
                    st.rerun()

    with col_ban:
        st.markdown("**Adicionar à Lista Negra**")
        st.caption("Deleta a palavra do acervo e bloqueia a IA no futuro de classificá-la novamente.")
        if st.button(
            "🚫 Banir Palavra", type="secondary", use_container_width=True, key=f"btn_ban_{key_prefix}_{target_id}"
        ):
            with st.spinner(f"Banindo '{target_name}' e expurgando banco..."):
                res = service.purge_stopwords([target_name.lower()])
                if "error" in res:
                    st.error(res["error"])
                else:
                    deleted_count = res.get("entities_deleted", 1)
                    st.success(f"Palavra banida! {deleted_count} registros deletados.")
                    st.rerun()


st.title("🗂️ Governança de Entidades Nomeadas")

st.markdown(
    "Audite, higienize e consolide Pessoas (PER), Locais (LOC) e Organizações (ORG) extraídas de forma automática pelo Worker NER."
)

# 1. GLOBAL INSTRUCTIONS HUB
with st.expander("💡 Central de Instruções: Como funciona a governança de Entidades?", expanded=False):
    st.markdown("""
    ### 🎯 O que são Entidades Nomeadas?
    São os núcleos de informação histórica identificados pelas nossas redes neurais de NLP nas colunas textuais do acervo:
    * **PER (Pessoas):** Nomes de prefeitos, engenheiros, requerentes históricos (ex: *David Carneiro*).
    * **LOC (Locais):** Ruas, praças, glebas e monumentos da cidade de Curitiba (ex: *Rua XV de Novembro*).
    * **ORG (Organizações):** Secretarias municipais, corporações, irmandades ou cartórios (ex: *Companhia Força e Luz*).

    ### 🔗 Como funciona o Estúdio de Desambiguação (Merge)?
    Variações na escrita manual antiga geram fragmentação de chaves (ex: *David Carneiro*, *Davd Carneiro*, e *Dr. David Carneiro*).
    Ao unificar os registros diretamente clicando nas tabelas, o sistema executa três passos na mesma transação:
    1. **Transferência Relacional:** Associa os documentos vinculados aos IDs secundários diretamente ao ID correto.
    2. **Catálogo de Sinônimos:** Preserva as grafias erradas como sinônimos da entidade principal para proteger pesquisas futuras no front-end.
    3. **Expurgo Seguro:** Deleta de forma limpa as linhas duplicadas para sanear os índices do banco de dados.
    """)

# 2. TAB DEFINITIONS
relevance_tab, merge_tab, maintenance_tab = st.tabs(
    ["📊 Análise de Frequência", "🔗 Unificação & Duplicatas", "🧹 Manutenção e Limpeza"]
)

# Initialize the Merge Cart in the Streamlit session
if "merge_cart_entities" not in st.session_state:
    st.session_state["merge_cart_entities"] = {}

# ======================================================================
# TAB 1: FREQUENCY ANALYSIS
# ======================================================================
with relevance_tab:
    st.subheader("Entidades Mais Citadas na Base Documental")

    filter_col, limit_col = st.columns(2)
    with filter_col:
        type_filter = st.selectbox(
            "Filtrar por Categoria NER:",
            ["TODAS", "PER", "LOC", "ORG"],
            help="Selecione um grupo específico para refinar a auditoria visual.",
        )
    with limit_col:
        limit = st.slider("Amostra de Exibição:", 10, 500, 30, help="Ajuste a escala do relatório tabular abaixo.")

    relevance_data = service.get_relevance(entity_type=type_filter, limit=limit)

    if relevance_data:
        df_relevance = pd.DataFrame(relevance_data)
        df_relevance.columns = ["ID", "Nome da Entidade", "Tipo", "Total de Ocorrências no Acervo"]
        event = st.dataframe(
            df_relevance, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row"
        )

        selected_rows = event.selection.rows  # type: ignore

        if len(selected_rows) > 0:
            selected_df = df_relevance.iloc[selected_rows]

            # Shortcut: Add to the cart directly from the frequency tab
            if st.button("🛒 Enviar selecionadas ao Cesto de Mesclagem (Aba 2)", type="primary"):
                for _, row in selected_df.iterrows():
                    st.session_state["merge_cart_entities"][row["ID"]] = {
                        "ID": row["ID"],
                        "Nome da Entidade": row["Nome da Entidade"],
                        "Tipo": row["Tipo"],
                    }
                st.success(f"{len(selected_rows)} entidades enviadas ao carrinho!")

        if len(selected_rows) == 1:
            render_individual_panel(df_relevance.iloc[selected_rows], key_prefix="aba_freq")
        elif len(selected_rows) >= 2:
            render_bulk_ban_panel(df_relevance.iloc[selected_rows], key_prefix="freq")

    else:
        st.info("Nenhum registro localizado para os filtros informados.")


# ======================================================================
# TAB 2: UNIFICATION & DUPLICATES (INTERACTIVE MERGE)
# ======================================================================
with merge_tab:
    st.subheader("Estúdio de Desambiguação de Termos")
    st.markdown("Utilize a inteligência computacional ou faça varreduras fonéticas direcionadas.")

    search_mode = st.radio(
        "Estratégia de Identificação de Conflitos:",
        ["Varrer Banco em Busca de Duplicatas (Pares)", "Buscar Termo Específico"],
        horizontal=True,
    )

    threshold = st.slider(
        "Limiar de Similaridade Textual (Métrica Levenshtein):",
        0.2,
        1.0,
        0.65,
        step=0.05,
        help="Proximidade ortográfica entre as palavras. 1.0 indica escrita idêntica.",
    )

    # ------------------------------------------------------------------
    # FLOW A: SPECIFIC SEARCH (Multi-Row Selection)
    # ------------------------------------------------------------------
    if search_mode == "Buscar Termo Específico":
        st.markdown(
            "🔍 **Instruções:** 1. Busque a entidade; 2. Selecione as caixas das linhas duplicadas; 3. Eleja o nome correto."
        )
        search_term = st.text_input(
            "Investigar Nome da Entidade:",
            placeholder="Ex: Marechal Deodoro",
            help="Busque variações",
        )

        if search_term:
            similar_tags = service.find_similar(target_name=search_term, threshold=threshold)
            if similar_tags:
                df_sim = pd.DataFrame(similar_tags)
                # Ensuring friendly column names
                df_sim = df_sim.rename(
                    columns={
                        "entity_id": "ID",
                        "name": "Nome da Entidade",
                        "entity_type": "Tipo",
                        "similarity": "Score",
                    }
                )

                event = st.dataframe(
                    df_sim,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="multi-row",
                )

                selected_rows = event.selection.rows  # type: ignore

                if len(selected_rows) > 0:
                    selected_df = df_sim.iloc[selected_rows]

                    st.markdown("---")
                    if st.button("🛒 Adicionar Selecionadas ao Cesto", type="primary", use_container_width=True):
                        for _, row in selected_df.iterrows():
                            st.session_state["merge_cart_entities"][row["ID"]] = {
                                "ID": row["ID"],
                                "Nome da Entidade": row["Nome da Entidade"],
                                "Tipo": row["Tipo"],
                            }
                        st.success(f"Adicionadas {len(selected_rows)} entidades ao carrinho!")
                        st.rerun()

                    # Keep the quick surgical actions
                    if len(selected_rows) == 1:
                        render_individual_panel(selected_df, key_prefix="merge")
                    else:
                        render_bulk_ban_panel(selected_df, key_prefix="merge_busca")
            else:
                st.info("Nenhuma entidade semelhante foi localizada.")

        # --- THE MERGE CART ---
        st.divider()
        st.markdown("### 🛒 Cesto de Mesclagem")

        if not st.session_state["merge_cart_entities"]:
            st.info("O cesto está vazio. Busque e adicione entidades acima para consolidá-las.")
        else:
            cart_df = pd.DataFrame(list(st.session_state["merge_cart_entities"].values()))

            col_cart1, col_cart2 = st.columns([4, 1])
            with col_cart1:
                st.dataframe(cart_df, use_container_width=True, hide_index=True)
            with col_cart2:
                if st.button("🗑️ Limpar Carrinho", use_container_width=True):
                    st.session_state["merge_cart_entities"] = {}
                    st.rerun()

            if len(cart_df) >= 1:
                st.markdown("#### 👑 Eleger Termo Oficial e Renomear")
                st.info("A entidade eleita vai herdar os documentos de todas as outras do cesto.")

                options_dict = {row["ID"]: row["Nome da Entidade"] for _, row in cart_df.iterrows()}

                canonical_id = st.radio(
                    "Qual registro representa a âncora principal (ID que vai sobreviver)?",
                    options=options_dict.keys(),
                    format_func=lambda x: options_dict[x],
                    key="radio_canonico_carrinho",
                )

                new_name = st.text_input(
                    "Deseja renomear a entidade final? (Opcional)",
                    placeholder="Ex: Secretaria Municipal de Urbanismo",
                    help="Se preenchido, o ID eleito receberá este nome, e o nome antigo dele virará sinônimo automaticamente.",
                )

                ids_to_merge = [int(id_ent) for id_ent in options_dict if id_ent != canonical_id]

                if st.button("🚀 Executar Mesclagem e Esvaziar Carrinho", type="primary", use_container_width=True):
                    with st.spinner("Processando mesclagem e gerando sinônimos no banco..."):
                        merge_response = service.merge_entities(
                            canonical_id=int(canonical_id),
                            ids_to_merge=ids_to_merge,
                            new_name=new_name.strip() if new_name.strip() else None,
                        )
                        if "error" in merge_response:
                            st.error(f"Falha na API: {merge_response['error']}")
                        else:
                            st.success(
                                f"🎉 Sucesso! {merge_response.get('documents_updated', 0)} vínculos movidos e {merge_response.get('entities_deleted', 0)} entidades deletadas."
                            )
                            st.session_state["merge_cart_entities"] = {}
                            st.rerun()

    # ------------------------------------------------------------------
    # FLOW B: FULL SCAN (Single-Row Selection)
    # ------------------------------------------------------------------
    else:
        if st.button("Executar Varredura Computacional da Base", type="primary", use_container_width=True):
            st.session_state["entity_pairs_found"] = service.find_similar_pairs(threshold=threshold)

        if st.session_state.get("entity_pairs_found"):
            pairs_df = pd.DataFrame(st.session_state["entity_pairs_found"])
            pairs_df = pairs_df.rename(
                columns={
                    "id_1": "ID A",
                    "name_1": "Entidade A",
                    "type_1": "Tipo A",
                    "id_2": "ID B",
                    "name_2": "Entidade B",
                    "type_2": "Tipo B",
                    "similarity": "Proximidade",
                }
            )

            st.markdown("### Suspeitas de Duplicidade Encontradas")
            st.caption("Clique em um par para abrir o painel de resolução imediata.")

            pairs_event = st.dataframe(
                pairs_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
            )

            selected_rows = pairs_event.selection.rows  # type: ignore

            if len(selected_rows) == 1:
                st.divider()
                row = pairs_df.iloc[selected_rows[0]]
                id1, term1 = int(row["ID A"]), row["Entidade A"]
                id2, term2 = int(row["ID B"]), row["Entidade B"]

                st.markdown(f"### ⚖️ Ação para: **{term1}** vs **{term2}**")
                col_merge, col_ban = st.columns(2)

                with col_merge:
                    st.markdown(f"### 👑 Resolver Duplicidade: **{term1}** vs **{term2}**")

                    pair_options = {id1: term1, id2: term2}
                    canonical_id = st.radio(
                        "Qual registro deve ser mantido como o termo oficial?",
                        options=pair_options.keys(),
                        format_func=lambda x: pair_options[x],
                        horizontal=True,
                    )

                    id_to_merge = id2 if canonical_id == id1 else id1
                    dead_term = pair_options[id_to_merge]
                    live_term = pair_options[canonical_id]

                    st.warning(
                        f"⚠️ **Confirmação:** A entidade **{dead_term}** será desativada do acervo e convertida em sinônimo de **{live_term}**."
                    )

                    if st.button("Fundir este Par de Entidades", type="primary", use_container_width=True):
                        with st.spinner("Atualizando registros..."):
                            merge_response = service.merge_entities(
                                canonical_id=canonical_id, ids_to_merge=[id_to_merge]
                            )
                            if "error" in merge_response:
                                st.error(f"Erro na operação: {merge_response['error']}")
                            else:
                                st.success("Par de entidades consolidado com sucesso!")
                                del st.session_state["entity_pairs_found"]
                                st.rerun()

                with col_ban:
                    st.markdown("**2. Falso Positivo Duplo?**")
                    st.caption(
                        "Se ambos os termos forem erros da IA, você pode enviá-los para a Lista Negra de uma só vez."
                    )
                    if st.button("🚫 Banir Ambos os Termos", type="secondary", use_container_width=True):
                        with st.spinner("Banindo termos..."):
                            res = service.purge_stopwords([term1.lower(), term2.lower()])
                            if "error" in res:
                                st.error(res["error"])
                            else:
                                st.success("Termos banidos da plataforma!")
                                del st.session_state["entity_pairs_found"]
                                st.rerun()

        elif "entity_pairs_found" in st.session_state:
            st.success("✨ Excelente! Nenhuma duplicidade localizada no acervo com este limiar.")


# ======================================================================
# TAB 3: MAINTENANCE (SAFE PURGE)
# ======================================================================
with maintenance_tab:
    st.subheader("Saneamento de Índices e Otimização")
    st.write("Efetue rotinas de limpeza profunda para remover resíduos estruturais.")

    # 1. BLACKLIST BLOCK (STOPWORDS)
    st.markdown("#### 🚫 Lista Negra de Entidades (Falsos Positivos)")
    with st.popover("❔ Como funciona a Lista Negra?"):
        st.markdown("""
        Se o robô continuar a extrair palavras que não são entidades (ex: *Feiras livres*, *Atenciosamente*),
        digite-as aqui. O sistema vai apagar todas as ocorrências atuais e impedir que o robô as extraia novamente.
        """)

    stopwords_input = st.text_area(
        "Digitar Falsos Positivos (Separados por vírgula):",
        placeholder="Exemplo: feiras livres, atenciosamente, documento",
        help="Insira os termos e o sistema fará a limpeza atômica em lote no banco.",
    )

    if st.button("Adicionar à Lista Negra e Expurgar", type="primary"):
        if not stopwords_input.strip():
            st.warning("Por favor, informe ao menos uma palavra.")
        else:
            word_list = [w.strip().lower() for w in stopwords_input.split(",") if w.strip()]
            with st.spinner("Atualizando regras do Worker e expurgando banco..."):
                res = service.purge_stopwords(word_list)
                if "error" in res:
                    st.error(f"Erro na operação: {res['error']}")
                else:
                    st.success(
                        f"🎉 Lista negra atualizada! {res.get('entities_deleted', 0)} entidades falsas foram apagadas do acervo."
                    )
                    st.balloons()

    st.divider()

    with st.popover("❔ Entender o impacto de expurgar Entidades Órfãs"):
        st.markdown("""
        Entidades órfãs são palavras gravadas na tabela taxonômica que **não possuem mais nenhum documento associado**.
        Isso ocorre quando documentos são excluídos, ou após revisões manuais profundas.

        Removê-las limpa termos fantasmas que poluiriam os filtros de pesquisa dos usuários, sem qualquer risco de perda de dados.
        """)

    if st.button(
        "🧹 Varrer e Expurgar Entidades Órfãs do Acervo",
        use_container_width=True,
        help="Executa DELETE físico de chaves sem relacionamentos ativos.",
    ):
        purge_response = service.purge_orphans()
        if "error" in purge_response:
            st.error(f"Não foi possível processar a limpeza: {purge_response['error']}")
        else:
            st.success(
                f"Saneamento concluído! Foram deletadas **{purge_response['entities_deleted']}** entidades fantasmas/órfãs do sistema."
            )
            st.balloons()
