import streamlit as st

from domains.archive.schemas.document_schema import DocumentSummary


def render_document_card(doc: DocumentSummary) -> None:
    """Render the expandable drawer for a single document."""

    with st.expander(f"📄 {doc.original_title}"):
        # Split into 3 columns: [Photo] [Texts] [Tags/Entities]
        image_col, text_col, meta_col = st.columns([1, 2, 1])

        with image_col:
            # Integration with our Thumbnails Worker (MinIO)
            if getattr(doc, "storage_thumbnail_uri", None):
                public_url = doc.storage_thumbnail_uri
                if public_url:
                    public_url = public_url.replace("s3://", "http://localhost:9000/")
                    st.image(public_url, use_container_width=True)
            else:
                st.markdown(
                    "<div style='background:#f0f2f6; border-radius:5px; padding:30px; text-align:center;'>"
                    "<span style='font-size:24px;'>🏛️</span><br><small>Sem miniatura</small></div>",
                    unsafe_allow_html=True,
                )

        with text_col:
            st.markdown("**Resumo (Scope & Content):**")
            st.write(doc.scope_content if doc.scope_content else "*Sem descrição detalhada.*")

            if doc.admin_bio_history:
                st.markdown("**Histórico Administrativo/Biográfico:**")
                st.write(doc.admin_bio_history)

        with meta_col:
            st.caption(f"**ID:** `{doc.description_id}`")
            # Added safe handling in case the review_status column does not exist
            status = getattr(doc, "review_status", None)
            st.caption(f"**Status:** `{status.name if status else 'PENDENTE'}`")

            if doc.tags:
                st.markdown("**🏷️ Tags Originais:**")
                tags_html = "".join([f"<span class='badge-tag'>{t.name.title()}</span>" for t in doc.tags])
                st.markdown(tags_html, unsafe_allow_html=True)

            st.divider()

            if doc.entities:
                st.markdown("**🤖 Entidades (NER):**")
                entities_html = ""

                for entity in doc.entities:
                    entity_type = entity.entity_type.upper()

                    # 1. Define the icon based on the entity type
                    if entity_type == "PER":
                        icon = "👤"  # Person / Authority
                    elif entity_type == "LOC":
                        icon = "🗺️"  # Place / Street / City
                    elif entity_type == "ORG":
                        icon = "🏢"  # Organization / Company / Public Office
                    else:
                        icon = "🔍"  # Safe fallback for other types

                    css_class = f"badge-{entity_type.lower()}"

                    # 2. Inject the icon directly inside the colored pill
                    entities_html += f"<span class='{css_class}'>{icon} {entity.name}</span>"

                st.markdown(entities_html, unsafe_allow_html=True)
