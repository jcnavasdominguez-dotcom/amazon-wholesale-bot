import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": None,
    "Electrónica": 172282,
    "Hogar y Cocina": 1055398,
    "Oficina": 1064954,
    "Juguetes": 1657930
}

def ejecutar_busqueda_inversa(
    marca=None,
    categoria="Todas",
    modo="GLOBAL",
    api_key="",
    min_roi=25.0,
    max_bsr=50000,
    min_precio=15.0,
    max_precio=150.0,
    min_sellers=3,
    max_sellers=12,
    max_amazon_share=20.0,
    min_drops=30,
    usar_precio_90d=True,
    solo_estandar=True,
    prep_fee=1.50,
    inbound_fee=0.50
):
    if not api_key:
        st.error("No se proporcionó una Keepa API Key válida.")
        return pd.DataFrame()

    # Construcción de parámetros para Keepa Product Finder Query
    selection = {
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100),
        "salesRanks_60_lte": int(max_bsr),
        "fbaOfferCount_gte": int(min_sellers),
        "fbaOfferCount_lte": int(max_sellers),
        "sort": [["salesRanks_60", "asc"]]
    }

    if modo == "MARCA" and marca:
        selection["title"] = marca

    cat_id = KEEPA_CATEGORIES.get(categoria)
    if cat_id:
        selection["rootCategory"] = cat_id

    import json
    query_json = json.dumps(selection)

    url = f"https://api.keepa.com/query?key={api_key}&domain=1&selection={query_json}"

    try:
        response = requests.get(url, timeout=20)
        data = response.json()

        if "error" in data:
            st.error(f"Error Keepa: {data['error'].get('message', 'Clave inválida o sin tokens')}")
            return pd.DataFrame()

        asin_list = data.get("asinList", [])

        if not asin_list:
            st.warning("Keepa no devolvió ASINs con esos criterios. Intenta ampliar los rangos.")
            return pd.DataFrame()

        # Obtener los primeros 15 productos encontrados
        asins_str = ",".join(asin_list[:15])
        prod_url = f"https://api.keepa.com/product?key={api_key}&domain=1&asin={asins_str}&stats=90"
        
        prod_resp = requests.get(prod_url, timeout=20)
        prod_data = prod_resp.json()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            
            # Obtener precio Buy Box o Precio Nuevo
            stats = prod.get("stats", {})
            current_price = stats.get("buyBoxPriceMin", 0) or stats.get("current", [0]*10)[1] or 0
            buybox_price = current_price / 100.0 if current_price > 0 else min_precio

            # Estimación referencial de costo mayorista (50% del PVP)
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + prep_fee + inbound_fee
            ganancia = buybox_price - costo_est - fba_fee
            roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0

            productos.append({
                "ASIN": asin,
                "Producto": title[:55] + "...",
                "Precio Venta ($)": round(buybox_price, 2),
                "Costo Est. ($)": round(costo_est, 2),
                "Ganancia Est. ($)": round(ganancia, 2),
                "ROI Est. (%)": round(roi, 2),
                "Enlace": f"https://www.amazon.com/dp/{asin}"
            })

        return pd.DataFrame(productos)

    except Exception as e:
        st.error(f"Error de conexión: {str(e)}")
        return pd.DataFrame()
