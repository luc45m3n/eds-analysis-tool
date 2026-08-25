# -*- coding: utf-8 -*-
"""
Ventana principal de la aplicación.
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import webbrowser
from pathlib import Path

from .analysis_tab import AnalisisEDS
from .stats_tab import Estadisticas

# Ruta a recursos (relativa a este archivo)
RESOURCES_DIR = Path(__file__).parent.parent / "resources"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.RESOURCES_DIR = RESOURCES_DIR
        self.current_path = str(Path.cwd())
        self.selected_path = ""

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(
            "TButton",
            padding=10,
            relief="flat",
            background="#4CAF50",
            foreground="white",
        )
        self.style.map("TButton", background=[("active", "#45a049")])
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabel", background="#f0f0f0", font=("Helvetica", 10))
        self.title("Análisis EDS")

        self.create_menu()

        self.main_frame = ttk.Frame(self, padding="20", style="TFrame")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Contenedor principal
        self.container = tk.Frame(self)
        self.container.pack(fill="both", expand=True)

        # Frame superior (logo)
        self.top_frame = tk.Frame(self.container)
        self.top_frame.pack(fill="x")
        self.load_logo()

        # Notebook (pestañas)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Pestañas
        self.tab_analisis = AnalisisEDS(self.notebook, app=self)
        self.notebook.add(self.tab_analisis, text="Análisis EDS")

        self.tab_estadisticas = Estadisticas(self.notebook)
        self.notebook.add(self.tab_estadisticas, text="Estadísticas")

    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ayuda", menu=help_menu)

        help_menu.add_command(label="Cita", command=self.open_citation)
        help_menu.add_command(
            label="Documentación de HyperSpy", command=self.open_web_pageHspy
        )
        help_menu.add_command(
            label="Documentación de eXSpy", command=self.open_web_pageeXSpy
        )
        help_menu.add_command(label="Acerca de .", command=self.open_info)

    def open_citation(self):
        webbrowser.open("https://zenodo.org/records/10709941")

    def open_web_pageHspy(self):
        webbrowser.open("https://hyperspy.org/hyperspy-doc/v2.0/user_guide/index.html")

    def open_web_pageeXSpy(self):
        webbrowser.open("https://exspy.readthedocs.io/en/latest/user_guide/index.html")

    def open_info(self):
        newWindow = tk.Toplevel(self)
        newWindow.title("Acerca de...")
        newWindow.geometry("310x280")
        tk.Label(
            newWindow, text="Semicuantificación EDS de TEM", font=("arial", 10, "bold")
        ).pack()
        tk.Label(
            newWindow,
            text="Método de cuantificación aplicado: Cliff-Lorimer",
            font=("arial", 10, "normal"),
        ).pack()
        tk.Label(
            newWindow,
            text="""Código base en Python 3.0\n Librerías: \n\t-HyperSpy\n\t-Pandas\n\t-NumPy\n\t-Matplotlib\n\t-SciPy\n\t-xml\n\t-tkinter\n\t-PIL""",
            font=("arial", 10, "normal"),
        ).pack()
        tk.Label(
            newWindow,
            text="Versión 2.0\nProgramado por: Lucas Menger\nConsultas: lucasmenger@cnea.gob.ar\n",
            font=("arial", 10, "normal"),
        ).pack()

    def load_logo(self):
        try:
            logo_path = RESOURCES_DIR / "logo.png"
            logo_image = Image.open(logo_path)
            logo_image.thumbnail((120, 60), Image.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo_image)
            self.logo_label = tk.Label(
                self.top_frame, image=self.logo_photo, bg="#f0f0f0"
            )
            self.logo_label.image = self.logo_photo
            self.logo_label.pack(pady=10)
        except Exception as e:
            print(f"Error al cargar el logo: {e}")
            self.logo_label = tk.Label(
                self.main_frame, text="LOGO", font=("Helvetica", 24), bg="#f0f0f0"
            )
            self.logo_label.pack(pady=10)