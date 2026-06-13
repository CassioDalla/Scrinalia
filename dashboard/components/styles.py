import streamlit as st


def apply_global_css():
    """Injeta as classes CSS personalizadas na aplicação."""
    st.markdown(
        """
        <style>
        .badge-per { background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 4px;}
        .badge-loc { background-color: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 4px;}
        .badge-org { background-color: #fef08a; color: #854d0e; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 4px;}
        .badge-tag { background-color: #f3f4f6; color: #374151; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 4px; border: 1px solid #d1d5db;}
        </style>
        """,
        unsafe_allow_html=True,
    )
