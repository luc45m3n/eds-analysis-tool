# -*- coding: utf-8 -*-
"""
Pestaña de Análisis EDS con procesamiento paralelo, cancelación, log en GUI y gráficos.
"""

import os
import glob
import threading
import logging
import sys
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import scrolledtext

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from core.processing import process_spectrum
from utils.helpers import extract_kfactors

logger = logging.getLogger(__name__)


class AnalisisEDS(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.current_path = app.current_path
        self.selected_path = ""
        self.cancel_event = threading.Event()
        self.executor = None
        self.futures = {}
        self.results = []
        self.progress_win = None
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        # --- Widgets existentes ---
        self.select_button = ttk.Button(
            self, text="Directorio de Trabajo", command=self.select_folder
        )
        self.select_button.pack(pady=5, fill=tk.X)

        self.path_label = ttk.Label(self, text=self.current_path, wraplength=660)
        self.path_label.pack(pady=5)

        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        ttk.Label(self, text="Muestra:").pack(pady=2, fill=tk.X)
        self.muestra_entry = ttk.Entry(self, width=50)
        self.muestra_entry.pack(pady=2, fill=tk.X)
        self.muestra_entry.insert(0, "Nombre_Muestra")

        self.elementos_entry_var = tk.StringVar(value="Al ,Ca ,Fe, Mg ,Na, Si")
        ttk.Label(self, text="Elementos (separados por coma):").pack(pady=2, fill=tk.X)
        self.elementos_entry = ttk.Entry(
            self, width=50, textvariable=self.elementos_entry_var
        )
        self.elementos_entry.pack(pady=2, fill=tk.X)

        # --- Selección de unidades ---
        units_frame = ttk.Frame(self)
        units_frame.pack(pady=2, fill=tk.X)
        ttk.Label(units_frame, text="Unidades:").pack(side=tk.LEFT, padx=5)
        self.units_var = tk.StringVar(value="wt")
        units_combo = ttk.Combobox(
            units_frame,
            textvariable=self.units_var,
            values=["wt", "at"],
            state="readonly",
            width=5
        )
        units_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(units_frame, text="(wt% / at%)").pack(side=tk.LEFT)

        # --- Selector de umbral ---
        umbral_frame = ttk.Frame(self)
        umbral_frame.pack(pady=2, fill=tk.X)
        ttk.Label(umbral_frame, text="Umbral de filtrado (%):").pack(side=tk.LEFT, padx=5)
        self.umbral_var = tk.StringVar(value="1.0")
        self.umbral_entry = ttk.Entry(umbral_frame, textvariable=self.umbral_var, width=8)
        self.umbral_entry.pack(side=tk.LEFT, padx=5)

        # --- Selector de sensibilidad SNR ---
        snr_frame = ttk.Frame(self)
        snr_frame.pack(pady=2, fill=tk.X)
        ttk.Label(snr_frame, text="Sensibilidad SNR:").pack(side=tk.LEFT, padx=5)
        self.snr_var = tk.StringVar(value="3.0")
        snr_combo = ttk.Combobox(
            snr_frame,
            textvariable=self.snr_var,
            values=["0","1.0", "2.0", "3.0", "4.0", "5.0", "10.0"],
            state="readonly",
            width=5
        )
        snr_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(snr_frame, text="(mayor = más estricto)").pack(side=tk.LEFT)

        # --- Carpeta de salida ---
        ttk.Label(self, text="Carpeta de salida:").pack(pady=2, fill=tk.X)
        self.output_dir_frame = ttk.Frame(self)
        self.output_dir_frame.pack(fill=tk.X, pady=2)
        self.output_dir_entry = ttk.Entry(self.output_dir_frame, width=40)
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.output_dir_entry.insert(0, "salida")
        self.output_dir_button = ttk.Button(
            self.output_dir_frame, text="Seleccionar", command=self.select_output_dir
        )
        self.output_dir_button.pack(side=tk.RIGHT, padx=(5, 0))

        # --- Cuentas mínimas ---
        self.cuentas_minimas_var = tk.StringVar(value="100000")
        ttk.Label(self, text="Cuentas mínimas:").pack(pady=2, fill=tk.X)
        self.cuentas_minimas_entry = ttk.Entry(
            self, width=10, textvariable=self.cuentas_minimas_var
        )
        self.cuentas_minimas_entry.pack(pady=2, fill=tk.X)

        # --- Lista de archivos ---
        self.file_listbox = tk.Listbox(
            list_frame,
            width=70,
            height=5,
            font=("Helvetica", 10),
            bg="white",
            fg="black",
            selectbackground="#a6a6a6",
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<Double-1>", self.on_double_click)

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.file_listbox.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        # --- Botones de control ---
        self.button_frame = ttk.Frame(self, style="TFrame")
        self.button_frame.pack(fill=tk.X, pady=10)

        self.analyze_button = ttk.Button(
            self.button_frame, text="Analizar EDS", command=self.start_analysis
        )
        self.analyze_button.pack(side=tk.RIGHT, expand=True, padx=(5, 0))

        self.cancel_button = ttk.Button(
            self.button_frame,
            text="Cancelar",
            command=self.cancel_analysis,
            state="disabled"
        )
        self.cancel_button.pack(side=tk.RIGHT, padx=(5, 0))

        self.update_file_list()
        

    # ----- Métodos existentes -----

    def select_output_dir(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, folder)

    def select_folder(self):
        self.current_path = filedialog.askdirectory()
        self.path_label.config(text=self.current_path)
        self.app.current_path = self.current_path
        self.update_file_list()

    def update_file_list(self):
        self.file_listbox.delete(0, tk.END)
        for item in os.listdir(self.current_path):
            full_path = os.path.join(self.current_path, item)
            if os.path.isdir(full_path):
                self.file_listbox.insert(tk.END, f"📁 {item}")
            elif item.lower().endswith(".spc") or item.lower().endswith(".xml"):
                self.file_listbox.insert(tk.END, f"📄 {item}")

    def on_double_click(self, event):
        selection = self.file_listbox.curselection()
        if selection:
            item = self.file_listbox.get(selection[0])
            item_name = item[2:]
            item_path = os.path.join(self.current_path, item_name)
            if os.path.isdir(item_path):
                self.current_path = item_path
                self.path_label.config(text=self.current_path)
                self.app.current_path = self.current_path
                self.update_file_list()

    def cancel_analysis(self):
        """Solicita la cancelación del análisis en curso."""
        if self.progress_win and self.progress_win.winfo_exists():
            self.log_message_progress("Cancelando análisis...", "WARNING")
        self.cancel_event.set()
        if self.executor:
            for future in self.futures.values():
                future.cancel()
            self.executor.shutdown(wait=False, cancel_futures=True)
        self.cancel_button.config(state="disabled")
        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.status_label.config(text="Cancelando...")

    # ----- Métodos para la ventana de progreso -----

    def log_message_progress(self, msg, level="INFO"):
        """Escribe UNA línea de mensaje en el área de log de la ventana de progreso."""
        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.log_text.config(state='normal')
            self.progress_win.log_text.insert(tk.END, f"[{level}] {msg}\n")
            self.progress_win.log_text.see(tk.END)
            self.progress_win.log_text.config(state='disabled')
            self.progress_win.update_idletasks()

    def log_block_progress(self, text, level="TERMINAL"):
        """
        Inserta un BLOQUE de texto (potencialmente varias líneas, p.ej. la tabla
        completa de un espectro) de una sola vez, en un único acceso al widget,
        para que no se intercale con bloques de otros hilos/tareas.
        """
        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.log_text.config(state='normal')
            for line in text.rstrip("\n").split("\n"):
                self.progress_win.log_text.insert(tk.END, f"[{level}] {line}\n")
            self.progress_win.log_text.see(tk.END)
            self.progress_win.log_text.config(state='disabled')
            self.progress_win.update_idletasks()

    def update_progress(self, value, max_value, status):
        """Actualiza la barra de progreso."""
        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.progress_bar["maximum"] = max_value
            self.progress_win.progress_bar["value"] = value
            self.progress_win.status_label.config(text=status)
            self.progress_win.update_idletasks()

    # ----- Clase para capturar stdout/stderr agrupando por tarea/hilo -----
    class ThreadLocalTee:
        """
        Redirige stdout/stderr. En vez de escribir línea por línea directo al log
        (lo cual, con varios hilos en paralelo, genera intercalado/solapamiento),
        cada hilo acumula su salida en un buffer propio (threading.local). El
        buffer se vacía explícitamente con start_capture()/stop_capture() al
        principio y al final de cada tarea, y el texto completo se vuelca al
        log como un solo bloque.
        """
        def __init__(self, original_stream):
            self.original_stream = original_stream
            self._local = threading.local()

        def start_capture(self):
            """Llamar al comienzo de la tarea, dentro del hilo worker."""
            self._local.buffer = io.StringIO()

        def stop_capture(self):
            """Llamar al final de la tarea. Devuelve el texto acumulado y limpia."""
            buf = getattr(self._local, "buffer", None)
            text = buf.getvalue() if buf is not None else ""
            self._local.buffer = None
            return text

        def write(self, message):
            buf = getattr(self._local, "buffer", None)
            if buf is not None:
                buf.write(message)
            elif message.strip():
                # Sin captura activa en este hilo (ej. hilo principal): no perdemos
                # el mensaje, lo mandamos igual a la terminal original más abajo.
                pass
            if self.original_stream:
                self.original_stream.write(message)

        def flush(self):
            if self.original_stream:
                self.original_stream.flush()

    def start_analysis(self):
        """Inicia el análisis en un hilo separado y abre la ventana de progreso."""
        if self.executor is not None:
            return

        # Crear ventana de progreso
        self.progress_win = tk.Toplevel(self)
        self.progress_win.title("Progreso del Análisis EDS")
        self.progress_win.geometry("700x550")
        self.progress_win.transient(self)
        self.progress_win.protocol("WM_DELETE_WINDOW", self.on_progress_window_close)

        # Frame para barra de progreso
        frame_progress = ttk.Frame(self.progress_win)
        frame_progress.pack(fill=tk.X, pady=10, padx=10)

        self.progress_win.progress_bar = ttk.Progressbar(
            frame_progress, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_win.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_win.status_label = ttk.Label(frame_progress, text="Iniciando...", width=30)
        self.progress_win.status_label.pack(side=tk.RIGHT, padx=5)

        # Área de log (con scroll)
        self.progress_win.log_text = scrolledtext.ScrolledText(
            self.progress_win, height=18, state='disabled', font=("Courier", 9)
        )
        self.progress_win.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Botón de cerrar (inicialmente deshabilitado hasta que termine)
        self.progress_win.close_button = ttk.Button(
            self.progress_win, text="Cerrar", command=self.close_progress_window, state="disabled"
        )
        self.progress_win.close_button.pack(pady=5)

        # Redirigir stdout y stderr al log de la GUI
        self._setup_output_redirect()

        # Ejecutar análisis en un hilo separado
        threading.Thread(target=self.analyze_eds, daemon=True).start()

    def _setup_output_redirect(self):
        """Redirige stdout y stderr usando el Tee thread-local (agrupado por tarea)."""
        self.stdout_logger = self.ThreadLocalTee(self._original_stdout)
        self.stderr_logger = self.ThreadLocalTee(self._original_stderr)
        sys.stdout = self.stdout_logger
        sys.stderr = self.stderr_logger

    def _restore_output(self):
        """Restaura stdout y stderr a sus valores originales."""
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr

    def close_progress_window(self):
        """Cierra la ventana de progreso y restaura la salida."""
        self._restore_output()
        if self.progress_win and self.progress_win.winfo_exists():
            self.progress_win.destroy()
            self.progress_win = None

    def on_progress_window_close(self):
        """Maneja el cierre manual de la ventana (no permite cerrar durante el análisis)."""
        if self.analyze_button['state'] == 'disabled':
            messagebox.showwarning(
                "Análisis en curso",
                "El análisis está en progreso. No puedes cerrar esta ventana."
            )
        else:
            self.close_progress_window()

    # ----- Wrapper que corre en cada hilo worker: captura su propia salida -----
    def _process_spectrum_captured(self, **kwargs):
        """
        Se ejecuta DENTRO del hilo worker del ThreadPoolExecutor.
        Activa la captura de stdout/stderr para ESTE hilo, corre process_spectrum,
        y devuelve el resultado junto con todo lo que se imprimió, como texto.
        """
        self.stdout_logger.start_capture()
        self.stderr_logger.start_capture()
        try:
            result = process_spectrum(**kwargs)
        finally:
            out_text = self.stdout_logger.stop_capture()
            err_text = self.stderr_logger.stop_capture()
        return result, out_text, err_text

    # ----- Método principal de análisis -----

    def analyze_eds(self):
        """Ejecuta el análisis (se ejecuta en un hilo secundario)."""
        self.results = []
        try:
            snr_umbral = float(self.snr_var.get().strip())
        except ValueError:
            snr_umbral = 3.0
            self.log_message("Valor SNR inválido. Usando 3.0 (estándar)", "WARNING")
        # Obtener parámetros en el hilo principal
        def get_params():
            try:
                umbral = float(self.umbral_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", "El umbral debe ser un número.")
                return None
            muestra = self.muestra_entry.get().strip()
            if not muestra:
                messagebox.showerror("Error", "Debe ingresar un nombre de muestra.")
                return None
            try:
                cuentas_minimas = float(self.cuentas_minimas_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Cuentas mínimas debe ser un número.")
                return None
            units_map = {"wt": "weight", "at": "atomic"}
            units = units_map.get(self.units_var.get(), "weight")
            elementos_str = self.elementos_entry_var.get()
            kfactor_path = Path(self.app.RESOURCES_DIR) / "kfactor.txt"
            elementos_data = extract_kfactors(elementos_str, str(kfactor_path))
            output_dir = self.output_dir_entry.get().strip() or "salida"
            path = self.current_path
            spc_files = glob.glob(os.path.join(path, "*.spc"))
            xml_files = glob.glob(os.path.join(path, "*.xml"))
            if not spc_files:
                messagebox.showerror("Error", "No se encontraron archivos .spc.")
                return None
            return (muestra, cuentas_minimas, units, elementos_data, output_dir, path, spc_files, xml_files, umbral)

        # Obtener parámetros (con timeout)
        params = None
        def get_params_callback():
            nonlocal params
            params = get_params()
        self.master.after(0, get_params_callback)

        import time
        timeout = 0
        while params is None and timeout < 10:
            time.sleep(0.1)
            timeout += 0.1
        if params is None:
            self.master.after(0, lambda: self.close_progress_window())
            return

        (muestra, cuentas_minimas, units, elementos_data, output_dir, path, spc_files, xml_files, umbral) = params

        total = len(spc_files)

        self.master.after(0, lambda: self.update_progress(0, total, "Iniciando..."))
        self.master.after(0, lambda: self.log_message_progress(f"Iniciando análisis de {total} espectros"))
        self.master.after(0, lambda: self.log_message_progress(f"Unidades: {units}, Cuentas mínimas: {cuentas_minimas}, Umbral: {umbral}%"))
        self.master.after(0, lambda: self.log_message_progress(f"Carpeta de salida: {output_dir}"))

        self.master.after(0, lambda: self.analyze_button.config(state="disabled"))
        self.master.after(0, lambda: self.cancel_button.config(state="normal"))
        self.master.after(0, lambda: self.progress_win.close_button.config(state="disabled"))

        self.cancel_event.clear()
        os.makedirs(output_dir, exist_ok=True)

        # Ejecutar en paralelo
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.futures = {}
        for i, spc_file in enumerate(spc_files):
            # Nota: ahora se somete el WRAPPER (_process_spectrum_captured),
            # no process_spectrum directamente, para poder capturar su salida
            # por tarea y evitar el solapamiento en el log.
            future = self.executor.submit(
                self._process_spectrum_captured,
                spc_file=spc_file,
                xml_files=xml_files,
                idx=i,
                muestra=muestra,
                cuentas_minimas=cuentas_minimas,
                elementos_data=elementos_data,
                output_dir=output_dir,
                units=units,
                umbral=umbral,
                snr_umbral=snr_umbral, 
                cancel_event=self.cancel_event,
                verbose=True
            )
            self.futures[future] = (i, spc_file)

        unit_label = 'wt.%' if units == 'weight' else 'at.%'

        txt_datos_path = os.path.join(output_dir, f"{muestra}_datos_completos.txt")
        txt_promedio_path = os.path.join(output_dir, f"{muestra}_promedio.txt")
        os.makedirs(output_dir, exist_ok=True)

        with open(txt_datos_path, 'w') as f:
            f.write(f"Elemento;{unit_label};Intensidad;Archivo\n")

        processed = 0
        for future in as_completed(self.futures):
            i, spc_file = self.futures[future]
            out_text, err_text = "", ""
            try:
                result, out_text, err_text = future.result(timeout=1)

                if result is not None and result.get('valid', False):
                    self.results.append(result)
                    df = result.get('composition', pd.DataFrame())
                    Area = result.get('Area', 'Desconocido')
                    Spot = result.get('Spot', '')
                    nombre_archivo = Path(spc_file).name

                    # --- ESCRIBIR DATOS COMPLETOS (APPEND) ---
                    with open(txt_datos_path, 'a') as f:
                        for _, row in df.iterrows():
                            if units == 'weight':
                                percent = row.get('wt.%', 0)
                            else:
                                percent = row.get('at.%', 0)
                            intensidad = row.get('Intensidad', 0)
                            f.write(f"{row['Elemento']};{percent:.2f};{intensidad:.2f};{nombre_archivo}\n")

                    if not df.empty:
                        elements = ', '.join(df['Elemento'].tolist())
                        msg = f"✅ {Area} ({Spot}) - {len(df)} elementos: {elements}"
                    else:
                        msg = f"⚠️ {Area} ({Spot}) - Sin elementos detectados"
                else:
                    error = result.get('error', 'Error desconocido') if result else 'Sin resultado'
                    msg = f"❌ {Path(spc_file).name}: {error}"

            except Exception as e:
                msg = f"❌ Error en {Path(spc_file).name}: {e}"
                out_text, err_text = "", ""

            processed += 1

            if out_text and out_text.strip():
                self.master.after(0, lambda t=out_text: self.log_block_progress(t, "TERMINAL"))
            if err_text and err_text.strip():
                self.master.after(0, lambda t=err_text: self.log_block_progress(t, "ERROR"))

            self.master.after(0, lambda m=msg: self.log_message_progress(m))
            self.master.after(0, lambda v=processed, t=total: self.update_progress(v, t, f"Procesado {v}/{t}"))

            if self.cancel_event.is_set():
                self.master.after(0, lambda: self.log_message_progress("Análisis cancelado por el usuario.", "WARNING"))
                break

        # --- BLOQUE DE PROMEDIOS ---
        if self.results:
            self.log_message_progress("Calculando promedios...", "INFO")
            
            all_dfs = []
            for res in self.results:
                df = res.get('composition')
                if df is not None and not df.empty:
                    percent_col = 'wt.%' if units == 'weight' else 'at.%'
                    if percent_col in df.columns:
                        all_dfs.append(df[['Elemento', percent_col]].copy())
            
            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True)
                promedio = combined.groupby('Elemento')[percent_col].mean().reset_index()
                promedio.columns = ['Elemento', f'Promedio_{unit_label}']
            
                with open(txt_promedio_path, 'w') as f:
                    f.write(f"Elemento;{unit_label}\n")
                    for _, row in promedio.iterrows():
                        f.write(f"{row['Elemento']};{row[f'Promedio_{unit_label}']:.2f}\n")
                
                self.log_message_progress(f"Archivo de promedios guardado: {txt_promedio_path}", "INFO")

        # ============================================================
        # FINALIZAR EJECUTOR
        # ============================================================
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None

        # Restaurar estado
        self.master.after(0, lambda: self.analyze_button.config(state="normal"))
        self.master.after(0, lambda: self.cancel_button.config(state="disabled"))
        self.master.after(0, lambda: self.progress_win.close_button.config(state="normal"))
        self.master.after(0, lambda: self.progress_win.status_label.config(text="Finalizado"))

        if self.cancel_event.is_set():
            self.master.after(0, lambda: self.log_message_progress("Procesamiento interrumpido.", "WARNING"))
        else:
            self.master.after(0, lambda: self.log_message_progress("Análisis completado exitosamente."))
            if self.results:
                self.master.after(0, lambda: self.log_message_progress(f"Se procesaron {len(self.results)} espectros válidos."))
                self.master.after(0, lambda: self.app.tab_estadisticas.set_results(self.results))
                self.master.after(0, lambda: self.app.tab_estadisticas.update_bar_chart())
                
                # Actualizar estadísticas con el archivo de datos completos
                txt_datos_path = os.path.join(output_dir, f"{muestra}_datos_completos.txt")
                if os.path.exists(txt_datos_path):
                    try:
                        df_nuevo = pd.read_csv(txt_datos_path, sep=";", decimal=".")
                        self.master.after(0, lambda: self.app.tab_estadisticas.cargar_dataframe(df_nuevo))
                    except Exception as e:
                        logger.error(f"Error al recargar archivo en estadísticas: {e}")
                        
    # ----- Gráfico de barras -----
    def show_bar_chart(self):
        """Genera un gráfico de barras con el promedio de wt% o at% de cada elemento."""
        if not self.results:
            return

        all_dfs = []
        for res in self.results:
            df = res.get('composition')
            if df is not None and not df.empty:
                # Detectar qué columna de porcentaje existe
                if 'wt.%' in df.columns:
                    percent_col = 'wt.%'
                elif 'at.%' in df.columns:
                    percent_col = 'at.%'
                else:
                    continue
                df = df[['Elemento', percent_col]].copy()
                all_dfs.append(df)

        if not all_dfs:
            self.log_message_progress("No hay datos para generar gráfico.", "WARNING")
            return

        combined = pd.concat(all_dfs, ignore_index=True)
        grouped = combined.groupby('Elemento')[percent_col].agg(['mean', 'std']).reset_index()
        grouped.columns = ['Elemento', 'Media', 'Desviacion']

        win = tk.Toplevel(self)
        win.title("Gráfico de barras - Composición promedio")
        win.geometry("700x500")

        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(
            grouped['Elemento'],
            grouped['Media'],
            yerr=grouped['Desviacion'],
            capsize=5,
            color='skyblue',
            edgecolor='black'
        )
        ax.set_ylabel(f'Porcentaje ({percent_col})')
        ax.set_title('Composición promedio de elementos')
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width()/2.,
                height + 0.5,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=9
            )

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        ttk.Button(win, text="Cerrar", command=win.destroy).pack(pady=5)

        self.log_message_progress(f"Gráfico de barras generado ({percent_col}).", "INFO")