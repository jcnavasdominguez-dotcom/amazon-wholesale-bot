import streamlit as st
from src.reverse_sourcing import ejecutar_busqueda_inversa
from src.catalog_analyzer import render_catalog_analyzer

st.set_page_config(page_title="Amazon Wholesale Finder", layout="wide")

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales con filtros avanzados para Reverse Sourcing")

# --- BARRA LATERAL RESTAURADA COMPLETA ---
with st.sidebar:
    st.header("⚙️ Filtros Wholesale")
    api_key = st.text_input("Keepa API Key", type="password")
    
    st.subheader("🛡️ Exclusión de Dominio")
    excluir_propia_marca = st.checkbox("Excluir si vende el Fabricante", value=True)
    
    st.subheader("📊 Criterios Financieros")
    min_roi = st.slider("ROI Mínimo deseado (%)", 0.0, 100.0, 20.0)
    
    st.subheader("👥 Competencia y Dominio")
    min_sellers = st.number_input("Min. Vendedores FBA", min_value=1, max_value=50, value=2)
    max_sellers = st.number_input("Max. Vendedores FBA", min_value=1, max_value=50, value=20)
    max_bsr = st.number_input("Max. BSR 90d", min_value=1000, max_value=500000, value=150000)

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2 = st.tabs(["🌐 Buscador Global", "📑 Analizador de Catálogos"])

with tab1:
    st.subheader("Búsqueda Inversa y Oportunidades")
    
    col_a, col_b = st.columns(2)
    with col_a:
        modo = st.radio("Tipo de Búsqueda", ["Global (Todo el Mercado)", "Por Marca Específica"])
    with col_b:
        categoria = st.selectbox(
            "Categoría de Amazon", 
            ["Todas", "Hogar y Cocina", "Electrónica", "Oficina", "Juguetes"]
        )
    
    marca = ""
    if modo == "Por Marca Específica":
        marca = st.text_input("Nombre exacto de la marca:")

    col1, col2 = st.columns(2)
    with col1:
        min_precio = st.number_input("Precio Venta Mínimo ($)", value=15.0)
    with col2:
        max_precio = st.number_input("Precio Venta Máximo ($)", value=250.0)

    if st.button("🔍 Escanear Oportunidades"):
        if not api_key:
            st.error("Por favor ingresa tu Keepa API Key en el menú lateral.")
        else:
            df_res = ejecutar_busqueda_inversa(
                marca=marca,
                categoria=categoria,
                modo="MARCA" if modo == "Por Marca Específica" else "GLOBAL",
                api_key=api_key,
                min_roi=min_roi,
                max_bsr=max_bsr,
                min_precio=min_precio,
                max_precio=max_precio,
                min_sellers=min_sellers,
                max_sellers=max_sellers,
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
