import streamlit as st
from src.reverse_sourcing import ejecutar_busqueda_inversa
from src.catalog_analyzer import render_catalog_analyzer

st.set_page_config(page_title="Amazon Wholesale Finder", layout="wide")

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales y análisis de catálogos para Reverse Sourcing")

# --- BARRA LATERAL CON TOOLTIPS Y EXPLICACIONES DETALLADAS ---
with st.sidebar:
    st.header("⚙️ Filtros Wholesale")
    api_key = st.text_input(
        "Keepa API Key", 
        type="password",
        help="Clave de API otorgada por Keepa. Requerida para realizar consultas de productos y traer métricas en tiempo real."
    )
    
    st.subheader("🛡️ Exclusión de Dominio")
    excluir_propia_marca = st.checkbox(
        "Excluir si vende el Fabricante", 
        value=True,
        help="Si está activo, descarta productos donde la propia marca comercial sea el único vendedor de la Buy Box o posea la tienda oficial, evitando riesgos de IP / Private Label."
    )
    
    st.subheader("📊 Criterios Financieros")
    porcentaje_costo = st.slider(
        "Costo Est. de Compra (% del P. Venta)", 
        10.0, 90.0, 50.0,
        help="Estimación de a qué porcentaje del precio de venta te venderá el mayorista el producto. El estándar Wholesale es entre 40% y 50% del MSRP."
    )
    min_roi = st.slider(
        "ROI Mínimo deseado (%)", 
        0.0, 100.0, 0.0,
        help="Retorno sobre la Inversión mínimo aceptable. Déjalo en 0.0% durante la prospección inicial para ver todos los productos viables."
    )
    
    st.subheader("👥 Competencia y Dominio")
    min_sellers = st.number_input(
        "Min. Vendedores FBA", 
        min_value=1, max_value=50, value=2,
        help="Cantidad mínima de vendedores compitiendo en el listing. Un valor ≥ 2 asegura que el producto es Wholesale y no Private Label."
    )
    max_sellers = st.number_input(
        "Max. Vendedores FBA", 
        min_value=1, max_value=50, value=20,
        help="Cantidad máxima de vendedores. Evita listings saturados (guerra de precios y poco volumen por vendedor)."
    )
    max_bsr = st.number_input(
        "Max. BSR 90d", 
        min_value=1000, max_value=500000, value=150000,
        help="Best Sellers Rank promedio de los últimos 90 días. A menor número, mayores ventas. Un BSR < 100,000 suele indicar rotación rápida."
    )
    max_amazon_share = st.slider(
        "Max % Buy Box de Amazon", 
        0.0, 100.0, 40.0,
        help="Porcentaje del tiempo que Amazon domina la caja de compra. Si Amazon tiene > 50% de la Buy Box, es muy difícil competir contra ellos."
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
        min_precio = st.number_input("Precio Venta Mínimo ($)", value=15.0)
    with col2:
        max_precio = st.number_input("Precio Venta Máximo ($)", value=250.0)

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
                    st.warning("No se obtuvieron resultados. Verifica el saldo de tokens de tu API Key o amplia el rango de precio.")

with tab2:
    render_catalog_analyzer(
        api_key=api_key,
        min_roi=min_roi,
        min_sellers=min_sellers,
        max_bsr=max_bsr,
        excluir_propia_marca=excluir_propia_marca,
        porcentaje_costo=porcentaje_costo
    )
