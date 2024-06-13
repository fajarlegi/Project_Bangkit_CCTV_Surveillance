from flask import Flask, render_template, Response
import cv2
import numpy as np
import torch
from ultralytics import YOLO
import time
import os
import json
from datetime import datetime
# import mysql.connector
# from minio import Minio
# import io


# Initialize the Minio client
# minio_client = Minio(
#     endpoint="192.168.56.1:9000",
#     access_key="rCIyKaEZnQwVR6MNxhpO",
#     secret_key="G1DRvWSVKm2X75l9412HqiXtnJF3SEvRDLcnaYZk",
#     secure=False
# )

# app = Flask(__name__, template_folder='../../../templates', static_folder='../../../static')

# # List json
# resource_data = []

# def get_db_connection():
#     return mysql.connector.connect(
#         host="localhost",
#         user="root",
#         password="",
#         database="lintasarta_cctv"
#     )

# def insert_into_db(msg, created_at, url):
#     connection = get_db_connection()
#     cursor = connection.cursor()
#     cursor.execute("INSERT INTO resource_data (msg, created_at, url) VALUES (%s, %s, %s)", (msg, created_at, url))
#     connection.commit()
#     cursor.close()
#     connection.close()

# def save_to_minio(image_bytes, bucket_name, object_name):
#     try:
#         if not minio_client.bucket_exists(bucket_name):
#             minio_client.make_bucket(bucket_name)
#         minio_client.put_object(bucket_name, object_name, io.BytesIO(image_bytes), len(image_bytes), content_type='image/jpeg')
#         return minio_client.get_presigned_url("GET", bucket_name, object_name)
#     except Exception as e:
#         print(f"Error uploading to MinIO: {e}")
#         return None


# Load YOLOv8 model
model = YOLO('yolov8n.pt')  # Replace with your model if you have a custom one

# Define geofence area (polygon vertices)
geofence_area = np.array([(100, 100), (500, 100), (500, 400), (100, 400)])

def is_in_geofence(point, geofence):
    return cv2.pointPolygonTest(geofence, point, False) >= 0

def process_frame(frame):
    results = model(frame)
    detections = results[0].boxes.xyxy.cpu().numpy()  # Adjusted to match the new output format
    scores = results[0].boxes.conf.cpu().numpy()  # Confidence scores
    classes = results[0].boxes.cls.cpu().numpy()  # Class IDs

    for i, detection in enumerate(detections):
        x1, y1, x2, y2 = detection
        conf = scores[i]
        cls = int(classes[i])
        if cls == 0:  # Class 0 is 'person' in COCO dataset
            person_center = ((x1 + x2) / 2, (y1 + y2) / 2)
            if is_in_geofence(person_center, geofence_area):
                color = (0, 255, 0)  # Green if inside geofence
                label = 'Inside Geofence'
                person_detected = True
            else:
                color = (0, 0, 255)  # Red if outside geofence
                label = 'Outside Geofence'
                person_detected = False

            # Draw bounding box and label
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # if person_detected:
            #     print("Person detected in the zone!")
            #     cv2.putText(frame, 'Person detected in the zone!', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            #     image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
            #     url = save_to_minio(image_bytes, "cobacctv", f"Detected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            #     if url:
            #         resource_data.append({
            #             'msg': 'Person in the Zone',
            #             'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            #             'url': url
            #         })
            #         insert_into_db('Person in the Zone', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)

    # Draw geofence area
    cv2.polylines(frame, [geofence_area], isClosed=True, color=(255, 0, 0), thickness=2)
    return frame

def generate_frames():
    cap = cv2.VideoCapture(0)  # Use 0 for webcam, or replace with video file path

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = process_frame(frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

    # # Determine the JSON filename based on the current date and hour
    # json_filename = datetime.now().strftime('%Y-%m-%d_%H') + '_resource_data.json'
     
    # # Load existing data from JSON file
    # if os.path.exists(json_filename):
    #     with open(json_filename, 'r') as json_file:
    #         existing_data = json.load(json_file)
    # else:
    #     existing_data = {"resource_data": []}

    # # Append new data to existing data
    # existing_data["resource_data"].extend(resource_data)

    # # Write updated data back to JSON file
    # with open(json_filename, 'w') as json_file:
    #     json.dump(existing_data, json_file)

# def insert_json_to_db():
#     json_filename = datetime.now().strftime('%Y-%m-%d_%H') + '_resource_data.json'
#     if os.path.exists(json_filename):
#         with open(json_filename, 'r') as json_file:
#             data = json.load(json_file)
#             for entry in data["resource_data"]:
#                 insert_into_db(entry['msg'], entry['created_at'], entry['url'])
#         return "Data inserted into database successfully!"
#     else:
#         return "JSON file not found!"
    
# @app.route('/dashboard-resource')
# def dashboard_resource():
#     # Fetch data data from the database
#     connection = get_db_connection()
#     cursor = connection.cursor()
#     cursor.execute("SELECT * FROM resource_data")
#     fetched_data = cursor.fetchall()
#     cursor.close()
#     connection.close()

#     # Prepare resource_data data for rendering
#     resource_data = [{'id': entry[0],'msg': entry[1], 'created_at': entry[2],'url': entry[3]} for entry in fetched_data]
#     # Render the template with data
#     return render_template('geofencing_cam.html', resource_data=resource_data)