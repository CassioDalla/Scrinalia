import sys
from pathlib import Path

import streamlit as st

project_root = Path(__file__).parent.parent.resolve()
sys.path.append(str(project_root))


# Global configuration (must be the very first Streamlit call)
st.set_page_config(page_title="Acervo Inteligente MVP", page_icon="🏛️", layout="wide")


# Register the pages
vitrine_page = st.Page("views/vitrine.py", title="Vitrine de Busca", icon="🔍")
taxonomy_page = st.Page("views/taxonomy_view.py", title="Tags e Assuntos", icon="🏷️")
entities_page = st.Page("views/entity_view.py", title="Entidades Nomeadas", icon="🗂️")
conflicts_page = st.Page("views/conflicts_view.py", title="Conflitos de Domínio", icon="⚔️")
quality_page = st.Page("views/cleaning_view.py", title="Qualidade de Dados", icon="🧼")
# Configure the sidebar navigation passing the pages
navigation = st.navigation(
    {
        "Descoberta": [vitrine_page],
        "Governança & Curadoria": [taxonomy_page, entities_page, conflicts_page, quality_page],
        "Engenharia de Sistema": [
            # workers_page
        ],
    }
)


navigation.run()
