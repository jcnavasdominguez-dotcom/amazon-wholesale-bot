import json
import re
import requests
import pandas as pd
import streamlit as st

KEEPA_CATEGORIES = {
    "Todas": 1055398,  # Hogar y Cocina como categoría principal por defecto
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
    """Limpia cadenas para comparaciones homogéneas entre marcas y vendedores."""
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras_irrelevantes = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa"]
    tokens = [w for w in texto.split() if w not in palabras_irrelevantes]
    return " ".join(tokens)

def es_dominada_por_fabricante(brand: str, seller_name: str) -> bool:
    """Compara si la Buy Box pertenece al fabricante o dueño de la marca."""
    if not brand or not seller_name:
        return False
    
    brand_norm = normalizar_texto(brand)
    seller_norm = normalizar_texto(seller_name)
    
    if not brand_norm or not seller_norm:
        return False

    if brand_norm in seller_norm or seller_norm in brand_norm:
        return True
    
    brand_tokens = set(brand_norm.split())
    seller_tokens = set(seller_norm.split())
    coincidencias = brand_tokens.intersection(seller_tokens)
    return any(len(word) > 3 for word in coincidencias)

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

    # 1. Petición primaria compatible con Keepa Query API
    selection = {
        "rootCategory": cat_id,
        "current_NEW_gte": int(min_precio * 100),
        "current_NEW_lte": int(max_precio * 100)
    }

    if modo == "MARCA" and marca.strip():
        selection["title"] = marca.strip()

    url = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection)}"

    try:
        response = requests.get(url, timeout=25)
        data = response.json()

        if "error" in data:
            st.error(f"Error Keepa API: {data['error'].get('message', 'Clave inválida o sin créditos')}")
            return pd.DataFrame()

        asin_list = data.get("asinList", [])

        # Plan B de la API: Si no trae ASINs, consulta general por categoría sin rango de precio estricto
        if not asin_list:
            selection_b = {"rootCategory": cat_id}
            if modo == "MARCA" and marca.strip():
                selection_b["title"] = marca.strip()
            
            url_b = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection_b)}"
            resp_b = requests.get(url_b, timeout=25)
            asin_list = resp_b.json().get("asinList", [])

        if not asin_list:
            st.warning("Keepa no devolvió ASINs para esta búsqueda. Selecciona una categoría específica como 'Juguetes' o 'Electrónica'.")
            return pd.DataFrame()

        # 2. Consultar datos extendidos de los primeros 40 ASINs
        asins_str = ",".join(asin_list[:40])
        prod_url = f"https://api.keepa.com/product?key={clean_key}&domain=1&asin={asins_str}&stats=90&offers=20"
        
        prod_resp = requests.get(prod_url, timeout=25)
        prod_data = prod_resp.json()

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

            # Obtener Precio (Buy Box o Precio Nuevo actual como alternativa)
            buybox_cents = stats.get("buyBoxPriceMin", 0) or 0
            if buybox_cents <= 0 and "current" in stats and len(stats["current"]) > 1:
                buybox_cents = stats["current"][1] or 0

            buybox_price = buybox_cents / 100.0 if buybox_cents > 0 else 0

            # Validar rango de precio en Python (permitir margen amplio si el precio recuperado es válido)
            if buybox_price > 0 and (buybox_price < (min_precio * 0.8) or buybox_price > (max_precio * 1.2)):
                continue
            if buybox_price <= 0:
                buybox_price = min_precio  # Asignación referencial mínima si no hay precio directo

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
        st.error(f"Error de ejecución: {str(e)}")
        return pd.DataFrame()
