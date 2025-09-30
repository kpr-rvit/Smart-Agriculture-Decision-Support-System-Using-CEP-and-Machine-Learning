from kafka import KafkaProducer
import pandas as pd
import json
import time

# Kafka producer
producer = KafkaProducer(
    bootstrap_servers="localhost:29092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

# Read first 5 rows for testing
df = pd.read_csv("stream_ready.csv")

for idx, row in df.iterrows():
    payload = row.to_dict()  # Keep all features
    producer.send("sensor-stream", payload)
    print("📤 Sent:", payload)
    producer.flush(timeout=2)
    time.sleep(0.1)

producer.close()
