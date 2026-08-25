# -*- coding: utf-8 -*-
"""
Módulo para manejo centralizado de logs y salida en consola.
Proporciona sincronización thread-safe para todas las salidas.
"""

import threading
import sys
from typing import Callable, Optional

# Lock global para sincronizar salidas (thread-safe)
_PRINT_LOCK = threading.Lock()

# Callback para enviar mensajes a la GUI (se establece desde analysis_tab)
_GUI_LOG_CALLBACK: Optional[Callable] = None


def set_gui_log_callback(callback: Callable):
    """
    Establece la función que enviará mensajes a la GUI.
    
    Args:
        callback: Función que acepta (mensaje, nivel) como argumentos.
    """
    global _GUI_LOG_CALLBACK
    _GUI_LOG_CALLBACK = callback


def log_message(msg: str, level: str = "INFO", to_gui: bool = True, to_terminal: bool = True):
    """
    Envía un mensaje al log de la GUI y/o a la terminal con sincronización.

    Args:
        msg: Mensaje a mostrar.
        level: Nivel (INFO, WARNING, ERROR, TERMINAL).
        to_gui: Si True, envía a la GUI.
        to_terminal: Si True, imprime en terminal.
    """
    with _PRINT_LOCK:
        # Enviar a la GUI
        if to_gui and _GUI_LOG_CALLBACK:
            try:
                _GUI_LOG_CALLBACK(msg, level)
            except Exception:
                # Si falla, imprimir en terminal como fallback
                print(f"[ERROR] Fallo al enviar a GUI: {msg}")

        # Imprimir en terminal
        if to_terminal:
            if level == "TERMINAL":
                print(msg)
            else:
                print(f"[{level}] {msg}")


class SyncLogger:
    """
    Logger que captura stdout/stderr y los envía a través de log_message.
    Reemplaza a TeeLogger con sincronización centralizada.
    """
    def __init__(self, original_stream, level: str = "TERMINAL"):
        self.original_stream = original_stream
        self.level = level
        self._buffer = ""

    def write(self, message: str):
        if not message:
            return
        self._buffer += message
        # Dividir en líneas completas
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line.strip():
                log_message(line.rstrip(), level=self.level, to_gui=True, to_terminal=True)

    def flush(self):
        # Enviar lo que quede en el buffer
        if self._buffer.strip():
            log_message(self._buffer.rstrip(), level=self.level, to_gui=True, to_terminal=True)
            self._buffer = ""
        if self.original_stream:
            self.original_stream.flush()