import json
import httpx
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

# ─── Carga de variables de entorno desde el archivo .env ────────────────────
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
MQTT_HOST    = os.getenv("MQTT_HOST")
MQTT_PORT    = int(os.getenv("MQTT_PORT", 8883))
MQTT_USER    = os.getenv("MQTT_USER")
MQTT_PASS    = os.getenv("MQTT_PASS")
MQTT_TOPIC   = os.getenv("MQTT_TOPIC", "sensor/bmp280")

# ─── Headers con service_role para bypasear RLS ────────────────────────────
HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

# ─── Callbacks MQTT ─────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, reason_code, properties):
    """Se ejecuta al conectar al broker HiveMQ. rc=0 indica exito."""
    print(f"MQTT conectado, rc={reason_code}")
    client.subscribe(MQTT_TOPIC)
    print(f"Suscrito a {MQTT_TOPIC}")

def on_message(client, userdata, msg):
    """Recibe JSON del ESP32 y lo inserta en Supabase via HTTP POST.
    Usa service_role key para bypasear RLS."""
    data = json.loads(msg.payload.decode())
    response = httpx.post(
        f"{SUPABASE_URL}/rest/v1/sensor_data",
        json=data, headers=HEADERS
    )
    print(f"Insertado: {data} -> {response.status_code}")

# ─── Cliente MQTT ───────────────────────────────────────────────────────────
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.tls_set()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_HOST, MQTT_PORT)

print("Bridge MQTT iniciado - esperando datos del ESP32...")
client.loop_forever()
