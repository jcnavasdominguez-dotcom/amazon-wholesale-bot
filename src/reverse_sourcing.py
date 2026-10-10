import json
import re
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

MARCAS_AMAZON_PRIVADAS = [
    "amazon", "amazon basics", "amazonbasics", "amazon essentials", 
    "solimo", "pinzon", "presto!", "mama bear", "happy belly"
]

def normalizar_texto(texto: str) -> str:
    """Limpia y normaliza cadenas para comparaciones precisas entre marca y vendedor."""
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras_irrelevantes = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa"]
    tokens = [w for w in texto.split() if w not in palabras_irrelevantes]
    return " ".join(tokens)

def es_dominada_por_fabricante(brand: str, seller_name: str) -> bool:
    """Determina si la Buy Box pertenece directamente al fabricante o dueño de la marca."""
    if not brand or not seller_name:
        return False
    
    brand_norm = normalizar_texto(brand)
    seller_norm = normalizar_texto(seller_name)
    
    if not brand_norm or not seller_norm:
        return False

    if brand_norm in seller_norm or seller_norm in brand_norm:
        return True
    
    # Comprobar coincidencia por palabras clave
    brand_tokens = set(brand_norm.split())
    seller_tokens = set(seller_norm.split())
    if brand_tokens and seller_tokens and len(brand_tokens.intersection(seller_tokens)) >= 1:
        # Evitar falsos positivos en palabras comunes cortas
        coincidencias = brand_tokens.intersection(seller_tokens)
        if any(len(word) > 3 for word in coincidencias):
            return True

    return False

def extraer_conteo_vendedores(prod: dict, stats: dict) -> tuple:
    """Extrae con precisión el conteo de vendedores FBA, FBM y total desde el payload de Keepa."""
    fba_count = prod.get("fbaOfferCount", 0)
    if not fba_count or fba_count == 0:
        fba_count = stats.get("retrievedOfferCountFBA", 0) or 0

    total_retrieved = stats.get("retrievedOfferCount", 0) or 0
    fbm_count = prod.get("fbmOfferCount", 0)
    if not fbm_count or fbm_count == 0:
        fbm_count = max(0, total_retrieved - fba_count)

    total_sellers = fba_count + fbm_count
    return fba_count, fbm_count, total_sellers

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

    # 1. Parámetros de consulta principal en Keepa Product Finder API
    selection = {
        "current_BUY_BOX_SHIPPING_gte": int(min_precio * 100),
        "current_BUY_BOX_SHIPPING_lte": int(max_precio * 100),
        "salesRank_gte": 1,
        "salesRank_lte": int(max_bsr),
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
        response = requests.get(url, timeout=25)
        data = response.json()

        if "error" in data:
            st.error(f"Error Keepa API: {data['error'].get('message', 'Clave inválida o sin créditos')}")
            return pd.DataFrame()

        asin_list = data.get("asinList", [])

        # 2. Reintento secundario de respaldo en caso de cero resultados por Buy Box estricta
        if not asin_list:
            selection_alt = {
                "current_NEW_gte": int(min_precio * 100),
                "current_NEW_lte": int(max_precio * 100),
                "salesRank_lte": int(max_bsr)
            }
            if cat_id:
                selection_alt["rootCategory"] = cat_id
            if modo == "MARCA" and marca:
                selection_alt["title"] = marca

            query_json_alt = json.dumps(selection_alt)
            url_alt = f"https://api.keepa.com/query?key={api_key}&domain=1&selection={query_json_alt}"
            resp_alt = requests.get(url_alt, timeout=25)
            data_alt = resp_alt.json()
            asin_list = data_alt.get("asinList", [])

        if not asin_list:
            st.warning("Keepa no devolvió productos con estos parámetros. Intenta ampliar los rangos de BSR o ajustar los límites de precio.")
            return pd.DataFrame()

        # 3. Solicitud de detalles extendidos de productos (limitado a los primeros 30 ASINs)
        asins_str = ",".join(asin_list[:30])
        prod_url = f"https://api.keepa.com/product?key={api_key}&domain=1&asin={asins_str}&stats=90&offers=20"
        
        prod_resp = requests.get(prod_url, timeout=25)
        prod_data = prod_resp.json()

        productos = []
        for prod in prod_data.get("products", []):
            asin = prod.get("asin", "N/A")
            title = prod.get("title", "Sin Título")
            brand = (prod.get("brand") or "Desconocida").strip()
            brand_norm = normalizar_texto(brand)

            # A. Exclusión de Marcas Privadas de Amazon
            if any(amz_brand in brand_norm for amz_brand in MARCAS_AMAZON_PRIVADAS):
                continue

            stats = prod.get("stats", {})

            # B. Métricas de Vendedores (FBA / FBM)
            fba_count, fbm_count, total_sellers = extraer_conteo_vendedores(prod, stats)
            
            if fba_count < min_sellers or fba_count > max_sellers:
                continue

            # C. Evaluación de la Buy Box
            current_price = stats.get("buyBoxPriceMin", 0) or stats.get("current", [0]*10)[1] or 0
            buybox_price = current_price / 100.0 if current_price > 0 else min_precio

            current_seller_name = stats.get("buyBoxCurrentSellerName", "") or ""
            
            # Buscar histórico de Buy Box si el nombre actual está vacío
            if not current_seller_name and "buyBoxSellerIdHistory" in stats:
                history = stats.get("buyBoxSellerIdHistory", [])
                if history:
                    current_seller_name = str(history[-1])

            # D. Filtrado por Dominio del Fabricante / Marca Directa
            if excluir_propia_marca:
                seller_norm = normalizar_texto(current_seller_name)
                
                # Excluir si la Buy Box es del fabricante o de Amazon directamente
                if es_dominada_por_fabricante(brand, current_seller_name):
                    continue
                if "amazon" in seller_norm:
                    continue

            # E. Participación estimada de Amazon en la Buy Box (porcentaje)
            buybox_amazon_share = stats.get("buyBoxAmazon30", 0) or stats.get("buyBoxAmazon90", 0) or 0
            if buybox_amazon_share > max_amazon_share:
                continue

            # F. Métricas de ventas y BSR
            bsr_90 = stats.get("avg", [0]*100)[3] if "avg" in stats and len(stats["avg"]) > 3 else max_bsr
            monthly_sold = prod.get("boughtInPastMonth", 0)

            # G. Cálculos Financieros (Costo, Fees, Ganancia, ROI)
            costo_est = buybox_price * 0.50
            fba_fee = buybox_price * 0.15 + 2.00  # Tarifa referencial de gestión logitudinal
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
