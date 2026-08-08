"""
backend/analysis/provider_evaluation.py

Evaluation framework για 3rd-party forecasting providers:
- Υπολογίζει MAE, RMSE, bias, correlation ανά provider έναντι actual
- Παράγει weighted/blended forecast (βάρος αντιστρόφως ανάλογο του πρόσφατου σφάλματος)
- Επισημαίνει (flags) σημαντικές αποκλίσεις (material deviations)
"""
import os
import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient
from backend.postgres_client import write_evaluation_run

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "energy-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "wind-data")

DEVIATION_THRESHOLD_STD = 2.0  # πόσες τυπικές αποκλίσεις ορίζουν "material deviation"


def fetch_series(client, org, bucket, measurement, field, tag_key, tag_value, minutes=60):
    query_api = client.query_api()
    query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> filter(fn: (r) => r.{tag_key} == "{tag_value}")
          |> filter(fn: (r) => r._field == "{field}")
          |> keep(columns: ["_time", "_value"])
    '''
    tables = query_api.query(query, org=org)
    records = []
    for table in tables:
        for record in table.records:
            records.append({"time": record.get_time(), "value": record.get_value()})
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.set_index("time")
    return df


def evaluate_providers(client, providers, minutes=60):
    actual_df = fetch_series(client, INFLUXDB_ORG, INFLUXDB_BUCKET,
                              "wind_speed", "speed", "turbine", "t1", minutes)
    if actual_df.empty:
        print("❌ Δεν βρέθηκαν πραγματικά δεδομένα t1.")
        return None, None

    actual_df = actual_df.rename(columns={"value": "actual"})

    merged = actual_df.copy()
    metrics = {}

    for provider in providers:
        fdf = fetch_series(client, INFLUXDB_ORG, INFLUXDB_BUCKET,
                            "provider_forecast", "predicted_speed", "provider", provider, minutes)
        if fdf.empty:
            print(f"⚠️  Δεν βρέθηκαν forecasts για {provider}, παραλείπεται.")
            continue
        fdf = fdf.rename(columns={"value": provider})
        # merge με tolerance, αφού τα timestamps είναι ίδια (γράφτηκαν με το ίδιο _time)
        merged = merged.join(fdf, how="inner")

    merged = merged.dropna()
    if merged.empty:
        print("❌ Δεν υπήρξε επικάλυψη timestamps μεταξύ actual και forecasts.")
        return None, None

    for provider in providers:
        if provider not in merged.columns:
            continue
        error = merged[provider] - merged["actual"]
        mae = error.abs().mean()
        rmse = np.sqrt((error ** 2).mean())
        bias = error.mean()
        corr = merged["actual"].corr(merged[provider])
        metrics[provider] = {"MAE": mae, "RMSE": rmse, "Bias": bias, "Correlation": corr}

    return merged, metrics


def compute_blended_forecast(merged, metrics):
    """Βάρος αντιστρόφως ανάλογο του RMSE -- πιο ακριβής provider, μεγαλύτερο βάρος."""
    inv_errors = {p: 1.0 / m["RMSE"] for p, m in metrics.items() if m["RMSE"] > 0}
    total = sum(inv_errors.values())
    weights = {p: w / total for p, w in inv_errors.items()}

    blended = sum(merged[p] * w for p, w in weights.items())
    merged = merged.copy()
    merged["blended_forecast"] = blended
    return merged, weights


def flag_material_deviations(merged, threshold_std=DEVIATION_THRESHOLD_STD):
    signed_deviation = merged["blended_forecast"] - merged["actual"]
    std = signed_deviation.std()  # std πάνω στη signed κατανομή, όχι στην ήδη-απόλυτη
    merged = merged.copy()
    merged["deviation"] = signed_deviation.abs()
    merged["material_deviation"] = merged["deviation"] > (threshold_std * std)
    return merged


def print_report(metrics, weights, merged):
    print("\n=== Provider Performance ===")
    for provider, m in metrics.items():
        w = weights.get(provider, 0)
        print(f"{provider:12s} | MAE: {m['MAE']:.3f} | RMSE: {m['RMSE']:.3f} | "
              f"Bias: {m['Bias']:+.3f} | Corr: {m['Correlation']:.3f} | Weight: {w:.2%}")
        write_evaluation_run(
            provider_name=provider,
            mae=float(m["MAE"]),
            rmse=float(m["RMSE"]),
            bias=float(m["Bias"]),
            correlation=float(m["Correlation"]),
            weight=float(w),
            sample_count=len(merged),
        )
    print("✅ Τα evaluation metrics αποθηκεύτηκαν στο PostgreSQL.")

    n_flagged = merged["material_deviation"].sum()
    print(f"\n=== Blended Forecast ===")
    print(f"Δείγματα: {len(merged)} | Material deviations (>{DEVIATION_THRESHOLD_STD}σ): {n_flagged} "
          f"({n_flagged/len(merged):.1%})")

    if n_flagged > 0:
        print("\nΠαραδείγματα σημαντικών αποκλίσεων:")
        print(merged[merged["material_deviation"]][["actual", "blended_forecast", "deviation"]].head(5))


if __name__ == "__main__":
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    providers = ["provider_A", "provider_B", "provider_C"]

    merged, metrics = evaluate_providers(client, providers, minutes=60)
    if merged is not None:
        merged, weights = compute_blended_forecast(merged, metrics)
        merged = flag_material_deviations(merged)
        print_report(metrics, weights, merged)

    client.close()