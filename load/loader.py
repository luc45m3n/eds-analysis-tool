# -*- coding: utf-8 -*-
"""
Módulo para cargar archivos de espectros y metadatos.
"""

import os
import glob
import xml.etree.ElementTree as ET
import logging
from pathlib import Path

import hyperspy.api as hs

logger = logging.getLogger(__name__)


def extract_tags(file_path):
    """Extrae tags de un archivo XML."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        tags = []
        for element in root:
            tags.append(element.attrib)
        return tags
    except ET.ParseError as e:
        logger.error(f"Error al parsear XML {file_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error inesperado al leer {file_path}: {e}")
        return []


def archivo_spot(file_paths):
    """Extrae nombres y spots de archivos XML."""
    archivo = []
    zona = []
    for file_path in file_paths:
        tags = extract_tags(file_path)
        if tags:
            f = Path(file_path).stem
            archivo.append(f)
            zona.append(tags[0].get("Label", "Desconocido"))
        else:
            archivo.append(Path(file_path).stem)
            zona.append("Desconocido")
    return archivo, zona


def load_spectrum(file_path, lazy=False):
    """
    Carga un espectro desde un archivo .spc.

    Args:
        file_path (str): Ruta al archivo .spc.
        lazy (bool): Si es True, carga los datos de forma lazy (sin leerlos del disco inmediatamente).

    Returns:
        Signal1D: Objeto Signal de HyperSpy (puede ser lazy).
    """
    try:
        signal = hs.load(file_path, lazy=lazy)
        signal.set_signal_type("EDS_TEM")
        return signal
    except Exception as e:
        logger.error(f"Error al cargar {file_path}: {e}")
        raise


def get_files_in_directory(directory, extension="*.spc"):
    """Devuelve lista de archivos con extensión."""
    pattern = os.path.join(directory, extension)
    return glob.glob(pattern)