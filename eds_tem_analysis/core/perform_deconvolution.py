# -*- coding: utf-8 -*-
"""
Deconvolución basada en modelo automático de HyperSpy para cuantificación EDS.

Flujo:
1. Crear modelo automático del espectro (HyperSpy detecta picos)
2. Ajustar fondo y modelo inicial
3. Bucle iterativo: calcular porcentajes atómicos/peso, eliminar el elemento
   con menor contribución si está por debajo del umbral, remover sus
   componentes del modelo, re-ajustar, y repetir hasta convergencia.

Este enfoque aprovecha que HyperSpy ya conoce los perfiles teóricos de
las líneas de rayos X (Kα, Kβ, Lα, etc.) y sus intensidades relativas,
por lo que la separación de picos solapados es físicamente consistente.
"""

import logging
import numpy as np
import pandas as pd
import hyperspy.api as hs
import exspy

logger = logging.getLogger(__name__)


def _get_atomic_weight(element: str) -> float:
    """Obtiene el peso atómico desde la base de datos de exspy."""
    try:
        elem_obj = getattr(exspy.material.elements, element)
        return float(elem_obj.General_properties.atomic_weight)
    except Exception as e:
        logger.warning(f"No se pudo obtener peso atómico para {element}: {e}")
        return 1.0


def _get_line_energy(element: str, line: str = 'Ka') -> float | None:
    """Obtiene la energía (keV) de una línea de rayos X."""
    try:
        elem_obj = getattr(exspy.material.elements, element)
        return float(getattr(elem_obj.Atomic_properties.Xray_lines, line).energy_keV)
    except Exception:
        return None


def _extract_max_areas(model) -> dict:
    """
    Extrae el área máxima (A.value) por elemento del modelo ajustado.
    Un elemento puede tener varias líneas (Kα, Kβ, etc.); se toma la mayor.
    """
    raw = {}
    for comp in model:
        name = comp.name
        if hasattr(comp, 'A'):
            element = name.split('_')[0]
            area = float(comp.A.value)
            if area > 0:
                raw.setdefault(element, []).append((name, area))

    result = {}
    for element, lines in raw.items():
        if lines:
            best_name, best_area = max(lines, key=lambda x: x[1])
            result[element] = {'componente': best_name, 'A_value': best_area}
    return result


