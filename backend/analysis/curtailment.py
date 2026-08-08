"""
backend/analysis/curtailment.py

Μοντελοποίηση grid curtailment: προσομοιώνει περιορισμούς παραγωγής λόγω
συμφόρησης δικτύου και υπολογίζει την επίπτωση στην παραγόμενη ενέργεια.
"""
import os
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient
from backend.postgres_client import write_curtailment_report

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "energy-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "wind-data")

GRID_CAPACITY_LIMIT_KW = 650.0     # μέγιστη χωρητικότητα σύνδεσης δικτύου
CURTAILMENT_EVENT_PROB = 0.02      # πιθανότητα έναρξης νέου curtailment event ανά δείγμα
CURTAILMENT_EVENT_LIMIT_KW = 300.0 # πιο αυστηρό όριο κατά τη διάρκεια ενός event
CURTAILMENT_EVENT_MIN_DURATION = 3 # ελάχιστη διάρκεια event σε samples (π.χ. 6 x 5s = 30s)
SAMPLE_INTERVAL_HOURS = 5 / 3600   # τα δεδομένα έρχονται κάθε 5 δευτερόλεπτα
ENERGY_PRICE_EUR_PER_MWH = 80.0    # ενδεικτική τιμή αγοράς για οικονομική εκτίμηση


def fetch_power_series(client, org, bucket, minutes=60):
    query_api = client.query_api()
    query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "wind_speed")
          |> filter(fn: (r) => r.turbine == "t1")
          |> filter(fn: (r) => r._field == "power")
          |> keep(columns: ["_time", "_value"])
    '''
    tables = query_api.query(query, org=org)
    records = []
    for table in tables:
        for record in table.records:
            records.append({"time": record.get_time(), "potential_power_kw": record.get_value()})
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.set_index("time").sort_index()
    return df


def simulate_curtailment_events(n_samples):
    """Προσομοιώνει on/off περιόδους εντολών curtailment από τον διαχειριστή δικτύου."""
    in_event = False
    event_remaining = 0
    flags = []
    for _ in range(n_samples):
        if not in_event and random.random() < CURTAILMENT_EVENT_PROB:
            in_event = True
            event_remaining = CURTAILMENT_EVENT_MIN_DURATION + random.randint(0, 5)
        flags.append(in_event)
        if in_event:
            event_remaining -= 1
            if event_remaining <= 0:
                in_event = False
    return flags


def apply_curtailment(df):
    df = df.copy()
    df["curtailment_event"] = simulate_curtailment_events(len(df))

    effective_limit = np.where(
        df["curtailment_event"],
        CURTAILMENT_EVENT_LIMIT_KW,
        GRID_CAPACITY_LIMIT_KW
    )
    df["effective_limit_kw"] = effective_limit
    df["delivered_power_kw"] = np.minimum(df["potential_power_kw"], df["effective_limit_kw"])
    df["curtailed_kw"] = df["potential_power_kw"] - df["delivered_power_kw"]
    df["is_curtailed"] = df["curtailed_kw"] > 0.01
    return df


def summarize_curtailment(df):
    total_potential_kwh = (df["potential_power_kw"] * SAMPLE_INTERVAL_HOURS).sum()
    total_delivered_kwh = (df["delivered_power_kw"] * SAMPLE_INTERVAL_HOURS).sum()
    total_curtailed_kwh = total_potential_kwh - total_delivered_kwh

    pct_energy_lost = (total_curtailed_kwh / total_potential_kwh * 100) if total_potential_kwh > 0 else 0
    pct_time_curtailed = df["is_curtailed"].mean() * 100
    economic_loss_eur = (total_curtailed_kwh / 1000) * ENERGY_PRICE_EUR_PER_MWH

    return {
        "total_potential_kwh": total_potential_kwh,
        "total_delivered_kwh": total_delivered_kwh,
        "total_curtailed_kwh": total_curtailed_kwh,
        "pct_energy_lost": pct_energy_lost,
        "pct_time_curtailed": pct_time_curtailed,
        "economic_loss_eur": economic_loss_eur,
    }


def print_report(summary):
    print("\n=== Curtailment Impact Report ===")
    print(f"Δυνητική παραγωγή:      {summary['total_potential_kwh']:.2f} kWh")
    print(f"Παραδοθείσα παραγωγή:   {summary['total_delivered_kwh']:.2f} kWh")
    print(f"Χαμένη ενέργεια:        {summary['total_curtailed_kwh']:.2f} kWh "
          f"({summary['pct_energy_lost']:.1f}% της δυνητικής)")
    print(f"Χρόνος υπό περιορισμό:  {summary['pct_time_curtailed']:.1f}% του διαστήματος")
    print(f"Εκτιμώμενη οικονομική επίπτωση: €{summary['economic_loss_eur']:.2f} "
          f"(@ €{ENERGY_PRICE_EUR_PER_MWH}/MWh)")
    write_curtailment_report(summary)
    print("✅ Το curtailment report αποθηκεύτηκε στο PostgreSQL.")


def plot_curtailment(df, output_path="curtailment_plot.png"):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df.index, df["potential_power_kw"], label="Δυνητική Ισχύς", color="steelblue", alpha=0.6)
    ax.plot(df.index, df["delivered_power_kw"], label="Παραδοθείσα Ισχύς", color="darkorange")
    ax.fill_between(df.index, df["delivered_power_kw"], df["potential_power_kw"],
                     where=df["is_curtailed"], color="red", alpha=0.3, label="Curtailed")
    ax.set_xlabel("Χρόνος")
    ax.set_ylabel("Ισχύς (kW)")
    ax.set_title("Grid Curtailment: Δυνητική vs Παραδοθείσα Ισχύς")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path)
    print(f"✅ Το γράφημα αποθηκεύτηκε ως '{output_path}'")


if __name__ == "__main__":
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    df = fetch_power_series(client, INFLUXDB_ORG, INFLUXDB_BUCKET, minutes=60)

    if df.empty:
        print("❌ Δεν βρέθηκαν δεδομένα ισχύος για t1.")
    else:
        df = apply_curtailment(df)
        summary = summarize_curtailment(df)
        print_report(summary)
        plot_curtailment(df)

    client.close()