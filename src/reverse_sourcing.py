import os
import requests
import json
import pandas as pd

def ejecutar_busqueda_inversa(marca=None, categoria='Todas', modo='GLOBAL', api_key='', min_roi=25.0, max_bsr=50000, min_precio=15.0, max_precio=100.0, min_sellers=3, max_sellers=12, max_amazon_share=20.0, min_drops=30, usar_precio_90d=True, solo_estandar=True, prep_fee=1.50, inbound_fee=0.50):
    
    # Si no hay API Key o es la clave por defecto, avisamos al usuario
    if not api_key or len(api_key.strip()) < 15 or 'tu_keepa' in api_key:
        print('[!] Sin API Key valida. Mostrando lista de prueba estatica.')
        # Retornar una lista de aviso en el DataFrame
        return pd.DataFrame([{
            'ASIN': 'CONFIGURACION_REQUERIDA',
            'Marca': 'SISTEMA',
            'Categoría': 'N/A',
            'Titulo': 'INGRESA TU KEEPA API KEY VALIDA EN LA BARRA LATERAL PARA BUSCAR EN AMAZON REAL',
            'Precio Ref.': '$0.00',
            'BSR 90d': 0,
            'Vendedores FBA': 0,
            'BuyBox Amazon %': '0%',
            'Ventas Est./Mes': 0,
            'Tu Cuota Est.': '0 uds',
            'Costo Max Compra': '$0.00',
            'Ganancia Est.': '$0.00',
            'ROI Target': f'{min_roi}%'
        }])
        
    print('[+] Consultando servidor real de Keepa Product Finder...')
    
    # Estructura de consulta a la API de Keepa (Query Endpoint)
    query_payload = {
        'title': marca if (modo == 'MARCA' and marca) else '',
        'salesRank90DaysMin': 1,
        'salesRank90DaysMax': max_bsr,
        'buyBoxMin': int(min_precio * 100),
        'buyBoxMax': int(max_precio * 100),
        'fbaSellerCountMin': min_sellers,
        'fbaSellerCountMax': max_sellers,
        'deltaLast30Days_DROPS_min': min_drops,
        'isOversize': False if solo_estandar else None
    }
    
    # URL del endpoint oficial de Query de Keepa
    url_query = f'https://api.keepa.com/query?key={api_key.strip()}&domain=1'
    
    try:
        response = requests.post(url_query, data=json.dumps(query_payload), headers={'Content-Type': 'application/json'})
        data = response.json()
        
        # Keepa devuelve una lista de ASINs reales coincidentes
        asins_encontrados = data.get('asinList', [])
        
        if not asins_encontrados:
            return pd.DataFrame()
            
        # Consultar detalles de los primeros ASINs encontrados
        asins_str = ','.join(asins_encontrados[:20]) # Limitamos a 20 para optimizar tokens
        url_details = f'https://api.keepa.com/product?key={api_key.strip()}&domain=1&asin={asins_str}&stats=90'
        res_details = requests.get(url_details).json()
        
        resultados = []
        for prod in res_details.get('products', []):
            asin = prod.get('asin', 'N/A')
            title = prod.get('title', 'Producto sin titulo')
            brand = prod.get('brand', 'Generico')
            cat = prod.get('categoryTree', [{'name': 'General'}])[-1]['name'] if prod.get('categoryTree') else 'General'
            
            # Extraccion de precios desde stats de Keepa
            stats = prod.get('stats', {})
            buybox_price = (stats.get('buyBoxPrice', 0) or 0) / 100.0
            buybox_90d = (stats.get('avg90', [0]*30)[18] or 0) / 100.0 if stats.get('avg90') else buybox_price
            
            precio_ref = buybox_90d if (usar_precio_90d and buybox_90d > 0) else buybox_price
            if precio_ref <= 0:
                continue
                
            bsr = stats.get('current', [0]*5)[3] or 999999
            fba_sellers = stats.get('current', [0]*20)[11] or 1
            amazon_share = stats.get('buyBoxSellerIdHistory', []).count('ATVPDKIKX0DER') # ID de Amazon.com
            
            fba_fee = precio_ref * 0.35
            costos_logistica_prep = prep_fee + inbound_fee
            costo_max_permitido = (precio_ref - fba_fee - costos_logistica_prep) / (1 + (min_roi / 100))
            ganancia_estimada = (precio_ref - fba_fee - costos_logistica_prep) - costo_max_permitido
            
            tu_cuota_ventas = int(100 / (fba_sellers + 1))
            
            resultados.append({
                'ASIN': asin,
                'Marca': brand,
                'Categoría': cat,
                'Titulo': title[:50] + '...',
                'Precio Ref.': f'${precio_ref:.2f}',
                'BSR 90d': bsr,
                'Vendedores FBA': fba_sellers,
                'BuyBox Amazon %': f'{amazon_share}%',
                'Ventas Est./Mes': 'Varias',
                'Tu Cuota Est.': f'~{tu_cuota_ventas} uds/mes',
                'Costo Max Compra': f'${costo_max_permitido:.2f}',
                'Ganancia Est.': f'${ganancia_estimada:.2f}',
                'ROI Target': f'{min_roi}%'
            })
            
        return pd.DataFrame(resultados)
        
    except Exception as e:
        print(f'[Error Keepa API]: {e}')
        return pd.DataFrame()
