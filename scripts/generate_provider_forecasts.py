"""
scripts/generate_provider_forecasts.py

Παράγει synthetic προβλέψεις από 3 "τρίτους" forecasting providers,
βασισμένες στις πραγματικές τιμές t1 που ήδη υπάρχουν στο InfluxDB.
Κάθε provider έχει διαφορετικό χαρακτήρα σφάλματος -- ακριβώς όπως θα
συμπεριφέρονταν πραγματικές ανταγωνιστικές forecasting εταιρείες.
"""
import os
import random
import pandas as pd
from influxdb_client import InfluxDBClient, Point

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "energy-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "wind-data")

# Χαρακτηριστικά κάθε provider: (bias σε m/s, τυπική απόκλιση θορύβου)
PROVIDER_PROFILES = {
    "provider_A": {"bias": 0.1, "noise_std": 0.3},   # καλός, σχεδόν αμερόληπτος
    "provider_B": {"bias": -0.8, "noise_std": 0.5},  # συστηματικά υποεκτιμά
    "provider_C": {"bias": 0.0, "noise_std": 1.2},   # αμερόληπτος αλλά ασταθής
}


def fetch_actual_t1(client, org, bucket, minutes=30):
    query_api = client.query_api()
    query = f'''
        from(bucket: "{bucket}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "wind_speed")
          |> filter(fn: (r) => r.turbine == "t1")
          |> filter(fn: (r) => r._field == "speed")
          |> keep(columns: ["_time", "_value"])
    '''
    tables = query_api.query(query, org=org)
    records = []
    for table in tables:
        for record in table.records:
            records.append({"time": record.get_time(), "speed": record.get_value()})
    return pd.DataFrame(records)


def generate_and_write_forecasts(df_actual, client, org, bucket):
    write_api = client.write_api()
    count = 0
    for _, row in df_actual.iterrows():
        actual_speed = row["speed"]
        ts = row["time"]
        for provider, profile in PROVIDER_PROFILES.items():
            predicted = actual_speed + profile["bias"] + random.gauss(0, profile["noise_std"])
            predicted = max(0, round(predicted, 2))
            point = (
                Point("provider_forecast")
                .tag("turbine", "t1")
                .tag("provider", provider)
                .field("predicted_speed", predicted)
                .time(ts)
            )
            write_api.write(bucket=bucket, org=org, record=point)
            count += 1
    write_api.close()
    print(f"✅ Γράφτηκαν {count} synthetic forecast points για {len(PROVIDER_PROFILES)} providers.")


if __name__ == "__main__":
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    df_actual = fetch_actual_t1(client, INFLUXDB_ORG, INFLUXDB_BUCKET, minutes=30)
    if df_actual.empty:
        print("❌ Δεν βρέθηκαν πραγματικά δεδομένα t1 στο InfluxDB. Άσε τον publisher να τρέξει λίγο ακόμα.")
    else:
        print(f"Βρέθηκαν {len(df_actual)} πραγματικά σημεία t1. Παράγονται forecasts...")
        generate_and_write_forecasts(df_actual, client, INFLUXDB_ORG, INFLUXDB_BUCKET)
    client.close()