"""
backend/analysis/power_forecasting.py

Time-series forecasting της ισχύος t1: πρόβλεψη T+1 βήμα μπροστά (~5 δευτ.)
χρησιμοποιώντας lag features + rolling statistics, με XGBoost.

Συγκρίνεται έναντι naive persistence baseline (predicted = τελευταία τιμή),
η τυπική πρακτική σύγκριση σε forecasting benchmarking.
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from influxdb_client import InfluxDBClient

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "energy-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "wind-data")

N_LAGS = 6           # τελευταία 6 δείγματα (~30 δευτ.) ως features
ROLLING_WINDOW = 6   # παράθυρο για rolling mean/std


def fetch_power_series(client, minutes=120):
    query_api = client.query_api()
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "wind_speed")
          |> filter(fn: (r) => r.turbine == "t1")
          |> filter(fn: (r) => r._field == "power")
          |> keep(columns: ["_time", "_value"])
    '''
    tables = query_api.query(query, org=INFLUXDB_ORG)
    records = []
    for table in tables:
        for record in table.records:
            records.append({"time": record.get_time(), "power": record.get_value()})
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.set_index("time").sort_index()
    return df


def build_features(df):
    """Δημιουργεί lag features, rolling στατιστικά, και ωριαία χαρακτηριστικά."""
    df = df.copy()

    for lag in range(1, N_LAGS + 1):
        df[f"lag_{lag}"] = df["power"].shift(lag)

    df["rolling_mean"] = df["power"].shift(1).rolling(ROLLING_WINDOW).mean()
    df["rolling_std"] = df["power"].shift(1).rolling(ROLLING_WINDOW).std()

    df["hour"] = df.index.hour
    df["minute"] = df.index.minute

    df["target"] = df["power"]  # η τιμή που θέλουμε να προβλέψουμε (τρέχουσα, δεδομένου του παρελθόντος)

    df = df.dropna()
    return df


def train_test_split_timeseries(df, test_fraction=0.2):
    """Χρονολογικό split -- ΠΟΤΕ τυχαίο shuffle σε time series, θα διέρρεε πληροφορία από το μέλλον."""
    split_idx = int(len(df) * (1 - test_fraction))
    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:]
    return train, test


def train_xgboost_model(train, feature_cols):
    model = XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
    )
    model.fit(train[feature_cols], train["target"])
    return model


def evaluate_forecast(test, feature_cols, model):
    predictions = model.predict(test[feature_cols])
    naive_baseline = test["lag_1"]  # naive persistence: πρόβλεψη = προηγούμενη τιμή

    mae_model = mean_absolute_error(test["target"], predictions)
    rmse_model = np.sqrt(mean_squared_error(test["target"], predictions))

    mae_naive = mean_absolute_error(test["target"], naive_baseline)
    rmse_naive = np.sqrt(mean_squared_error(test["target"], naive_baseline))

    improvement_pct = (mae_naive - mae_model) / mae_naive * 100 if mae_naive > 0 else 0

    return {
        "mae_model": mae_model,
        "rmse_model": rmse_model,
        "mae_naive": mae_naive,
        "rmse_naive": rmse_naive,
        "improvement_pct": improvement_pct,
        "predictions": predictions,
    }


def print_report(results, n_test):
    print("\n=== Power Forecasting Report (XGBoost vs Naive Persistence) ===")
    print(f"Test samples: {n_test}")
    print(f"\n{'Model':15s} | {'MAE (kW)':>10s} | {'RMSE (kW)':>10s}")
    print(f"{'XGBoost':15s} | {results['mae_model']:>10.2f} | {results['rmse_model']:>10.2f}")
    print(f"{'Naive (T-1)':15s} | {results['mae_naive']:>10.2f} | {results['rmse_naive']:>10.2f}")
    print(f"\nΒελτίωση έναντι naive baseline: {results['improvement_pct']:+.1f}%")
    if results["improvement_pct"] > 0:
        print("Το XGBoost model ξεπερνά το naive persistence baseline.")
    else:
        print("Το naive baseline παραμένει ισχυρό -- συνηθισμένο σε πολύ βραχυπρόθεσμο (5s) forecasting "
              "όπου η αδράνεια του ανέμου κάνει δύσκολο να ξεπεραστεί η απλή επιμονή.")


def plot_forecast(test, results, output_path="power_forecast_plot.png"):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(test.index, test["target"], label="Πραγματική Ισχύς", color="steelblue")
    ax.plot(test.index, results["predictions"], label="XGBoost Πρόβλεψη", color="darkorange", alpha=0.8)
    ax.plot(test.index, test["lag_1"], label="Naive (T-1)", color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Χρόνος")
    ax.set_ylabel("Ισχύς (kW)")
    ax.set_title("Power Forecasting: XGBoost vs Naive Baseline")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path)
    print(f"✅ Το γράφημα αποθηκεύτηκε ως '{output_path}'")


if __name__ == "__main__":
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    raw_df = fetch_power_series(client, minutes=120)
    client.close()

    if raw_df.empty or len(raw_df) < 50:
        print(f"❌ Ανεπαρκή δεδομένα ({len(raw_df)} samples). Χρειάζονται τουλάχιστον ~50 δείγματα.")
    else:
        df = build_features(raw_df)
        feature_cols = [c for c in df.columns if c not in ("power", "target")]

        train, test = train_test_split_timeseries(df, test_fraction=0.2)
        model = train_xgboost_model(train, feature_cols)
        results = evaluate_forecast(test, feature_cols, model)

        print_report(results, len(test))
        plot_forecast(test, results)