"""
backend/analysis/portfolio_report.py

Portfolio-level report: συνθέτει provider performance, curtailment impact,
και asset status σε ενιαία εικόνα -- συνδέοντας forecast deviations με
πραγματικό οικονομικό/ενεργειακό αντίκτυπο, όπως ζητά ρόλος τύπου
"Energy Analysis & Forecasting Supervisor".

Διαβάζει αποκλειστικά από το PostgreSQL summary layer (όχι InfluxDB raw data).
"""
import os
import psycopg2
import psycopg2.extras

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_analytics")
POSTGRES_USER = os.getenv("POSTGRES_USER", "energy_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "energy_pass")


def get_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT, dbname=POSTGRES_DB,
        user=POSTGRES_USER, password=POSTGRES_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def fetch_latest_provider_performance(conn):
    """Το πιο πρόσφατο evaluation run ανά provider."""
    query = """
        SELECT DISTINCT ON (p.name)
            p.name AS provider_name, e.mae, e.rmse, e.bias, e.correlation,
            e.weight, e.sample_count, e.run_time
        FROM evaluation_runs e
        JOIN providers p ON e.provider_id = p.id
        ORDER BY p.name, e.run_time DESC
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def fetch_latest_curtailment(conn, asset_name="t1"):
    """Το πιο πρόσφατο curtailment report για το asset."""
    query = """
        SELECT c.*, a.asset_name, a.capacity_kw
        FROM curtailment_events c
        JOIN assets a ON c.asset_id = a.id
        WHERE a.asset_name = %s
        ORDER BY c.run_time DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (asset_name,))
        return cur.fetchone()


def fetch_asset_summary(conn):
    query = "SELECT asset_name, asset_type, capacity_kw, location FROM assets"
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def compute_portfolio_metrics(providers, curtailment):
    """Συνθέτει ενιαία portfolio-level metrics."""
    if not providers:
        return None

    best_provider = min(providers, key=lambda p: p["rmse"])
    worst_provider = max(providers, key=lambda p: p["rmse"])

    total_weight = sum(float(p["weight"]) for p in providers)
    weighted_avg_mae = sum(float(p["mae"]) * float(p["weight"]) for p in providers) / total_weight if total_weight else 0

    result = {
        "best_provider": best_provider["provider_name"],
        "best_provider_rmse": float(best_provider["rmse"]),
        "worst_provider": worst_provider["provider_name"],
        "worst_provider_rmse": float(worst_provider["rmse"]),
        "portfolio_weighted_mae": weighted_avg_mae,
    }

    if curtailment:
        result["curtailment_pct_energy_lost"] = float(curtailment["pct_energy_lost"])
        result["curtailment_economic_loss_eur"] = float(curtailment["economic_loss_eur"])
        # Σημείωση μονάδων: το weighted_avg_mae είναι σε m/s (σφάλμα πρόβλεψης
        # ταχύτητας ανέμου, όπως το υπολογίζει το provider_evaluation.py), όχι
        # σε kW -- δεν συγκρίνεται απευθείας με τη χωρητικότητα ισχύος του asset.
        # Το κρατάμε ρητά ως m/s στο report αντί να το διαιρέσουμε λανθασμένα
        # με kW capacity.
        result["portfolio_weighted_mae_unit"] = "m/s (wind speed forecast error)"

    return result


def print_portfolio_report(assets, providers, curtailment, metrics):
    print("\n" + "=" * 60)
    print("PORTFOLIO-LEVEL FORECASTING & OPERATIONS REPORT")
    print("=" * 60)

    print("\n--- Assets in Portfolio ---")
    for a in assets:
        print(f"  {a['asset_name']:10s} | {a['asset_type']:15s} | "
              f"{a['capacity_kw']:>8} kW | {a['location']}")

    print("\n--- 3rd-Party Forecast Provider Performance (latest evaluation) ---")
    for p in sorted(providers, key=lambda x: x["rmse"]):
        print(f"  {p['provider_name']:12s} | MAE={float(p['mae']):.2f} | "
              f"RMSE={float(p['rmse']):.2f} | Bias={float(p['bias']):+.2f} | "
              f"Weight={float(p['weight']):.1%}")

    if curtailment:
        print("\n--- Curtailment / Asset Availability Impact ---")
        print(f"  Δυνητική παραγωγή:      {float(curtailment['total_potential_kwh']):.1f} kWh")
        print(f"  Χαμένη ενέργεια:        {float(curtailment['total_curtailed_kwh']):.1f} kWh "
              f"({float(curtailment['pct_energy_lost']):.1f}%)")
        print(f"  Οικονομική επίπτωση:    €{float(curtailment['economic_loss_eur']):.2f}")

    if metrics:
        print("\n--- Portfolio-Level Synthesis ---")
        print(f"  Καλύτερος provider:     {metrics['best_provider']} "
              f"(RMSE={metrics['best_provider_rmse']:.2f})")
        print(f"  Χειρότερος provider:    {metrics['worst_provider']} "
              f"(RMSE={metrics['worst_provider_rmse']:.2f})")
        print(f"  Weighted portfolio MAE: {metrics['portfolio_weighted_mae']:.2f} "
              f"{metrics.get('portfolio_weighted_mae_unit', '')}")
        if "curtailment_pct_energy_lost" in metrics:
            print(f"\n  💡 Insight: Η αβεβαιότητα forecasting ({metrics['portfolio_weighted_mae']:.2f} m/s "
                  f"weighted MAE) και το\n     curtailment ({metrics['curtailment_pct_energy_lost']:.1f}% "
                  f"ενεργειακή απώλεια) είναι δύο ξεχωριστές\n     πηγές λειτουργικού ρίσκου -- η πρώτη "
                  f"επηρεάζει imbalance cost στην αγορά,\n     η δεύτερη άμεσα τη φυσική παραγωγή. "
                  f"Και τα δύο απαιτούν συνεχές monitoring.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    conn = get_connection()
    try:
        assets = fetch_asset_summary(conn)
        providers = fetch_latest_provider_performance(conn)
        curtailment = fetch_latest_curtailment(conn, asset_name="t1")
        metrics = compute_portfolio_metrics(providers, curtailment)

        if not providers:
            print("❌ Δεν βρέθηκαν evaluation runs. Τρέξε πρώτα το provider_evaluation.py.")
        else:
            print_portfolio_report(assets, providers, curtailment, metrics)
    finally:
        conn.close()