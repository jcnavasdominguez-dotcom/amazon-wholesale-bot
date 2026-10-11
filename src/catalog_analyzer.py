import json
import re
import requests
import pandas as pd
import streamlit as st

MARCAS_EXCLUIDAS_DIRECTAS = [
    "amazon", "amazon basics", "amazonbasics", "amazon essentials", "solimo", "pinzon",
    "ugg", "shark", "ninja", "keurig", "levoit", "bissell", "yankee candle",
    "black+decker", "black & decker", "black decker", "dewalt", "stanley", "craftsman",
    "apple", "dyson", "sony", "samsung", "bose", "lego", "owala", "celsius",
    "utopia bedding", "zulay kitchen", "hy hao yun lai", "bedsure", "bare home",
    "hatch baby", "beckham hotel collection", "cgk unlimited", "lane linen",
    "niagara sleep solution", "mellanni", "pampers", "huggies", "euhomy", "upsimples", "bedlore"
]

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa", "brand", "shop"]
    tokens = [w for w in texto.split() if w not in palabras]
    return " ".join(tokens)

def es_marca_bloqueada(brand: str, seller_name: str) -> bool:
    if not brand:
        return False
    brand_norm = normalizar_texto(brand)
    seller_norm = normalizar_texto(seller_name)

    for marca_b in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_b)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    if seller_norm and brand_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True

    return False

def render_catalog_analyzer(api_key="", min_roi=20.0, min_sellers=2, max_bsr=150000, excluir_propia_marca=True):
    st.subheader("📂 Cargar y Analizar Catálogo / Exportación de Keepa")
    st.markdown("Sube un archivo **CSV / Excel** exportado desde Keepa Product Finder o pega una lista de **ASINs** directamente.")

    opcion_carga = st.radio("Método de entrada de datos:", ["Subir Archivo (CSV / Excel)", "Pegar lista de ASINs"], horizontal=True)

    asins_para_procesar = []

    if opcion_carga == "Subir Archivo (CSV / Excel)":
        archivo_subido = st.file_uploader("Selecciona tu archivo de Keepa o Proveedor", type=["csv", "xlsx"])
        if archivo_subido is not None:
            try:
                if archivo_subido.name.endswith(".csv"):
                    df_input = pd.read_csv(archivo_subido)
                else:
                    df_input = pd.read_excel(archivo_subido)

                st.success(f"Archivo cargado exitosamente. Filas detectadas: {len(df_input)}")

                # Buscar columna que contenga ASINs
                col_asin = None
                for col in df_input.columns:
                    if "asin" in col.lower():
                        col_asin = col
                        break

                if col_asin:
                    asins_para_procesar = df_input[col_asin].dropna().astype(str).tolist()
                    st.info(f"Se encontraron {len(asins_para_procesar)} ASINs en la columna `{col_asin}`.")
                else:
                    st.error("No se encontró una columna llamada 'ASIN' en el archivo.")
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")

    else:
        asin_text = st.text_area("Pega aquí los ASINs (separados por coma, espacio o salto de línea):", height=150)
        if asin_text:
            asins_para_procesar = re.findall(r'B[0-9A-Z]{9}', asin_text.upper())
            st.info(f"ASINs válidos extraídos: {len(asins_para_procesar)}")

    if st.button("🚀 Analizar ASINs Cargados"):
        clean_key = str(api_key).strip()
        if not clean_key:
            st.error("Ingresa una Keepa API Key válida en la barra lateral.")
            return

        if not asins_para_procesar:
            st.warning("Por favor carga un archivo o pega al menos un ASIN válido.")
            return

        asins_unicos = list(dict.fromkeys(asins_para_procesar))[:100]  # Procesar hasta 100 ASINs
        asins_str = ",".join(asins_unicos)

        st.info(f"Consultando métricas en Keepa para {len(asins_unicos)} productos...")

        prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90"

        try:
            prod_resp = requests.get(prod_url, timeout=30).json()

            if "error" in prod_resp:
                st.error(f"Error Keepa API: {prod_resp['error'].get('message', 'Clave inválida')}")
                return

            productos = []
            for prod in prod_resp.get("products", []):
                asin = prod.get("asin", "N/A")
                title = prod.get("title", "Sin Título")
                brand = (prod.get("brand") or "Desconocida").strip()
                stats = prod.get("stats", {})

                # Vendedor Buy Box
                current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

                # Filtro de Marcas Directas
                if excluir_propia_marca and es_marca_bloqueada(brand, current_seller_name):
                    continue

                # Vendedores totales
                fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
                total_sellers = stats.get("retrievedOfferCount", 0) or (fba_count + 1)

                if total_sellers < min_sellers:
                    continue

                # Precio y BSR
                buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
                if buybox_cents <= 0 and "current" in stats and len(stats["current"]) > 1:
                    buybox_cents = stats["current"][1] or 0

                buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else 0.0
                bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else 0
                monthly_sold = prod.get("boughtInPastMonth", 0)

                # Financiero
                costo_est = buybox_price * 0.50
                fba_fee = buybox_price * 0.15 + 2.00
                ganancia = buybox_price - costo_est - fba_fee
                roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0

                if roi < min_roi:
                    continue

                productos.append({
                    "ASIN": asin,
                    "Producto": title[:40] + "...",
                    "Marca": brand,
                    "Total Vend.": total_sellers,
                    "Vendedor BuyBox": current_seller_name[:20] if current_seller_name else "Multivendedor",
                    "BSR 90d": bsr_90 if bsr_90 > 0 else "N/A",
                    "Ventas/Mes": monthly_sold,
                    "P. Venta ($)": round(buybox_price, 2),
                    "Costo Est. ($)": round(costo_est, 2),
                    "Ganancia ($)": round(ganancia, 2),
                    "ROI Est. (%)": round(roi, 2),
                    "Enlace": f"https://www.amazon.com/dp/{asin}"
                })

            df_resultado = pd.DataFrame(productos)
            if not df_resultado.empty:
                st.success(f"¡Se encontraron {len(df_resultado)} productos rentables!")
                st.dataframe(df_resultado, use_container_width=True)
            else:
                st.warning("Ningún producto de la lista superó los filtros de ROI, competencia o marca.")

        except Exception as e:
            st.error(f"Error procesando la solicitud: {str(e)}")
