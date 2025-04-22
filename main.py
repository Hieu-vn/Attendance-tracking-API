import paho.mqtt.client as mqtt
import json
import os
from datetime import datetime

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker with result code {rc}")
        device_id = "1736631"
        client.subscribe(f"mqtt/face/{device_id}/Rec")
        print(f"📥 Subscribed to topic: Rec")
    else:
        print(f"❌ Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    print(f"\n📩 Message received on topic {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode())
        operator = payload.get('operator', '')
        info = payload.get('info', {})
        timestamp = info.get('time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if operator != "RecPush":
            print("⚠️ Skipping non-RecPush message.")
            return

        # Tạo thư mục lưu dữ liệu nếu chưa có
        os.makedirs("data", exist_ok=True)

        # Đặt tên file theo thời gian để không bị ghi đè
        safe_timestamp = timestamp.replace(" ", "_").replace(":", "-")
        json_path = os.path.join("data", f"Rec_{safe_timestamp}.json")

        # Lưu file JSON
        with open(json_path, "w", encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)

        print(f"✅ Saved Rec JSON to: {json_path}")

    except Exception as e:
        print(f"⚠️ Failed to parse message: {e}")

# MQTT Config
MQTT_SERVER = "14.224.247.204"
MQTT_PORT = 1883
MQTT_USERNAME = "mqtthpa"
MQTT_PASSWORD = "59@XuanDieu"

client = mqtt.Client(client_id="client_1736631_rec_only")
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_message = on_message

# Kết nối và chạy
try:
    client.connect(MQTT_SERVER, MQTT_PORT, keepalive=60)
    print("🚀 Connecting to MQTT Broker...")

    client.loop_start()

    while True:
        key = input("👉 Press 'q' + Enter to quit: ")
        if key.lower() == 'q':
            print("👋 Quitting...")
            client.disconnect()
            break

except Exception as e:
    print(f"❌ Could not connect to MQTT Broker: {e}")
 