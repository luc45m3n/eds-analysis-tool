# -*- coding: utf-8 -*-
"""
Generación de informes en PDF a partir de los resultados de cuantificación.
"""

import logging
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from adjustText import adjust_text
    HAS_ADJUSTTEXT = True
except ImportError:
    HAS_ADJUSTTEXT = False
    logger.warning("adjustText no instalado. Las anotaciones pueden solaparse.")


# --------------------------------------------------------------------------
# Función principal
# --------------------------------------------------------------------------

def generate_pdf_from_signal(signal, metadata: dict, df: pd.DataFrame, output_path: Path,
                              energy_dict: dict, line_dict: dict,
                              percent_col: str, unit_label: str):
    """
    Genera un PDF con el espectro y la tabla de composición.

    Args:
        signal: Objeto Signal de HyperSpy
        metadata: Diccionario con 'Area' y 'Spot'
        df: DataFrame con Elemento, porcentaje, Intensidad
        output_path: Ruta de salida del PDF
        energy_dict: Diccionario {elemento: energia_keV}
        line_dict: Diccionario {elemento: 'Ka'/'Kb'/...}
        percent_col: Nombre de la columna de porcentaje ('wt.%' o 'at.%')
        unit_label: Etiqueta a mostrar en la tabla ('wt.%' o 'at.%')
    """
    try:
        x = signal.axes_manager[0].axis
        y = signal.data

        line_data = _build_line_data(df, energy_dict, line_dict)

        with PdfPages(output_path) as pdf:
            fig = plt.figure(figsize=(8.5, 11))
            gs = fig.add_gridspec(2, 1, height_ratios=[3, 1])

            ax_spectrum = fig.add_subplot(gs[0])
            ax_spectrum.plot(x, y, color='steelblue', linewidth=0.8)
            ax_spectrum.set_title(f"Espectro - {metadata.get('Area', '')} {metadata.get('Spot', '')}")
            ax_spectrum.set_xlabel("Energía (keV)")
            ax_spectrum.set_ylabel("Cuentas")
            ax_spectrum.grid(True, alpha=0.3)

            if line_data:
                _add_peak_annotations(ax_spectrum, x, y, line_data)

            _draw_composition_table(fig.add_subplot(gs[1]), df, percent_col, unit_label)

            pdf.savefig(fig)
            plt.close(fig)

        logger.info(f"PDF generado: {output_path}")
    except Exception as e:
        logger.error(f"Error al generar PDF: {e}")
        raise


# --------------------------------------------------------------------------
# Helpers de datos
# --------------------------------------------------------------------------

def _build_line_data(df: pd.DataFrame, energy_dict: dict, line_dict: dict):
    """
    Construye [(label, energia, intensidad), ...] a partir de los diccionarios.

    Args:
        df: DataFrame con columna 'Elemento' y 'Intensidad'
        energy_dict: {elemento: energia_keV}
        line_dict: {elemento: 'Ka'/'Kb'/...}

    Returns:
        list: Lista de tuplas (label, energia, intensidad)
    """
    line_data = []
    for elem in df['Elemento'].tolist():
        energy = energy_dict.get(elem)
        if energy is None:
            continue  # sin energía no hay pico que anotar
        linea = line_dict.get(elem, 'Ka')
        label = f"{elem}_{linea}"
        intensidad = df.loc[df['Elemento'] == elem, 'Intensidad'].values[0] if 'Intensidad' in df.columns else None
        line_data.append((label, energy, intensidad))
    return line_data


# --------------------------------------------------------------------------
# Anotaciones del espectro
# --------------------------------------------------------------------------

def _peak_at_energy(x, y, energy):
    """Devuelve (energía_real, y_del_pico) para una energía dada."""
    idx = np.argmin(np.abs(x - energy))
    step = x[1] - x[0] if len(x) > 1 else 0.05
    if abs(x[idx] - energy) < step / 2:
        return x[idx], y[idx]
    return energy, float(np.interp(energy, x, y))


