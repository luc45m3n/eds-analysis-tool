#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path

# Añadir el directorio actual al sys.path para encontrar el paquete
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import App

if __name__ == "__main__":
    app = App()
    app.mainloop()