import pandas as pd
import streamlit as st
from services.entity_service import StreamlitEntityService as service

st.title("🗂️ Governança de Entidades Nomeadas")
st.markdown(
    "Audite, higienize e consolide Pessoas (PER), Locais (LOC) e Organizações (ORG) extraídas de forma automática pelo Worker NER."
)

# 1. CENTRAL DE INSTRUÇÕES GLOBAL
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

# 2. DEFINIÇÃO DAS ABAS
tab_relevancia, tab_mesclagem, tab_manutencao = st.tabs(
    ["📊 Análise de Frequência", "🔗 Unificação & Duplicatas", "🧹 Manutenção e Limpeza"]
)

# ======================================================================
# ABA 1: ANÁLISE DE FREQUÊNCIA
# ======================================================================
with tab_relevancia:
    st.subheader("Entidades Mais Citadas na Base Documental")

    col_filtro, col_limit = st.columns(2)
    with col_filtro:
        tipo_filtro = st.selectbox(
            "Filtrar por Categoria NER:",
            ["TODAS", "PER", "LOC", "ORG"],
            help="Selecione um grupo específico para refinar a auditoria visual.",
        )
    with col_limit:
        limite = st.slider("Amostra de Exibição:", 10, 500, 30, help="Ajuste a escala do relatório tabular abaixo.")

    dados_relevancia = service.get_relevance(entity_type=tipo_filtro, limit=limite)

    if dados_relevancia:
        df_relevance = pd.DataFrame(dados_relevancia)
        df_relevance.columns = ["ID", "Nome da Entidade", "Tipo", "Total de Ocorrências no Acervo"]
        st.dataframe(df_relevance, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro localizado para os filtros informados.")


# ======================================================================
# ABA 2: UNIFICAÇÃO & DUPLICATAS (MERGE INTERATIVO)
# ======================================================================
with tab_mesclagem:
    st.subheader("Estúdio de Desambiguação de Termos")
    st.markdown("Utilize a inteligência computacional ou faça varreduras fonéticas direcionadas.")

    modo_busca = st.radio(
        "Estratégia de Identificação de Conflitos:",
        ["Varrer Banco em Busca de Duplicatas (Pares)", "Buscar Termo Específico"],
        horizontal=True,
    )

    limiar = st.slider(
        "Limiar de Similaridade Textual (Métrica Levenshtein):",
        0.2,
        1.0,
        0.65,
        step=0.05,
        help="Proximidade ortográfica entre as palavras. 1.0 indica escrita idêntica.",
    )

    # ------------------------------------------------------------------
    # FLUXO A: BUSCA ESPECÍFICA (Multi-Row Selection)
    # ------------------------------------------------------------------
    if modo_busca == "Buscar Termo Específico":
        st.markdown(
            "🔍 **Instruções:** 1. Busque a entidade; 2. Selecione as caixas das linhas duplicadas; 3. Eleja o nome correto."
        )
        termo_busca = st.text_input(
            "Investigar Nome da Entidade:",
            placeholder="Ex: Marechal Deodoro",
            help="Busque variações",
        )

        if termo_busca:
            similares = service.find_similar(target_name=termo_busca, threshold=limiar)
            if similares:
                df_sim = pd.DataFrame(similares)
                # Garantindo nomes amigáveis nas colunas
                df_sim = df_sim.rename(
                    columns={
                        "entity_id": "ID",
                        "name": "Nome da Entidade",
                        "entity_type": "Tipo",
                        "similarity": "Score",
                    }
                )

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
                    st.markdown("### 👑 Eleger Registro Canônico")
                    st.info("A entidade eleita preservará o seu ID e herdará os documentos das linhas eliminadas.")

                    df_selecionado = df_sim.iloc[linhas_selecionadas]
                    opcoes_dict = {row["ID"]: row["Nome da Entidade"] for _, row in df_selecionado.iterrows()}

                    id_canonico = st.radio(
                        "Qual registro representa a grafia correta/oficial?",
                        options=opcoes_dict.keys(),
                        format_func=lambda x: opcoes_dict[x],
                    )

                    ids_para_mesclar = [id_ent for id_ent in opcoes_dict if id_ent != id_canonico]
                    nomes_mesclados = [opcoes_dict[id_ent] for id_ent in ids_para_mesclar]

                    st.warning(
                        f"⚠️ **Confirmação:** As entidades **{', '.join(nomes_mesclados)}** serão removidas e os seus históricos acoplados a **{opcoes_dict[id_canonico]}**."
                    )

                    if st.button("Executar Fusão de Entidades", type="primary", use_container_width=True):
                        with st.spinner("Processando fusão..."):
                            resposta_merge = service.merge_entities(
                                canonical_id=id_canonico, ids_to_merge=ids_para_mesclar
                            )
                            if "error" in resposta_merge:
                                st.error(f"Falha na API: {resposta_merge['error']}")
                            else:
                                st.success(
                                    f"✅ Sucesso! Vínculos movidos: {resposta_merge['documents_updated']} documentos | Linhas eliminadas: {resposta_merge['entities_deleted']}"
                                )
                                st.rerun()

                elif len(linhas_selecionadas) == 1:
                    st.caption("💡 Selecione ao menos **duas linhas** para acionar o painel relacional.")
            else:
                st.info("Nenhuma entidade semelhante foi localizada.")

    # ------------------------------------------------------------------
    # FLUXO B: VARREDURA COMPLETA (Single-Row Selection)
    # ------------------------------------------------------------------
    else:
        if st.button("Executar Varredura Computacional da Base", type="primary", use_container_width=True):
            st.session_state["pares_entidades_encontrados"] = service.find_similar_pairs(threshold=limiar)

        if st.session_state.get("pares_entidades_encontrados"):
            df_pares = pd.DataFrame(st.session_state["pares_entidades_encontrados"])
            df_pares = df_pares.rename(
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

            evento_pares = st.dataframe(
                df_pares, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
            )

            linhas_selecionadas = evento_pares.selection.rows  # type: ignore

            if len(linhas_selecionadas) == 1:
                st.divider()
                linha = df_pares.iloc[linhas_selecionadas[0]]
                id1, termo1 = int(linha["ID A"]), linha["Entidade A"]
                id2, termo2 = int(linha["ID B"]), linha["Entidade B"]

                st.markdown(f"### 👑 Resolver Duplicidade: **{termo1}** vs **{termo2}**")

                opcoes_par = {id1: termo1, id2: termo2}
                id_canonico = st.radio(
                    "Qual registro deve ser mantido como o termo oficial?",
                    options=opcoes_par.keys(),
                    format_func=lambda x: opcoes_par[x],
                    horizontal=True,
                )

                id_para_mesclar = id2 if id_canonico == id1 else id1
                termo_morto = opcoes_par[id_para_mesclar]
                termo_vivo = opcoes_par[id_canonico]

                st.warning(
                    f"⚠️ **Confirmação:** A entidade **{termo_morto}** será desativada do acervo e convertida em sinônimo de **{termo_vivo}**."
                )

                if st.button("Fundir este Par de Entidades", type="primary", use_container_width=True):
                    with st.spinner("Atualizando registros..."):
                        resposta_merge = service.merge_entities(
                            canonical_id=id_canonico, ids_to_merge=[id_para_mesclar]
                        )
                        if "error" in resposta_merge:
                            st.error(f"Erro na operação: {resposta_merge['error']}")
                        else:
                            st.success("Par de entidades consolidado com sucesso!")
                            del st.session_state["pares_entidades_encontrados"]
                            st.rerun()

        elif "pares_entidades_encontrados" in st.session_state:
            st.success("✨ Excelente! Nenhuma duplicidade localizada no acervo com este limiar.")


# ======================================================================
# ABA 3: MANUTENÇÃO (PURGE SEGURO)
# ======================================================================
with tab_manutencao:
    st.subheader("Saneamento de Índices e Otimização")
    st.write("Efetue rotinas de limpeza profunda para remover resíduos estruturais.")

    with st.popover("❔ Entender o impacto de expurgar Entidades Órfãs"):
        st.markdown("""
        Entidades órfãs são palavras gravadas na tabela taxonômica que **não possuem mais nenhum documento associado**. 
        Isso ocorre quando documentos são excluídos, ou após revisões manuais profundas.

        Removê-las limpa termos fantasmas que poluiriam os filtros de pesquisa dos usuários, sem qualquer risco de perda de dados.
        """)

    st.divider()

    if st.button(
        "🧹 Varrer e Expurgar Entidades Órfãs do Acervo",
        use_container_width=True,
        help="Executa DELETE físico de chaves sem relacionamentos ativos.",
    ):
        resposta_purge = service.purge_orphans()
        if "error" in resposta_purge:
            st.error(f"Não foi possível processar a limpeza: {resposta_purge['error']}")
        else:
            st.success(
                f"Saneamento concluído! Foram deletadas **{resposta_purge['entities_deleted']}** entidades fantasmas/órfãs do sistema."
            )
            st.balloons()
