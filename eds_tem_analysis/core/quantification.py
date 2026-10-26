import logging
import re
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
import exspy
from exspy.misc.elements import elements_db
logger = logging.getLogger(__name__)


def _scalar(x) -> float:
    """Extrae un valor escalar float de un objeto HyperSpy o de un número."""
    return float(x.data[0]) if hasattr(x, 'data') else float(x)


def _build_result(
    valid: bool,
    total_counts: float,
    metadata: Dict[str, Any],
    signal=None,
    composition: Optional[pd.DataFrame] = None,
    eliminated: Optional[List[str]] = None,
    energy_dict: Optional[Dict[str, float]] = None,
    line_dict: Optional[Dict[str, str]] = None,
    error: Optional[str] = None,
    method: str = "default",
) -> Dict[str, Any]:
    """
    Arma el diccionario de resultado con un esquema consistente en TODOS
    los caminos de salida de quantify_spectrum (antes, el camino de error
    en la cuantificación inicial no incluía 'composition', 'eliminated_elements'
    ni 'signal', lo que podía romper con KeyError a quien consume el resultado).

    Se agregaron 'energy_dict' y 'line_dict' como parámetros opcionales:
    antes se los pasaba desde quantify_spectrum sin que la firma los
    aceptara, lo que producía un TypeError al construir el resultado final.
    """
    return {
        'valid': valid,
        'composition': composition if composition is not None else pd.DataFrame(),
        'total_counts': total_counts,
        'eliminated_elements': eliminated if eliminated is not None else [],
        'energy_dict': energy_dict if energy_dict is not None else {},
        'line_dict': line_dict if line_dict is not None else {},
        'metadata': metadata,
        'signal': signal,
        'error': error,
        'method': method,
    }


def _calculate_snr(energy, y_data, x_data, window_width=0.15):
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


def _lookup_line_energy(elem: str, line: str) -> Optional[float]:
    """
    Busca la energía (keV) de una línea X-ray de un elemento en exspy,
    probando primero el estilo de atributos (Atomic_properties.Xray_lines.X)
    y luego el estilo de diccionario (elements_db), por si la versión de
    exspy instalada expone la base de datos de una forma u otra.
    Registra por qué falla cada intento, en vez de fallar en silencio.
    """
    # Estilo atributos
    try:
        element_obj = getattr(exspy.material.elements, elem)
        return float(element_obj.Atomic_properties.Xray_lines[line].energy_keV)
    except Exception as e:
        logger.debug(f"Lookup por atributos falló para {elem}_{line}: {e}")

    # Estilo diccionario (elements_db)
    # NOTA: 'elements_db' ya está importado a nivel de módulo; se quitó el
    # 'from exspy.misc.elements import elements_db' local que era redundante.
    try:
        return float(elements_db[elem]['Atomic_properties']['Xray_lines'][line]['energy (keV)'])
    except Exception as e:
        logger.debug(f"Lookup por diccionario falló para {elem}_{line}: {e}")

    return None


def _get_energies_from_signal(signal, elements_list):
    """
    Obtiene las energías de las líneas X-ray desde las intensityes.
    """
    energy_dict = {}
    try:
        intensities = signal.get_lines_intensity()
        for sig in intensities:
            title = sig.metadata.General.title if hasattr(sig.metadata, 'General') else ""
            m = re.search(r'(\w+)_(\w+)\s+at\s+([\d.]+)\s*keV', title)
            if m:
                elemento = m.group(1)
                energy = float(m.group(3))
                energy_dict[elemento] = energy
    except Exception as e:
        logger.debug(f"No se pudieron obtener energías desde intensityes: {e}")

    # Fallback: usar eXspy para obtener energías (Ka y luego La, sin cambios)
    for elem in elements_list:
        if elem in energy_dict:
            continue
        energy = _lookup_line_energy(elem, 'Ka')
        if energy is None:
            energy = _lookup_line_energy(elem, 'La')
        if energy is not None:
            energy_dict[elem] = energy
        else:
            logger.warning(f"No se encontró energía Ka ni La para el elemento '{elem}'")

    return energy_dict


