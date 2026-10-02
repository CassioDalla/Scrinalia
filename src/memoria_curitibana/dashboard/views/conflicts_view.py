import pandas as pd
import streamlit as st

from memoria_curitibana.dashboard.services.taxonomy_api import TaxonomyApiService

st.title("⚔️ Governança Cruzada: Conflitos de Domínio")
st.markdown("""
### Mapeamento e Resolução de Fronteiras Semânticas
Este ecossistema atua para resolver discordâncias entre os modelos de **Assuntos (Tags)** e **Entidades Nomeadas (NER)**.
Quando ambos os motores extraem termos idênticos ou graficamente semelhantes, ocorre uma fragmentação do acervo. Aqui você define quem deve governar o termo.
""")

# ======================================================================
# GOVERNANCE INSTRUCTIONS HUB
# ======================================================================
with st.expander("📖 Central de Ajuda: Como decidir o vencedor?", expanded=False):
    st.markdown("""
    ### ⚖️ Critérios de Julgamento Arquivístico

    1. **Quando escolher "Manter como Assunto (Tag)":**
       * O termo representa um conceito abstrato, uma tipologia informal ou um tema genérico.
       * *Exemplos:* "Urbanismo", "Imigração", "Fotografia", "Casamentos", "Habitação".
       * *Impacto:* A linha da Entidade é extinta. Todos os documentos associados passam a ser indexados por esta Tag no motor de busca.

    2. **Quando escolher "Manter como Entidade (PER/LOC/ORG)":**
       * O termo aponta para um núcleo concreto da história: um Nome Próprio (PER), um Espaço Geográfico/Logradouro (LOC) ou uma Instituição Comercial/Pública (ORG).
       * *Exemplos:* "Batel" (LOC), "Ipomea" (ORG), "David Carneiro" (PER).
       * *Impacto:* A Tag é eliminada da taxonomia. Os documentos herdados são acoplados ao grafo da Entidade correspondente.
    """)

# ======================================================================
# CONTROL AND SCANNING PANEL
# ======================================================================
st.write("---")
config_col, button_col = st.columns([3, 1])

with config_col:
    conflict_threshold = st.slider(
        "Limiar de Alarme para Conflitos (Métrica Levenshtein):",
        0.75,
        1.0,
        0.90,
        step=0.05,
        help="Ajuste a sensibilidade ortográfica. 1.0 busca apenas termos com escrita 100% idêntica.",
    )

with button_col:
    st.write("##")  # Vertical alignment of the button
    run_scan = st.button("🚨 Varrer Conflitos", type="primary", use_container_width=True)

# State management to keep the results between Streamlit 'reruns'
if "domain_conflicts" not in st.session_state:
    st.session_state["domain_conflicts"] = None

if run_scan:
    with st.spinner("Varrendo tabelas taxonômicas e calculando matriz de similaridade..."):
        st.session_state["domain_conflicts"] = TaxonomyApiService.get_cross_domain_conflicts(
            threshold=conflict_threshold
        )

# ======================================================================
# RESULTS DISPLAY AND INTERACTIVE TABLE
# ======================================================================
if st.session_state["domain_conflicts"] is not None:
    if st.session_state["domain_conflicts"]:
        conflicts_df = pd.DataFrame(st.session_state["domain_conflicts"])

        # Cosmetic column formatting for the end user
        df_display = conflicts_df.rename(
            columns={
                "tag_id": "ID (Tag)",
                "tag_name": "Nomenclatura (Tag)",
                "entity_id": "ID (Entidade)",
                "entity_name": "Nomenclatura (Entidade)",
                "entity_type": "Categoria NER",
                "similarity": "Grau de Colisão",
            }
        )

        st.markdown(f"### 🎯 Foram localizadas **{len(conflicts_df)} ambiguidades** estruturais.")
        st.caption("Selecione uma linha da tabela abaixo para abrir o painel de veredito individual.")

        # Interactive table with single-row selection mode
        table_event = st.dataframe(
            df_display, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )

        selected_rows = table_event.selection.rows  # type: ignore

        # ======================================================================
        # CROSS-MERGE PANEL (ONLY APPEARS WHEN A ROW IS CLICKED)
        # ======================================================================
        if len(selected_rows) == 1:
            target_index = selected_rows[0]
            data_row = conflicts_df.iloc[target_index]

            tag_id = int(data_row["tag_id"])
            tag_name = str(data_row["tag_name"])
            entity_id = int(data_row["entity_id"])
            entity_name = str(data_row["entity_name"])
            entity_type = str(data_row["entity_type"])

            st.divider()
            st.markdown(f"### ⚖️ Painel de Veredito: `{tag_name}` vs `{entity_name}` ({entity_type})")
            st.write("Escolha qual estrutura de dados representa a realidade histórica deste termo:")

            col_tag, col_entity = st.columns(2)

            with col_tag:
                st.markdown("#### 🏷️ Declarar como Assunto (Tag)")
                st.caption(
                    f"A entidade de ID {entity_id} será deletada. Seus documentos associados virarão metadados de Tag."
                )

                if st.button(
                    "Confirmar Vitória da Tag",
                    type="secondary",
                    use_container_width=True,
                    key=f"btn_winner_tag_{tag_id}_{entity_id}",
                ):
                    with st.spinner("Movendo ponteiros relacionais no banco..."):
                        res = TaxonomyApiService.resolve_cross_domain_conflict("TAG", tag_id, entity_id)
                        if "error" in res:
                            st.error(f"Falha na API: {res['error']}")
                        else:
                            st.success(
                                f"Sucesso! {res['data']['documents_transferred']} documentos transferidos para o domínio de Tags."
                            )
                            # Clear the cache to force a new scan without the resolved record
                            st.session_state["domain_conflicts"] = None
                            st.rerun()

            with col_entity:
                st.markdown(f"#### 🤖 Declarar como Entidade ({entity_type})")
                st.caption(f"A tag de ID {tag_id} será desativada. Seus documentos migrarão para o grafo de Entidades.")

                if st.button(
                    "Confirmar Vitória da Entidade",
                    type="primary",
                    use_container_width=True,
                    key=f"btn_winner_ent_{tag_id}_{entity_id}",
                ):
                    with st.spinner("Movendo ponteiros relacionais no PostgreSQL..."):
                        res = TaxonomyApiService.resolve_cross_domain_conflict("ENTITY", tag_id, entity_id)
                        if "error" in res:
                            st.error(f"Falha na API: {res['error']}")
                        else:
                            st.success(
                                f"Sucesso! {res['data']['documents_transferred']} documentos transferidos para a Entidade."
                            )
                            # Clear the cache to force a new scan without the resolved record
                            st.session_state["domain_conflicts"] = None
                            st.rerun()

    else:
        st.success("✨ Excelente! Não existem conflitos de domínios na base de dados para o limiar configurado.")
else:
    st.info("💡 Clique no botão 'Varrer Conflitos' acima para iniciar a análise cruzada de taxonomias.")
