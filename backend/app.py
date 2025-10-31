from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from kafka import KafkaConsumer
import json
import threading
import time
from collections import deque
from datetime import datetime
import pandas as pd
import joblib

import joblib
import numpy as np

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global storage
sensor_data_buffer = deque(maxlen=100)  # Last 100 readings
forecast_buffer = deque(maxlen=50)
alerts_buffer = deque(maxlen=100)
alert_frequency = {}

# Load crop recommendation model
try:
    crop_model = joblib.load('crop_model.pkl')
    label_encoder = joblib.load('label_encoder.pkl')
    print("✅ Crop recommendation model loaded successfully")
except FileNotFoundError:
    print("⚠️ Crop model not found. Run train_crop_model.py first!")
    crop_model = None
    label_encoder = None

# Kafka consumers running in background threads
def consume_sensor_stream():
    """Consume raw sensor data"""
    consumer = KafkaConsumer(
        'sensor-stream',
        bootstrap_servers='localhost:29092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='latest'
    )
    
    for message in consumer:
        data = message.value
        data['timestamp'] = datetime.now().isoformat()
        sensor_data_buffer.append(data)
        
        # Emit to connected clients
        socketio.emit('sensor_update', data)
        
        # Check for alerts based on thresholds
        check_and_emit_alerts(data)

def consume_forecast_stream():
    """Consume ML forecasts"""
    consumer = KafkaConsumer(
        'ml-forecast',
        bootstrap_servers='localhost:29092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='latest'
    )
    
    for message in consumer:
        data = message.value
        data['timestamp'] = datetime.now().isoformat()
        forecast_buffer.append(data)
        
        socketio.emit('forecast_update', data)

def check_and_emit_alerts(data):
    """Generate alerts based on thresholds"""
    alerts = []
    temp = data.get('temperature_2m (°C)', 0)
    humidity = data.get('relative_humidity_2m (%)', 0)
    
    # Temperature alerts
    if temp > 35:
        alert = {
            'timestamp': datetime.now().isoformat(),
            'parameter': 'Temperature',
            'value': f"{temp}°C",
            'condition': '> 35°C',
            'alert_type': 'High Temperature',
            'severity': 'Critical',
            'action': 'Activate irrigation, provide shade nets'
        }
        alerts.append(alert)
        alert_frequency['High Temperature'] = alert_frequency.get('High Temperature', 0) + 1
        
    elif temp < 10:
        alert = {
            'timestamp': datetime.now().isoformat(),
            'parameter': 'Temperature',
            'value': f"{temp}°C",
            'condition': '< 10°C',
            'alert_type': 'Low Temperature',
            'severity': 'Warning',
            'action': 'Use frost protection, delay planting'
        }
        alerts.append(alert)
        alert_frequency['Low Temperature'] = alert_frequency.get('Low Temperature', 0) + 1
    
    # Humidity alerts
    if humidity < 30:
        alert = {
            'timestamp': datetime.now().isoformat(),
            'parameter': 'Humidity',
            'value': f"{humidity}%",
            'condition': '< 30%',
            'alert_type': 'Low Humidity',
            'severity': 'Warning',
            'action': 'Increase irrigation frequency'
        }
        alerts.append(alert)
        alert_frequency['Low Humidity'] = alert_frequency.get('Low Humidity', 0) + 1
        
    elif humidity > 80:
        alert = {
            'timestamp': datetime.now().isoformat(),
            'parameter': 'Humidity',
            'value': f"{humidity}%",
            'condition': '> 80%',
            'alert_type': 'High Humidity',
            'severity': 'Warning',
            'action': 'Monitor for fungal diseases, improve ventilation'
        }
        alerts.append(alert)
        alert_frequency['High Humidity'] = alert_frequency.get('High Humidity', 0) + 1
    
    # Store and emit alerts
    for alert in alerts:
        alerts_buffer.append(alert)
        socketio.emit('new_alert', alert)

# REST API Endpoints
@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """Get recent sensor readings"""
    return jsonify(list(sensor_data_buffer))

@app.route('/api/forecasts', methods=['GET'])
def get_forecasts():
    """Get ML forecasts"""
    return jsonify(list(forecast_buffer))

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    return jsonify(list(alerts_buffer))

@app.route('/api/alert-frequency', methods=['GET'])
def get_alert_frequency():
    """Get alert frequency statistics"""
    return jsonify(alert_frequency)

