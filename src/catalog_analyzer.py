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
    "yafex", "hilife", "kitsch", "innqoo", "godonlif", "cgk unlimited", "lane linen",
    "giuseppe zanotti", "gucci", "louis vuitton"
]

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa", "brand", "shop"]
    tokens = [w for w in texto.split() if w not in palabras]
    return " ".join(tokens)

def es_marca_bloqueada(brand: str, seller_name: str, offers_nuevas: list) -> bool:
    if not brand:
        return False
    brand_norm = normalizar_texto(brand)
    seller_norm = normalizar_texto(seller_name)

    # 1. Bloqueo por lista extendida de marcas directas / Private Label
    for marca_b in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_b)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    # 2. Bloqueo si el vendedor en la Buy Box es la propia marca
    if seller_norm and brand_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True

    # 3. Bloqueo si la marca es el único vendedor activo de unidades Nuevas
    for offer in offers_nuevas:
        s_name = normalizar_texto(offer.get("sellerName", ""))
        if s_name and (brand_norm in s_name or s_name in brand_norm):
            if len(offers_nuevas) <= 1:
                return True

    return False

def render_catalog_analyzer(api_key="", min_roi=0.0, min_sellers=2, max_bsr=150000, excluir_propia_marca=True, porcentaje_costo=50.0):
    st.subheader("📂 Cargar y Analizar Catálogo / Exportación de Keepa")
    st.markdown("Sube tu archivo **CSV / Excel** exportado desde Keepa Product Finder o pega una lista de **ASINs** directamente.")

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

                col_asin = None
                for col in df_input.columns:
                    if "asin" in col.lower():
                        col_asin = col
                        break

                if col_asin:
                    asins_para_procesar = df_input[col_asin].dropna().astype(str).tolist()
                    st.info(f"Se encontraron {len(asins_para_procesar)} ASINs en la columna `{col_asin}`.")
                else:
                    st.error("No se encontró una columna de ASINs en el archivo.")
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

        asins_unicos = list(dict.fromkeys(asins_para_procesar))[:100]
        asins_str = ",".join(asins_unicos)

        st.info(f"Consultando métricas en Keepa para {len(asins_unicos)} productos...")

        # Requerir ofertas explicitamente para verificar condicion Nuevo vs Usado
        prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90&offers=20"

        try:
            prod_resp = requests.get(prod_url, timeout=30).json()

            if "error" in prod_resp:
                st.error(f"Error Keepa API: {prod_resp['error'].get('message', 'Clave inválida')}")
                return

            productos = []
            for prod in prod_resp.get("products", []):
                if not prod or not prod.get("asin"):
                    continue

                asin = prod.get("asin")
                title = prod.get("title", "Sin Título")
                brand = (prod.get("brand") or "Desconocida").strip()
                stats = prod.get("stats", {}) or {}
                offers = prod.get("offers", []) or []

                # 1. FILTRO ESTRUCTURAL: Verificar únicamente vendedores en estado NUEVO
                offers_nuevas = []
                fba_nuevos = 0
                fbm_nuevos = 0

                if offers:
                    for offer in offers:
                        condition = offer.get("condition", -1)
                        is_new = (condition == 0) or offer.get("isNew", False)
                        if is_new:
                            offers_nuevas.append(offer)
                            if offer.get("isFBA", False):
                                fba_nuevos += 1
                            else:
                                fbm_nuevos += 1
                    total_nuevos = fba_nuevos + fbm_nuevos
                else:
                    fba_nuevos = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
                    total_nuevos = stats.get("retrievedOfferCount", 0)

                # Descartar productos sin stock (total_nuevos <= 0 o -2) o Private Label (< min_sellers nuevos)
                if total_nuevos < min_sellers or total_nuevos <= 0:
                    continue

                # 2. Vendedor Buy Box
                current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

                # 3. Excluir marcas directas / tiendas oficiales
                if excluir_propia_marca and es_marca_bloqueada(brand, current_seller_name, offers_nuevas):
                    continue

                # 4. Validar disponibilidad y BSR
                bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats.get("avg", [])) > 3 else 0
                if max_bsr > 0 and bsr_90 > max_bsr:
                    continue

                buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
                if buybox_cents <= 0 and "current" in stats and len(stats.get("current", [])) > 1:
                    buybox_cents = stats["current"][1] or 0

                if buybox_cents <= 0:
                    continue  # Descartar si no hay precio activo en Amazon

                buybox_price = buybox_cents / 100.0
                monthly_sold = prod.get("boughtInPastMonth", 0) or 0

                # 5. Cálculos Financieros
                costo_est = buybox_price * (porcentaje_costo / 100.0)
                fba_fee = buybox_price * 0.15 + 2.00
                ganancia = buybox_price - costo_est - fba_fee
                roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0.0

                if min_roi > 0 and roi < min_roi:
                    continue

                productos.append({
                    "ASIN": asin,
                    "Producto": title[:40] + "...",
                    "Marca": brand,
                    "Total Vend. Nuevos": total_nuevos,
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
                st.success(f"¡Se filtraron exitosamente {len(df_resultado)} productos Wholesale disponibles!")
                st.dataframe(df_resultado, use_container_width=True)
            else:
                st.warning("Ningún producto de la lista cumple con tener competencia multivendedor de productos NUEVOS activa en Amazon.")

        except Exception as e:
            st.error(f"Error procesando la solicitud: {str(e)}")