def _add_peak_annotations(ax, x, y, line_data):
    """
    Añade anotaciones de picos:
    - Línea vertical desde una base cercana a y=0 hasta el pico.
    - Etiqueta anclada al pico, alternando arriba/abajo para evitar solapamiento.
    - Ajuste fino con adjustText si está disponible.
    """
    peak_info = []
    for label, energy, _ in line_data:
        if energy is None:
            continue
        energy_actual, y_peak = _peak_at_energy(x, y, energy)
        if energy_actual is None or y_peak is None:
            continue
        if y_peak > y.max() * 0.01:
            display_label = label.replace('_', ' ')
            peak_info.append((display_label, energy_actual, y_peak))

    if not peak_info:
        return

    peak_info.sort(key=lambda p: p[1])  # ordenar por energía

    y_max, y_min = y.max(), y.min()
    y_range = y_max - y_min
    x_range = x[-1] - x[0]

    y_base = y_max * 0.02
    base_offset = y_range * 0.05
    max_offset = y_range * 0.18
    x_offset = 0.02 * x_range
    cluster_gap = 0.04 * x_range

    texts = []
    prev_energy = None
    slot = 0

    for label, energy, y_peak in peak_info:
        if prev_energy is not None and (energy - prev_energy) < cluster_gap:
            slot += 1
        else:
            slot = 0
        prev_energy = energy

        above = (slot % 2 == 0)
        offset = min(base_offset + (slot // 2) * base_offset, max_offset)
        y_pos = y_peak + offset if above else y_peak - offset
        y_pos = max(y_min + y_range * 0.03, min(y_max - y_range * 0.03, y_pos))
        va = 'bottom' if above else 'top'

        # Línea vertical desde la base hasta el pico
        ax.plot([energy, energy], [y_base, y_peak],
                color='gray', linestyle='-', linewidth=0.85, alpha=0.8)

        # Marcador en el pico
        ax.plot(energy, y_peak, 'v', color='red', markersize=7, alpha=0.8)

        # Etiqueta
        text = ax.text(
            energy + x_offset * (1 if above else -1),
            y_pos, label,
            ha='center', va=va, fontsize=8, fontweight='bold', color='darkred',
        )
        texts.append(text)

    if len(texts) > 1 and HAS_ADJUSTTEXT:
        try:
            adjust_text(
                texts,
                expand_points=(1.0, 1.0),
                expand_text=(1.0, 1.0),
                autoalign='xy',
                only_move={'text': 'y'},
                avoid_self=True,
                lim=50,
                precision=0.01,
                time_lim=0.3,
            )
        except Exception as e:
            logger.warning(f"adjustText falló: {e}")


def _find_peaks_auto(x, y, df):
    """Busca picos automáticamente en el espectro (uno por elemento)."""
    from scipy.signal import find_peaks

    peaks, _ = find_peaks(y, height=y.max() * 0.05, distance=10)
    if len(peaks) == 0:
        return []

    best_idx = max(peaks, key=lambda idx: y[idx])
    return [(elem, x[best_idx], y[best_idx]) for elem in df['Elemento']]


# --------------------------------------------------------------------------
# Tabla de composición
# --------------------------------------------------------------------------

def _draw_composition_table(ax_table, df, percent_col, unit_label):
    """
    Dibuja la tabla de composición en el eje de matplotlib.
    """
    ax_table.axis('off')

    if not percent_col or percent_col not in df.columns:
        ax_table.text(0.5, 0.5, "Datos de composición no disponibles",
                      ha='center', va='center')
        return

    table_data = [["Elemento", unit_label, "Intensidad"]]
    for _, row in df.iterrows():
        intensidad = row.get('Intensidad', 0)
        intensidad = 0 if pd.isna(intensidad) else intensidad
        table_data.append([
            row['Elemento'],
            f"{row[percent_col]:.2f}",
            f"{intensidad:.2f}"
        ])

    table = ax_table.table(cellText=table_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    for (i, j), cell in table.get_celld().items():
        if i == 0:
            cell.set_facecolor('#000000')
            cell.set_text_props(color='white', weight='bold')
        else:
            cell.set_facecolor('#f0f0f0')