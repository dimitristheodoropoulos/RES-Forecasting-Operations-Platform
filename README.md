# Energy-Assessment-MCP-Analysis

**Python-based energy analytics platform for wind resource assessment, 3rd-party forecast provider evaluation, and grid curtailment modeling — built around a real-time MQTT/InfluxDB pipeline with a PostgreSQL analytics layer, and validated against real ERA5 reanalysis data.**

Το project υλοποιεί ένα end-to-end pipeline για αξιολόγηση αιολικού δυναμικού και forecasting operations, συνδυάζοντας real-time data ingestion, στατιστική ανάλυση, machine learning, evaluation frameworks και validation έναντι πραγματικών δεδομένων.

## Domain Context

Το project καλύπτει τέσσερις βασικές λειτουργικές περιοχές που συναντώνται σε RES Aggregation / Energy Forecasting operations:

1. **Measure-Correlate-Predict (MCP)** — κλασική μεθοδολογία εκτίμησης αιολικού δυναμικού, συσχετίζοντας μια περιοχή ενδιαφέροντος (target) με μια περιοχή αναφοράς (reference) με μακροχρόνιο ιστορικό.
2. **3rd-Party Forecast Provider Evaluation** — framework αξιολόγησης πολλαπλών forecasting providers (MAE/RMSE/Bias/Correlation), με weighted forecast blending και αυτόματο εντοπισμό σημαντικών αποκλίσεων (material deviations).
3. **Grid Curtailment Modeling** — προσομοίωση περιορισμών παραγωγής λόγω συμφόρησης δικτύου, με ποσοτικοποίηση ενεργειακής και οικονομικής επίπτωσης.
4. **Real Data Validation** — σύγκριση του synthetic simulator έναντι πραγματικών δεδομένων ERA5 reanalysis, για ποσοτική επιβεβαίωση ρεαλισμού.

---

## Architecture Overview

Wind Data Simulator (t1 + T2_ref)
|
| MQTT
v
Mosquitto MQTT Broker
|
v
MQTT → InfluxDB Bridge
|
v
InfluxDB (raw time-series: wind_speed, provider_forecast)
|
+--> MCP Analysis (correlation + linear regression) --> mcp_scatter_plot.png
|
+--> Provider Evaluation (MAE/RMSE/Bias/weighting) ----+
| |
+--> Curtailment Modeling (grid limits + economics) ---+--> PostgreSQL
| | (summary/relational layer)
+--> influx_to_postgres.py (raw archival) -------------+
|
v
ERA5 Reanalysis (Copernicus CDS)
|
v
Reality Validation Report (simulated vs real distribution comparison)

### Γιατί δύο βάσεις δεδομένων

* **InfluxDB** — high-frequency raw time-series (MQTT stream κάθε 5 δευτερόλεπτα). Βέλτιστο για write-heavy, χρονικά δεδομένα.
* **PostgreSQL** — structured, relational summary layer: provider metadata, evaluation history, curtailment reports, raw archival με foreign keys. Βέλτιστο για reporting/ιστορική ανάλυση και σχέσεις μεταξύ οντοτήτων (providers, assets).

---

## Project Structure

Energy-Assessment-MCP-Analysis/

├── backend/
│ ├── influx/
│ │ └── influx_client.py # InfluxDB client (MCP queries)
│ ├── analysis/
│ │ ├── mcp.py # MCP correlation + regression
│ │ ├── provider_evaluation.py # Provider MAE/RMSE/Bias + weighted blending
│ │ ├── curtailment.py # Grid curtailment simulation + impact
│ │ └── reality_check.py # Simulated vs ERA5 real-data validation
│ ├── postgres_client.py # PostgreSQL write helpers (FK-aware)
│ └── run_mcp.py
│
├── mcp_analysis/
│ ├── correlation.py # Pearson/Spearman correlation
│ └── prediction.py # Linear regression model
│
├── data/
│ ├── raw/ # ERA5 NetCDF downloads
│ ├── processed/
│ └── reference/
│
├── data_simulator/
│ └── simulate_wind_data.py
│
├── docker/
│ ├── docker-compose.yml # 6 services, all restart: unless-stopped
│ ├── postgres/
│ │ └── init.sql # Relational schema (providers, assets, evaluations...)
│ ├── grafana/ influxdb/ mosquitto/
│ ├── mqtt-publisher/app/publisher.py # t1 + T2_ref synthetic streams
│ └── mqtt-to-influx/mqtt_to_influx.py
│
├── scripts/
│ ├── setup_env.sh
│ ├── generate_provider_forecasts.py # Synthetic 3rd-party forecast simulator
│ ├── download_era5_wind.py # Copernicus CDS API downloader
│ ├── inspect_era5_data.py # NetCDF exploration
│ └── influx_to_postgres.py # Raw data archival bridge
│
├── requirements.txt
├── README.md
├── mcp_scatter_plot.png
├── curtailment_plot.png
└── reality_check_plot.png

---

## Requirements

### Software prerequisites

