import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": 1055398,
    "Electrónica": 172282,
    "Hogar y Cocina": 1055398,
    "Oficina": 1064954,
    "Juguetes": 1657930
}

MARCAS_AMAZON_PRIVADAS = [
    "amazon", "amazon basics", "amazonbasics", "amazon essentials", 
    "solimo", "pinzon", "presto!", "mama bear", "happy belly"
]

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa"]
    return " ".join([w for w in texto.split() if w not in palabras])

def es_dominada_por_fabricante(brand: str, seller_name: str) -> bool:
    if not brand or not seller_name:
        return False
    b_norm, s_norm = normalizar_texto(brand), normalizar_texto(seller_name)
    if not b_norm or not s_norm:
        return False
    if b_norm in s_norm or s_norm in b_norm:
        return True
    coincidencias = set(b_norm.split()).intersection(set(s_norm.split()))
    return any(len(w) > 3 for w in coincidencias)

def obtener_asins_keepa(clean_key: str, cat_id: int, modo: str, marca: str) -> list:
    """Obtiene una lista garantizada de ASINs probando múltiples endpoints de Keepa."""
    asin_list = []

    # Intento 1: Consulta por Bestsellers de la Categoría
    try:
        bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
        resp = requests.get(bs_url, timeout=15)
        data = resp.json()
        if "bestSellersList" in data and "asinList" in data["bestSellersList"]:
            asin_list = data["bestSellersList"]["asinList"]
    except Exception:
        pass

    # Intento 2: Si es por marca o falla la lista de Bestsellers, usamos la Búsqueda de Keepa
    if not asin_list:
        term = marca.strip() if (modo == "MARCA" and marca.strip()) else "best seller"
        try:
            search_url = f"https://api.keepa.com/search?key={clean_key}&domain=1&type=product&term={term}"
            resp = requests.get(search_url, timeout=15)
            data = resp.json()
            if "products" in data:
                asin_list = [p.get("asin") for p in data["products"] if p.get("asin")]
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

    # 1. Obtener ASINs mediante estrategia multi-endpoint
    asin_list = obtener_asins_keepa(clean_key, cat_id, modo, marca)

    if not asin_list:
        st.warning("No se pudieron recuperar ASINs de Keepa. Verifica los créditos de tu API Key.")
        return pd.DataFrame()

    # 2. Consultar datos y métricas detalladas para los ASINs obtenidos
    asins_str = ",".join(asin_list[:40])
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
            brand_norm = normalizar_texto(brand)

            # Excluir marcas privadas de Amazon
            if any(amz in brand_norm for amz in MARCAS_AMAZON_PRIVADAS):
                continue

            stats = prod.get("stats", {})

            # Obtener Precio
            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats["current"]) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else min_precio

            # Vendedores FBA y FBM
            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            fbm_count = prod.get("fbmOfferCount", 0) or max(0, (stats.get("retrievedOfferCount", 0) - fba_count))
            total_sellers = fba_count + fbm_count

            # BSR
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else 0

            # Vendedor BuyBox
            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            # Exclusión de Fabricante Directo o Amazon
            if excluir_propia_marca and current_seller_name:
                seller_norm = normalizar_texto(current_seller_name)
                if es_dominada_por_fabricante(brand, current_seller_name) or "amazon" in seller_norm or "owala" in seller_norm:
                    continue

            # Métricas Financieras
            monthly_sold = prod.get("boughtInPastMonth", 0)
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + 2.00
            ganancia = buybox_price - costo_est - fba_fee
            roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0

            productos.append({
                "ASIN": asin,
                "Producto": title[:40] + "...",
                "Marca": brand,
                "Vend. FBA": fba_count,
                "Vend. FBM": fbm_count,
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
        st.error(f"Error de conexión: {str(e)}")
        return pd.DataFrame()
