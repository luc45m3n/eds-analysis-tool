# -*- coding: utf-8 -*-
"""
Funciones auxiliares para el análisis EDS.
"""

import re
import pandas as pd
from functools import lru_cache
from pathlib import Path
import logging
import numpy as np
import exspy

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_kfactors(filepath="kfactor.txt"):
    """
    Carga el archivo de factores K y lo cachea en memoria.
    """
    try:
        df = pd.read_csv(
            Path(filepath),
            sep=";",
            names=["elemento", "kfactor"],
            index_col="elemento"
        )
        logger.info(f"Factores K cargados desde {filepath}")
        return df
    except FileNotFoundError:
        logger.error(f"No se encontró el archivo de factores K: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Error al leer {filepath}: {e}")
        raise


def extract_kfactors(elementos_str, kfactor_file="kfactor.txt"):
    """
    Extrae los factores K para una lista de elementos.
    """
    kfactors_df = load_kfactors(kfactor_file)
    elementos = [elem.strip() for elem in elementos_str.split(",")]
    elementos_data = []
    for elem in elementos:
        if elem in kfactors_df.index:
            elementos_data.append({
                "elemento": elem,
                "kfactor": kfactors_df.loc[elem, "kfactor"],
                "intensidad": None,
                "wt": None,
                "k_alpha": None
            })
        else:
            logger.warning(f"Elemento '{elem}' no encontrado en el archivo de factores K")
    return elementos_data


def convertir_a_lista(secuencia):
    """Convierte una secuencia de objetos HyperSpy a una lista plana."""
    return [elemento.data[0] for elemento in secuencia]


def get_xray_energy(element: str, line: str = "Ka") -> float:
    """
    Obtiene la energía de una línea X-ray para un elemento usando eXspy.
    """
    try:
        element_obj = getattr(exspy.material.elements, element)
        line_obj = getattr(element_obj.Atomic_properties.Xray_lines, line)
        return line_obj.energy_keV
    except AttributeError as e:
        raise ValueError(f"Elemento '{element}' o línea '{line}' no encontrado: {e}")


def get_xray_energies_for_elements(elements: list, line: str = "Ka") -> dict:
    """
    Obtiene las energías de una línea específica para una lista de elementos.
    """
    energy_dict = {}
    for elem in elements:
        try:
            energy_dict[elem] = get_xray_energy(elem, line)
        except ValueError as e:
            logger.warning(f"No se pudo obtener energía para {elem}: {e}")
    return energy_dict


def calculate_snr(energy, y_data, x_data, window_width=0.15):
    """
    Calcula la relación señal/ruido (SNR) para un pico en 'energy' keV.
    """
    idx_peak = np.argmin(np.abs(x_data - energy))
    if idx_peak < 5 or idx_peak >= len(x_data) - 5:
        return 0.0
    
    # Región del pico
    half_width = max(1, int(window_width / 2 / (x_data[1] - x_data[0])))
    idx_start = max(0, idx_peak - half_width)
    idx_end = min(len(x_data) - 1, idx_peak + half_width)
    
    y_peak = y_data[idx_peak]
    y_background = np.median(y_data[idx_start:idx_end])
    signal_net = y_peak - y_background
    
    if signal_net <= 0:
        return 0.0
    
    # Ruido: desviación estándar en una región sin picos
    noise_window = min(50, idx_peak // 2)
    idx_noise_start = max(0, idx_peak - noise_window - 30)
    idx_noise_end = max(1, idx_peak - noise_window)
    
    if idx_noise_end - idx_noise_start < 10:
        noise_std = np.std(y_data)
    else:
        noise_std = np.std(y_data[idx_noise_start:idx_noise_end])
    
    if noise_std == 0:
        return 0.0
    
    return signal_net / noise_std