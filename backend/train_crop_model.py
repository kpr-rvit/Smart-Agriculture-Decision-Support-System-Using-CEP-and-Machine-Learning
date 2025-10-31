import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
import joblib

# Load the dataset
print("Loading Crop_Recommendation.csv...")
df = pd.read_csv('Crop_Recommendation.csv')

print(f"Dataset shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print(f"\nFirst few rows:")
print(df.head())

# Features and target
X = df[['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']]
y = df['label']

# Encode labels
label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(y)

print(f"\nUnique crops: {label_encoder.classes_}")
print(f"Number of crops: {len(label_encoder.classes_)}")

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
)

print(f"\nTraining set size: {len(X_train)}")
print(f"Test set size: {len(X_test)}")

# Train Random Forest model
print("\nTraining Random Forest model...")
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=20,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# Evaluate
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

print(f"\nModel Performance:")
print(f"Training Accuracy: {train_score * 100:.2f}%")
print(f"Test Accuracy: {test_score * 100:.2f}%")

# Feature importance
feature_importance = pd.DataFrame({
    'feature': X.columns,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(f"\nFeature Importance:")
print(feature_importance)

# Save model and label encoder
joblib.dump(model, 'crop_model.pkl')
joblib.dump(label_encoder, 'label_encoder.pkl')

print("\n✅ Model saved as 'crop_model.pkl'")
print("✅ Label encoder saved as 'label_encoder.pkl'")

# Test prediction
print("\n🧪 Testing prediction with sample values:")
sample = [[90, 42, 43, 20.87, 82.00, 6.5, 202.93]]
prediction = model.predict(sample)
probabilities = model.predict_proba(sample)[0]

# Get top 3 predictions
top_3_indices = np.argsort(probabilities)[-3:][::-1]
print("\nTop 3 Recommendations:")
for i, idx in enumerate(top_3_indices, 1):
    crop_name = label_encoder.inverse_transform([idx])[0]
    confidence = probabilities[idx] * 100
    print(f"{i}. {crop_name}: {confidence:.2f}%")