def quantify_spectrum(
    signal,
    elements_data: List[Dict[str, Any]],
    min_total_counts: float = 100000.0,
    min_weight_percent: float = 1.0,
    snr_umbral: float = 3.0,
    method: str = 'CL',
    composition_units: str = 'weight',
    auto_refine: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    use_deconvolution: bool = False,
    integration_windows: Optional[List[float]] = None,
    background_windows: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Cuantifica un espectro EDS-TEM utilizando HyperSpy.
    """
    if metadata is None:
        metadata = {}
    # Determinar el método de integración (es fijo para toda la ejecución)
    
    if use_deconvolution:
        method_used = "deconvolution"
    elif integration_windows is not None:
        method_used = "custom_windows"
    else:
        method_used = "default"

    try:
        signal.set_signal_type("EDS_TEM")
    except Exception as e:
        logger.warning(f"No se pudo establecer tipo EDS_TEM: {e}")

    total_counts = float(signal.data.sum())
    if total_counts < min_total_counts:
        logger.info(f"Cuentas insuficientes: {total_counts:.0f} < {min_total_counts}")
        return _build_result(valid=False, 
                             total_counts=total_counts, 
                             metadata=metadata, 
                             signal=signal, 
                             method=method_used)

    kfactor_dict = {elem['elemento']: elem['kfactor'] for elem in elements_data}
    element_names = sorted(kfactor_dict.keys())
    percent_col = 'wt.%' if composition_units == 'weight' else 'at.%'

    # --- OBTENER ENERGIAS PARA SNR ---
    x = signal.axes_manager[0].axis
    y = signal.data
    fallback_energy_dict = _get_energies_from_signal(signal, element_names)

       

    def quantificar_con_elementos(elements_list):
        """Realiza la cuantificación para una lista de elementos (ordenada)."""
        signal.set_elements(elements_list)

        if 'Sample.xray_lines' in signal.metadata:
            del signal.metadata.Sample.xray_lines

        signal.add_lines()

        available_lines = signal.metadata.Sample.xray_lines
        filtered_lines = [l for l in available_lines if l.split('_')[0] in elements_list]

        if len(filtered_lines) != len(elements_list):
            line_elements = [l.split('_')[0] for l in filtered_lines]
            elements_to_use = [e for e in elements_list if e in line_elements]
            if not elements_to_use:
                raise ValueError("Ninguno de los elementos tiene líneas disponibles.")
            signal.set_elements(elements_to_use)
            signal.add_lines()
            filtered_lines = list(signal.metadata.Sample.xray_lines)
            elements_to_use = [l.split('_')[0] for l in filtered_lines]
        else:
            elements_to_use = elements_list

        local_energy_dict = {}
        local_line_dict = {}
        for line in filtered_lines:
            elem, line_type = line.split('_', 1)
            energy = _lookup_line_energy(elem, line_type)
            if energy is None:
                energy = fallback_energy_dict.get(elem)
            if energy is None:
                logger.warning(f"Failed to retrieve energy for {line}")
            local_energy_dict[elem] = energy
            local_line_dict[elem] = line_type

        # <-- AQUÍ SÍ: filtered_lines ya está definido
        integration_kwargs = {}

        if use_deconvolution:
            integration_kwargs['deconvolution'] = True
            logger.info("Integration method: deconvolution")

        elif integration_windows is not None:
            # La GUI envía background_windows como lista [bw, bw]
            # pero estimate_background_windows espera un float para windows_width
            ww_float = float(background_windows) if background_windows else 1.0

            try:
                bw = signal.estimate_background_windows(
                    xray_lines=filtered_lines,
                    line_width=list(integration_windows),  # [wl, wr]
                    windows_width=ww_float,                # float único
                )
                integration_kwargs['background_windows'] = bw
                logger.info(
                    f"Custom windows OK: line_width={integration_windows}, "
                    f"windows_width={ww_float}"
                )
            except Exception as e:
                logger.error(f"Error estimating background windows: {e}")
                # Fallback: no pasar background_windows, dejar que exspy use default
                integration_kwargs['background_windows'] = None

        else:
            logger.info("Integration method: default")

        intensities = signal.get_lines_intensity(**integration_kwargs)
        intensity_values = [_scalar(i) for i in intensities]

        if len(intensity_values) != len(elements_to_use):
            logger.error(
                f"Mismatch: current xray_lines={list(signal.metadata.Sample.xray_lines)}, "
                f"expected elements={elements_to_use}"
            )
            raise ValueError(
                f"Number of intensities ({len(intensity_values)}) does not match elements ({len(elements_to_use)})"
            )

        factors = [kfactor_dict[e] for e in elements_to_use]
        composition = signal.quantification(
            intensities, method=method, factors=factors, composition_units=composition_units
        )
        comp_values = [_scalar(c) for c in composition]

        return elements_to_use, intensity_values, comp_values, local_energy_dict, local_line_dict

    def recompute(elements_list) -> tuple:
        elems, intens, comps, energy_dict, line_dict = quantificar_con_elementos(sorted(elements_list))
        out = pd.DataFrame({'Element': elems, percent_col: comps, 'Intensity': intens})
        out.loc[out['Intensity'] < 0, percent_col] = 0.0
        return out, energy_dict, line_dict

    logger.debug("BEFORE quantificar_con_elementos")
    try:
        df, energy_dict, line_dict = recompute(element_names)
        logger.debug(f"AFTER recompute: energy_dict={energy_dict}")
    except Exception as e:
        logger.error(f"Error in initial quantification: {e}")
        return _build_result(valid=False, 
                            total_counts=total_counts, 
                            metadata=metadata, 
                            signal=signal, 
                            error=str(e),
                            method=method_used)
                             

    eliminated: List[str] = []

    if auto_refine:
        max_iter = 20
        for _ in range(max_iter):
            if len(df) <= 1:
                if len(df) == 1:
                    df.loc[df.index[0], percent_col] = 100.0
                break

            snr_values = {}
            for elem in df['Element'].tolist():
                if elem in energy_dict and energy_dict[elem] is not None:
                    snr = _calculate_snr(energy_dict[elem], y, x)
                else:
                    max_intensity = df['Intensity'].max() if not df.empty else 1
                    intensity_ratio = df[df['Element'] == elem]['Intensity'].values[0] / max_intensity
                    snr = 5.0 if intensity_ratio >= 0.01 else 1.0
                snr_values[elem] = snr

            df['SNR'] = df['Element'].map(snr_values)

            below_threshold = df[
                (df[percent_col] < min_weight_percent) |
                (df['SNR'] < snr_umbral)
            ]

            if len(below_threshold) == 0:
                break

            min_idx = below_threshold[percent_col].idxmin()
            eliminated.append(df.loc[min_idx, 'Element'])
            remaining = df.drop(min_idx)['Element'].tolist()

            if len(remaining) <= 1:
                df = df.drop(min_idx).reset_index(drop=True)
                break

            try:
                df, energy_dict, line_dict = recompute(remaining)
            except Exception as e:
                logger.error(f"Error in refinement: {e}")
                break
        else:
            logger.warning(f"Refinement reached maximum iterations ({max_iter})")

    if 'SNR' in df.columns:
        df = df.drop(columns=['SNR'])

    return _build_result(
        valid=True,
        total_counts=total_counts,
        metadata=metadata,
        signal=signal,
        composition=df,
        eliminated=eliminated,
        energy_dict=energy_dict,
        line_dict=line_dict,
        method=method_used,
    )