import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": 1055398,  # Hogar y Cocina por defecto
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

def es_marca_bloqueada(brand: str, seller_name: str) -> bool:
    if not brand:
        return False

    brand_norm = normalizar_texto(brand)
    seller_norm = normalizar_texto(seller_name)

    # Bloqueo por lista negra
    for marca_b in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_b)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    # Coincidencia directa entre Marca y Vendedor Buy Box (Fabricante directo)
    if seller_norm and brand_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True

    return False

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

    # 1. Verificar tokens antes de ejecutar
    try:
        t_resp = requests.get(f"https://api.keepa.com/tokens?key={clean_key}", timeout=10).json()
        if "tokensLeft" in t_resp:
            st.info(f"🔑 Tokens disponibles antes de la consulta: {t_resp['tokensLeft']}")
            if t_resp["tokensLeft"] < 10:
                st.error("Tokens insuficientes (<10). Espera unos minutos para recargar.")
                return pd.DataFrame()
    except Exception:
        pass

    # 2. QUERY OPTIMIZADA: Filtra productos directamente en los servidores de Keepa
    selection = {
        "rootCategory": cat_id,
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100),
        "offerCount_gte": int(min_sellers),
        "buyBoxIsAmazon": False
    }

    if modo == "MARCA" and marca.strip():
        selection["title"] = marca.strip()

    try:
        q_url = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection)}"
        q_resp = requests.get(q_url, timeout=20).json()
        asin_list = q_resp.get("asinList", [])

        if not asin_list:
            st.warning("Keepa no encontró productos con estos filtros exactos. Prueba ampliar el rango de precios.")
            return pd.DataFrame()

        # 3. Descargar únicamente los primeros 25 productos pre-filtrados (Ahorro máximo de tokens)
        asins_str = ",".join(asin_list[:25])
        prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90"
        
        prod_resp = requests.get(prod_url, timeout=25).json()

        productos = []
        for prod in prod_resp.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = (prod.get("brand") or "Desconocida").strip()
            stats = prod.get("stats", {})

            # Obtener vendedor Buy Box
            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            # Excluir marcas directas/fabricantes
            if excluir_propia_marca and es_marca_bloqueada(brand, current_seller_name):
                continue

            # Precio de la Buy Box o precio Nuevo
            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats["current"]) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else min_precio

            # BSR
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else 0
            monthly_sold = prod.get("boughtInPastMonth", 0)

            # Conteo de vendedores
            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            total_sellers = stats.get("retrievedOfferCount", 0) or (fba_count + 1)

            # Cálculos Financieros
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + 2.00
            ganancia = buybox_price - costo_est - fba_fee
            roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0

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

        return pd.DataFrame(productos)

    except Exception as e:
        st.error(f"Error en la consulta: {str(e)}")
        return pd.DataFrame()
