import sys
from pathlib import Path

import streamlit as st

raiz_projeto = Path(__file__).parent.parent.resolve()
sys.path.append(str(raiz_projeto))


# Configuração global (deve ser a primeiríssima chamada do Streamlit)
st.set_page_config(page_title="Acervo Inteligente MVP", page_icon="🏛️", layout="wide")


# Registra as duas páginas
pagina_vitrine = st.Page("views/vitrine.py", title="Vitrine de Busca", icon="🔍")
pagina_taxonomia = st.Page("views/taxonomy_view.py", title="Taxonomia", icon="🧹")

# Configura a navegação lateral passando as duas páginas
navegacao = st.navigation({
    "Descoberta": [
        pagina_vitrine
    ],
    "Governança & Curadoria": [
        pagina_taxonomia,
    ],
    "Engenharia de Sistema": [
        #pagina_workers
    ]
})
 



navegacao.run()
