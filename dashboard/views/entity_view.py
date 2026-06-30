from typing import Literal, cast

import pandas as pd
import streamlit as st
from services.entity_service import StreamlitEntityService as service


## =========================================================================
##                 COMPONENTES REUTILIZAVEIS DA VIEW
## =========================================================================
def render_painel_banimento_lote(df_selecionado: pd.DataFrame, key_prefix: str):
    """
    Componente para Ações em Lote (>1 linha selecionada):
    Bane múltiplas entidades de uma só vez.
    """
    st.divider()
    st.markdown("### 🚫 Banimento em Massa (Lista Negra)")

    nomes_alvo = df_selecionado["Nome da Entidade"].tolist()

    st.warning(
        f"⚠️ **Atenção:** Você selecionou **{len(nomes_alvo)} entidades** para banimento. Elas serão excluídas e o Worker será bloqueado de gerá-las novamente."
    )

    with st.expander("Ver lista de entidades que serão banidas"):
        st.write(", ".join(nomes_alvo))

    if st.button(
        "🚫 Banir Todas as Entidades Selecionadas",
        type="primary",
        use_container_width=True,
        key=f"btn_ban_lote_{key_prefix}",
    ):
        with st.spinner("Adicionando à lista negra e expurgando do banco..."):
            res = service.purge_stopwords([nome.lower() for nome in nomes_alvo])
            if "error" in res:
                st.error(res["error"])
            else:
                qtd_apagadas = res.get("entities_deleted", 0)
                st.success(
                    f"🎉 {len(nomes_alvo)} palavras banidas com sucesso! {qtd_apagadas} registros deletados do acervo."
                )
                st.rerun()


def render_painel_individual(df_selecionado: pd.DataFrame, key_prefix: str):
    """
    Componente reutilizável para o painel de Ações Individuais (Reclassificar e Excluir).
    """
    st.divider()
    st.markdown("### 🛠️ Ações Individuais")
    st.write("Ajuste a classificação ou exclua pontualmente este registro.")

    id_alvo = int(df_selecionado.iloc[0]["ID"])
    nome_alvo = df_selecionado.iloc[0]["Nome da Entidade"]
    tipo_atual = df_selecionado.iloc[0]["Tipo"]

    col_reclass, col_delete, col_ban = st.columns(3)

    with col_reclass:
        st.markdown(f"**Reclassificar: {nome_alvo}**")
        novo_tipo = st.selectbox(
            "Nova Categoria",
            ["PER", "LOC", "ORG"],
            index=["PER", "LOC", "ORG"].index(tipo_atual) if tipo_atual in ["PER", "LOC", "ORG"] else 0,
            key=f"reclass_{key_prefix}_{id_alvo}",
        )
        if st.button(
            "Atualizar Categoria", type="primary", use_container_width=True, key=f"btn_reclass_{key_prefix}_{id_alvo}"
        ):
            if novo_tipo == tipo_atual:
                st.warning("A entidade já possui esta categoria.")
            else:
                with st.spinner("Atualizando banco e gerando sinônimos..."):
                    novo_tipo = cast(Literal["PER", "ORG", "LOC"], novo_tipo)
                    res = service.reclassify_entity(id_alvo, novo_tipo)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success(f"Categoria alterada para {novo_tipo}!")
                        st.rerun()

    with col_delete:
        st.markdown("**Exclusão**")
        st.caption("Remove apenas este ID específico.")
        if st.button(
            "🗑️ Excluir Entidade", type="secondary", use_container_width=True, key=f"btn_del_{key_prefix}_{id_alvo}"
        ):
            with st.spinner("Excluindo registro..."):
                res = service.delete_entity(id_alvo)
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.success("Entidade excluída com sucesso!")
                    st.rerun()

    with col_ban:
        st.markdown("**Adicionar à Lista Negra**")
        st.caption("Deleta a palavra do acervo e bloqueia a IA no futuro de classificá-la novamente.")
        if st.button(
            "🚫 Banir Palavra", type="secondary", use_container_width=True, key=f"btn_ban_{key_prefix}_{id_alvo}"
        ):
            with st.spinner(f"Banindo '{nome_alvo}' e expurgando banco..."):
                res = service.purge_stopwords([nome_alvo.lower()])
                if "error" in res:
                    st.error(res["error"])
                else:
                    qtd_apagadas = res.get("entities_deleted", 1)
                    st.success(f"Palavra banida! {qtd_apagadas} registros deletados.")
                    st.rerun()


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

