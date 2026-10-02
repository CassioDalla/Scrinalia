import streamlit as st

from dashboard.components.document_card import render_document_card
from dashboard.components.styles import apply_global_css
from dashboard.services.search_service import search_document

apply_global_css()

st.title("🏛️ Motor de Descoberta do Acervo")
st.markdown("Busca semântica e visualização de entidades extraídas por Inteligência Artificial.")

search_term = st.text_input("🔍 Pesquisar no acervo (ex: Matadouro, Colombo, João)...")

with st.spinner("Consultando Camada Ouro..."):
    results = search_document(search_term)

if not results:
    st.warning("Nenhum documento encontrado.")
else:
    st.success(f"Mostrando {len(results)} documentos encontrados.")

    for doc in results:
        render_document_card(doc)