def perform_deconvolution(
    signal,
    elements_list: list[str],
    kfactor_dict: dict[str, float],
    beam_energy: float | None = None,
    min_weight_percent: float = 1.0,
    composition_units: str = 'weight',
    max_iterations: int = 20,
) -> dict:
    """
    Realiza cuantificación EDS por deconvolución de modelo con refinamiento
    iterativo por umbral de porcentaje.

    Returns
    -------
    dict con claves:
        - composition: pd.DataFrame con Element, wt.%/at.%, Intensidad
        - eliminated_elements: list
        - energy_dict: dict
        - line_dict: dict
        - intensity_dict: dict (área neta por elemento)
    """
    # 1. Obtener beam_energy del metadata si no se pasó
    if beam_energy is None:
        try:
            beam_energy = float(signal.metadata.Acquisition_instrument.TEM.beam_energy)
        except Exception:
            beam_energy = 200.0
            logger.warning(f"beam_energy no disponible, usando default {beam_energy} keV")

    # 2. Crear modelo automático de HyperSpy
    model = signal.create_model()

    # 3. Ajustar fondo y modelo inicial
    try:
        model.fit_background()
        model.fit()
    except Exception as e:
        logger.error(f"Error en ajuste inicial del modelo: {e}")
        return {
            'composition': pd.DataFrame(),
            'eliminated_elements': list(elements_list),
            'energy_dict': {},
            'line_dict': {},
            'intensity_dict': {},
            'error': f'Initial fit failed: {e}'
        }

    # 4. Filtrar componentes: solo mantener los elementos de interest_list
    #    (HyperSpy puede haber detectado contaminantes como C, O, Cu, etc.)
    elementos_set = set(elements_list)
    for comp in tuple(model):
        name = comp.name
        if hasattr(comp, 'A'):
            element = name.split('_')[0]
            if element not in elementos_set:
                logger.debug(f"Removiendo componente no deseado: {name}")
                model.remove(comp)

    # Re-ajustar tras remover contaminantes
    try:
        model.fit()
    except Exception as e:
        logger.warning(f"Error en re-ajuste tras filtrar contaminantes: {e}")

    # 5. Extraer áreas iniciales
    max_areas = _extract_max_areas(model)

    if not max_areas:
        return {
            'composition': pd.DataFrame(),
            'eliminated_elements': list(elements_list),
            'energy_dict': {},
            'line_dict': {},
            'intensity_dict': {},
            'error': 'No valid components in model'
        }

    # 6. Bucle iterativo de refinamiento por umbral
    eliminated = []
    active_elements = set(max_areas.keys())

    for iteration in range(max_iterations):
        # Calcular porcentajes según unidades
        parciales = {}
        suma_total = 0.0

        for element, data in max_areas.items():
            intensity = data['A_value']
            k = kfactor_dict.get(element, 1.0)

            if composition_units == 'atomic':
                aw = _get_atomic_weight(element)
                valor = (intensity * k) / aw
            else:
                valor = intensity * k

            parciales[element] = valor
            suma_total += valor

        if suma_total == 0:
            break

        porcentajes = {e: (v / suma_total) * 100 for e, v in parciales.items()}

        # Buscar el elemento con menor porcentaje por debajo del umbral
        elemento_a_eliminar = None
        menor_pct = 100.0
        for element, pct in porcentajes.items():
            if pct < min_weight_percent and pct < menor_pct:
                menor_pct = pct
                elemento_a_eliminar = element

        # Criterio de parada: todos los elementos superan el umbral
        if elemento_a_eliminar is None:
            logger.info(f"Convergencia alcanzada en iteración {iteration + 1}")
            break

        # Eliminar elemento
        logger.info(
            f"Iteración {iteration + 1}: '{elemento_a_eliminar}' "
            f"({menor_pct:.2f}%) por debajo del umbral. Removiendo..."
        )
        eliminated.append(elemento_a_eliminar)
        active_elements.discard(elemento_a_eliminar)
        del max_areas[elemento_a_eliminar]

        # Remover componentes del modelo
        for comp in tuple(model):
            if comp.name.split('_')[0] == elemento_a_eliminar:
                model.remove(comp)

        # Re-ajustar modelo
        try:
            model.fit()
        except Exception as e:
            logger.warning(f"Error en re-ajuste iteración {iteration + 1}: {e}")
            break

        # Actualizar áreas máximas tras re-ajuste
        max_areas = _extract_max_areas(model)

        # Si no quedan elementos, salir
        if not max_areas:
            break

    # 7. Calcular composición final
    if not max_areas:
        return {
            'composition': pd.DataFrame(),
            'eliminated_elements': eliminated,
            'energy_dict': {},
            'line_dict': {},
            'intensity_dict': {},
            'error': 'All elements eliminated during refinement'
        }

    parciales = {}
    suma_total = 0.0
    intensity_dict = {}

    for element, data in max_areas.items():
        intensity = data['A_value']
        intensity_dict[element] = intensity
        k = kfactor_dict.get(element, 1.0)

        if composition_units == 'atomic':
            aw = _get_atomic_weight(element)
            valor = (intensity * k) / aw
        else:
            valor = intensity * k

        parciales[element] = valor
        suma_total += valor

    percent_col = 'at.%' if composition_units == 'atomic' else 'wt.%'
    porcentajes_finales = {e: (v / suma_total) * 100 for e, v in parciales.items()}

    # Construir diccionarios de energía y línea
    energy_dict = {}
    line_dict = {}
    for element in porcentajes_finales.keys():
        energy = _get_line_energy(element, 'Ka')
        if energy is not None:
            energy_dict[element] = energy
            line_dict[element] = 'Ka'

    # DataFrame de composición
    df = pd.DataFrame({
        'Element': list(porcentajes_finales.keys()),
        percent_col: list(porcentajes_finales.values()),
        'Intensity': [intensity_dict[e] for e in porcentajes_finales.keys()]
    })

    return {
        'composition': df,
        'eliminated_elements': eliminated,
        'energy_dict': energy_dict,
        'line_dict': line_dict,
        'intensity_dict': intensity_dict,
        'active_elements': list(porcentajes_finales.keys()),
        'error': None
    }