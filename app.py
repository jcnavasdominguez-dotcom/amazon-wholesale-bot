import streamlit as st
from src.reverse_sourcing import ejecutar_busqueda_inversa
from src.catalog_analyzer import render_catalog_analyzer

st.set_page_config(page_title="Amazon Wholesale Finder", layout="wide")

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales y análisis de catálogos para Reverse Sourcing")

# --- BARRA LATERAL CON CAMPOS DE TEXTO NUMÉRICOS PARA MAYOR PRECISIÓN ---
with st.sidebar:
    st.header("⚙️ Filtros Wholesale")
    api_key = st.text_input(
        "Keepa API Key", 
        type="password",
        help="Clave de API otorgada por Keepa para realizar consultas de productos[cite: 30, 31]."
    )
    
    st.subheader("🛡️ Exclusión de Dominio")
    excluir_propia_marca = st.checkbox(
        "Excluir si vende el Fabricante", 
        value=True,
        help="Descarta productos donde la propia marca comercial sea el único vendedor de la Buy Box o posea la tienda oficial[cite: 27]."
    )
    
    st.subheader("📊 Criterios Financieros")
    porcentaje_costo = st.number_input(
        "Costo Est. de Compra (% del P. Venta)", 
        min_value=1.0, max_value=99.0, value=50.0, step=0.5,
        help="Estimación de costo del producto en relación al precio de venta en Amazon (el estándar Wholesale es entre 40% y 50%)[cite: 27]."
    )
    min_roi = st.number_input(
        "ROI Mínimo deseado (%)", 
        min_value=0.0, max_value=500.0, value=0.0, step=0.5,
        help="Retorno sobre la Inversión mínimo aceptable[cite: 27]. Déjalo en 0.0% para ver todas las oportunidades viables[cite: 27]."
    )
    
    st.subheader("👥 Competencia y Dominio")
    min_sellers = st.number_input(
        "Min. Vendedores FBA", 
        min_value=1, max_value=50, value=2, step=1,
        help="Cantidad mínima de vendedores en el listing (≥ 2 asegura producto Wholesale)[cite: 27]."
    )
    max_sellers = st.number_input(
        "Max. Vendedores FBA", 
        min_value=1, max_value=100, value=20, step=1,
        help="Cantidad máxima de vendedores. Evita listings saturados."
    )
    max_bsr = st.number_input(
        "Max. BSR 90d", 
        min_value=1000, max_value=5000000, value=150000, step=5000,
        help="Best Sellers Rank promedio de los últimos 90 días[cite: 27, 28]. A menor número, mayor velocidad de venta[cite: 27, 28]."
    )
    max_amazon_share = st.number_input(
        "Max % Buy Box de Amazon", 
        min_value=0.0, max_value=100.0, value=40.0, step=1.0,
        help="Porcentaje del tiempo que Amazon domina la caja de compra. Si es > 50%, es difícil competir."
    )

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
        min_precio = st.number_input("Precio Venta Mínimo ($)", value=15.0, step=1.0)
    with col2:
        max_precio = st.number_input("Precio Venta Máximo ($)", value=250.0, step=1.0)

    if st.button("🔍 Escanear Oportunidades"):
        if not api_key:
            st.error("Por favor ingresa tu Keepa API Key en el menú lateral.")
        else:
            with st.spinner("Escaneando mercado en Keepa y procesando métricas..."):
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
                    max_amazon_share=max_amazon_share,
                    excluir_propia_marca=excluir_propia_marca,
                    porcentaje_costo=porcentaje_costo
                )
                if not df_res.empty:
                    st.success(f"¡Se encontraron {len(df_res)} productos viables!")
                    st.dataframe(df_res, use_container_width=True)
                else:
                    st.warning("No se obtuvieron resultados para los criterios seleccionados. Intenta ampliar el rango de precio[cite: 30].")

with tab2:
    render_catalog_analyzer(
        api_key=api_key,
        min_roi=min_roi,
        min_sellers=min_sellers,
        max_bsr=max_bsr,
        excluir_propia_marca=excluir_propia_marca,
        porcentaje_costo=porcentaje_costo
    )
