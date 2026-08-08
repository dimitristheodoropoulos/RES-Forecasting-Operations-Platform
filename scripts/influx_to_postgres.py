import os
import logging

import psycopg2

from influxdb_client import InfluxDBClient


# ==========================
# Logging
# ==========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)


# ==========================
# InfluxDB config
# ==========================

INFLUXDB_URL = os.getenv(
    "INFLUXDB_URL",
    "http://localhost:8086"
)

INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN",
    "admintoken"
)

INFLUXDB_ORG = os.getenv(
    "INFLUXDB_ORG",
    "energy-org"
)

INFLUXDB_BUCKET = os.getenv(
    "INFLUXDB_BUCKET",
    "wind-data"
)


# ==========================
# PostgreSQL config
# ==========================

POSTGRES_HOST = os.getenv(
    "POSTGRES_HOST",
    "localhost"
)

POSTGRES_PORT = os.getenv(
    "POSTGRES_PORT",
    "5432"
)

POSTGRES_DB = os.getenv(
    "POSTGRES_DB",
    "energy_analytics"
)

POSTGRES_USER = os.getenv(
    "POSTGRES_USER",
    "energy_user"
)

POSTGRES_PASSWORD = os.getenv(
    "POSTGRES_PASSWORD",
    "energy_pass"
)


# ==========================
# Query InfluxDB
# ==========================

def read_from_influx():

    client = InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG
    )


    query_api = client.query_api()


    query = f'''

from(bucket: "{INFLUXDB_BUCKET}")

|> range(start: -30d)

|> filter(fn: (r) =>
    r["_measurement"] == "wind_speed"
)

|> pivot(
    rowKey:["_time"],
    columnKey:["_field"],
    valueColumn:"_value"
)

'''


    tables = query_api.query(
        query=query
    )


    rows=[]


    for table in tables:

        for record in table.records:

            rows.append(
                {
                    "timestamp":
                        record["_time"],

                    "turbine":
                        record["turbine"],

                    "wind_speed":
                        record["speed"],

                    "direction":
                        record["direction"],

                    "power":
                        record["power"]
                }
            )


    client.close()

    logging.info(
        f"Read {len(rows)} records from InfluxDB"
    )


    return rows



# ==========================
# Insert PostgreSQL
# ==========================

def write_to_postgres(rows):

    if not rows:
        return


    conn = psycopg2.connect(

        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD

    )


    cursor = conn.cursor()


    insert_sql = """

INSERT INTO wind_measurements
(
 turbine,
 timestamp,
 wind_speed,
 direction,
 power
)

VALUES
(
 %s,%s,%s,%s,%s
)

ON CONFLICT
(
 turbine,
 timestamp
)

DO NOTHING;

"""


    inserted=0


    for row in rows:

        cursor.execute(
            insert_sql,
            (
                row["turbine"],
                row["timestamp"],
                row["wind_speed"],
                row["direction"],
                row["power"]
            )
        )

        inserted += cursor.rowcount



    conn.commit()

    cursor.close()
    conn.close()


    logging.info(
        f"Inserted {inserted} new records into PostgreSQL"
    )



# ==========================
# Main
# ==========================

def main():

    logging.info(
        "Starting InfluxDB -> PostgreSQL ingestion"
    )


    data = read_from_influx()


    write_to_postgres(
        data
    )


    logging.info(
        "Pipeline completed"
    )



if __name__ == "__main__":

    main()