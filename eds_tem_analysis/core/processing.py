# -*- coding: utf-8 -*-
"""
Módulo de procesamiento de espectros EDS.
"""

import os
import logging
from pathlib import Path
import pandas as pd
import threading

from core.quantification import quantify_spectrum
from report.pdf_generator import generate_pdf_from_signal
from load.loader import load_spectrum, archivo_spot

_print_lock = threading.Lock()
logger = logging.getLogger(__name__)


def process_spectrum(
    spc_file: str,
    xml_files: list,
    idx: int,
    muestra: str,
    cuentas_minimas: float,
    elementos_data: list,
    output_dir: str = "salida",
    units: str = "weight",
    umbral: float = 1.0,
    snr_umbral: float = 3.0, 
    generate_pdf: bool = True,
    cancel_event: threading.Event = None,
    verbose: bool = True
):
    """
    Procesa un archivo .spc individual, realizando la cuantificación y generando el PDF.
    verbose: Si True, imprime resultados en consola.
    Retorna: (result, out_text, err_text, Area, Spot, df_composition)
    """
    
    # Comprobar cancelación
    if cancel_event and cancel_event.is_set():
        return None
    
    # Determinar Area y Spot
    if xml_files:
        try:
            a_s = archivo_spot(xml_files)
            Area = a_s[0][idx] if idx < len(a_s[0]) else muestra
            Spot = a_s[1][idx] if idx < len(a_s[1]) else f"Punto_{idx+1}"
        except Exception as e:
            logger.error(f"Error al procesar XML: {e}. Usando valores por defecto.")
            Area = muestra
            Spot = f"Punto_{idx+1}"
    else:
        Area = muestra
        Spot = f"Punto_{idx+1}"

    if cancel_event and cancel_event.is_set():
        return None

    # Cargar espectro
    signal = load_spectrum(spc_file, lazy=False)

    if cancel_event and cancel_event.is_set():
        return None

    # Cuantificar
    metadata = {"Area": Area, "Spot": Spot}
    result = quantify_spectrum(
        signal=signal,
        elements_data=elementos_data,
        min_total_counts=cuentas_minimas,  
        min_weight_percent=umbral,
        snr_umbral=snr_umbral,
        method='CL',
        composition_units=units,
        auto_refine=True,
        metadata=metadata
    )


    if cancel_event and cancel_event.is_set():
        return None

    # Obtener total_counts del resultado
    total_counts = result.get('total_counts', 0.0)
    
    energy_dict = result.get('energy_dict', {})
    line_dict = result.get('line_dict', {})

    # Si no es válido, registrar y salir
    if not result['valid']:
        with open(os.path.join(output_dir, "CuentasInsuficientes.txt"), "a") as f:
            f.write(f"Eliminar Archivo - {Area} - {Spot} - Cuentas Insuficientes - #Cuentas: {total_counts:.0f}\n")
        logger.info(f"Eliminar Archivo {Area} {Spot} - Cuentas Insuficientes #Cuentas: {total_counts:.0f}")
        return {
            'valid': False,
            'Area': Area,
            'Spot': Spot,
            'total_counts': total_counts,
            'composition': pd.DataFrame(),
            'error': 'Cuentas insuficientes'
        }

    # Actualizar elementos_data con los resultados
    df = result['composition']
    for elem in elementos_data:
        elem['wt'] = 0.0
        elem['intensidad'] = 0.0
    for _, row in df.iterrows():
        elem_name = row['Elemento']
        for elem in elementos_data:
            if elem['elemento'] == elem_name:
                if 'wt.%' in row:
                    elem['wt'] = row['wt.%']
                elif 'at.%' in row:
                    elem['wt'] = row['at.%']
                elem['intensidad'] = row['Intensidad']
                if elem_name in energy_dict:
                    elem['energia_keV'] = energy_dict[elem_name]
                    elem['linea'] = line_dict.get(elem_name, 'Ka')
                break

    # --- SALIDA EN TERMINAL (opcional) ---
    if verbose:
        if units == 'weight':
            unit_label = 'wt.%'
        else:
            unit_label = 'at.%'
        with _print_lock:
            print("\n #### Resultado EDS, Analisis con HyperSpy ####")
            print(f"Archivo {Area} {Spot} # Cuentas: {total_counts:.2f}")
            print('|-------------------------------|---------------|')
            print('|     Composición en masa       |    Calidad    |')
            print('|-------------------------------|---------------|')
            print(f'|    Elemento  |     {unit_label}     |   Intensidad  |')
            print('|-------------------------------|---------------|')
            for elem in elementos_data:
                if elem['wt'] > 0.0:
                    print(f"| {elem['elemento']} \t\t|    {elem['wt']:.2f} \t|   {elem['intensidad']:.2f}    |")
            print('################################################\n')



    if cancel_event and cancel_event.is_set():
        return None
    # --- Generar PDF (solo si está habilitado) ---
    percent_col = 'wt.%' if units == 'weight' else 'at.%'
    unit_label = percent_col
    if generate_pdf:
        filtro_df = df[df[percent_col] > 0].copy()
        
        if not filtro_df.empty:
            # Asegurar columna Intensidad
            if 'Intensidad' not in filtro_df.columns:
                intensidades = []
                for elem in filtro_df['Elemento']:
                    for e in elementos_data:
                        if e['elemento'] == elem:
                            intensidades.append(e['intensidad'])
                            break
                filtro_df['Intensidad'] = intensidades

            def sanitize_filename(name):
                import re
                return re.sub(r'[<>:"/\\|?*]', '_', name)

            safe_name = sanitize_filename(f"{Area}_{Spot}")
            output_pdf = Path(output_dir) / f"{safe_name}.pdf"
            
            generate_pdf_from_signal(
                signal=signal,
                metadata={"Area": Area, "Spot": Spot},
                df=filtro_df,
                output_path=output_pdf,
                energy_dict=energy_dict,
                line_dict=line_dict,
                percent_col=percent_col,
                unit_label=unit_label,
            )

    return {
        'valid': True,
        'Area': Area,
        'Spot': Spot,
        'total_counts': total_counts,
        'composition': df,
        'energy_dict': energy_dict,
        'line_dict': line_dict,
        'nombre_archivo_spc': Path(spc_file).name,
        'error': None
    }