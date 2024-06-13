from flask import Flask, render_template, Response
import cv2
import numpy as np
import torch
from models.experimental import attempt_load
from utils.general import non_max_suppression, scale_boxes
import time
import os
import json
from datetime import datetime
import mysql.connector
from minio import Minio
import io

# Initialize the Minio client
minio_client = Minio(
    endpoint="192.168.56.1:9000",
    access_key="rCIyKaEZnQwVR6MNxhpO",
    secret_key="G1DRvWSVKm2X75l9412HqiXtnJF3SEvRDLcnaYZk",
    secure=False
)


app = Flask(__name__, template_folder='../../../templates', static_folder='../../../static')

# List json
resource_data = []

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="lintasarta_cctv"
    )
    
def insert_into_db(msg, created_at, url):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("INSERT INTO resource_data (msg, created_at, url) VALUES (%s, %s, %s)", (msg, created_at, url))
    connection.commit()
    cursor.close()
    connection.close()

def save_to_minio(image_bytes, bucket_name, object_name):
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
        minio_client.put_object(bucket_name, object_name, io.BytesIO(image_bytes), len(image_bytes), content_type='image/jpeg')
        return minio_client.get_presigned_url("GET", bucket_name, object_name)
    except Exception as e:
        print(f"Error uploading to MinIO: {e}")
        return None
    
def letterbox(img, new_shape=(640, 640), color=(114, 114, 114)):
    shape = img.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    canvas = np.full((new_shape[1], new_shape[0], 3), color, dtype=np.uint8)
    margin = ((new_shape[1] - new_unpad[0]) // 2, (new_shape[0] - new_unpad[1]) // 2)
    canvas[margin[1]:margin[1] + new_unpad[1], margin[0]:margin[0] + new_unpad[0]] = img
    return canvas

def load_yolov5_model(weights_path):
    model = attempt_load(weights_path)
    model.eval()
    return model

def detect_people(frame, model):
    img_size = 640
    img = letterbox(frame, new_shape=(640, 640))
    img = img[:, :, ::-1].transpose(2, 0, 1)
    img = np.ascontiguousarray(img)
    img = torch.from_numpy(img)
    img = img.float()
    img /= 255.0
    if img.ndimension() == 3:
        img = img.unsqueeze(0)
    with torch.no_grad():
        pred = model(img)[0]
    pred = non_max_suppression(pred, 0.25, 0.45)
    bboxes = []
    for det in pred:
        if det is not None and len(det):
            det[:, :4] = scale_boxes(img.shape[2:], det[:, :4], frame.shape).round()
            for *xyxy, conf, cls in det:
                if int(cls) == 0 and conf > 0.8:
                    bboxes.append(xyxy)
    return bboxes

def draw_zone(frame, zone):
    cv2.polylines(frame, [np.array(zone, dtype=np.int32)], isClosed=True, color=(0, 255, 0), thickness=2)

def point_in_polygon(x, y, polygon):
    result = cv2.pointPolygonTest(np.array(polygon, dtype=np.int32), (x, y), False)
    return result >= 0

def draw_bounding_boxes(frame, detections):
    for bbox in detections:
        x1, y1, x2, y2 = map(int, bbox[:4])
        label = 'Person'
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

def generate_frames(zone):
    weights_path = 'yolov5_ultralytics/models/yolov5n.pt'
    model = load_yolov5_model(weights_path)

    cap = cv2.VideoCapture(0)  # 0 untuk webcam internal
    if not cap.isOpened():
        print("Error: Failed to open IPCam.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        detections = detect_people(frame, model)

        person_detected = False
        for bbox in detections:
            x1, y1, x2, y2 = map(int, bbox[:4])
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            if point_in_polygon(center_x, center_y, zone):
                person_detected = True
                break

        if person_detected:
            print("Person detected in the zone!")
            cv2.putText(frame, 'Person detected in the zone!', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
            url = save_to_minio(image_bytes, "cobacctv", f"Detected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            if url:
                resource_data.append({
                    'msg': 'Person in the Zone',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'url': url
                })
                insert_into_db('Person in the Zone', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)

        draw_zone(frame, zone)
        draw_bounding_boxes(frame, detections)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()
    
    # Determine the JSON filename based on the current date and hour
    json_filename = datetime.now().strftime('%Y-%m-%d_%H') + '_resource_data.json'
     
    # Load existing data from JSON file
    if os.path.exists(json_filename):
        with open(json_filename, 'r') as json_file:
            existing_data = json.load(json_file)
    else:
        existing_data = {"resource_data": []}

    # Append new data to existing data
    existing_data["resource_data"].extend(resource_data)

    # Write updated data back to JSON file
    with open(json_filename, 'w') as json_file:
        json.dump(existing_data, json_file)


@app.route('/insert_json_to_db')
def insert_json_to_db():
    json_filename = datetime.now().strftime('%Y-%m-%d_%H') + '_resource_data.json'
    if os.path.exists(json_filename):
        with open(json_filename, 'r') as json_file:
            data = json.load(json_file)
            for entry in data["resource_data"]:
                insert_into_db(entry['msg'], entry['created_at'], entry['url'])
        return "Data inserted into database successfully!"
    else:
        return "JSON file not found!"
    
@app.route('/dashboard-resource')
def dashboard_resource():
    # Fetch data data from the database
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM resource_data")
    fetched_data = cursor.fetchall()
    cursor.close()
    connection.close()

    # Prepare resource_data data for rendering
    resource_data = [{'id': entry[0],'msg': entry[1], 'created_at': entry[2],'url': entry[3]} for entry in fetched_data]
    # Render the template with data
    return render_template('dashboard_resource.html', resource_data=resource_data)

@app.route('/geofancing-cam')
def index():
    return render_template('geofancing_cam.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(zone), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    # Example polygon (define your polygon as per requirement)
    zone = [(100, 200), (100, 300), (100, 800), (900, 100)]
    app.run(debug=True, port=5001)
