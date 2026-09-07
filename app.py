import streamlit as st
import pandas as pd
from src.reverse_sourcing import ejecutar_busqueda_inversa

st.set_page_config(page_title="Amazon Wholesale Finder", layout="wide", page_icon="📦")

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales con filtros avanzados")

# Sidebar - Filtros del Bot
st.sidebar.header("⚙️ Filtros Wholesale")
api_key = st.sidebar.text_input("Keepa API Key", type="password", key="keepa_key")

st.sidebar.subheader("📊 Criterios Financieros")
min_roi = st.sidebar.slider("ROI Mínimo deseado (%)", 0.0, 100.0, 15.0)

st.sidebar.subheader("👥 Competencia y Dominio")
min_sellers = st.sidebar.number_input("Min. Vendedores FBA", value=2)
max_sellers = st.sidebar.number_input("Max. Vendedores FBA", value=20)
max_amazon_share = st.sidebar.slider("Max % Buy Box de Amazon", 0.0, 100.0, 40.0)

st.sidebar.subheader("🚀 Demanda y Logística")
max_bsr = st.sidebar.number_input("BSR Máximo", value=150000)

# Main UI
tab1, tab2 = st.tabs(["🌐 Buscador Global", "📄 Analizador de Catálogos"])

with tab1:
    st.subheader("Búsqueda Inversa y Oportunidades")
    
    col1, col2 = st.columns(2)
    with col1:
        tipo_busqueda = st.radio("Tipo de Búsqueda", ["Global (Todo el Mercado)", "Por Marca Específica"])
    with col2:
        categoria = st.selectbox("Categoría de Amazon", ["Todas", "Electrónica", "Hogar y Cocina", "Oficina", "Juguetes"])
    
    col3, col4 = st.columns(2)
    with col3:
        min_precio = st.number_input("Precio Venta Mínimo ($)", value=15.0)
    with col4:
        max_precio = st.number_input("Precio Venta Máximo ($)", value=250.0)

    marca_txt = ""
    if tipo_busqueda == "Por Marca Específica":
        marca_txt = st.text_input("Nombre de la Marca", value="Logitech")

    modo_str = "MARCA" if tipo_busqueda == "Por Marca Específica" else "GLOBAL"

    if st.button("🔍 Escanear Oportunidades"):
        if not api_key:
            st.error("Por favor, ingresa tu API Key de Keepa en el panel lateral.")
        else:
            with st.spinner("Consultando la API de Keepa..."):
                df_resultados = ejecutar_busqueda_inversa(
                    marca=marca_txt,
                    categoria=categoria,
                    modo=modo_str,
                    api_key=api_key,
                    min_roi=min_roi,
                    max_bsr=max_bsr,
                    min_precio=min_precio,
                    max_precio=max_precio,
                    min_sellers=min_sellers,
                    max_sellers=max_sellers,
                    max_amazon_share=max_amazon_share
                )

                if not df_resultados.empty:
                    st.success(f"¡Se encontraron {len(df_resultados)} productos!")
                    st.dataframe(
                        df_resultados,
                        column_config={"Enlace": st.column_config.LinkColumn("Ver en Amazon")},
                        use_container_width=True
                    )
                else:
                    st.info("No se encontraron productos con la combinación de filtros actual.")
