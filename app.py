import streamlit as st
import pandas as pd
from src.reverse_sourcing import ejecutar_busqueda_inversa

st.set_page_config(
    page_title="Amazon Wholesale Finder", 
    layout="wide", 
    page_icon="📦"
)

st.title("📦 Amazon Wholesale Finder")
st.caption("Explorador inteligente de oportunidades globales con filtros avanzados para Reverse Sourcing")

# -----------------------------------------------------------------------------
# 1. AUTENTICACIÓN Y SECRETS
# -----------------------------------------------------------------------------
# Lee la clave automáticamente desde Streamlit Secrets si está configurada
api_key_secret = ""
try:
    if "KEEPA_API_KEY" in st.secrets:
        api_key_secret = st.secrets["KEEPA_API_KEY"]
except Exception:
    pass

# -----------------------------------------------------------------------------
# 2. PANEL LATERAL - FILTROS Y TOOLTIPS
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Filtros Wholesale")

api_key_input = st.sidebar.text_input(
    "Keepa API Key", 
    value=api_key_secret,
    type="password", 
    key="keepa_key",
    help="Clave de acceso a Keepa. Si la guardaste en Secrets, se cargará automáticamente sin pedirla cada vez."
)

st.sidebar.subheader("🛡️ Exclusión de Dominio")
excluir_propia_marca = st.sidebar.checkbox(
    "Excluir si vende el Fabricante", 
    value=True,
    help="Filtra y descarta productos donde la propia marca o fabricante posee la Buy Box, evitando competir directamente contra el dueño de la marca."
)

st.sidebar.subheader("📊 Criterios Financieros")
min_roi = st.sidebar.slider(
    "ROI Mínimo deseado (%)", 
    0.0, 100.0, 20.0,
    help="Retorno Sobre la Inversión mínimo aceptable (Ganancia Neta / Costo Estimado del Producto). Filtra oportunidades con escaso margen de beneficio."
)

st.sidebar.subheader("👥 Competencia y Dominio")
min_sellers = st.sidebar.number_input(
    "Min. Vendedores FBA", 
    value=2,
    help="Número mínimo de vendedores FBA en el listado. Tener al menos 2 o 3 vendedores confirma que la marca autoriza la reventa (Wholesale)."
)
max_sellers = st.sidebar.number_input(
    "Max. Vendedores FBA", 
    value=20,
    help="Límite máximo de vendedores FBA. Listados con más de 15-20 vendedores suelen desatar guerras de precios agresivas que destruyen el margen."
)
max_amazon_share = st.sidebar.slider(
    "Max % Buy Box de Amazon", 
    0.0, 100.0, 40.0,
    help="Porcentaje del tiempo que Amazon domina la Buy Box. Si Amazon retiene más del 40-50%, será extremadamente difícil captar ventas."
)

st.sidebar.subheader("🚀 Demanda y Logística")
max_bsr = st.sidebar.number_input(
    "BSR Máximo (Sales Rank)", 
    value=150000,
    help="Best Sellers Rank promedio de los últimos 90 días. A menor número de BSR, mayor es la velocidad de rotación y venta en Amazon."
)

# -----------------------------------------------------------------------------
# 3. INTERFAZ PRINCIPAL Y PESTAÑAS
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["🌐 Buscador Global", "📄 Analizador de Catálogos"])

with tab1:
    st.subheader("Búsqueda Inversa y Oportunidades")
    
    col1, col2 = st.columns(2)
    with col1:
        tipo_busqueda = st.radio(
            "Tipo de Búsqueda", 
            ["Global (Todo el Mercado)", "Por Marca Específica"],
            help="Global: Escanea todo Amazon bajo los parámetros de rendimiento. Por Marca: Limita el filtrado a una marca/fabricante en particular."
        )
    with col2:
        categoria = st.selectbox(
            "Categoría de Amazon", 
            ["Todas", "Electrónica", "Hogar y Cocina", "Oficina", "Juguetes"],
            help="Filtra la búsqueda para enfocar la prospección en una categoría raíz de Amazon."
        )
    
    col3, col4 = st.columns(2)
    with col3:
        min_precio = st.number_input(
            "Precio Venta Mínimo ($)", 
            value=15.0,
            help="Precio de venta mínimo en Amazon. Productos por debajo de $15 suelen dejar muy poco margen tras descontar tarifas FBA."
        )
    with col4:
        max_precio = st.number_input(
            "Precio Venta Máximo ($)", 
            value=250.0,
            help="Precio de venta máximo para acotar el capital de trabajo requerido en los pedidos iniciales a mayoristas."
        )

    marca_txt = ""
    if tipo_busqueda == "Por Marca Específica":
        marca_txt = st.text_input(
            "Nombre de la Marca", 
            value="Logitech",
            help="Ingresa el nombre exacto de la marca que deseas evaluar."
        )

    modo_str = "MARCA" if tipo_busqueda == "Por Marca Específica" else "GLOBAL"

    # Prioridad: usar lo que se ingrese manualmente en el input, o el Secret guardado
    api_key_final = api_key_input if api_key_input else api_key_secret

    if st.button("🔍 Escanear Oportunidades"):
        if not api_key_final:
            st.error("No se detectó una API Key de Keepa. Agrégala en el panel lateral o en Secrets de Streamlit.")
        else:
            with st.spinner("Analizando productos y métricas de competencia en Keepa..."):
                df_resultados = ejecutar_busqueda_inversa(
                    marca=marca_txt,
                    categoria=categoria,
                    modo=modo_str,
                    api_key=api_key_final,
                    min_roi=min_roi,
                    max_bsr=max_bsr,
                    min_precio=min_precio,
                    max_precio=max_precio,
                    min_sellers=min_sellers,
                    max_sellers=max_sellers,
                    max_amazon_share=max_amazon_share,
                    excluir_propia_marca=excluir_propia_marca
                )

                if not df_resultados.empty:
                    st.success(f"¡Se encontraron {len(df_resultados)} productos viables!")
                    st.dataframe(
                        df_resultados,
                        column_config={"Enlace": st.column_config.LinkColumn("Ver en Amazon")},
                        use_container_width=True
                    )
                else:
                    st.info("No se encontraron productos que superen los filtros de marca, competencia y rentabilidad en esta consulta.")

with tab2:
    st.info("Módulo de Análisis de Catálogos de Proveedores (Próximamente).")
