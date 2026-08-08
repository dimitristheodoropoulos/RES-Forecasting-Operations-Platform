"""
backend/analysis/reality_check.py

Reality Validation Report: συγκρίνει τα στατιστικά χαρακτηριστικά του
synthetic wind simulator έναντι πραγματικών δεδομένων ERA5 reanalysis.

Σημείωση μεθοδολογίας: δεν γίνεται timestamp-προς-timestamp MCP correlation,
καθώς τα δύο datasets δεν καλύπτουν κοινή χρονική περίοδο (συνηθισμένος
περιορισμός σε πραγματικά MCP campaigns με σύντομο ιστορικό μέτρησης).
Αντ' αυτού συγκρίνονται κατανομές/στατιστικά -- έγκυρη τεχνική για πρώτη
εκτίμηση ρεαλισμού ενός μοντέλου έναντι reanalysis climatology.
"""
import os
import numpy as np
import pandas as pd
import xarray as xr
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "energy-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "wind-data")


def fetch_simulated_speeds(client, minutes=60):
    query_api = client.query_api()
    query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "wind_speed")
          |> filter(fn: (r) => r.turbine == "t1")
          |> filter(fn: (r) => r._field == "speed")
          |> keep(columns: ["_value"])
    '''
    tables = query_api.query(query, org=INFLUXDB_ORG)
    values = [record.get_value() for table in tables for record in table.records]
    return pd.Series(values, name="simulated_speed")


def fetch_era5_speeds(filepath="data/raw/era5_wind_attica_recent.nc"):
    ds = xr.open_dataset(filepath)
    u = ds["u10"]
    v = ds["v10"]
    speed = np.sqrt(u**2 + v**2)
    return pd.Series(speed.values.flatten(), name="era5_speed")


def compare_distributions(sim, era5):
    stats = pd.DataFrame({
        "simulated": [sim.mean(), sim.std(), sim.min(), sim.max(), sim.median()],
        "era5_real": [era5.mean(), era5.std(), era5.min(), era5.max(), era5.median()],
    }, index=["mean", "std", "min", "max", "median"])
    return stats


def plot_comparison(sim, era5, output_path="reality_check_plot.png"):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(sim, bins=20, alpha=0.6, label=f"Simulated (n={len(sim)})", color="steelblue", density=True)
    ax.hist(era5, bins=20, alpha=0.6, label=f"ERA5 Real (n={len(era5)})", color="darkorange", density=True)
    ax.set_xlabel("Ταχύτητα Ανέμου (m/s)")
    ax.set_ylabel("Πυκνότητα")
    ax.set_title("Reality Check: Κατανομή Simulated vs Πραγματικών (ERA5) Δεδομένων")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path)
    print(f"✅ Το γράφημα αποθηκεύτηκε ως '{output_path}'")


def print_report(stats, sim, era5):
    print("\n=== Reality Validation Report ===")
    print(stats.round(2))

    ratio = sim.mean() / era5.mean()
    print(f"\nΟ simulator παράγει κατά μέσο όρο {ratio:.1f}x υψηλότερες ταχύτητες ανέμου "
          f"από το πραγματικό ERA5 reanalysis για την περιοχή.")
    print("Αυτό υποδεικνύει ότι το synthetic μοντέλο αντιπροσωπεύει μια πιο 'αιολική' "
          "τοποθεσία απ' ό,τι είναι στην πραγματικότητα η συγκεκριμένη περιοχή της Αττικής.")


if __name__ == "__main__":
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    sim = fetch_simulated_speeds(client, minutes=60)
    era5 = fetch_era5_speeds()
    client.close()

    if sim.empty or era5.empty:
        print("❌ Λείπουν δεδομένα από μία από τις δύο πηγές.")
    else:
        stats = compare_distributions(sim, era5)
        print_report(stats, sim, era5)
        plot_comparison(sim, era5)