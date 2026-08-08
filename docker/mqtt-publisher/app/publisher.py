import time
import random
import paho.mqtt.client as mqtt
import os
import logging
import json # Προσθήκη για JSON payload
import math # Προσθήκη για ημιτονοειδές κύμα
from datetime import datetime # Προσθήκη για ISO timestamp (αν και θα χρησιμοποιήσουμε epoch int)

# Ρύθμιση logging με timestamp
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO
)

broker = os.getenv("MQTT_BROKER", "mosquitto")
port = int(os.getenv("MQTT_PORT", 1883))
# !!! ΣΗΜΑΝΤΙΚΟ: Το topic θα είναι wind/measurements όπως συμφωνήσαμε
topic = os.getenv("MQTT_TOPIC", "wind/measurements")

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info(f"Συνδεθήκαμε επιτυχώς στον broker {broker}:{port}")
    else:
        logging.error(f"Αποτυχία σύνδεσης με broker, κωδικός {rc}")

def on_disconnect(client, userdata, rc):
    logging.warning("Αποσυνδέθηκε από broker")

client = mqtt.Client(protocol=mqtt.MQTTv311)
client.on_connect = on_connect
client.on_disconnect = on_disconnect

try:
    client.connect(broker, port, 60)
except Exception as e:
    logging.error(f"Σφάλμα σύνδεσης: {e}")
    exit(1)

client.loop_start()

# Αναγνωριστικά τουρμπίνας/σταθμού αναφοράς
turbine_id = "t1"
reference_id = "T2_ref"

# Παράμετροι για ένα απλό trend/cycle (24-ωρος κύκλος)
start_time = time.time()
cycle_duration = 3600 * 24 # Ένας κύκλος 24 ωρών σε δευτερόλεπτα

def build_payload(station_id, base_speed, direction):
    wind_speed = max(0, round(base_speed, 2))
    power_output = round(0.5 * 1.2 * (wind_speed**3), 2) # kW
    return {
        "turbine": station_id,
        "speed": wind_speed,
        "direction": direction,
        "power": power_output,
        "timestamp": int(time.time()) # Timestamp σε epoch δευτερόλεπτα
    }

try:
    while True:
        current_time = time.time()
        elapsed_time = current_time - start_time

        # Προσθήκη εποχιακής διακύμανσης (π.χ. ημέρας/νύχτας) στην ταχύτητα ανέμου
        daily_cycle_factor = math.sin((elapsed_time / cycle_duration) * 2 * math.pi)

        # --- Κύρια τοποθεσία (t1) ---
        # Η ταχύτητα θα κυμαίνεται περίπου 5 m/s έως 11 m/s
        base_wind_speed_t1 = 8 + daily_cycle_factor * 3 + random.uniform(-2.0, 2.0)
        wind_direction_t1 = random.randint(0, 359)
        data_t1 = build_payload(turbine_id, base_wind_speed_t1, wind_direction_t1)

        # --- Σταθμός αναφοράς (T2_ref) ---
        # Ίδιος γενικός καιρικός κύκλος, μικρή συστηματική απόκλιση + ανεξάρτητος θόρυβος,
        # όπως θα συνέβαινε με έναν πραγματικό κοντινό μετεωρολογικό σταθμό αναφοράς
        base_wind_speed_ref = base_wind_speed_t1 * 0.95 + random.uniform(-0.5, 0.5) + 0.3
        wind_direction_ref = (wind_direction_t1 + random.randint(-15, 15)) % 360
        data_ref = build_payload(reference_id, base_wind_speed_ref, wind_direction_ref)

        # Δημοσίευση και των δύο payloads
        for data in (data_t1, data_ref):
            result = client.publish(topic, json.dumps(data))
            status = result[0]
            if status == 0:
                logging.info(f"Απεστάλη: {data} στο θέμα {topic}")
            else:
                logging.error(f"Αποτυχία αποστολής στο θέμα {topic}")

        time.sleep(5) # Στέλνει δεδομένα κάθε 5 δευτερόλεπτα
except KeyboardInterrupt:
    logging.info("Τερματισμός publisher από χρήστη")
finally:
    client.loop_stop()
    client.disconnect()