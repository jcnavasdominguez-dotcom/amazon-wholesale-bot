import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": 1055398,
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
    "yafex", "hilife", "kitsch", "innqoo", "godonlif", "cgk unlimited", "lane linen"
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

    for marca_b in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_b)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    if seller_norm and brand_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True

    for offer in offers_nuevas:
        s_name = normalizar_texto(offer.get("sellerName", ""))
        if s_name and (brand_norm in s_name or s_name in brand_norm):
            if len(offers_nuevas) <= 1:
                return True

    return False

def ejecutar_busqueda_inversa(
    marca="",
    categoria="Todas",
    modo="GLOBAL",
    api_key="",
    min_roi=0.0,
    max_bsr=150000,
    min_precio=15.0,
    max_precio=250.0,
    min_sellers=2,
    max_sellers=20,
    max_amazon_share=40.0,
    excluir_propia_marca=True,
    porcentaje_costo=50.0
):
    clean_key = str(api_key).strip()
    if not clean_key:
        st.error("No se proporcionó una Keepa API Key válida.")
        return pd.DataFrame()

    cat_id = KEEPA_CATEGORIES.get(categoria, 1055398)

    # Consulta a Product Finder /query exigiendo productos NUEVOS
    selection = {
        "rootCategory": cat_id,
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100),
        "offerCount_gte": int(min_sellers),
        "buyBoxIsAmazon": False
    }

    if modo == "MARCA" and marca.strip():
        selection["title"] = marca.strip()

    asin_list = []
    try:
        q_url = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection)}"
        resp = requests.get(q_url, timeout=15).json()
        if "asinList" in resp and resp["asinList"]:
            asin_list = resp["asinList"]
    except Exception:
        pass

    if not asin_list:
        try:
            bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
            resp = requests.get(bs_url, timeout=15).json()
            if "bestSellersList" in resp and "asinList" in resp["bestSellersList"]:
                asin_list = resp["bestSellersList"]["asinList"]
        except Exception:
            pass

    if not asin_list:
        st.warning("Keepa no devolvió productos activos para los criterios seleccionados.")
        return pd.DataFrame()

    asins_str = ",".join(asin_list[:40])
    prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90&offers=20"

    try:
        prod_resp = requests.get(prod_url, timeout=25).json()

        if "error" in prod_resp:
            st.error(f"Error Keepa API: {prod_resp['error'].get('message', 'Clave inválida')}")
            return pd.DataFrame()

        productos = []
        for prod in prod_resp.get("products", []):
            if not prod or not prod.get("asin"):
                continue

            asin = prod.get("asin")
            title = prod.get("title", "Sin Título")
            brand = (prod.get("brand") or "Desconocida").strip()
            stats = prod.get("stats", {}) or {}
            offers = prod.get("offers", []) or []

            # Filtrar exclusivamente ofertas en condición NUEVO
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
                total_nuevos = stats.get("retrievedOfferCount", 0)

            # Excluir si no hay suficientes vendedores de unidades Nuevas o no hay disponibilidad
            if total_nuevos < min_sellers or total_nuevos <= 0:
                continue

            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            if excluir_propia_marca and es_marca_bloqueada(brand, current_seller_name, offers_nuevas):
                continue

            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats.get("current", [])) > 1:
                buybox_cents = stats["current"][1] or 0

            if buybox_cents <= 0:
                continue

            buybox_price = buybox_cents / 100.0
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats.get("avg", [])) > 3 else 0
            
            if max_bsr > 0 and bsr_90 > max_bsr:
                continue

            monthly_sold = prod.get("boughtInPastMonth", 0) or 0

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

        return pd.DataFrame(productos)

    except Exception as e:
        st.error(f"Error procesando búsqueda: {str(e)}")
        return pd.DataFrame()
