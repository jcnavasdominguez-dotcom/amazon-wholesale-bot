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

MARCAS_AMAZON_PRIVADAS = ["amazon", "amazon basics", "amazonbasics", "amazon essentials", "solimo"]

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

        # Consultar detalles y estadísticas de los primeros 25 ASINs
        asins_str = ",".join(asin_list[:25])
        prod_url = f"https://api.keepa.com/product?key={api_key}&domain=1&asin={asins_str}&stats=90&offers=20"
        
        prod_resp = requests.get(prod_url, timeout=20)
        prod_data = prod_resp.json()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = prod.get("brand", "Desconocida").strip()
            brand_lower = brand.lower()

            # 1. Filtrar Marcas Propias de Amazon automáticamente
            if any(amz_brand in brand_lower for amz_brand in MARCAS_AMAZON_PRIVADAS):
                continue

            stats = prod.get("stats", {})
            
            # Conteo real de Vendedores FBA / FBM desde Keepa
            fba_count = prod.get("fbaOfferCount", 0) or stats.get("retrievedOfferCountFBA", 0) or 0
            fbm_count = prod.get("fbmOfferCount", 0) or (stats.get("retrievedOfferCount", 0) - fba_count)
            fbm_count = max(0, fbm_count)
            total_sellers = fba_count + fbm_count

            # Validación de cantidad mínima/máxima de vendedores FBA
            if fba_count < min_sellers or fba_count > max_sellers:
                continue

            # Obtener datos de la Buy Box
            current_price = stats.get("buyBoxPriceMin", 0) or 0
            buybox_price = current_price / 100.0 if current_price > 0 else min_precio

            # Extraer el vendedor actual o previo de la Buy Box
            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""
            if not current_seller_name and "buyBoxSellerIdHistory" in stats:
                history = stats.get("buyBoxSellerIdHistory", [])
                if history:
                    current_seller_name = str(history[-1])

            # 2. Exclusión de Dominio Directo del Fabricante
            if excluir_propia_marca:
                # Si el vendedor coincide con la marca o el vendedor dice "Amazon" / "Owala"
                seller_lower = current_seller_name.lower().strip()
                if brand_lower and seller_lower and (brand_lower in seller_lower or seller_lower in brand_lower):
                    continue
                if "amazon" in seller_lower or "owala" in seller_lower:
                    continue

            # Métricas de rendimiento
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else max_bsr
            monthly_sold = prod.get("boughtInPastMonth", 0)

            # Estimaciones Financieras (Margen / ROI)
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + 2.00  # Fee estimado
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
                "Total Vend.": total_sellers,
                "Vendedor BuyBox": current_seller_name[:18] if current_seller_name else "Multivendedor",
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
