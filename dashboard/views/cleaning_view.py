import pandas as pd
import streamlit as st
from services.cleaning_service import StreamlitCleaningService as service

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
# FORMULÁRIO DE CRIAÇÃO DA REGRA
# ======================================================================
col1, col2 = st.columns([1, 1])

with col1:
    nome_regra = st.text_input("Nome da Regra:", placeholder="Ex: Remover 'Av. Avenida'", help="Um nome para identificar esta rotina no banco de dados.")
    coluna_alvo = st.selectbox(
        "Coluna Alvo no Acervo:", 
        options=[
            ("original_title", "Título Original"),
            ("scope_content", "Conteúdo / Descrição"),
            ("admin_bio_history", "História Administrativa"),
            ("provenance", "Proveniência"),
            ("archivist_notes", "Notas do Arquivista")
        ],
        format_func=lambda x: x[1]
    )

with col2:
    padrao_regex = st.text_input("Padrão Regex (Python):", placeholder=r"Ex: \b(av\.?\s+avenida)\b", help="A expressão regular para localizar a anomalia.")
    texto_substituicao = st.text_input("Substituir por:", placeholder="Deixe em branco para apagar a anomalia", help="O texto que vai entrar no lugar do padrão encontrado.")

# Estado para guardar a simulação
if "simulacao_limpeza" not in st.session_state:
    st.session_state["simulacao_limpeza"] = None

# ======================================================================
# BOTÃO DE DRY-RUN (SIMULAÇÃO SEGURA)
# ======================================================================
if st.button("🧪 Simular Impacto (Dry-Run)", type="secondary", use_container_width=True):
    if not nome_regra or not padrao_regex:
        st.warning("Preencha o Nome da Regra e o Padrão Regex para simular.")
    else:
        with st.spinner("Testando Regex contra amostras reais do banco de dados..."):
            # Envia a coluna (índice 0 da tupla selecionada)
            resultado = service.preview_dry_run(
                target_column=coluna_alvo[0], # type: ignore
                regex_pattern=padrao_regex,
                replacement_string=texto_substituicao
            )
            st.session_state["simulacao_limpeza"] = resultado

# ======================================================================
# EXIBIÇÃO DA SIMULAÇÃO E BOTÃO DE SALVAR
# ======================================================================
if st.session_state["simulacao_limpeza"]:
    res = st.session_state["simulacao_limpeza"]
    
    st.divider()
    st.markdown("### 🔬 Resultados da Simulação")
    
    # 1. Se for inválido, mostra o erro e bloqueia (não mostra o botão)
    if not res.get("is_valid_regex", False):
        st.error(f"❌ Sintaxe de Regex Inválida: {res.get('error_message')}")
    
    # 2. Se for válido, seguimos em frente!
    else:
        if res.get("matches_found", 0) == 0:
            st.info("⚠️ O seu Regex é válido, mas não encontrou nenhum resultado na amostra testada. Pode salvá-lo na mesma como medida preventiva para novos documentos.")
        else:
            st.success(f"✅ Regex validado! Encontrados **{res['matches_found']}** matches na amostra de teste.")
            
            # Monta a tabela de Antes e Depois (Diff) apenas se houver dados
            amostras = res.get("samples", [])
            df_amostras = pd.DataFrame(amostras)
            
            df_display = df_amostras.rename(columns={
                "description_id": "ID do Documento",
                "original_text": "Texto Original (Antes)",
                "modified_text": "Texto Modificado (Depois)"
            })
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # O botão de "Salvar" FICA AQUI DENTRO, visível sempre que a regra for válida
        st.markdown("---")
        st.warning("Tem a certeza de que deseja ativar esta regra? O Worker irá aplicá-la ao acervo.")
        
        if st.button("🚀 Salvar e Ativar Regra", type="primary", use_container_width=True):
            with st.spinner("A guardar regra no banco de dados..."):
                resposta = service.create_rule(
                    name=nome_regra,
                    target_column=coluna_alvo[0], # type: ignore
                    regex_pattern=padrao_regex,
                    replacement_string=texto_substituicao
                )
                
                if "error" in resposta:
                    st.error(f"Falha ao salvar a regra: {resposta['error']}")
                else:
                    st.success("🎉 Regra salva e ativada com sucesso!")
                    st.session_state["simulacao_limpeza"] = None # Limpa a tela
                    st.rerun() # Refresh imediato para a regra aparecer na lista em baixo!

# ======================================================================
# LISTAGEM E GESTÃO DE REGRAS ATIVAS
# ======================================================================
st.divider()
st.subheader("📋 Regras de Limpeza Ativas")
st.markdown("Estas regras estão atualmente a ser processadas em background pelo Worker.")

regras_ativas = service.get_active_rules()

if not regras_ativas:
    st.info("Nenhuma regra de limpeza ativa no momento.")
else:
    # Cabeçalho da tabela improvisada
    col_h1, col_h2, col_h3, col_h4 = st.columns([2, 2, 3, 1])
    col_h1.caption("NOME DA REGRA")
    col_h2.caption("COLUNA ALVO")
    col_h3.caption("REGEX ➡️ SUBSTITUIÇÃO")
    col_h4.caption("AÇÃO")
    
    st.divider()

    for regra in regras_ativas:
        # Container para manter o alinhamento de cada linha
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
            
            col1.write(f"**{regra['rule_name']}**")
            col2.code(regra['target_column'])
            
            # Formatação amigável: mostra o que vira o quê
            substituicao = regra['replacement_string'] if regra['replacement_string'] else "[Apagar]"
            col3.write(f"`{regra['regex_pattern']}` ➡️ `{substituicao}`")
            
            # O parâmetro 'key' é obrigatório em loops no Streamlit para os botões não se sobreporem
            if col4.button("❌ Desativar", key=f"deactivate_{regra['rule_id']}", use_container_width=True):
                sucesso = service.deactivate_rule(regra['rule_id'])
                if sucesso:
                    st.toast(f"Regra '{regra['name']}' desativada!")
                    st.rerun() # Dá o refresh imediato na interface
                else:
                    st.error("Erro ao desativar a regra.")
            
        st.markdown("---")