@app.route('/api/recommend-crop', methods=['POST'])
def recommend_crop():
    """Crop recommendation based on trained ML model"""
    data = request.json
    
    if crop_model is None or label_encoder is None:
        return jsonify({'error': 'Model not loaded. Please train the model first.'}), 500
    
    try:
        # Extract features in order: N, P, K, temperature, humidity, ph, rainfall
        N = float(data.get('nitrogen', 0))
        P = float(data.get('phosphorus', 0))
        K = float(data.get('potassium', 0))
        temperature = float(data.get('temperature', 0))
        humidity = float(data.get('humidity', 0))
        ph = float(data.get('ph', 0))
        rainfall = float(data.get('rainfall', 0))
        
        # Prepare input for model
        input_features = np.array([[N, P, K, temperature, humidity, ph, rainfall]])
        
        # Get prediction probabilities
        probabilities = crop_model.predict_proba(input_features)[0]
        
        # Get top 3 predictions
        top_3_indices = np.argsort(probabilities)[-3:][::-1]
        
        # Prepare recommendations
        recommendations = []
        for idx in top_3_indices:
            crop_name = label_encoder.inverse_transform([idx])[0]
            confidence = float(probabilities[idx] * 100)
            
            # Get suitable conditions description
            suitable_conditions = get_crop_description(crop_name, confidence)
            
            recommendations.append({
                'crop': crop_name.capitalize(),
                'confidence': round(confidence, 2),
                'suitable_conditions': suitable_conditions
            })
        
        return jsonify({
            'recommendations': recommendations,
            'input_conditions': {
                'N': N, 'P': P, 'K': K,
                'temperature': temperature,
                'humidity': humidity,
                'ph': ph,
                'rainfall': rainfall
            }
        })
        
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid input parameters: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Prediction error: {str(e)}'}), 500

def get_crop_description(crop_name, confidence):
    """Get description for crop based on confidence"""
    crop_info = {
        'rice': 'High humidity, warm temperature, abundant rainfall',
        'maize': 'Moderate climate, well-drained soil, medium rainfall',
        'chickpea': 'Cool season, low humidity, moderate rainfall',
        'kidneybeans': 'Cool climate, moderate moisture, well-drained soil',
        'pigeonpeas': 'Warm climate, drought tolerant, light soil',
        'mothbeans': 'Hot climate, low rainfall, sandy soil',
        'mungbean': 'Warm climate, moderate rainfall, loamy soil',
        'blackgram': 'Warm climate, moderate rainfall, clay loam',
        'lentil': 'Cool season, moderate moisture, loamy soil',
        'pomegranate': 'Hot dry climate, low rainfall, well-drained',
        'banana': 'Tropical climate, high humidity, rich soil',
        'mango': 'Tropical climate, well-drained, moderate rainfall',
        'grapes': 'Mediterranean climate, low humidity, dry season',
        'watermelon': 'Warm climate, sandy soil, moderate water',
        'muskmelon': 'Warm climate, sandy loam, moderate water',
        'apple': 'Cool temperate, well-drained, moderate rainfall',
        'orange': 'Subtropical, well-drained, acidic soil',
        'papaya': 'Tropical, well-drained, year-round warmth',
        'coconut': 'Coastal tropical, sandy soil, high rainfall',
        'cotton': 'Warm climate, moderate rainfall, deep soil',
        'jute': 'Hot humid climate, alluvial soil, high rainfall',
        'coffee': 'Cool tropical, high altitude, well-drained'
    }
    
    desc = crop_info.get(crop_name.lower(), 'Suitable for given parameters')
    
    if confidence > 80:
        return f"Excellent match! {desc}"
    elif confidence > 60:
        return f"Good match. {desc}"
    else:
        return f"Possible option. {desc}"

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get dashboard statistics"""
    active_alerts = len([a for a in alerts_buffer if 
                        (datetime.now() - datetime.fromisoformat(a['timestamp'])).seconds < 300])
    
    last_event = sensor_data_buffer[-1]['timestamp'] if sensor_data_buffer else None
    
    return jsonify({
        'active_alerts': active_alerts,
        'total_alerts': len(alerts_buffer),
        'last_event': last_event,
        'cep_status': 'Active',
        'total_readings': len(sensor_data_buffer)
    })

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # Send initial data
    emit('initial_data', {
        'sensors': list(sensor_data_buffer)[-20:],
        'alerts': list(alerts_buffer)[-20:],
        'forecasts': list(forecast_buffer)[-20:]
    })

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # Start Kafka consumers in background
    threading.Thread(target=consume_sensor_stream, daemon=True).start()
    threading.Thread(target=consume_forecast_stream, daemon=True).start()
    
    # Run Flask app
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
