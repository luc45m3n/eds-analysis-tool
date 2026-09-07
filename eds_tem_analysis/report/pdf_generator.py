# -*- coding: utf-8 -*-
"""
Generación de informes en PDF a partir de los resultados de cuantificación.
"""

import logging
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # <-- FORZAR BACKEND SIN GUI

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
                             energy_dict: dict = None, line_dict: dict = None):
    """
    Genera un PDF con el espectro y la tabla de composición.
    energy_dict: diccionario {elemento: energia_keV}
    line_dict: diccionario {elemento: linea} (ej. 'Ka', 'Kb', 'La')
    """
    try:
        percent_col, unit_label = _get_percent_column(df)

        x = signal.axes_manager[0].axis
        y = signal.data
        
        # --- PASAR LOS DICCIONARIOS A _extract_line_data ---
        line_data = _extract_line_data(signal, x, y, df, energy_dict, line_dict)

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

def _get_percent_column(df: pd.DataFrame):
    """Determina qué columna de porcentaje usar y su etiqueta."""
    if 'wt.%' in df.columns:
        return 'wt.%', 'wt.%'
    if 'at.%' in df.columns:
        return 'at.%', 'at.%'

    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
    if len(numeric_cols) > 0:
        return numeric_cols[0], numeric_cols[0]

    return None, 'Porcentaje'


def _extract_line_data(signal, x, y, df: pd.DataFrame, energy_dict: dict = None, line_dict: dict = None):
    """
    Obtiene las líneas X-ray desde los diccionarios proporcionados.
    Si no se proporcionan, intenta extraer de la señal.
    """
    line_data = []
    
    # --- PRIORIDAD 1: Usar energy_dict y line_dict ---
    if energy_dict:
        for elem in df['Elemento'].tolist():
            if elem in energy_dict:
                energy = energy_dict[elem]
                linea = line_dict.get(elem, 'Ka') if line_dict else 'Ka'
                label = f"{elem}_{linea}"
                # Obtener intensidad desde el DataFrame
                intensidad = df[df['Elemento'] == elem]['Intensidad'].values[0] if 'Intensidad' in df.columns else None
                line_data.append((label, energy, intensidad))
        if line_data:
            return line_data
    
    # --- PRIORIDAD 2: Intentar extraer desde la señal ---
    try:
        for sig in signal.get_lines_intensity():
            title = getattr(sig.metadata, 'General', None)
            title = title.title if title else ""
            m = re.search(r':\s*(\w+)\s+at\s+([\d.]+)\s*keV', title)
            if m:
                label, energy = m.group(1), float(m.group(2))
                line_data.append((label, energy, float(sig.data[0])))
    except Exception as e:
        logger.warning(f"No se pudieron obtener líneas X-ray: {e}")
        try:
            line_data = [(line.replace('_', ' '), None, None)
                         for line in signal.metadata.Sample.xray_lines]
        except Exception:
            pass

    # --- PRIORIDAD 3: Buscar picos automáticamente ---
    if not line_data:
        logger.info("No se encontraron líneas X-ray, buscando picos automáticamente...")
        line_data = _find_peaks_auto(x, y, df)

    return line_data


# --------------------------------------------------------------------------
# Anotaciones del espectro
# --------------------------------------------------------------------------

def _peak_at_energy(x, y, energy):
    """Devuelve (energía_real, y_del_pico) para una energía dada."""
    idx = np.argmin(np.abs(x - energy))
    if abs(x[idx] - energy) < 0.05:
        return x[idx], y[idx]
    return energy, float(np.interp(energy, x, y))


def _add_peak_annotations(ax, x, y, line_data):
    """
    Añade anotaciones de picos:
    - Línea vertical tenue desde una base cercana a y=0 hasta el pico.
    - Etiqueta anclada a la altura real de SU pico (no a una banda fija),
      así nunca queda flotando lejos de un pico bajo.
    - Solo se alterna arriba/abajo cuando hay picos cercanos en energía
      que podrían solaparse; picos aislados van pegados a su propio pico.
    - La distancia etiqueta-pico está acotada (max_offset) para garantizar
      que la anotación siga señalando el pico correcto.
    - Ajuste fino con adjustText si está disponible.
    """
    peak_info = []
    for label, energy, _ in line_data:
        if energy is None:
            continue
        energy_actual, y_peak = _peak_at_energy(x, y, energy)
        if y_peak > y.max() * 0.01:
            # Convertir label para mostrar "Al Ka" en lugar de "Al_Ka"
            display_label = label.replace('_', ' ')
            peak_info.append((display_label, energy_actual, y_peak))

    if not peak_info:
        return

    peak_info.sort(key=lambda p: p[1])  # ordenar por energía

    y_max, y_min = y.max(), y.min()
    y_range = y_max - y_min
    x_range = x[-1] - x[0]

    y_base = y_max * 0.02        # base de la línea vertical (cerca de y=0)
    base_offset = y_range * 0.05     # separación mínima etiqueta-pico
    max_offset = y_range * 0.18      # tope: la etiqueta nunca se aleja más que esto del pico
    x_offset = 0.02 * x_range
    cluster_gap = 0.04 * x_range     # picos más cercanos que esto compiten por espacio

    texts = []
    prev_energy = None
    slot = 0  # posición dentro de un grupo de picos cercanos entre sí

    for label, energy, y_peak in peak_info:
        if prev_energy is not None and (energy - prev_energy) < cluster_gap:
            slot += 1
        else:
            slot = 0
        prev_energy = energy

        # Solo alterna arriba/abajo si compite por espacio con un pico cercano
        above = (slot % 2 == 0)
        offset = min(base_offset + (slot // 2) * base_offset, max_offset)
        y_pos = y_peak + offset if above else y_peak - offset
        y_pos = max(y_min + y_range * 0.03, min(y_max - y_range * 0.03, y_pos))
        va = 'bottom' if above else 'top'

        # Línea vertical sutil desde la base hasta el pico
        ax.plot([energy, energy], [y_base, y_peak],
                color='gray', linestyle='-', linewidth=0.85, alpha=0.8)

        # Etiqueta, cerca (en X e Y) del pico al que corresponde
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
                only_move={'text': 'y'},  # solo mover verticalmente
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
    ax_table.axis('off')

    if not percent_col or percent_col not in df.columns:
        ax_table.text(0.5, 0.5, "Datos de composición no disponibles",
                      ha='center', va='center')
        return

    table_data = [["Elemento", unit_label, "Intensidad"]]
    for _, row in df.iterrows():
        table_data.append([
            row['Elemento'],
            f"{row[percent_col]:.2f}",
            f"{row.get('Intensidad', 0):.2f}"
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