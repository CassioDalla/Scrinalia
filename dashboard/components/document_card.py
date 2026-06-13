import streamlit as st

from core.models.gold_layer import GoldDescriptionModel


def render_document_card(doc: GoldDescriptionModel):
    """Renderiza a gaveta expansível para um único documento."""

    with st.expander(f"📄 {doc.original_title}"):
        # Dividimos em 3 colunas: [Foto] [Textos] [Tags/Entidades]
        col_img, col_texto, col_meta = st.columns([1, 2, 1])

        with col_img:
            # Integração com o nosso Worker de Thumbnails (MinIO)
            if getattr(doc, "storage_thumbnail_uri", None):
                url_publica = doc.storage_thumbnail_uri
                if url_publica:
                    url_publica = url_publica.replace("s3://", "http://localhost:9000/")
                    st.image(url_publica, use_container_width=True)
            else:
                st.markdown(
                    "<div style='background:#f0f2f6; border-radius:5px; padding:30px; text-align:center;'>"
                    "<span style='font-size:24px;'>🏛️</span><br><small>Sem miniatura</small></div>",
                    unsafe_allow_html=True,
                )

        with col_texto:
            st.markdown("**Resumo (Scope & Content):**")
            st.write(doc.scope_content if doc.scope_content else "*Sem descrição detalhada.*")

            if doc.admin_bio_history:
                st.markdown("**Histórico Administrativo/Biográfico:**")
                st.write(doc.admin_bio_history)

        with col_meta:
            st.caption(f"**ID:** `{doc.description_id}`")
            # Adicionado tratamento seguro caso a coluna review_status não exista
            status = getattr(doc, "review_status", None)
            st.caption(f"**Status:** `{status.name if status else 'PENDENTE'}`")

            if doc.tags:
                st.markdown("**🏷️ Tags Originais:**")
                tags_html = "".join([f"<span class='badge-tag'>{t.name.title()}</span>" for t in doc.tags])
                st.markdown(tags_html, unsafe_allow_html=True)

            st.divider()

            if doc.entities:
                st.markdown("**🤖 Entidades (NER):**")
                ent_html = ""

                for e in doc.entities:
                    tipo = e.entity_type.upper()

                    # 1. Define o ícone com base no tipo da entidade
                    if tipo == "PER":
                        icone = "👤"  # Pessoa / Autoridade
                    elif tipo == "LOC":
                        icone = "🗺️"  # Local / Rua / Cidade
                    elif tipo == "ORG":
                        icone = "🏢"  # Organização / Empresa / Repartição Pública
                    else:
                        icone = "🔍"  # Fallback seguro para outros tipos

                    classe_css = f"badge-{tipo.lower()}"

                    # 2. Injeta o ícone diretamente dentro da pílula colorida
                    ent_html += f"<span class='{classe_css}'>{icone} {e.name}</span>"

                st.markdown(ent_html, unsafe_allow_html=True)
