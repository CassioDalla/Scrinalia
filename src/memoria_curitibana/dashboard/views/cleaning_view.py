import pandas as pd
import streamlit as st

from memoria_curitibana.dashboard.services.cleaning_service import StreamlitCleaningService as service

st.title("🧹 Qualidade de Dados (Motor Regex)")
st.markdown("""
Crie regras avançadas de limpeza textual para higienizar o acervo retroativamente.
As regras ativas serão processadas silenciosamente pelo Worker em *background*.
""")

with st.expander("💡 Guia Rápido: Como usar Expressões Regulares (Regex)?"):
    st.markdown("""
    * **Apagar uma palavra exata:** `\\bpalavra\\b` (O `\\b` garante que não apaga pedaços de outras palavras).
    * **Ignorar maiúsculas/minúsculas:** O nosso motor já ignora isso automaticamente (`IGNORECASE` está ativo na API).
    * **Remover espaços duplicados:** Padrão: `\\s{2,}` | Substituir por: ` ` (um único espaço).
    * **Remover "Av. Avenida":** Padrão: `\\bav\\.?\\s+avenida\\b` | Substituir por: `Avenida`.
    """)

st.divider()

# ======================================================================
# RULE CREATION FORM
# ======================================================================
col1, col2 = st.columns([1, 1])

with col1:
    rule_name = st.text_input(
        "Nome da Regra:",
        placeholder="Ex: Remover 'Av. Avenida'",
        help="Um nome para identificar esta rotina no banco de dados.",
    )
    target_column = st.selectbox(
        "Coluna Alvo no Acervo:",
        options=[
            ("original_title", "Título Original"),
            ("scope_content", "Conteúdo / Descrição"),
            ("admin_bio_history", "História Administrativa"),
            ("provenance", "Proveniência"),
            ("archivist_notes", "Notas do Arquivista"),
        ],
        format_func=lambda x: x[1],
    )

with col2:
    regex_pattern = st.text_input(
        "Padrão Regex (Python):",
        placeholder=r"Ex: \b(av\.?\s+avenida)\b",
        help="A expressão regular para localizar a anomalia.",
    )
    replacement_text = st.text_input(
        "Substituir por:",
        placeholder="Deixe em branco para apagar a anomalia",
        help="O texto que vai entrar no lugar do padrão encontrado.",
    )

# State to hold the simulation
if "cleaning_simulation" not in st.session_state:
    st.session_state["cleaning_simulation"] = None

# ======================================================================
# DRY-RUN BUTTON (SAFE SIMULATION)
# ======================================================================
if st.button("🧪 Simular Impacto (Dry-Run)", type="secondary", use_container_width=True):
    if not rule_name or not regex_pattern:
        st.warning("Preencha o Nome da Regra e o Padrão Regex para simular.")
    else:
        with st.spinner("Testando Regex contra amostras reais do banco de dados..."):
            # Send the column (index 0 of the selected tuple)
            result = service.preview_dry_run(
                target_column=target_column[0],  # type: ignore
                regex_pattern=regex_pattern,
                replacement_string=replacement_text,
            )
            st.session_state["cleaning_simulation"] = result

# ======================================================================
# SIMULATION DISPLAY AND SAVE BUTTON
# ======================================================================
if st.session_state["cleaning_simulation"]:
    res = st.session_state["cleaning_simulation"]

    st.divider()
    st.markdown("### 🔬 Resultados da Simulação")

    # 1. If invalid, show the error and stop (do not show the button)
    if not res.get("is_valid_regex", False):
        st.error(f"❌ Sintaxe de Regex Inválida: {res.get('error_message')}")

    # 2. If valid, we move on!
    else:
        if res.get("matches_found", 0) == 0:
            st.info(
                "⚠️ O seu Regex é válido, mas não encontrou nenhum resultado na amostra testada. Pode salvá-lo na mesma como medida preventiva para novos documentos."
            )
        else:
            st.success(f"✅ Regex validado! Encontrados **{res['matches_found']}** matches na amostra de teste.")

            # Build the Before and After table (Diff) only if there is data
            samples = res.get("samples", [])
            samples_df = pd.DataFrame(samples)

            df_display = samples_df.rename(
                columns={
                    "description_id": "ID do Documento",
                    "original_text": "Texto Original (Antes)",
                    "modified_text": "Texto Modificado (Depois)",
                }
            )
            st.dataframe(df_display, use_container_width=True, hide_index=True)

        # The "Save" button stays HERE INSIDE, visible whenever the rule is valid
        st.markdown("---")
        st.warning("Tem a certeza de que deseja ativar esta regra? O Worker irá aplicá-la ao acervo.")

        if st.button("🚀 Salvar e Ativar Regra", type="primary", use_container_width=True):
            with st.spinner("A guardar regra no banco de dados..."):
                response = service.create_rule(
                    name=rule_name,
                    target_column=target_column[0],  # type: ignore
                    regex_pattern=regex_pattern,
                    replacement_string=replacement_text,
                )

                if "error" in response:
                    st.error(f"Falha ao salvar a regra: {response['error']}")
                else:
                    st.success("🎉 Regra salva e ativada com sucesso!")
                    st.session_state["cleaning_simulation"] = None  # Clears the screen
                    st.rerun()  # Immediate refresh so the rule shows in the list below!

# ======================================================================
# LISTING AND MANAGEMENT OF ACTIVE RULES
# ======================================================================
st.divider()
st.subheader("📋 Regras de Limpeza Ativas")
st.markdown("Estas regras estão atualmente a ser processadas em background pelo Worker.")

active_rules = service.get_active_rules()

if not active_rules:
    st.info("Nenhuma regra de limpeza ativa no momento.")
else:
    # Improvised table header
    col_h1, col_h2, col_h3, col_h4 = st.columns([2, 2, 3, 1])
    col_h1.caption("NOME DA REGRA")
    col_h2.caption("COLUNA ALVO")
    col_h3.caption("REGEX ➡️ SUBSTITUIÇÃO")
    col_h4.caption("AÇÃO")

    st.divider()

    for rule in active_rules:
        # Container to keep each row aligned
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 2, 3, 1])

            col1.write(f"**{rule['rule_name']}**")
            col2.code(rule["target_column"])

            # Friendly formatting: shows what becomes what
            replacement = rule["replacement_string"] if rule["replacement_string"] else "[Apagar]"
            col3.write(f"`{rule['regex_pattern']}` ➡️ `{replacement}`")

            # The 'key' parameter is mandatory in Streamlit loops so the buttons do not overlap
            if col4.button("❌ Desativar", key=f"deactivate_{rule['rule_id']}", use_container_width=True):
                success = service.deactivate_rule(rule["rule_id"])
                if success:
                    st.toast(f"Regra '{rule['name']}' desativada!")
                    st.rerun()  # Gives the immediate interface refresh
                else:
                    st.error("Erro ao desativar a regra.")

        st.markdown("---")
