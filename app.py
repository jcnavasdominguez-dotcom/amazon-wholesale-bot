import streamlit as st
from src.reverse_sourcing import ejecutar_busqueda_inversa
from src.catalog_analyzer import render_catalog_analyzer

st.set_page_config(page_title="Amazon Wholesale Finder", layout="wide")

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales y análisis de catálogos")

# Barra lateral de configuración
with st.sidebar:
    st.header("⚙️ Filtros Wholesale")
    api_key = st.text_input("Keepa API Key", type="password")
    excluir_propia_marca = st.checkbox("Excluir si vende el Fabricante", value=True)
    min_roi = st.slider("ROI Mínimo deseado (%)", 0.0, 100.0, 20.0)
    min_sellers = st.number_input("Min. Vendedores", min_value=1, max_value=50, value=2)
    max_bsr = st.number_input("Max. BSR 90d", min_value=1000, max_value=500000, value=150000)

# Pestañas principales
tab1, tab2 = st.tabs(["🌐 Buscador Global", "📑 Analizador de Catálogos"])

with tab1:
    st.subheader("Búsqueda Inversa y Oportunidades")
    col1, col2 = st.columns(2)
    with col1:
        min_precio = st.number_input("Precio Venta Mínimo ($)", value=15.0)
    with col2:
        max_precio = st.number_input("Precio Venta Máximo ($)", value=250.0)

    if st.button("🔍 Escanear Oportunidades"):
        df_res = ejecutar_busqueda_inversa(
            api_key=api_key,
            min_roi=min_roi,
            min_sellers=min_sellers,
            max_bsr=max_bsr,
            min_precio=min_precio,
            max_precio=max_precio,
            excluir_propia_marca=excluir_propia_marca
        )
        if not df_res.empty:
            st.dataframe(df_res, use_container_width=True)

with tab2:
    render_catalog_analyzer(
        api_key=api_key,
        min_roi=min_roi,
        min_sellers=min_sellers,
        max_bsr=max_bsr,
        excluir_propia_marca=excluir_propia_marca
    )