# Inicialização do Carrinho de Mesclagem na sessão do Streamlit
if "cart_merge_entities" not in st.session_state:
    st.session_state["cart_merge_entities"] = {}

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
        evento = st.dataframe(
            df_relevance, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row"
        )

        linhas_selecionadas = evento.selection.rows  # type: ignore

        if len(linhas_selecionadas) > 0:
            df_selecionado = df_relevance.iloc[linhas_selecionadas]

            # Atalho: Adicionar ao carrinho direto da aba de frequência
            if st.button("🛒 Enviar selecionadas ao Cesto de Mesclagem (Aba 2)", type="primary"):
                for _, row in df_selecionado.iterrows():
                    st.session_state["cart_merge_entities"][row["ID"]] = {
                        "ID": row["ID"],
                        "Nome da Entidade": row["Nome da Entidade"],
                        "Tipo": row["Tipo"],
                    }
                st.success(f"{len(linhas_selecionadas)} entidades enviadas ao carrinho!")

        if len(linhas_selecionadas) == 1:
            render_painel_individual(df_relevance.iloc[linhas_selecionadas], key_prefix="aba_freq")
        elif len(linhas_selecionadas) >= 2:
            render_painel_banimento_lote(df_relevance.iloc[linhas_selecionadas], key_prefix="freq")

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

                if len(linhas_selecionadas) > 0:
                    df_selecionado = df_sim.iloc[linhas_selecionadas]

                    st.markdown("---")
                    if st.button("🛒 Adicionar Selecionadas ao Cesto", type="primary", use_container_width=True):
                        for _, row in df_selecionado.iterrows():
                            st.session_state["cart_merge_entities"][row["ID"]] = {
                                "ID": row["ID"],
                                "Nome da Entidade": row["Nome da Entidade"],
                                "Tipo": row["Tipo"],
                            }
                        st.success(f"Adicionadas {len(linhas_selecionadas)} entidades ao carrinho!")
                        st.rerun()

                    # Mantém as ações cirúrgicas rápidas
                    if len(linhas_selecionadas) == 1:
                        render_painel_individual(df_selecionado, key_prefix="merge")
                    else:
                        render_painel_banimento_lote(df_selecionado, key_prefix="merge_busca")
            else:
                st.info("Nenhuma entidade semelhante foi localizada.")

        # --- O CARRINHO DE MESCLAGEM ---
        st.divider()
        st.markdown("### 🛒 Cesto de Mesclagem")

        if not st.session_state["cart_merge_entities"]:
            st.info("O cesto está vazio. Busque e adicione entidades acima para consolidá-las.")
        else:
            df_carrinho = pd.DataFrame(list(st.session_state["cart_merge_entities"].values()))

            col_cart1, col_cart2 = st.columns([4, 1])
            with col_cart1:
                st.dataframe(df_carrinho, use_container_width=True, hide_index=True)
            with col_cart2:
                if st.button("🗑️ Limpar Carrinho", use_container_width=True):
                    st.session_state["cart_merge_entities"] = {}
                    st.rerun()

            if len(df_carrinho) >= 1:
                st.markdown("#### 👑 Eleger Termo Oficial e Renomear")
                st.info("A entidade eleita vai herdar os documentos de todas as outras do cesto.")

                opcoes_dict = {row["ID"]: row["Nome da Entidade"] for _, row in df_carrinho.iterrows()}

                id_canonico = st.radio(
                    "Qual registro representa a âncora principal (ID que vai sobreviver)?",
                    options=opcoes_dict.keys(),
                    format_func=lambda x: opcoes_dict[x],
                    key="radio_canonico_carrinho",
                )

                novo_nome = st.text_input(
                    "Deseja renomear a entidade final? (Opcional)",
                    placeholder="Ex: Secretaria Municipal de Urbanismo",
                    help="Se preenchido, o ID eleito receberá este nome, e o nome antigo dele virará sinônimo automaticamente.",
                )

                ids_para_mesclar = [id_ent for id_ent in opcoes_dict if id_ent != id_canonico]

                if st.button("🚀 Executar Mesclagem e Esvaziar Carrinho", type="primary", use_container_width=True):
                    with st.spinner("Processando mesclagem e gerando sinônimos no banco..."):
                        resposta_merge = service.merge_entities(
                            canonical_id=id_canonico,
                            ids_to_merge=ids_para_mesclar,
                            new_name=novo_nome.strip() if novo_nome.strip() else None,
                        )
                        if "error" in resposta_merge:
                            st.error(f"Falha na API: {resposta_merge['error']}")
                        else:
                            st.success(
                                f"🎉 Sucesso! {resposta_merge.get('documents_updated', 0)} vínculos movidos e {resposta_merge.get('entities_deleted', 0)} entidades deletadas."
                            )
                            st.session_state["cart_merge_entities"] = {}
                            st.rerun()

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

                st.markdown(f"### ⚖️ Ação para: **{termo1}** vs **{termo2}**")
                col_merge, col_ban = st.columns(2)

                with col_merge:
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

                with col_ban:
                    st.markdown("**2. Falso Positivo Duplo?**")
                    st.caption(
                        "Se ambos os termos forem erros da IA, você pode enviá-los para a Lista Negra de uma só vez."
                    )
                    if st.button("🚫 Banir Ambos os Termos", type="secondary", use_container_width=True):
                        with st.spinner("Banindo termos..."):
                            res = service.purge_stopwords([termo1.lower(), termo2.lower()])
                            if "error" in res:
                                st.error(res["error"])
                            else:
                                st.success("Termos banidos da plataforma!")
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

    # 1. BLOCO DA LISTA NEGRA (STOPWORDS)
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
            lista_palavras = [w.strip().lower() for w in stopwords_input.split(",") if w.strip()]
            with st.spinner("Atualizando regras do Worker e expurgando banco..."):
                res = service.purge_stopwords(lista_palavras)
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
        resposta_purge = service.purge_orphans()
        if "error" in resposta_purge:
            st.error(f"Não foi possível processar a limpeza: {resposta_purge['error']}")
        else:
            st.success(
                f"Saneamento concluído! Foram deletadas **{resposta_purge['entities_deleted']}** entidades fantasmas/órfãs do sistema."
            )
            st.balloons()
