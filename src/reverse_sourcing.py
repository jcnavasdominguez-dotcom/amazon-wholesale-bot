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
    "apple", "dyson", "sony", "samsung", "bose", "lego", "owala", "celsius"
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

    # Búsqueda por Bestsellers (Consumo: 1 Token)
    asin_list = []
    try:
        bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
        resp = requests.get(bs_url, timeout=15).json()
        if "bestSellersList" in resp and "asinList" in resp["bestSellersList"]:
            asin_list = resp["bestSellersList"]["asinList"]
    except Exception:
        pass

    if not asin_list:
        term = marca.strip() if (modo == "MARCA" and marca.strip()) else "kitchen"
        try:
            search_url = f"https://api.keepa.com/search?key={clean_key}&domain=1&type=product&term={term}"
            resp = requests.get(search_url, timeout=15).json()
            if "products" in resp:
                asin_list = [p.get("asin") for p in resp["products"] if p.get("asin")]
        except Exception:
            pass

    if not asin_list:
        st.error("No se pudieron recuperar productos desde Keepa.")
        return pd.DataFrame()

    # Procesar sólo 12 ASINs por consulta para respetar el límite de 21 tokens/min
    asins_str = ",".join(asin_list[:12])
    prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90"

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

            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            if excluir_propia_marca and es_marca_bloqueada(brand, current_seller_name):
                continue

            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            fbm_count = prod.get("fbmOfferCount", 0) or 0
            total_sellers = stats.get("retrievedOfferCount", 0) or (fba_count + fbm_count)

            if total_sellers <= 0 or (min_sellers > 0 and total_sellers < min_sellers):
                continue

            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats.get("current", [])) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else min_precio
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats.get("avg", [])) > 3 else 0
            monthly_sold = prod.get("boughtInPastMonth", 0) or 0

            costo_est = buybox_price * (porcentaje_costo / 100.0)
            fba_fee = buybox_price * 0.15 + 2.00
            ganancia = buybox_price - costo_est - fba_fee
            roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0.0

            productos.append({
                "ASIN": asin,
                "Producto": title[:40] + "...",
                "Marca": brand,
                "Vend. FBA": fba_count,
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

        return pd.DataFrame(productos)

    except Exception as e:
        st.error(f"Error procesando búsqueda: {str(e)}")
        return pd.DataFrame()
