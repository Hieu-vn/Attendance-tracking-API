from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
import json
import os
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("mqtt_service.log")]
)
logger = logging.getLogger("mqtt_service")

app = FastAPI(title="MQTT Bridge Service")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cấu hình MQTT
MQTT_SERVER = "14.224.247.204"
MQTT_PORT = 1883
MQTT_USERNAME = "mqtthpa"
MQTT_PASSWORD = "59@XuanDieu"
API_ENDPOINT = "http://127.0.0.1:5000/api/v1/mqtt/process"  # Điểm cuối của API Flask

# Lưu trữ client MQTT
mqtt_client = None
mqtt_connected = False
device_subscriptions = {}

# Khởi tạo thư mục lưu dữ liệu
os.makedirs("mqtt_data", exist_ok=True)

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        logger.info(f"✅ Connected to MQTT Broker with result code {rc}")
        
        # Đăng ký lại các subscription khi kết nối lại
        for device_id in device_subscriptions:
            topic = f"mqtt/face/{device_id}/Rec"
            client.subscribe(topic)
            logger.info(f"Re-subscribed to topic: {topic}")
    else:
        mqtt_connected = False
        logger.error(f"❌ Failed to connect to MQTT Broker, return code {rc}")

def on_message(client, userdata, msg):
    logger.info(f"📩 Message received on topic {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode())
        
        # Kiểm tra xem có phải sự kiện nhận diện khuôn mặt không
        operator = payload.get('operator', '')
        if operator != "RecPush":
            logger.warning("⚠️ Skipping non-RecPush message.")
            return
        
        # Lưu file JSON để backup
        timestamp = payload.get('info', {}).get('time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        safe_timestamp = timestamp.replace(" ", "_").replace(":", "-")
        json_path = os.path.join("mqtt_data", f"Rec_{safe_timestamp}.json")
        
        with open(json_path, "w", encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
            
        logger.info(f"✅ Saved Rec JSON to: {json_path}")
        
        # Gửi dữ liệu đến API xử lý
        try:
            response = requests.post(
                API_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 201:
                logger.info(f"✅ Data sent to API successfully: {response.json()}")
            else:
                logger.error(f"❌ Failed to send data to API: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.exception(f"❌ Error sending data to API: {str(e)}")

    except json.JSONDecodeError:
        logger.error("❌ Failed to parse MQTT message as JSON")
    except Exception as e:
        logger.exception(f"⚠️ Error processing message: {str(e)}")

def init_mqtt_client():
    global mqtt_client
    # Nếu client đã tồn tại, hủy kết nối trước
    if mqtt_client is not None:
        try:
            mqtt_client.disconnect()
        except:
            pass
    
    client_id = f"face_recognition_bridge_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    mqtt_client = mqtt.Client(client_id=client_id)
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    try:
        mqtt_client.connect