import pandas as pd
import os

def cargar_catalogo(ruta_archivo, col_upc='UPC', col_costo='PRECIO_MAYORISTA'):
    if not os.path.exists(ruta_archivo):
        raise FileNotFoundError(f'El archivo {ruta_archivo} no existe.')

    print(f'[+] Cargando catalogo desde: {ruta_archivo}')
    
    # Detectar extension (csv o excel)
    if ruta_archivo.endswith('.csv'):
        df = pd.read_csv(ruta_archivo, dtype={col_upc: str})
    elif ruta_archivo.endswith(('.xls', '.xlsx')):
        df = pd.read_excel(ruta_archivo, dtype={col_upc: str})
    else:
        raise ValueError('Formato no soportado. Usa CSV o Excel.')

    # Filtrar solo las columnas necesarias y limpiar valores nulos o costo 0
    df[col_upc] = df[col_upc].str.strip()
    df[col_costo] = pd.to_numeric(df[col_costo], errors='coerce')
    
    # Conservar filas con UPC valido y Costo > 0
    df_limpio = df[df[col_upc].notna() & (df[col_costo] > 0)].copy()
    
    print(f'[OK] Filas originales: {len(df)} | Filas validas procesables: {len(df_limpio)}')
    return df_limpio
