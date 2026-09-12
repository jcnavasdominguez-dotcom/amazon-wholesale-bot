import json
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
    if not api_key:
        st.error("No se proporcionó una Keepa API Key válida.")
        return pd.DataFrame()

    selection = {
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100),
        "salesRanks_60_lte": int(max_bsr),
        "fbaOfferCount_gte": int(min_sellers),
        "fbaOfferCount_lte": int(max_sellers)
    }

    if modo == "MARCA" and marca:
        selection["title"] = marca

    cat_id = KEEPA_CATEGORIES.get(categoria)
    if cat_id:
        selection["rootCategory"] = cat_id

    query_json = json.dumps(selection)
    url = f"https://api.keepa.com/query?key={api_key}&domain=1&selection={query_json}"

    try:
        response = requests.get(url, timeout=20)
        data = response.json()

        if "error" in data:
            st.error(f"Error Keepa API: {data['error'].get('message', 'Clave inválida o sin créditos')}")
            return pd.DataFrame()

        asin_list = data.get("asinList", [])

        if not asin_list:
            st.warning("Keepa no devolvió productos con estos parámetros de búsqueda.")
            return pd.DataFrame()

        # Consultar detalles y estadísticas de los primeros 20 ASINs
        asins_str = ",".join(asin_list[:20])
        prod_url = f"https://api.keepa.com/product?key={api_key}&domain=1&asin={asins_str}&stats=90&offers=20"
        
        prod_resp = requests.get(prod_url, timeout=20)
        prod_data = prod_resp.json()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = prod.get("brand", "Desconocida")
            
            stats = prod.get("stats", {})
            current_price = stats.get("buyBoxPriceMin", 0) or 0
            buybox_price = current_price / 100.0 if current_price > 0 else min_precio

            # Métrica de BSR Promedio y Ventas Mensuales
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else max_bsr
            monthly_sold = prod.get("boughtInPastMonth", 0)

            # Nombre/Vendedor de la Buy Box
            current_seller_name = stats.get("buyBoxCurrentSellerName", "N/A")

            # Filtro contra Venta Directa del Fabricante / Marca
            if excluir_propia_marca and brand and current_seller_name:
                if brand.lower().strip() in current_seller_name.lower().strip():
                    continue

            # Estimaciones Financieras (Margen / ROI)
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + 2.00  # Estimación logística base
            ganancia = buybox_price - costo_est - fba_fee
            roi = (ganancia / costo_est) * 100 if costo_est > 0 else 0

            if roi < min_roi:
                continue

            productos.append({
                "ASIN": asin,
                "Producto": title[:45] + "...",
                "Marca": brand,
                "Vendedor BuyBox": current_seller_name[:20],
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