* Docker & Docker Compose
* Python 3.12+
* (Προαιρετικό, για ERA5) Δωρεάν λογαριασμός στο [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)

```bash
python --version
docker --version
docker compose version
```

---

## Installation

### 1. Clone repository

```bash
git clone https://github.com/dimitristheodoropoulos/Energy-Assessment-MCP-Analysis.git
cd Energy-Assessment-MCP-Analysis
```

### 2. Python environment

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start infrastructure

```bash
cd docker
docker compose up -d
```

Ξεκινούν 6 services: **InfluxDB** (`:8086`), **PostgreSQL** (`:5432`), **Grafana** (`:3000`), **Mosquitto** (`:1883`/`:9001`), **mqtt_publisher**, **mqtt_to_influx**. Όλα με `restart: unless-stopped` — δεν χρειάζεται χειροκίνητο restart μετά από reboot.

### 4. (Προαιρετικό) ERA5 setup

Για το reality validation module, χρειάζεται CDS API key στο `~/.cdsapirc`:
url: https://cds.climate.copernicus.eu/api
key: <your-key>

---

## Usage

### MCP Analysis (t1 vs T2_ref)

```bash
python -m backend.run_mcp
```
→ `mcp_scatter_plot.png` — correlation, R², regression coefficients.

### Provider Evaluation

```bash
python scripts/generate_provider_forecasts.py   # παράγει synthetic forecasts 3 providers
python -m backend.analysis.provider_evaluation
```
→ MAE/RMSE/Bias/Correlation ανά provider, inverse-error weighting, blended forecast, material deviation flagging (>2σ). Αποθηκεύεται στο PostgreSQL (`evaluation_runs`).

### Curtailment Modeling

```bash
python -m backend.analysis.curtailment
```
→ `curtailment_plot.png` — δυνητική vs παραδοθείσα ισχύς, % ενεργειακής/οικονομικής επίπτωσης. Αποθηκεύεται στο PostgreSQL (`curtailment_events`).

### ERA5 Reality Validation

```bash
python scripts/download_era5_wind.py
python -m backend.analysis.reality_check
```
→ `reality_check_plot.png` — σύγκριση κατανομών simulated vs πραγματικού ERA5 reanalysis για την περιοχή της Αττικής.

### Raw Data Archival

```bash
python scripts/influx_to_postgres.py
```
→ Μεταφέρει raw time-series από InfluxDB στο PostgreSQL (`wind_measurements`) για μακροχρόνια σχεσιακή ανάλυση.

---

## Database Schema (PostgreSQL)

| Πίνακας | Ρόλος |
|---|---|
| `providers` | Metadata 3rd-party forecasting providers |
| `assets` | Registry ανεμογεννητριών/RES assets |
| `wind_measurements` | Raw time-series archival από InfluxDB |
| `weather_observations` | Reserved για μελλοντικά ML features |
| `forecast_predictions` / `forecast_evaluations` | Πρόβλεψη vs πραγματικότητα ανά asset |
| `evaluation_runs` | Ιστορικό MAE/RMSE/Bias/weight ανά provider |
| `curtailment_events` | Ιστορικό curtailment impact reports |

---

## Technologies

| Category | Technology |
|---|---|
| Language | Python 3.12 |
| Data Processing | Pandas / NumPy / Xarray |
| Machine Learning | Scikit-learn |
| Time-Series DB | InfluxDB 2.7 |
| Relational DB | PostgreSQL 16 |
| Messaging | MQTT / Mosquitto |
| Real Data Source | ERA5 Reanalysis (Copernicus CDS) |
| Containers | Docker / Docker Compose |
| Visualization | Matplotlib / Grafana |

---

## Known Limitations & Honest Notes

* Το live MQTT stream (t1/T2_ref) και το ERA5 dataset δεν καλύπτουν κοινή χρονική περίοδο (συνηθισμένος περιορισμός σε πραγματικά MCP campaigns με σύντομο ιστορικό μέτρησης) — γι' αυτό το reality check συγκρίνει στατιστικά χαρακτηριστικά αντί για timestamp-προς-timestamp correlation.
* Οι 3 forecast providers είναι synthetic, σχεδιασμένοι με ελεγχόμενο bias/noise ώστε να επιδεικνύουν το evaluation framework — σε production θα αντικαθίσταντο με πραγματικά provider feeds.
* Το curtailment μοντέλο χρησιμοποιεί απλοποιημένη rule-based λογική (σταθερό grid limit + τυχαία events) αντί για πραγματικά ΑΔΜΗΕ δεδομένα.

---

## Future Improvements

* Αντικατάσταση synthetic forecast providers με πραγματικά 3rd-party feeds.
* Πλήρες ιστορικό ERA5 (πολυετές) για robust seasonal validation.
* Advanced forecasting models (Prophet, XGBoost, LSTM) πέρα από linear regression.
* Πραγματικά δεδομένα curtailment από ΑΔΜΗΕ/ΕΛΕΤΑΕΝ όπου διαθέσιμα.
* Automated scheduled runs (cron/Airflow) για evaluation & curtailment reports.

---

## License

MIT License