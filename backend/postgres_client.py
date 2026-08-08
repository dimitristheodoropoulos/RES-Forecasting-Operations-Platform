"""
backend/postgres_client.py

Helper module για σύνδεση/εγγραφή στο PostgreSQL summary layer.
"""
import os
import psycopg2

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_analytics")
POSTGRES_USER = os.getenv("POSTGRES_USER", "energy_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "energy_pass")


def get_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def get_provider_id(cur, provider_name):
    cur.execute("SELECT id FROM providers WHERE name = %s", (provider_name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Άγνωστος provider: {provider_name}")
    return row[0]


def get_asset_id(cur, asset_name="t1"):
    cur.execute("SELECT id FROM assets WHERE asset_name = %s", (asset_name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Άγνωστο asset: {asset_name}")
    return row[0]


def write_evaluation_run(provider_name, mae, rmse, bias, correlation, weight, sample_count):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            provider_id = get_provider_id(cur, provider_name)
            cur.execute(
                """
                INSERT INTO evaluation_runs
                    (provider_id, mae, rmse, bias, correlation, weight, sample_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (provider_id, mae, rmse, bias, correlation, weight, sample_count),
            )
        conn.commit()
    finally:
        conn.close()


def write_curtailment_report(summary, asset_name="t1"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            asset_id = get_asset_id(cur, asset_name)
            cur.execute(
                """
                INSERT INTO curtailment_events
                    (asset_id, total_potential_kwh, total_delivered_kwh, total_curtailed_kwh,
                     pct_energy_lost, pct_time_curtailed, economic_loss_eur)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    asset_id,
                    float(summary["total_potential_kwh"]),
                    float(summary["total_delivered_kwh"]),
                    float(summary["total_curtailed_kwh"]),
                    float(summary["pct_energy_lost"]),
                    float(summary["pct_time_curtailed"]),
                    float(summary["economic_loss_eur"]),
                ),
            )
        conn.commit()
    finally:
        conn.close()