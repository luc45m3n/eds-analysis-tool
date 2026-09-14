# -*- coding: utf-8 -*-
"""
Pestaña de Estadísticas con gráficos embebidos en Tkinter.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class Estadisticas(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.df = None           # DataFrame para gráfico de dispersión (datos completos)
        self.df_promedio = None  # DataFrame para gráfico de barras (promedio)
        self.results = None
        self.current_file_path = None
        self.current_promedio_path = None
        self.x_var = tk.StringVar()
        self.y_vars = {}

        # --- Frame superior: controles ---
        control_frame = ttk.Frame(self)
        control_frame.pack(fill=tk.X, pady=5)

        self.open_button = ttk.Button(
            control_frame,
            style="TButton",
            text="Abrir archivo de resultados",
            command=self.open_file_and_update
        )
        self.open_button.pack(side=tk.LEFT, padx=5)

        self.reload_button = ttk.Button(
            control_frame,
            style="TButton",
            text="Recargar desde disco",
            command=self.reload_from_disk
        )
        self.reload_button.pack(side=tk.LEFT, padx=5)

        # --- Notebook interno (sub-pestañas) ---
        self.inner_notebook = ttk.Notebook(self)
        self.inner_notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # --- Pestaña 1: Gráfico de barras (usando promedio) ---
        self.bar_tab = ttk.Frame(self.inner_notebook)
        self.inner_notebook.add(self.bar_tab, text="📊 Composición promedio")

        self.bar_frame = ttk.Frame(self.bar_tab)
        self.bar_frame.pack(fill=tk.BOTH, expand=True)

        self.bar_fig = Figure(figsize=(6, 4), dpi=100)
        self.bar_ax = self.bar_fig.add_subplot(111)
        self.bar_canvas = FigureCanvasTkAgg(self.bar_fig, master=self.bar_frame)
        self.bar_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._show_empty_message(self.bar_ax, "Cargue un archivo de resultados")
        self.bar_canvas.draw()

        # --- Pestaña 2: Gráfico de dispersión (usando datos completos) ---
        self.scatter_tab = ttk.Frame(self.inner_notebook)
        self.inner_notebook.add(self.scatter_tab, text="📈 Dispersión")

        scatter_control_frame = ttk.Frame(self.scatter_tab)
        scatter_control_frame.pack(fill=tk.X, pady=5)

        self.xy_frame = ttk.Frame(scatter_control_frame)
        self.xy_frame.pack(fill=tk.X, pady=5)

        self.frame_x = ttk.LabelFrame(self.xy_frame, text="Eje X", style="TFrame")
        self.frame_y = ttk.LabelFrame(self.xy_frame, text="Eje Y", style="TFrame")
        self.frame_x.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        self.frame_y.pack(side=tk.RIGHT, padx=10, fill=tk.BOTH, expand=True)

        self.update_scatter_button = ttk.Button(
            scatter_control_frame,
            style="TButton",
            text="Actualizar gráfico de dispersión",
            command=self.update_scatter_plot
        )
        self.update_scatter_button.pack(pady=5)

        self.scatter_frame = ttk.Frame(self.scatter_tab)
        self.scatter_frame.pack(fill=tk.BOTH, expand=True)

        self.scatter_fig = Figure(figsize=(6, 4), dpi=100)
        self.scatter_ax = self.scatter_fig.add_subplot(111)
        self.scatter_canvas = FigureCanvasTkAgg(self.scatter_fig, master=self.scatter_frame)
        self.scatter_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._show_empty_message(self.scatter_ax, "Seleccione elementos y presione 'Actualizar'")
        self.scatter_canvas.draw()

    # ----- Métodos auxiliares -----

    def _show_empty_message(self, ax, message):
        ax.clear()
        ax.text(0.5, 0.5, message, ha='center', va='center', transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])

    def _get_percent_col(self, df):
        if df is None or df.empty:
            return None
        if 'wt.%' in df.columns:
            return 'wt.%'
        elif 'at.%' in df.columns:
            return 'at.%'
        for col in df.columns:
            if '%' in col:
                return col
        return None

    # ----- Métodos públicos -----

    def set_results(self, results):
        """Recibe los resultados del análisis y actualiza el gráfico de barras."""
        self.results = results
        self.update_bar_chart_from_results()

    def cargar_dataframe(self, df):
        """Carga un DataFrame de datos completos para dispersión."""
        self.df = df
        self.actualizar_checkboxes()
        self.update_scatter_plot()

    def cargar_promedio(self, df_promedio):
        """Carga un DataFrame de promedios para el gráfico de barras."""
        self.df_promedio = df_promedio
        self.update_bar_chart()

    def reload_from_disk(self):
        """Recarga los archivos desde disco."""
        if self.current_file_path:
            try:
                import os
                if os.path.exists(self.current_file_path):
                    self.df = pd.read_csv(self.current_file_path, sep=";", decimal=".")
                    self.actualizar_checkboxes()
                    self.update_scatter_plot()
                    messagebox.showinfo("Recargado", "Datos de dispersión recargados.")
                else:
                    messagebox.showerror("Error", "El archivo de datos completos ya no existe.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo recargar:\n{e}")
        
        if self.current_promedio_path:
            try:
                import os
                if os.path.exists(self.current_promedio_path):
                    self.df_promedio = pd.read_csv(self.current_promedio_path, sep=";", decimal=".")
                    self.update_bar_chart()
                else:
                    messagebox.showerror("Error", "El archivo de promedios ya no existe.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo recargar promedio:\n{e}")

    def open_file_and_update(self):
        """Abre un archivo de resultados y detecta si es datos completos o promedio."""
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            try:
                self.current_file_path = file_path
                df_temp = pd.read_csv(file_path, sep=";", decimal=".")
                
                # Detectar si es archivo de promedios o datos completos
                # Si tiene columna 'Archivo' → datos completos
                # Si solo tiene 2 columnas (Elemento, wt.%) → promedio
                if 'Archivo' in df_temp.columns:
                    # Archivo de datos completos
                    self.df = df_temp
                    self.actualizar_checkboxes()
                    self.update_scatter_plot()
                    messagebox.showinfo("Info", "Archivo de datos completos cargado. Disponible gráfico de dispersión.")
                else:
                    # Archivo de promedios
                    self.df_promedio = df_temp
                    self.update_bar_chart()
                    messagebox.showinfo("Info", "Archivo de promedios cargado. Disponible gráfico de barras.")
                    # Deshabilitar dispersión (no hay datos suficientes)
                    self._show_empty_message(self.scatter_ax, "No disponible para archivo de promedios")
                    self.scatter_canvas.draw()
                    
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")

    def actualizar_checkboxes(self):
        """Actualiza los Radiobuttons y Checkbuttons según los elementos."""
        if self.df is None:
            return
        elementos = self.df["Elemento"].unique()
        for widget in self.frame_x.winfo_children():
            widget.destroy()
        for widget in self.frame_y.winfo_children():
            widget.destroy()

        self.x_var.set("")
        self.y_vars = {}

        for elemento in sorted(elementos):
            tk.Radiobutton(
                self.frame_x, text=elemento, variable=self.x_var, value=elemento
            ).pack(anchor="w")
            var = tk.BooleanVar()
            tk.Checkbutton(self.frame_y, text=elemento, variable=var).pack(anchor="w")
            self.y_vars[elemento] = var

    # ----- GRÁFICO DE BARRAS (desde promedios) -----
    def update_bar_chart_from_results(self):
        """Genera gráfico de barras desde self.results (resultados del análisis)."""
        if not self.results:
            self._show_empty_message(self.bar_ax, "No hay datos para gráfico")
            self.bar_canvas.draw()
            return

        all_dfs = []
        for res in self.results:
            df = res.get('composition')
            if df is not None and not df.empty:
                percent_col = self._get_percent_col(df)
                if percent_col:
                    all_dfs.append(df[['Elemento', percent_col]].copy())

        if not all_dfs:
            self._show_empty_message(self.bar_ax, "No hay datos para gráfico")
            self.bar_canvas.draw()
            return

        combined = pd.concat(all_dfs, ignore_index=True)
        percent_col = self._get_percent_col(combined)
        grouped = combined.groupby('Elemento')[percent_col].mean().reset_index()
        grouped.columns = ['Elemento', 'Media']

        self._draw_bar_chart(grouped, percent_col)

    def update_bar_chart(self):
        """Genera gráfico de barras desde self.df_promedio (archivo de promedios)."""
        if self.df_promedio is None or self.df_promedio.empty:
            self._show_empty_message(self.bar_ax, "No hay datos de promedios")
            self.bar_canvas.draw()
            return

        percent_col = self._get_percent_col(self.df_promedio)
        if percent_col is None:
            self._show_empty_message(self.bar_ax, "No se encontró columna de porcentaje")
            self.bar_canvas.draw()
            return

        # El archivo de promedios ya tiene Elemento y el porcentaje
        grouped = self.df_promedio[['Elemento', percent_col]].copy()
        grouped.columns = ['Elemento', 'Media']

        self._draw_bar_chart(grouped, percent_col)

    def _draw_bar_chart(self, grouped, percent_col):
        """Dibuja el gráfico de barras con los datos agrupados."""
        grouped = grouped.sort_values('Media', ascending=False)

        self.bar_ax.clear()
        bars = self.bar_ax.bar(
            grouped['Elemento'],
            grouped['Media'],
            capsize=5,
            color='skyblue',
            edgecolor='black'
        )
        self.bar_ax.set_ylabel(f'Porcentaje ({percent_col})')
        self.bar_ax.set_title('Composición promedio de elementos')
        self.bar_ax.grid(axis='y', linestyle='--', alpha=0.7)

        for bar in bars:
            height = bar.get_height()
            self.bar_ax.text(
                bar.get_x() + bar.get_width()/2.,
                height + 0.5,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=8
            )

        self.bar_fig.tight_layout()
        self.bar_canvas.draw()

    # ----- GRÁFICO DE DISPERSIÓN (desde datos completos) -----
    def update_scatter_plot(self):
        """Actualiza el gráfico de dispersión con los elementos seleccionados."""
        if self.df is None:
            self._show_empty_message(self.scatter_ax, "Cargue un archivo de datos completos")
            self.scatter_canvas.draw()
            return

        percent_col = self._get_percent_col(self.df)
        if percent_col is None:
            self._show_empty_message(self.scatter_ax, "No se encontró columna de porcentaje")
            self.scatter_canvas.draw()
            return

        x_element = self.x_var.get()
        y_elements = [
            element
            for element, var in self.y_vars.items()
            if var.get() and element != x_element
        ]

        if not x_element or not y_elements:
            self._show_empty_message(self.scatter_ax, 
                                     "Seleccione un elemento en 'x' y uno o más en 'y'")
            self.scatter_canvas.draw()
            return

        x_data = self.df[self.df["Elemento"] == x_element][percent_col].reset_index(drop=True)

        if x_data.empty:
            self._show_empty_message(self.scatter_ax, f"No hay datos para '{x_element}'")
            self.scatter_canvas.draw()
            return

        self.scatter_ax.clear()
        colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']

        for i, y_element in enumerate(y_elements):
            y_data = self.df[self.df["Elemento"] == y_element][percent_col].reset_index(drop=True)
            min_len = min(len(x_data), len(y_data))
            if min_len == 0:
                continue
            x_plot = x_data[:min_len]
            y_plot = y_data[:min_len]
            color = colors[i % len(colors)]
            self.scatter_ax.scatter(
                x_plot, y_plot,
                label=y_element,
                alpha=0.6,
                s=30,
                color=color,
                edgecolors='black',
                linewidth=0.5
            )

        self.scatter_ax.set_xlabel(f"{x_element} {percent_col}")
        self.scatter_ax.set_ylabel(percent_col)
        self.scatter_ax.set_title(f'Dispersión: {x_element} vs otros elementos')
        self.scatter_ax.legend()
        self.scatter_ax.grid(True, alpha=0.3)
        self.scatter_fig.tight_layout()
        self.scatter_canvas.draw()