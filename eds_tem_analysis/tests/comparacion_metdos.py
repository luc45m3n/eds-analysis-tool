import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Cargar cada archivo de cuantificación por separado
# (Asegúrate de ajustar los nombres de ruta de tus 3 archivos)
df_default = pd.read_csv('F:/TEM/Muestra5C/default/default_data.txt', sep=';')
df_custom = pd.read_csv('F:/TEM/Muestra5C/custom/custom_data.txt', sep=';')
df_deconv = pd.read_csv('F:/TEM/Muestra5C/deconv/deconv_data.txt', sep=';')

# Limpiar espacios en los nombres de las columnas por seguridad
for df in [df_default, df_custom, df_deconv]:
    df.columns = [c.strip() for c in df.columns]

# 2. Renombrar las columnas de valor para diferenciarlas al fusionar
# Suponiendo que las columnas se llaman 'wt.%' e 'Intensity'
df_default = df_default.rename(columns={'wt.%': 'wt_default', 'Intensity': 'int_default'})
df_custom = df_custom.rename(columns={'wt.%': 'wt_custom', 'Intensity': 'int_custom'})
df_deconv = df_deconv.rename(columns={'wt.%': 'wt_deconv', 'Intensity': 'int_deconv'})

# Eliminamos la columna 'Method' antigua si venía dentro de cada archivo
for df in [df_default, df_custom, df_deconv]:
    if 'Method' in df.columns:
        df.drop(columns=['Method'], inplace=True)

# 3. Fusionar los DataFrames utilizando 'File' y 'Element' como claves comunes
# Usamos un outer join (o inner join según prefieras) para alinear las mediciones
df_merged = pd.merge(df_default, df_custom, on=['File', 'Element'], how='inner')
df_merged = pd.merge(df_merged, df_deconv, on=['File', 'Element'], how='inner')

print("--- Vista previa de la tabla consolidada (comparativa) ---")
print(df_merged.head(10), "\n")

# 4. Calcular las diferencias absolutas entre los métodos (%wt)
df_merged['diff_custom_vs_default'] = df_merged['wt_custom'] - df_merged['wt_default']
df_merged['diff_custom_vs_deconv'] = df_merged['wt_custom'] - df_merged['wt_deconv']
df_merged['diff_deconv_vs_default'] = df_merged['wt_deconv'] - df_merged['wt_default']

# 5. Generar la Matriz de Correlación y Gráficos Comparativos
plt.figure(figsize=(10, 6))

# Seleccionamos solo las columnas de porcentajes en peso para correlacionar
cols_wt = ['wt_default', 'wt_custom', 'wt_deconv']
matriz_corr = df_merged[cols_wt].corr()

# Mapa de calor de correlación
sns.heatmap(matriz_corr, annot=True, cmap='coolwarm', vmin=0.8, vmax=1.0, fmt='.4f', 
            xticklabels=['Default', 'Custom', 'Deconv'], 
            yticklabels=['Default', 'Custom', 'Deconv'])
plt.title('Matriz de Correlación entre Métodos (%wt)')
plt.tight_layout()
plt.show()

# Gráficos de dispersión cruzados (Pairplot) para ver desvíos visuales
g = sns.pairplot(df_merged[cols_wt], kind='reg', diag_kind='kde')
g.figure.suptitle("Comparativa de Tendencias Lineales entre los 3 Métodos", y=0.98)
g.figure.subplots_adjust(top=0.88)
plt.show()

# 6. Resumen estadístico de las diferencias (Sesgos y dispersión)
print("--- Resumen Estadístico de las Diferencias entre Métodos (%wt) ---")
cols_diff = [c for c in df_merged.columns if 'diff_' in c]
print(df_merged[cols_diff].describe())