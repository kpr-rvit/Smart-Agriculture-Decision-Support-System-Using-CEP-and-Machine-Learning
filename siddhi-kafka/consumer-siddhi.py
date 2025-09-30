from kafka import KafkaConsumer
import json, joblib
import numpy as np
import requests
from collections import deque

# Load ML model
model = joblib.load("xgb_multi_model.pkl")

FEATURES = [
    "temperature_2m (°C)",
    "relative_humidity_2m (%)",
    "wind_speed_10m (km/h)",
    "soil_temperature_0_to_7cm (°C)"
]

look_back, horizon = 72, 6
buffer = deque(maxlen=look_back)

# Kafka consumer (reads full feature rows)
consumer = KafkaConsumer(
    "sensor-stream",
    bootstrap_servers="localhost:29092",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="ml-consumer-group"
)

# Siddhi HTTP endpoint
SIDDHI_URL = "http://localhost:8006/SensorStream"

print("✅ Consumer started. Waiting for messages...")

for record in consumer:
    msg = record.value
    row = [msg.get(f, 0) for f in FEATURES]
    buffer.append(row)

    if len(buffer) == look_back:
        # ML prediction
        X_input = np.array(buffer).flatten().reshape(1, -1)
        y_pred = model.predict(X_input).reshape(horizon, len(FEATURES))

        # First-hour temperature
        temp_first_hour = float(y_pred[0, FEATURES.index("temperature_2m (°C)")])
        print(f"🔮 Forecast - First hour temperature: {temp_first_hour}°C")

        # Send to Siddhi via HTTP
        try:
            r = requests.post(
                "http://localhost:8006/SensorStream",
                json={"sensorId": "ml-forecast", "temperature": temp_first_hour}
            )
            print(f"📨 Sent to Siddhi (status {r.status_code})")
        except Exception as e:
            print("❌ Error sending to Siddhi:", e)