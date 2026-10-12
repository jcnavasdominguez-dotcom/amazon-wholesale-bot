import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": None,
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

def estimar_ventas_por_bsr(bsr: int) -> int:
    """Calcula una estimación aproximada de ventas mensuales según el BSR."""
    if bsr <= 0:
        return 0
    if bsr <= 100:
        return 3000
    elif bsr <= 500:
        return 1500
    elif bsr <= 1000:
        return 800
    elif bsr <= 5000:
        return 350
    elif bsr <= 10000:
        return 180
    elif bsr <= 50000:
        return 60
    elif bsr <= 100000:
        return 20
    else:
        return 5

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

    cat_id = KEEPA_CATEGORIES.get(categoria)

    asin_list = []

    # 1. Búsqueda Bestsellers si hay categoría seleccionada
    if cat_id:
        try:
            bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
            resp = requests.get(bs_url, timeout=15).json()
            if "bestSellersList" in resp and "asinList" in resp["bestSellersList"]:
                asin_list = resp["bestSellersList"]["asinList"]
        except Exception:
            pass

    # 2. Búsqueda por término neutro en Búsqueda Global
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

    # Procesar un lote de 20 ASINs por consulta (Consumo optimizado: 1-2 tokens)
    asins_str = ",".join(asin_list[:20])
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

            # Extracción limpia de vendedores
            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            fbm_count = prod.get("fbmOfferCount", 0) or 0
            raw_sellers = stats.get("retrievedOfferCount", 0)

            # Limpiar valor numérico negativo (-2) de Keepa
            total_sellers = raw_sellers if raw_sellers > 0 else (fba_count + fbm_count if (fba_count + fbm_count) > 0 else 1)

            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats.get("current", [])) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else min_precio
            
            if buybox_price < min_precio or buybox_price > max_precio:
                continue

            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats.get("avg", [])) > 3 else 0
            
            # Estimación inteligente de ventas si Keepa no trae la insignia
            monthly_sold = prod.get("boughtInPastMonth", 0) or 0
            if monthly_sold == 0 and bsr_90 > 0:
                monthly_sold = estimar_ventas_por_bsr(bsr_90)

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
                "Ventas/Mes Est.": monthly_sold,
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
