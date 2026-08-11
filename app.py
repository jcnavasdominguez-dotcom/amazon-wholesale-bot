import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from src.reverse_sourcing import ejecutar_busqueda_inversa

load_dotenv()

st.set_page_config(page_title='Amazon Wholesale Suite', page_icon='📦', layout='wide')

# --- BARRA LATERAL CON EXPLICACIONES (HELP TOOLTIPS) ---
st.sidebar.title('⚙️ Filtros Profesionales Wholesale')
api_key = st.sidebar.text_input('Keepa API Key', value=os.getenv('KEEPA_API_KEY', ''), type='password', help='Tu clave de API de Keepa para consultar datos en tiempo real de Amazon USA.')

st.sidebar.subheader('📊 Criterios de Financieros')
min_roi = st.sidebar.slider('ROI Mínimo deseado (%)', 10.0, 60.0, float(os.getenv('MIN_ROI', 25.0)), help='Retorno de inversión mínimo aceptable tras descontar costo del producto, tarifas de Amazon FBA y costo del Prep Center.')
usar_precio_90d = st.sidebar.checkbox('Usar Precio Promedio Buy Box 90 días', value=True, help='RECOMENDADO: Protege tus calculos calculando el ROI con el precio historico de 90 dias en lugar del precio actual, evitando picos o desplomes temporales.')

st.sidebar.subheader('👥 Competencia y Dominio')
col_s1, col_s2 = st.sidebar.columns(2)
with col_s1:
    min_sellers = st.number_input('Min. Vendedores FBA', value=3, help='Filtro Anti-IP Claim: Si hay menos de 3 vendedores, la marca podria ser privada o enviar denuncias de propiedad intelectual.')
with col_s2:
    max_sellers = st.number_input('Max. Vendedores FBA', value=12, help='Filtro Anti-Guerra de Precios: Mas de 12 o 15 vendedores genera competencia desmedida y destruccion de margenes por repricers.')

max_amazon_share = st.sidebar.slider('Max % Buy Box de Amazon', 0.0, 50.0, 20.0, help='Filtro Anti-Monopolio: Si Amazon gana la Buy Box mas del 20% del tiempo, no dejara suficiente rotacion para tu inventario.')

st.sidebar.subheader('🚀 Demanda y Logística')
max_bsr = st.sidebar.number_input('BSR Máximo (Top Rank)', value=int(os.getenv('MAX_BSR_90', 50000)), help='Mejor Clasificacion de Ventas. Mide la velocidad general del producto (cuanto menor el numero, mas rápido se vende).')
min_drops = st.sidebar.number_input('Min. Drops BSR / mes', value=30, help='Caidas de BSR mensuales. Cada caida equivale a minimo 1 venta. Asegura que el producto se venda constantemente.')
solo_estandar = st.sidebar.checkbox('Excluir productos Oversize (Grandes/Pesados)', value=True, help='Filtro de Costo Logistico: Evita productos grandes o pesados que generan tarifas altas de almacenamiento y envio.')

st.sidebar.markdown('---')
st.sidebar.subheader('🚚 Logística Prep Center')
prep_fee = st.sidebar.number_input('Costo Prep Center ($/ud)', value=float(os.getenv('PREP_CENTER_FEE', 1.50)), help='Tarifa por inspeccion, empaque y etiquetado FNSKU en tu centro de preparacion.')
inbound_fee = st.sidebar.number_input('Envío Inbound FBA ($/ud)', value=float(os.getenv('INBOUND_SHIPPING_FEE', 0.50)), help='Tarifa estimada de envio consolidado por UPS desde tu Prep Center a bodegas de Amazon.')

# --- CONTENIDO PRINCIPAL ---
st.title('📦 Amazon Wholesale Finder')
st.caption('Explorador inteligente de oportunidades globales con filtros avanzados')

tab1, tab2 = st.tabs(['🌐 Buscador Global de Oportunidades', '📄 Analizador de Catálogos (Wholesale)'])

with tab1:
    st.header('Búsqueda Inversa y Oportunidades de Mercado')
    
    col_modo, col_cat = st.columns([1, 1])
    with col_modo:
        tipo_busqueda = st.radio('Tipo de Búsqueda', ['🌐 Global (Todo el Mercado)', '🏷️ Por Marca Específica'], horizontal=True)
    with col_cat:
        categoria_sel = st.selectbox('Categoría de Amazon', ['Todas', 'Electrónica', 'Hogar y Cocina', 'Oficina', 'Juguetes'])
        
    marca_input = None
    if tipo_busqueda == '🏷️ Por Marca Específica':
        marca_input = st.text_input('Escribe el nombre de la Marca', 'Logitech')
        
    col_p1, col_p2, col_btn = st.columns([1, 1, 1])
    with col_p1:
        min_p = st.number_input('Precio Venta Mínimo ($)', value=15.0, help='Evita productos de bajo precio donde las tarifas fijas de Amazon absorben la ganancia.')
    with col_p2:
        max_p = st.number_input('Precio Venta Máximo ($)', value=150.0)
    with col_btn:
        st.write('')
        st.write('')
        btn_buscar = st.button('🔍 Escanear Oportunidades')
        
    if btn_buscar:
        modo_str = 'MARCA' if tipo_busqueda == '🏷️ Por Marca Específica' else 'GLOBAL'
        with st.spinner('Escaneando el mercado aplicando filtros profesionales...'):
            df_res = ejecutar_busqueda_inversa(
                marca=marca_input,
                categoria=categoria_sel,
                modo=modo_str,
                api_key=api_key,
                min_roi=min_roi,
                max_bsr=max_bsr,
                min_precio=min_p,
                max_precio=max_p,
                min_sellers=min_sellers,
                max_sellers=max_sellers,
                max_amazon_share=max_amazon_share,
                min_drops=min_drops,
                usar_precio_90d=usar_precio_90d,
                solo_estandar=solo_estandar,
                prep_fee=prep_fee,
                inbound_fee=inbound_fee
            )
            if df_res.empty:
                st.warning('No se encontraron productos que cumplan con TODOS los criterios de seguridad y ROI seleccionados.')
            else:
                st.success(f'¡Se encontraron {len(df_res)} oportunidades altamente rentables y seguras!')
                st.dataframe(df_res)
                
                csv = df_res.to_csv(index=False).encode('utf-8')
                st.download_button('📥 Descargar Oportunidades (CSV)', data=csv, file_name='oportunidades_wholesale.csv', mime='text/csv')

with tab2:
    st.header('Análisis de Catálogo de Proveedor')
    uploaded_file = st.file_uploader('Sube el archivo CSV del mayorista', type=['csv'])
    if uploaded_file is not None:
        st.info('Módulo listo para procesar listas con los nuevos criterios.')
