# -*- coding: utf-8 -*-
"""
Script de benchmark para comparar los tiempos de procesamiento de los 3 métodos
de integración: default, custom_windows y deconvolution.

Este script es independiente de la GUI y se ejecuta directamente desde consola.

Uso:
    python benchmark_methods.py --input_dir F:/TEM/Muestra5C --elements "Al, Fe, Si"
"""

import argparse
import glob
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict

from pathlib import Path
import sys
import logging

# Sube los niveles necesarios para llegar a la carpeta que contiene a 'core' y 'tests'
# Si tests y core están dentro de 'eds_tem_analysis', .parent.parent es correcto.
# Si core está un nivel más arriba, añade un .parent extra.
ROOT_DIR = Path(__file__).resolve().parent.parent 

# Imprime esto temporalmente para verificar a dónde apunta exactamente:
print(f"DEBUG - ROOT_DIR actual: {ROOT_DIR}")
print(f"DEBUG - Contenido de ROOT_DIR: {[p.name for p in ROOT_DIR.iterdir()]}")

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ahora importamos
import hyperspy.api as hs
import pandas as pd

from core.quantification import quantify_spectrum
from core.perform_deconvolution import perform_deconvolution
from utils.helpers import extract_kfactors

# Ahora sí funcionan los imports del proyecto
import hyperspy.api as hs
import pandas as pd


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def benchmark_method(
    spc_files: List[str],
    elements_data: List[Dict],
    method_name: str,
    use_deconvolution: bool = False,
    integration_windows: List[float] = None,
    background_windows: float = None,
    num_samples: int = 10,
) -> Dict:
    """
    Ejecuta el método especificado sobre num_samples espectros y retorna estadísticas de tiempo.
    """
    times = []
    results = []
    
    # Limitar a num_samples espectros para el benchmark
    files_to_process = spc_files[:num_samples]
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking method: {method_name}")
    logger.info(f"Processing {len(files_to_process)} spectra...")
    logger.info(f"{'='*60}")
    
    for i, spc_file in enumerate(files_to_process, 1):
        try:
            # Cargar espectro
            signal = hs.load(spc_file, signal_type='EDS_TEM')
            
            # Medir tiempo de cuantificación
            start = time.perf_counter()
            
            result = quantify_spectrum(
                signal=signal,
                elements_data=elements_data,
                min_total_counts=0,  # Desactivar filtro de cuentas para el benchmark
                min_weight_percent=1.0,
                snr_umbral=0.0,  # Desactivar filtro SNR
                method='CL',
                composition_units='weight',
                auto_refine=False,  # Desactivar refinamiento para medir solo la cuantificación
                use_deconvolution=use_deconvolution,
                integration_windows=integration_windows,
                background_windows=background_windows,
            )
            
            end = time.perf_counter()
            elapsed = end - start
            
            # Verificar qué método se usó realmente
            method_used = result.get('method', 'unknown')
            
            times.append(elapsed)
            results.append({
                'file': Path(spc_file).name,
                'time': elapsed,
                'valid': result.get('valid', False),
                'elements': len(result.get('composition', [])),
                'method_used': method_used,
            })
            
            logger.info(f"[{i}/{len(files_to_process)}] {Path(spc_file).name}: {elapsed:.3f} s (method: {method_used})")
            
        except Exception as e:
            logger.error(f"Error processing {spc_file}: {e}")
            times.append(0.0)
            results.append({
                'file': Path(spc_file).name,
                'time': 0.0,
                'valid': False,
                'elements': 0,
                'method_used': method_name,
                'error': str(e),
            })
    
    # Calcular estadísticas
    valid_times = [t for t in times if t > 0]
    
    stats = {
        'method': method_name,
        'total_spectra': len(files_to_process),
        'successful': len(valid_times),
        'failed': len(times) - len(valid_times),
        'mean_time': sum(valid_times) / len(valid_times) if valid_times else 0.0,
        'median_time': sorted(valid_times)[len(valid_times)//2] if valid_times else 0.0,
        'min_time': min(valid_times) if valid_times else 0.0,
        'max_time': max(valid_times) if valid_times else 0.0,
        'std_time': (sum((t - sum(valid_times)/len(valid_times))**2 for t in valid_times) / len(valid_times))**0.5 if valid_times else 0.0,
        'total_time': sum(valid_times),
        'results': results,
    }
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Benchmark EDS integration methods')
    parser.add_argument('--input_dir', type=str, required=True, help='Directory containing .spc files')
    parser.add_argument('--elements', type=str, default='Al, Fe, Si', help='Comma-separated list of elements')
    parser.add_argument('--num_samples', type=int, default=10, help='Number of spectra to process per method')
    parser.add_argument('--kfactor_file', type=str, default='resources/kfactor.txt', help='Path to kfactor file')
    parser.add_argument('--output', type=str, default='benchmark_results.csv', help='Output CSV file')
    
    args = parser.parse_args()
    
    # Buscar archivos .spc
    spc_files = glob.glob(f"{args.input_dir}/*.spc")
    if not spc_files:
        logger.error(f"No .spc files found in {args.input_dir}")
        return
    
    logger.info(f"Found {len(spc_files)} .spc files in {args.input_dir}")
    
    # Cargar k-factors
    elements_data = extract_kfactors(args.elements, args.kfactor_file)
    if not elements_data:
        logger.error("No elements data loaded. Check kfactor file and element list.")
        return
    
    logger.info(f"Elements: {[e['elemento'] for e in elements_data]}")
    
    # Definir los 3 métodos
    methods = [
        {
            'name': 'default',
            'use_deconvolution': False,
            'integration_windows': None,
            'background_windows': None,
        },
        {
            'name': 'custom_windows',
            'use_deconvolution': False,
            'integration_windows': [4.0, 4.0],
            'background_windows': 2.0,
        },
        {
            'name': 'deconvolution',
            'use_deconvolution': True,
            'integration_windows': None,
            'background_windows': None,
        },
    ]
    
    # Ejecutar benchmark para cada método
    all_stats = []
    for method in methods:
        stats = benchmark_method(
            spc_files=spc_files,
            elements_data=elements_data,
            method_name=method['name'],
            use_deconvolution=method['use_deconvolution'],
            integration_windows=method['integration_windows'],
            background_windows=method['background_windows'],
            num_samples=args.num_samples,
        )
        all_stats.append(stats)
    
    # Mostrar resumen
    logger.info(f"\n{'='*60}")
    logger.info("BENCHMARK SUMMARY")
    logger.info(f"{'='*60}")
    
    for stats in all_stats:
        logger.info(f"\nMethod: {stats['method']}")
        logger.info(f"  Successful: {stats['successful']}/{stats['total_spectra']}")
        logger.info(f"  Mean time: {stats['mean_time']:.3f} s/spectrum")
        logger.info(f"  Median time: {stats['median_time']:.3f} s/spectrum")
        logger.info(f"  Std dev: {stats['std_time']:.3f} s")
        logger.info(f"  Range: [{stats['min_time']:.3f}, {stats['max_time']:.3f}] s")
        logger.info(f"  Total time: {stats['total_time']:.3f} s")
    
    # Guardar resultados en CSV
    df_results = pd.DataFrame()
    for stats in all_stats:
        for result in stats['results']:
            result['method'] = stats['method']
        df_method = pd.DataFrame(stats['results'])
        df_results = pd.concat([df_results, df_method], ignore_index=True)
    
    df_results.to_csv(args.output, index=False)
    logger.info(f"\nResults saved to {args.output}")
    
    # Calcular speedup relativo al método default
    default_time = next((s['mean_time'] for s in all_stats if s['method'] == 'default'), 1.0)
    
    logger.info(f"\n{'='*60}")
    logger.info("RELATIVE SPEED (compared to default)")
    logger.info(f"{'='*60}")
    for stats in all_stats:
        speedup = stats['mean_time'] / default_time if default_time > 0 else 0
        logger.info(f"{stats['method']}: {speedup:.2f}x")


if __name__ == '__main__':
    main()