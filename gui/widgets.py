import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import glob
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from script.analysis import extract_kfactors, get_sample_info, analyze_eds_sample
from script.report_generator import generate_eds_report


class AnalysisTab(ttk.Frame):
    """Pestaña para el análisis EDS."""
    
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self._setup_ui()
        
    def _setup_ui(self):
        """Configura la interfaz de usuario de la pestaña."""
        
        # Equipos TECNAI/CM200
        self.equipo_var = tk.StringVar(value="TECNAI")
        ttk.Label(self, text="Seleccionar modelo de equipo:").pack(pady=2, fill=tk.X)
        equipo_menu = ttk.OptionMenu(self, self.equipo_var, "TECNAI", "TECNAI", "Philips CM200")
        equipo_menu.pack(pady=2, fill=tk.X)

        self.path_label = ttk.Label(self, text=self.app.current_path, wraplength=660)
        self.path_label.pack(pady=5)
        
        # Configuración del directorio de trabajo
        self.select_button = ttk.Button(
            self, text="Directorio de Trabajo", command=self._select_folder
        )
        self.select_button.pack(pady=5, fill=tk.X)

        # Frame principal
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configuración del análisis
        config_frame = ttk.LabelFrame(main_frame, text="Configuración", padding=10)
        config_frame.pack(fill=tk.X, pady=5)
        
        # Campo para el nombre de la muestra (CORRECCIÓN CLAVE)
        sample_frame = ttk.Frame(config_frame)
        sample_frame.pack(fill=tk.X, pady=5)
        ttk.Label(sample_frame, text="Muestra:").pack(side=tk.LEFT)
        
        # Definimos self.muestra_entry como atributo de la clase
        self.muestra_entry = ttk.Entry(sample_frame)
        self.muestra_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.muestra_entry.insert(0, "Nombre de la muestra")
        
        # Campo para elementos (también corregido para ser consistente)
        elements_frame = ttk.Frame(config_frame)
        elements_frame.pack(fill=tk.X, pady=5)
        ttk.Label(elements_frame, text="Elementos (separados por coma):").pack(side=tk.LEFT)
        
        self.elementos_entry_var = tk.StringVar(value="Al, Ca, Fe, Mg, Na, Si")
        self.elementos_entry = ttk.Entry(elements_frame, textvariable=self.elementos_entry_var)
        self.elementos_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Cuentas mínimas
        ttk.Label(config_frame, text="Cuentas mínimas:").pack(side=tk.LEFT)
        self.min_counts_entry = ttk.Entry(config_frame, width=10)
        self.min_counts_entry.pack(pady=2, fill=tk.X)
        #self.min_counts_entry.insert(0, "100000")
        self.cuentas_minimas_var = tk.StringVar(value="100000")  # Valor preestablecido
        self.cuentas_minimas_entry = ttk.Entry(
            config_frame, 
            textvariable=self.cuentas_minimas_var,
            validate="key",
            validatecommand=(self.register(self._validate_number), '%P')
        )

        # Lista de archivos
        self.file_listbox = tk.Listbox(
            self,
            width=70,
            height=5,
            font=("Helvetica", 10),
            bg="white",
            fg="black",
            selectbackground="#a6a6a6",
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.file_listbox.bind("<Double-1>", self._on_double_click)
        
        # Botón de análisis
        self.analyze_button = ttk.Button(
            self, text="Analizar EDS", command=self._run_analysis
        )
        self.analyze_button.pack(side=tk.BOTTOM, pady=10)

        # Etiqueta de estado
        self.status_label = ttk.Label(main_frame, text="", foreground="blue")
        self.status_label.pack(fill=tk.X, pady=5)
        
        self._update_file_list()

        
    def _run_analysis(self):
        """Método de análisis corregido"""
        try:
            self.analyze_button.config(state=tk.DISABLED)
            self.status_label.config(text="Preparando análisis...")
            self.update()
            
            # Obtener parámetros del UI
            params = {
                'muestra': self.muestra_entry.get(),
                'elementos': self.elementos_entry_var.get(),
                'cuentas_minimas': int(self.cuentas_minimas_var.get()),
                'equipo': self.equipo_var.get(),
                'path': self.app.current_path
            }
            
            # Validaciones básicas
            if not params['muestra'] or params['muestra'].strip() == "":
                raise ValueError("Debe ingresar un nombre de muestra")
                
            if not params['elementos'] or params['elementos'].strip() == "":
                raise ValueError("Debe especificar elementos a analizar")
            
            # Procesar archivos
            self._process_files(params)
            
            self.status_label.config(text="Análisis completado", foreground="green")
            messagebox.showinfo("Éxito", "Análisis realizado correctamente")
            
        except ValueError as ve:
            messagebox.showerror("Error de validación", str(ve))
            self.status_label.config(text=f"Error: {str(ve)}", foreground="red")
        except Exception as e:
            messagebox.showerror("Error", f"Error inesperado: {str(e)}")
            self.status_label.config(text=f"Error: {str(e)}", foreground="red")
        finally:
            self.analyze_button.config(state=tk.NORMAL)
            

    def _process_files(self, params):
        """Procesa los archivos individualmente"""
        # Construye la ruta correcta a kfactor.txt
        kfactor_path = os.path.join(self.app.app_dir, "data", "kfactor.txt")
        
        # Verifica si el archivo existe
        if not os.path.exists(kfactor_path):
            raise FileNotFoundError(f"No se encontró kfactor.txt en: {kfactor_path}")
        
        # Pasa la ruta correcta a extract_kfactors
        elementos_data = extract_kfactors(params['elementos'], kfactor_path)
        output_dir = os.path.join(params['path'], "salida")
        os.makedirs(output_dir, exist_ok=True)
        
        spc_files = glob.glob(os.path.join(params['path'], "*.spc"))
        if not spc_files:
            raise ValueError("No se encontraron archivos .spc en el directorio")
        
        resultados_totales = []
        
        for spc_file in spc_files:
            self.status_label.config(text=f"Procesando {os.path.basename(spc_file)}...")
            self.update()
            
            try:
                # Configurar información según el equipo
                if params['equipo'] == "TECNAI":
                    xml_file = spc_file.replace('.spc', '.xml')
                    if not os.path.exists(xml_file):
                        raise FileNotFoundError(f"Archivo XML no encontrado para {os.path.basename(spc_file)}")
                    
                    sample_info = get_sample_info([xml_file])
                    nombre_muestra = sample_info[0][0]
                    area = sample_info[1][0]
                else:
                    nombre_muestra = os.path.splitext(os.path.basename(spc_file))[0]
                    area = "Área no especificada"
                
                # Analizar archivo
                resultados = analyze_eds_sample(
                    spc_file,
                    (nombre_muestra, area),
                    elementos_data,
                    params['cuentas_minimas'],
                    params['equipo']
                )
                resultados_totales.append(resultados)
                
                # Generar reporte PDF
                generate_eds_report(
                    output_dir,
                    nombre_muestra,
                    area,
                    [elem for elem in elementos_data if elem['wt'] > 0]
                )
                
            except Exception as e:
                print(f"Error procesando {os.path.basename(spc_file)}: {str(e)}")
                continue
        
        # Guardar resultados consolidados
        if resultados_totales:
            with open(os.path.join(output_dir, f"{params['muestra']}_resultados.txt"), "w") as f:
                f.write("Elemento;wt.%;Intensidad;Archivo;Equipo\n")
                for res in resultados_totales:
                    for elem in res['elements']:
                        if elem['wt'] > 0:
                            f.write(
                                f"{elem['elemento']};{elem['wt']:.2f};"
                                f"{elem['intensidad']:.2f};"
                                f"{res['filename']};{params['equipo']}\n"
                            )
        else:
            raise ValueError("No se pudo procesar ningún archivo correctamente")

    def _stop_analysis(self):
        """Detiene el análisis en curso"""
        self.stop_event.set()
        messagebox.showinfo("Información", "Deteniendo el análisis...")
        
    def _reset_ui(self):
        """Restablece la UI después del análisis"""
        self.analyze_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress['value'] = 0

    def _select_folder(self):
        """Selecciona un directorio de trabajo."""
        initial_dir = self.app.current_path if os.path.exists(self.app.current_path) else self.app.app_dir
        new_path = filedialog.askdirectory(initialdir=initial_dir)
        if new_path:
            self.app.current_path = new_path
            self.path_label.config(text=self.app.current_path)
            self._update_file_list()
            
    def _update_file_list(self):
        """Actualiza la lista de archivos en el directorio actual."""
        self.file_listbox.delete(0, tk.END)
        
        try:
            for item in os.listdir(self.app.current_path):
                item_path = os.path.join(self.app.current_path, item)
                if os.path.isdir(item_path):
                    self.file_listbox.insert(tk.END, f"📁 {item}")
                elif item.endswith(".spc"):
                    self.file_listbox.insert(tk.END, f"📄 {item}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el directorio: {str(e)}")
                
    def _on_double_click(self, event):
        """Maneja el doble clic en un elemento de la lista."""
        selection = self.file_listbox.curselection()
        if selection:
            item = self.file_listbox.get(selection[0])
            item_name = item[2:]
            item_path = os.path.join(self.app.current_path, item_name)
            
            if os.path.isdir(item_path):
                self.app.current_path = item_path
                self.path_label.config(text=self.app.current_path)
                self._update_file_list()

    def _validate_number(self, value):
        """Valida que el valor sea un número positivo"""
        if value == "":
            return True
        try:
            return int(value) >= 0
        except ValueError:
            return False

    def analyze_eds(self):
        """Versión adaptada con selección de equipo"""
        try:
            # Obtener parámetros de la interfaz
            equipo = self.equipo_var.get()
            muestra = self.muestra_entry.get()
            cuentas_minimas = int(self.cuentas_minimas_entry.get())
            elementos_str = self.elementos_entry_var.get()

            # Validaciones básicas
            if not muestra:
                raise ValueError("Debe especificar un nombre de muestra")
            if not elementos_str:
                raise ValueError("Debe especificar elementos a analizar")
            if cuentas_minimas <= 0:
                raise ValueError("Las cuentas mínimas deben ser positivas")

            # Resto del código de análisis...
            print(f"Análisis iniciado para {muestra} con {cuentas_minimas} cuentas mínimas")

        except ValueError as e:
            messagebox.showerror("Error de validación", f"Datos incorrectos: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo completar el análisis: {str(e)}")

            # Configurar rutas
            output_dir = os.path.join(self.current_path, "salida")
            os.makedirs(output_dir, exist_ok=True)

            # Extraer factores K
            kfactor_path = os.path.join(self.app.app_dir, "data", "kfactor.txt")
            print(kfactor_path)
            elementos_data = extract_kfactors(elementos_str, kfactor_path)

            # Obtener archivos .spc
            spc_files = sorted(glob.glob(os.path.join(self.current_path, "*.spc")))

            if not spc_files:
                raise FileNotFoundError("No se encontraron archivos .spc en el directorio")

            # Procesar según el equipo seleccionado
            if equipo == "TECNAI":
                # Para TECNAI, buscar archivos XML correspondientes
                xml_files = sorted(glob.glob(os.path.join(self.current_path, "*.xml")))

                if len(spc_files) != len(xml_files):
                    print(f"Advertencia: {len(spc_files)} archivos .spc vs {len(xml_files)} archivos .xml")

                # Emparejar archivos por nombre base
                paired_files = []
                for spc in spc_files:
                    base = os.path.splitext(os.path.basename(spc))[0]
                    xml = f"{base}.xml"
                    xml_path = os.path.join(self.current_path, xml)

                    if os.path.exists(xml_path):
                        paired_files.append((spc, xml_path))
                    else:
                        print(f"Advertencia: No se encontró {xml} para {os.path.basename(spc)}")
                        paired_files.append((spc, None))
            else:
                # Para CM200, no necesitamos XML
                paired_files = [(spc, None) for spc in spc_files]

            # Archivo de resultados
            resultados_path = os.path.join(output_dir, f"{muestra}.txt")
            with open(resultados_path, "w") as f:
                f.write("Elemento;wt.%;Intensidad;Archivo;Equipo\n")

            # Procesar cada archivo
            for i, (spc_file, xml_file) in enumerate(paired_files, 1):
                try:
                    # Obtener información de muestra según el equipo
                    if equipo == "TECNAI" and xml_file:
                        sample_info = get_sample_info([xml_file])
                        nombre_muestra = sample_info[0][0]
                        area = sample_info[1][0]
                    else:
                        nombre_muestra = os.path.splitext(os.path.basename(spc_file))[0]
                        area = "Área no especificada"

                    # Analizar muestra
                    resultados = analyze_eds_sample(
                        spc_file,
                        (nombre_muestra, area),
                        elementos_data,
                        cuentas_minimas,
                        equipo
                    )

                    # Guardar resultados
                    with open(resultados_path, "a") as f:
                        for elem in resultados["elements"]:
                            if elem["wt"] > 0:
                                f.write(
                                    f"{elem['elemento']};{elem['wt']:.2f};"
                                    f"{elem['intensidad']:.2f};"
                                    f"{resultados['filename']};{equipo}\n"
                                )


                except Exception as e:
                    print(f"Error procesando {os.path.basename(spc_file)}: {str(e)}")
                    continue
                
            messagebox.showinfo(
                "Análisis completado",
                f"Procesados {len(paired_files)} archivos correctamente\n"
                f"Resultados guardados en: {resultados_path}"
            )

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo completar el análisis: {str(e)}")


class StatisticsTab(ttk.Frame):
    """Pestaña para análisis estadísticos."""
    
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.df = None
        self._setup_ui()
        
    def _setup_ui(self):
        """Configura la interfaz de usuario de la pestaña."""
        # Botón para abrir archivo
        self.open_button = ttk.Button(
            self, text="Abrir archivo", command=self._open_file
        )
        self.open_button.pack(pady=10)
        
        # Frame para selección de ejes
        self.axes_frame = ttk.Frame(self)
        self.axes_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Frame para eje X
        self.x_frame = ttk.LabelFrame(self.axes_frame, text="Eje X")
        self.x_frame.pack(side=tk.LEFT, padx=10, fill=tk.BOTH, expand=True)
        
        # Frame para eje Y
        self.y_frame = ttk.LabelFrame(self.axes_frame, text="Eje Y")
        self.y_frame.pack(side=tk.RIGHT, padx=10, fill=tk.BOTH, expand=True)
        
        # Botón para generar gráfico
        self.plot_button = ttk.Button(
            self, text="Generar Gráfico", command=self._generate_plot
        )
        self.plot_button.pack(side=tk.BOTTOM, pady=10)
        
    def _open_file(self):
        """Carga archivo de resultados y actualiza la interfaz."""
        initial_dir = os.path.join(self.app.current_path, "salida")
        if not os.path.exists(initial_dir):
            initial_dir = self.app.current_path
            
        file_path = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("Text files", "*.txt")]
        )
        
        if file_path:
            try:
                from script.statistics import load_eds_results
                self.df = load_eds_results(file_path)
                self._update_checkboxes()
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar el archivo: {str(e)}")
    
    def _update_checkboxes(self):
        """Actualiza los checkboxes con los elementos disponibles."""
        if self.df is None:
            return
            
        # Limpiar frames anteriores
        for widget in self.x_frame.winfo_children():
            widget.destroy()
        for widget in self.y_frame.winfo_children():
            widget.destroy()
        
        # Obtener elementos únicos
        elements = self.df['Elemento'].unique()
        self.x_var = tk.StringVar()
        self.y_vars = {}
        
        # Radio buttons para eje X
        ttk.Label(self.x_frame, text="Seleccione un elemento:").pack(anchor='w')
        for elem in elements:
            rb = ttk.Radiobutton(
                self.x_frame, 
                text=elem, 
                variable=self.x_var, 
                value=elem
            )
            rb.pack(anchor='w')
        
        # Checkbuttons para eje Y
        ttk.Label(self.y_frame, text="Seleccione elementos a comparar:").pack(anchor='w')
        for elem in elements:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(
                self.y_frame, 
                text=elem, 
                variable=var
            )
            cb.pack(anchor='w')
            self.y_vars[elem] = var
    
    def _generate_plot(self):
        """Genera el gráfico de correlación."""
        if self.df is None or self.df.empty:
            messagebox.showwarning("Advertencia", "Primero cargue un archivo de resultados")
            return
            
        x_element = self.x_var.get()
        if not x_element:
            messagebox.showwarning("Advertencia", "Seleccione un elemento para el eje X")
            return
            
        y_elements = [elem for elem, var in self.y_vars.items() if var.get()]
        if not y_elements:
            messagebox.showwarning("Advertencia", "Seleccione al menos un elemento para el eje Y")
            return
            
        try:
            from script.statistics import plot_element_correlation
            
            # Crear directorio de salida si no existe
            output_dir = os.path.join(self.app.current_path, "salida")
            os.makedirs(output_dir, exist_ok=True)
            
            # Generar y guardar gráfico
            plot_path = os.path.join(output_dir, f"correlacion_{x_element}.png")
            fig = plot_element_correlation(self.df, x_element, y_elements, plot_path)
            
            # Mostrar gráfico
            plt.show()
            
            messagebox.showinfo(
                "Gráfico generado", 
                f"Gráfico guardado en {plot_path}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el gráfico: {str(e)}")