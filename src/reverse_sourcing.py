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
    "apple", "dyson", "sony", "samsung", "bose", "lego", "owala", "celsius",
    "utopia bedding", "zulay kitchen", "hy hao yun lai", "bedsure", "bare home",
    "hatch baby", "beckham hotel collection", "cgk unlimited", "lane linen",
    "niagara sleep solution", "mellanni", "pampers", "huggies", "euhomy", "upsimples", "bedlore"
]

def normalizar_texto(texto: str) -> str:
    """Limpia cadenas para comparar marcas y vendedores sin importar formato."""
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    palabras = ["inc", "llc", "corp", "co", "ltd", "store", "official", "direct", "us", "usa", "brand", "shop"]
    tokens = [w for w in texto.split() if w not in palabras]
    return " ".join(tokens)

def es_marca_o_fabricante_directo(brand: str, seller_name: str, offers_nuevas: list) -> bool:
    """Valida si la marca vende directamente o es la tienda oficial."""
    if not brand:
        return False

    brand_norm = normalizar_texto(brand)
    if not brand_norm:
        return False

    # 1. Bloqueo por lista extendida de fabricantes/marcas directas
    for marca_bloqueada in MARCAS_EXCLUIDAS_DIRECTAS:
        m_norm = normalizar_texto(marca_bloqueada)
        if m_norm and (m_norm in brand_norm or brand_norm in m_norm):
            return True

    # 2. Bloqueo por coincidencia en vendedor Buy Box
    seller_norm = normalizar_texto(seller_name)
    if seller_norm:
        if brand_norm in seller_norm or seller_norm in brand_norm:
            return True
        coincidencias = set(brand_norm.split()).intersection(set(seller_norm.split()))
        if any(len(w) > 3 for w in coincidencias):
            return True

    # 3. Bloqueo si la marca es un vendedor en ofertas NUEVAS
    for offer in offers_nuevas:
        s_name = normalizar_texto(offer.get("sellerName", ""))
        if s_name and (brand_norm in s_name or s_name in brand_norm):
            return True

    return False

def obtener_asins_robustivo(clean_key: str, cat_id, min_precio: float, max_precio: float, modo: str, marca: str) -> list:
    """Recupera ASINs de Keepa mediante múltiples endpoints."""
    asin_list = []

    # Estrategia 1: Query API por precio y multivendedor
    try:
        selection = {
            "current_NEW_gte": int(min_precio * 100),
            "current_NEW_lte": int(max_precio * 100),
            "offerCount_gte": 2
        }
        if cat_id:
            selection["rootCategory"] = cat_id
        if modo == "MARCA" and marca.strip():
            selection["title"] = marca.strip()

        q_url = f"https://api.keepa.com/query?key={clean_key}&domain=1&selection={json.dumps(selection)}"
        resp = requests.get(q_url, timeout=15).json()
        if "asinList" in resp and resp["asinList"]:
            asin_list = resp["asinList"]
    except Exception:
        pass

    # Estrategia 2: Bestsellers si Query no devuelve datos
    if not asin_list and cat_id:
        try:
            bs_url = f"https://api.keepa.com/bestsellers?key={clean_key}&domain=1&category={cat_id}"
            resp = requests.get(bs_url, timeout=15).json()
            if "bestSellersList" in resp and "asinList" in resp["bestSellersList"]:
                asin_list = resp["bestSellersList"]["asinList"]
        except Exception:
            pass

    # Estrategia 3: Búsqueda general por término
    if not asin_list:
        term = marca.strip() if (modo == "MARCA" and marca.strip()) else "home"
        try:
            search_url = f"https://api.keepa.com/search?key={clean_key}&domain=1&type=product&term={term}"
            resp = requests.get(search_url, timeout=15).json()
            if "products" in resp:
                asin_list = [p.get("asin") for p in resp["products"] if p.get("asin")]
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

    cat_id = KEEPA_CATEGORIES.get(categoria)

    # 1. Verificar tokens de la API
    try:
        t_resp = requests.get(f"https://api.keepa.com/tokens?key={clean_key}", timeout=10).json()
        if "tokensLeft" in t_resp:
            st.info(f"🔑 Estado API Keepa: {t_resp['tokensLeft']} tokens disponibles.")
            if t_resp["tokensLeft"] <= 0:
                st.error("Tu API Key de Keepa no tiene tokens disponibles actualmente.")
                return pd.DataFrame()
    except Exception:
        pass

    # 2. Obtener lista de ASINs
    asin_list = obtener_asins_robustivo(clean_key, cat_id, min_precio, max_precio, modo, marca)

    if not asin_list:
        st.error("La API de Keepa no devolvió productos. Verifica tu saldo de tokens en Keepa.")
        return pd.DataFrame()

    # 3. Consultar detalles extendidos
    asins_str = ",".join(asin_list[:60])
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
            stats = prod.get("stats", {})
            offers = prod.get("offers", [])

            # --- CONTEO Y FILTRADO INLINE DE UNIDADES NUEVAS ---
            offers_nuevas = []
            fba_nuevos = 0
            fbm_nuevos = 0

            if offers:
                for offer in offers:
                    # Condition 0 representa 'Nuevo' en Keepa (se ignoran usados)
                    condition = offer.get("condition", -1)
                    is_new = (condition == 0) or offer.get("isNew", False)
                    if is_new:
                        offers_nuevas.append(offer)
                        if offer.get("isFBA", False):
                            fba_nuevos += 1
                        else
