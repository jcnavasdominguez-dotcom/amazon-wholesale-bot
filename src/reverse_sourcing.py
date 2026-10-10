import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": 1055398,  # Hogar y Cocina por defecto para búsquedas globales
    "Hogar y Cocina": 1055398,
    "Electrónica": 172282,
    "Oficina": 1064954,
    "Juguetes": 1657930
}

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

def es_marca_o_fabricante_directo(brand: str, seller_name: str, offers_nuevas: list) -> bool:
    if not brand:
        return False

    brand_norm = normalizar_texto(brand)
    if not brand_norm:
        return False

    for marca_bloqueada in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_bloqueada)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    seller_norm = normalizar_texto(seller_name)
    if seller_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True
        coincidencias = set(brand_norm.split()).intersection(set(seller_norm.split()))
        if any(len(w) > 3 for w in coincidencias):
            return True

    for offer in offers_nuevas:
        s_name = normalizar_texto(offer.get("sellerName", ""))
        if s_name and (brand_norm in s_name or s_name in brand_norm):
            return True

    return False

def obtener_asins_robustivo(clean_key: str, cat_id: int, min_precio: float, max_precio: float, modo: str, marca: str) -> list:
    asin_list = []

    # Intento 1: API /bestsellers de la categoría
    try:
        bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
        resp = requests.get(bs_url, timeout=15).json()
        if "bestSellersList" in resp and "asinList" in resp["bestSellersList"]:
            asin_list = resp["bestSellersList"]["asinList"]
    except Exception:
        pass

    # Intento 2: API /search por término
    if not asin_list:
        term = marca.strip() if (modo == "MARCA" and marca.strip()) else "home"
        try:
            search_url = f"https://api.keepa.com/search?key={clean_key}&domain=1&type=product&term={term}"
            resp = requests.get(search_url, timeout=15).json()
            if "products" in resp:
                asin_list = [p.get("asin") for p in resp["products"] if p.get("asin")]
        except Exception:
            pass

    return asin_list

def ejecutar_busqueda_inversa(
    marca="",
    categoria="Todas",
    modo="GLOBAL",
    api_key="",
    min_roi=20.0,
    max_bsr=150000,
    min_precio=15.0,
    max_precio=250.0,
    min_sellers=2,
    max_sellers=20,
    max_amazon_share=40.0,
    excluir_propia_marca=True
):
    clean_key = str(api_key).strip()
    if not clean_key:
        st.error("No se proporcionó una Keepa API Key válida.")
        return pd.DataFrame()

    cat_id = KEEPA_CATEGORIES.get(categoria, 1055398)

    # Verificación de tokens de la API
    try:
        t_resp = requests.get(f"https://api.keepa.com/tokens?key={clean_key}", timeout=10).json()
        if "tokensLeft" in t_resp:
            st.info(f"🔑 Estado API Keepa: {t_resp['tokensLeft']} tokens disponibles.")
            if t_resp["tokensLeft"] <= 0:
                st.error("Tu API Key de Keepa no tiene tokens disponibles actualmente.")
                return pd.DataFrame()
    except Exception:
        pass

    asin_list = obtener_asins_robustivo(clean_key, cat_id, min_precio, max_precio, modo, marca)

    if not asin_list:
        st.error("La API de Keepa no devolvió productos para la consulta.")
        return pd.DataFrame()

    # Procesar muestra de hasta 100 ASINs
    asins_str = ",".join(asin_list[:100])
    prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90&offers=20"

    try:
        prod_resp = requests.get(prod_url, timeout=25)
        prod_data = prod_resp.json()

        if "error" in prod_data:
            st.error(f"Error Keepa API: {prod_data['error'].get('message', 'Clave inválida')}")
            return pd.DataFrame()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = (prod.get("brand") or "Desconocida").strip()
            stats = prod.get("stats", {})
            offers = prod.get("offers", [])

            # 1. Contar ofertas en condición NUEVO
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
                fbm_nuevos = prod.get("fbmOfferCount", 0) or max(0, (stats.get("retrievedOfferCount", 0) - fba_nuevos))
                total_nuevos = fba_nuevos + fbm_nuevos

            # Excluir Private Label o listings sin competencia multivendedor de productos nuevos
            if total_nuevos < min_sellers:
                continue

            # 2. Vendedor de la Buy Box
            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            # Excluir fabricantes y marcas directas
            if excluir_propia_marca and es_marca_o_fabricante_directo(brand, current_seller_name, offers_nuevas):
                continue

            # 3. Validar precio
            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats["current"]) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else min_precio

            if buybox_price < min_precio or buybox_price > max_precio:
                continue

            # 4. Ranking BSR
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else 0
            if max_bsr > 0 and bsr_90 > max_bsr:
                continue

            monthly_sold = prod.get("boughtInPastMonth", 0)

            # 5. Cálculos Financieros
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
                "Vend. FBA (Nuevos)": fba_nuevos,
                "Vend. FBM (Nuevos)": fbm_nuevos,
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

        return pd.DataFrame(productos)

    except Exception as e:
        st.error(f"Error de ejecución: {str(e)}")
        return pd.DataFrame()
