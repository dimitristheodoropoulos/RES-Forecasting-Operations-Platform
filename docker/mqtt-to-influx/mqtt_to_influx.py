import os
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WriteOptions


# =====================================
# InfluxDB configuration
# =====================================

INFLUXDB_URL = os.getenv(
    "INFLUXDB_URL",
    "http://influxdb:8086"
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


# =====================================
# MQTT configuration
# =====================================

MQTT_BROKER = os.getenv(
    "MQTT_BROKER",
    "mosquitto"
)

MQTT_PORT = int(
    os.getenv("MQTT_PORT", 1883)
)

MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC",
    "wind/measurements"
)


# =====================================
# Logging
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)


write_api = None


# =====================================
# MQTT callbacks
# =====================================

def on_connect(client, userdata, flags, rc):

    if rc == 0:

        logging.info(
            f"Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT}"
        )

        client.subscribe(MQTT_TOPIC)

        logging.info(
            f"Subscribed to topic {MQTT_TOPIC}"
        )

    else:

        logging.error(
            f"MQTT connection failed. Code: {rc}"
        )


def parse_timestamp(value):

    if value is None:

        return datetime.now(timezone.utc)


    if isinstance(value, (int, float)):

        return datetime.fromtimestamp(
            value,
            tz=timezone.utc
        )


    try:

        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    except Exception:

        logging.warning(
            "Invalid timestamp format. Using current UTC time."
        )

        return datetime.now(timezone.utc)



def on_message(client, userdata, msg):

    try:

        payload = json.loads(
            msg.payload.decode("utf-8")
        )


        logging.info(
            f"Received MQTT message: {payload}"
        )


        point_time = parse_timestamp(
            payload.get("timestamp")
        )


        point = (

            Point("wind_speed")

            .tag(
                "turbine",
                payload.get(
                    "turbine",
                    "unknown"
                )
            )

            .field(
                "speed",
                float(payload["speed"])
            )

            .field(
                "direction",
                int(payload["direction"])
            )

            .field(
                "power",
                float(payload["power"])
            )

            .time(point_time)

        )


        write_api.write(
            bucket=INFLUXDB_BUCKET,
            org=INFLUXDB_ORG,
            record=point
        )


        logging.info(
            "Data written successfully to InfluxDB"
        )


    except json.JSONDecodeError:

        logging.error(
            "Invalid JSON payload"
        )


    except KeyError as e:

        logging.error(
            f"Missing field: {e}"
        )


    except Exception as e:

        logging.exception(
            f"Processing error: {e}"
        )



def on_disconnect(client, userdata, rc):

    logging.warning(
        f"MQTT disconnected. Code: {rc}"
    )


# =====================================
# Main
# =====================================

def main():

    global write_api


    influx_client = InfluxDBClient(

        url=INFLUXDB_URL,

        token=INFLUXDB_TOKEN,

        org=INFLUXDB_ORG

    )


    write_api = influx_client.write_api(

        write_options=WriteOptions(

            batch_size=1

        )

    )


    mqtt_client = mqtt.Client(

        client_id="mqtt-to-influx",

        protocol=mqtt.MQTTv311

    )


    mqtt_client.on_connect = on_connect

    mqtt_client.on_message = on_message

    mqtt_client.on_disconnect = on_disconnect


    try:

        logging.info(
            "Connecting to MQTT broker..."
        )


        mqtt_client.connect(

            MQTT_BROKER,

            MQTT_PORT,

            60

        )


        mqtt_client.loop_forever()


    except KeyboardInterrupt:

        logging.info(
            "Stopping service..."
        )


    except Exception as e:

        logging.exception(
            f"Fatal error: {e}"
        )


    finally:

        influx_client.close()



if __name__ == "__main__":

    main()