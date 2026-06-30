import pandas as pd
import streamlit as st
from services.taxonomy_api import TaxonomyApiService

st.title("⚔️ Governança Cruzada: Conflitos de Domínio")
st.markdown("""
### Mapeamento e Resolução de Fronteiras Semânticas
Este ecossistema atua para resolver discordâncias entre os modelos de **Assuntos (Tags)** e **Entidades Nomeadas (NER)**.
Quando ambos os motores extraem termos idênticos ou graficamente semelhantes, ocorre uma fragmentação do acervo. Aqui você define quem deve governar o termo.
""")

# ======================================================================
# CENTRAL DE INSTRUÇÕES DE GOVERNANÇA
# ======================================================================
with st.expander("ℹ️ Central de Ajuda: Como decidir o vencedor?", expanded=False):
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
# PAINEL DE CONTROLE E ESCANEAMENTO
# ======================================================================
st.write("---")
col_config, col_btn = st.columns([3, 1])

with col_config:
    threshold_conflito = st.slider(
        "Limiar de Alarme para Conflitos (Métrica Levenshtein):",
        0.75,
        1.0,
        0.90,
        step=0.05,
        help="Ajuste a sensibilidade ortográfica. 1.0 busca apenas termos com escrita 100% idêntica.",
    )

with col_btn:
    st.write("##")  # Alinhamento vertical do botão
    executar_scan = st.button("🚨 Varrer Conflitos", type="primary", use_container_width=True)

# Gerenciamento de estado para manter os resultados entre os 'reruns' do Streamlit
if "conflitos_dominio" not in st.session_state:
    st.session_state["conflitos_dominio"] = None

if executar_scan:
    with st.spinner("Varrendo tabelas taxonômicas e calculando matriz de similaridade..."):
        st.session_state["conflitos_dominio"] = TaxonomyApiService.get_cross_domain_conflicts(
            threshold=threshold_conflito
        )

# ======================================================================
# EXIBIÇÃO DOS RESULTADOS E TABELA INTERATIVA
# ======================================================================
if st.session_state["conflitos_dominio"] is not None:
    if st.session_state["conflitos_dominio"]:
        df_conflitos = pd.DataFrame(st.session_state["conflitos_dominio"])

        # Formatação cosmética das colunas para o usuário final
        df_display = df_conflitos.rename(
            columns={
                "tag_id": "ID (Tag)",
                "tag_name": "Nomenclatura (Tag)",
                "entity_id": "ID (Entidade)",
                "entity_name": "Nomenclatura (Entidade)",
                "entity_type": "Categoria NER",
                "similarity": "Grau de Colisão",
            }
        )

        st.markdown(f"### 🎯 Foram localizadas **{len(df_conflitos)} ambiguidades** estruturais.")
        st.caption("Selecione uma linha da tabela abaixo para abrir o painel de veredito individual.")

        # Tabela interativa com modo de seleção de linha única
        evento_tabela = st.dataframe(
            df_display, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )

        linhas_selecionadas = evento_tabela.selection.rows  # type: ignore

        # ======================================================================
        # PAINEL DE FUSÃO CRUZADA (APARECE APENAS AO CLICAR EM UMA LINHA)
        # ======================================================================
        if len(linhas_selecionadas) == 1:
            index_alvo = linhas_selecionadas[0]
            linha_dados = df_conflitos.iloc[index_alvo]

            tag_id = int(linha_dados["tag_id"])
            tag_nome = str(linha_dados["tag_name"])
            entity_id = int(linha_dados["entity_id"])
            entity_nome = str(linha_dados["entity_name"])
            entity_tipo = str(linha_dados["entity_type"])

            st.divider()
            st.markdown(f"### ⚖️ Painel de Veredito: `{tag_nome}` vs `{entity_nome}` ({entity_tipo})")
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
                            # Limpa o cache para forçar nova varredura sem o registro resolvido
                            st.session_state["conflitos_dominio"] = None
                            st.rerun()

            with col_entity:
                st.markdown(f"#### 🤖 Declarar como Entidade ({entity_tipo})")
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
                            # Limpa o cache para forçar nova varredura sem o registro resolvido
                            st.session_state["conflitos_dominio"] = None
                            st.rerun()

    else:
        st.success("✨ Excelente! Não existem conflitos de domínios na base de dados para o limiar configurado.")
else:
    st.info("💡 Clique no botão 'Varrer Conflitos' acima para iniciar a análise cruzada de taxonomias.")
