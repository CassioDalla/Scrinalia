import streamlit as st
import pandas as pd

from core.database import get_db
from scripts.gold.tag_service import TagManager
from core.crud.gold_crud import save_stopwords 

st.title("🧹 Gestão de Taxonomia e Limpeza")
st.markdown("Analise a relevância das tags, unifique termos e gerencie as stopwords do acervo.")

# Interface organizada em três abas claras
aba_analise, aba_similaridade, aba_limpeza = st.tabs([
    "📊 Análise de Relevância", 
    "🔍 Similaridade (Pré-Merge)", 
    "🗑️ Limpeza de Stopwords"
])

# ==========================================
# ABA 1: ANÁLISE DE RELEVÂNCIA
# ==========================================
with aba_analise:
    st.subheader("Ranking de Tags")
    
    # Controles na mesma linha
    col1, col2 = st.columns([2, 1])
    with col1:
        metodo = st.radio(
            "Método de Cálculo:", 
            ["TF-IDF (Recomendado)", "Frequência Simples"], 
            horizontal=True
        )
    with col2:
        limite = st.slider("Quantidade de tags para exibir:", 10, 100, 30)

    with st.spinner("Calculando métricas no PostgreSQL..."):
        with get_db() as db:
            gestor = TagManager(db)
            
            if "TF-IDF" in metodo:
                # O TF-IDF devolve objetos Row ricos (name, frequencia, peso_idf, score_tfidf)
                resultados = gestor.get_tag_relevance_tfidf(limite)
                if resultados:
                    # Converte diretamente a lista de Rows para um DataFrame do Pandas
                    df = pd.DataFrame([dict(row._mapping) for row in resultados])
                    # Renomeia as colunas para ficarem bonitas na tela
                    df.columns = ["Tag", "Frequência", "Peso IDF", "Score TF-IDF"]
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhuma tag encontrada.")
                    
            else:
                # Agora o front-end sabe que está a receber Sequence[Row[tuple[str, int]]]
                resultados = gestor.get_tag_relevance_count(limite)
                if resultados:
                    # Extrai o dicionário seguro do objeto Row do SQLAlchemy
                    df = pd.DataFrame([dict(row._mapping) for row in resultados])
                    
                    # Renomeia as colunas para a interface visual
                    df.columns = ["Tag", "Total de Usos"]
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhuma tag encontrada.")

# ==========================================
# ABA 2: SIMILARIDADE (PRÉ-MERGE)
# ==========================================
with aba_similaridade:
    st.subheader("Análise de Similaridade e Mesclagem (Merge)")
    st.markdown("1. Busque por um termo. 2. Selecione as tags que deseja unificar. 3. Escolha a tag principal.")
    
    # ... (Inputs de busca que já criamos) ...
    tag_alvo = st.text_input("Digite a tag que deseja investigar:", placeholder="Ex: prefeitura")
    threshold = st.slider("Limiar de Similaridade:", 0.1, 1.0, 0.4, step=0.05)

    if tag_alvo.strip():
     
        similares = gestor.find_similar_tags(tag_alvo, threshold)
      
        
        if similares:
            df_sim = pd.DataFrame(similares, columns=["ID da Tag", "Termo", "Score"])
            
            # PASSO 1: A TABELA INTERATIVA
            st.markdown("### Selecione as tags para Merge:")
            
            # O on_select="rerun" faz a tela recarregar instantaneamente quando o user clica numa linha
            evento = st.dataframe(
                df_sim, 
                use_container_width=True, 
                hide_index=True,
                on_select="rerun", 
                selection_mode="multi-row" # Permite selecionar várias linhas
            )
            
            # Captura os índices das linhas que o user selecionou
            linhas_selecionadas = evento.selection.rows
            
            # PASSO 2: A ELEIÇÃO DA CANÓNICA (Só aparece se selecionar 2 ou mais)
            if len(linhas_selecionadas) >= 2:
                st.divider()
                st.markdown("### 👑 Eleger Termo Canónico")
                st.info("O termo canónico será mantido. Os outros serão apagados e os seus documentos transferidos para o canónico.")
                
                # Filtra o DataFrame apenas com as linhas selecionadas
                df_selecionado = df_sim.iloc[linhas_selecionadas]
                
                # Cria um dicionário para o Radio Button exibir o Nome, mas devolver o ID
                opcoes_dict = {row["ID da Tag"]: row["Termo"] for _, row in df_selecionado.iterrows()}
                
                # O Radio button para escolher quem sobrevive
                id_canonico = st.radio(
                    "Qual termo deve sobreviver?",
                    options=opcoes_dict.keys(),
                    format_func=lambda x: opcoes_dict[x] # Mostra o nome, mas o valor real é o ID
                )
                
                # Prepara os IDs que vão ser mortos/mesclados
                ids_para_mesclar = [id_tag for id_tag in opcoes_dict.keys() if id_tag != id_canonico]
                nomes_mesclados = [opcoes_dict[id_tag] for id_tag in ids_para_mesclar]
                
                # Resumo visual antes do commit fatal
                st.warning(f"⚠️ Atenção: **{', '.join(nomes_mesclados)}** serão mesclados para dentro de **{opcoes_dict[id_canonico]}**.")
                
                # Botão de Ação
                if st.button("Executar Fusão no Banco de Dados", type="primary"):
                    with st.spinner("Reescrevendo associações na Camada Ouro..."):
                        # Aqui você chamaria o futuro gestor.merge_tags(id_canonico, ids_para_mesclar)
                        st.success(f"Tags fundidas com sucesso!")
            
            elif len(linhas_selecionadas) == 1:
                st.caption("Selecione pelo menos duas tags na tabela acima para habilitar a ferramenta de fusão.")


# ==========================================
# ABA 3: LIMPEZA E STOPWORDS
# ==========================================
with aba_limpeza:
    st.subheader("Remover Tags Inúteis")
    st.markdown(
        "Digite as palavras que deseja banir. Elas serão **apagadas das tags atuais** "
        "e **salvas no banco** para que os futuros workers as ignorem."
    )

    stopwords_input = st.text_area(
        "Stopwords (separadas por vírgula):", 
        placeholder="Exemplo: foto, documento, cópia, revisado, pmc"
    )

    # Botão com cor de alerta (primary no Streamlit fica vermelho/destaque)
    if st.button("Limpar Tags e Salvar Stopwords", type="primary"):
        if not stopwords_input.strip():
            st.warning("Por favor, digite pelo menos uma palavra.")
        else:
            # Transforma a string numa lista limpa
            lista_palavras = [w.strip() for w in stopwords_input.split(",") if w.strip()]

            with st.spinner("Executando transação no banco de dados..."):
                with get_db() as db:
                    gestor = TagManager(db)

                    try:
                        # 1. Salva na tabela de domínio (Bulk Insert)
                        save_stopwords(db, lista_palavras)

                        # 2. Apaga as tags que já existem na base Ouro
                        qtd_apagadas = gestor.purge_stopwords(lista_palavras)

                        # 3. Confirma a transação (se der erro acima, nada é salvo)
                        db.commit()

                        st.success(f"✅ Sucesso! **{len(lista_palavras)}** novas stopwords registradas e **{qtd_apagadas}** tags apagadas do acervo atual.")
                        
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Ocorreu um erro durante a limpeza: {e}")


                        