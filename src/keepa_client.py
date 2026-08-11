import requests
import os

def consultar_producto_keepa(upc, api_key, domain=1):
    if not api_key or api_key == 'tu_keepa_api_key_aqui':
        # Modo simulacion si no hay API Key cargada
        return {
            'asin': f'ASIN_MOCK_{upc[-4:]}',
            'titulo': 'Producto Simulado para Prueba',
            'precio_venta': 29.99,
            'bsr_90': 18500,
            'amazon_buybox': False,
            'exito': True,
            'modo': 'SIMULACION'
        }

    url = f'https://api.keepa.com/product?key={api_key}&domain={domain}&code={upc}&stats=90'
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'products' in data and len(data['products']) > 0:
            product = data['products'][0]
            stats = product.get('stats', {})
            
            # Convertir precios (Keepa maneja precios x100)
            current_price = stats.get('current', [0, 0])[1] / 100.0
            avg_bsr_90 = stats.get('avg', [0, 0, 0, 0])[3]
            amazon_in_buybox = stats.get('buyBoxIsAmazon', False)
            
            return {
                'asin': product.get('asin'),
                'titulo': product.get('title'),
                'precio_venta': current_price,
                'bsr_90': avg_bsr_90,
                'amazon_buybox': amazon_in_buybox,
                'exito': True,
                'modo': 'REAL'
            }
    except Exception as e:
        print(f'[!] Error consultando UPC {upc}: {e}')
    
    return {'exito': False}
