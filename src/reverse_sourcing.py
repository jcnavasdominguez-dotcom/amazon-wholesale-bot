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

MARCAS_AMAZON_PRIVADAS = ["amazon", "amazon basics", "amazonbasics", "amazon essentials", "solimo"]

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

    # Consulta básica a Keepa
    selection = {
        "rootCategory": cat_id,
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100)
    }

    if modo == "MARCA" and marca.strip():
        selection["title"] = marca.strip()

    url = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection)}"

    try:
        response = requests.get(url, timeout=20)
        data = response.json()

        if "error" in data:
            st.error(f"Error Keepa API: {data['error'].get('message', 'Clave inválida o sin créditos')}")
            return pd.DataFrame()

        asin_list = data.get("asinList", [])

        if not asin_list:
            st.warning("Keepa no devolvió productos. Cambia la categoría a 'Electrónica' o 'Juguetes' para verificar.")
            return pd.DataFrame()

        # Obtener detalle de ASINs
        asins_str = ",".join(asin_list[:40])
        prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90"
        
        prod_resp = requests.get(prod_url, timeout=20)
        prod_data = prod_resp.json()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = (prod.get("brand") or "Desconocida").strip()

            if any(amz in normalizar_texto(brand) for amz in MARCAS_AMAZON_PRIVADAS):
                continue

            stats = prod.get("stats", {})
            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            fbm_count = prod.get("fbmOfferCount", 0) or max(0, (stats.get("retrievedOfferCount", 0) - fba_count))
            
            if fba_count < min_sellers or fba_count > max_sellers:
                continue

            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else 0
            if max_bsr > 0 and bsr_90 > max_bsr:
                continue

            current_price = stats.get("buyBoxPriceMin", 0) or stats.get("current", [0]*10)[1] or 0
            buybox_price = current_price / 100.0 if current_price > 0 else min_precio
            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""

            if excluir_propia_marca:
                seller_norm = normalizar_texto(current_seller_name)
                if es_dominada_por_fabricante(brand, current_seller_name) or "amazon" in seller_norm or "owala" in seller_norm:
                    continue

            monthly_sold = prod.get("boughtInPastMonth", 0)
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
                "Vend. FBA": fba_count,
                "Vend. FBM": fbm_count,
                "Total Vend.": fba_count + fbm_count,
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
