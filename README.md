# EDS-TEM Analysis Tool

A Python GUI for semi-quantitative EDS analysis in TEM. It manages batch processing and signal filtering, while relying on HyperSpy and eXSpy for the core computational work.

## Features

- **Cliff-Lorimer quantification** with user-defined K-factors
- **Three integration strategies**:
  - `default` – symmetric 2×FWHM windows (fast, for isolated peaks)
  - `custom_windows` – asymmetric FWHM-parameterized windows with background subtraction
  - `deconvolution` – model-based Gaussian fitting with iterative refinement
- **Iterative element refinement** with dual threshold (weight % and SNR)
- **Parallel processing** (ThreadPoolExecutor)
- **Interactive Tkinter GUI** with scrollable analysis tab and statistics tab
- **Automatic PDF report** per spectrum with annotated X-ray peaks
- **Live progress tracking** with per-task log capture
- **Robust statistics tab**: scatter plots correctly aligned by spectrum, handling undetected elements as 0
- **Batch processing** of `.spc` files with optional `.xml` metadata

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Git (optional, for cloning)

### Clone the repository

```bash
git clone https://github.com/luc45m3n/eds-analysis-tool.git
cd eds-analysis-tool
```
### Create a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate      # On Linux/Mac
venv\Scripts\activate         # On Windows
```
### Install dependencies
```bash
pip install -r requirements.txt
```
#### Required libraries

| Library | Version | Purpose |
|---|---|---|
| hyperspy | ≥ 2.0 | Spectral processing |
| exspy | ≥ 0.1 | EDS extension for HyperSpy |
| numpy | ≥ 1.20 | Numerical operations |
| pandas | ≥ 1.3 | Data handling |
| matplotlib | ≥ 3.4 | Plotting and PDF generation |
| Pillow | ≥ 9.0 | Image handling (logo) |
| scipy | ≥ 1.7 | Peak finding and statistics |
| adjustText | ≥ 0.8 | Label overlap prevention |

## Usage

### Launching the GUI

```bash
python EDS_TEM_GUI.py
```
### Workflow
1- **Select Working Directory** – Choose the folder containing your `.spc` and `.xml` files.  
2- **Enter sample name** – Used for output file naming.  
3- **Define elements** – Comma-separated list (e.g., `Al`, `Ca`, `Fe`, `Mg`, `Na`, `Si`).  
4- **Choose units** – `wt.%` or `at.%`.  
5- **Set refinement threshold** – Minimum weight % to retain an element (default: 1.0%).  
6- **Adjust SNR sensitivity** – SNR threshold (default: 3.0; higher = more stringent).  
7. **Select Integration Method** – Choose `default`, `custom_windows`, or `deconvolution`.
   For `custom_windows`, specify *Window Left*, *Window Right* and *Background* (in multiples of FWHM).
8. **Click "Analyze EDS"** – Processing begins in parallel.  

### Output Files  
|File | Description|  
|---|---|
|`{sample}_datos_completos.txt` |	All individual spectrum results (for scatter plots)|  
|`{sample}_promedio.txt`	| Average composition per element (for bar charts)|  
|`{sample}_*.pdf`	|PDF report per spectrum with annotated peaks and composition table|  
|`CuentasInsuficientes.txt`	| Log of spectra rejected due to insufficient counts|  

### Statistics Tab
- Bar chart – Average composition with standard deviation.
- Scatter plot – Elemental correlations (element vs element).

### Project Structure
```text
eds_analysis/
├── EDS_TEM_GUI.py                 # Main entry point
├── requirements.txt               # Python dependencies
├── resources/
│   ├── kfactor.txt                # User-defined K-factors
│   └── logo.png                   # Application logo
└── eds_tem_analysis/              # Core package
    ├── core/
    │   ├── quantification.py      # Quantification engine + SNR filter
    │   └── processing.py          # Spectrum processing pipeline
    │   └── perform_deconvolution.py   # Model-based deconvolution module
    ├── gui/
    │   ├── main_window.py         # Main window
    │   ├── analysis_tab.py        # Analysis tab
    │   └── stats_tab.py           # Statistics tab
    ├── load/
    │   └── loader.py              # .spc and .xml file loading
    ├── report/
    │   └── pdf_generator.py       # PDF report generation
    └── utils/
        └── helpers.py             # Helper functions (K-factors, SNR)
```
#### K-Factor File Format  
The K-factor file (`kfactor.txt`) must be a semicolon-separated file with the following format:
```
elemento;kfactor
Al;1.22
Ca;1.52
Fe;0.87
Mg;1.02
Na;1.00
Si;1.00
```

# Publication  
Please acknowledge the following libraries:  
- HyperSpy: [De la Peña et al., 2019 (DOI: 10.1017/S1431927619006287)](https://doi.org/10.5281/zenodo.592838)  
- eXSpy: EDS extension for HyperSpy  https://zenodo.org/doi/10.5281/zenodo.10252344 
- Cliff-Lorimer: Cliff & Lorimer, 1975, J. Microsc. 103: 203–207  

### Additionally, if you use this tool in your research, please cite:
Menger, L. (2026). EDS-TEM Analysis Tool: A Python-based GUI for Semi-quantitative EDS Analysis. https://github.com/luc45m3n/eds-analysis-tool

