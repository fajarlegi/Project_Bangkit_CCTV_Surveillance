from flask import Flask, render_template, Response
import cv2
import numpy as np
from ultralytics import YOLO
import time
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


# Load YOLOv8 model
model = YOLO("weights\yolov8n.pt")

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
                color =(0, 0, 255)
                label = 'Inside Geofence'
                person_detected = True
            else:
                color = (0, 255, 0) 
                label = 'Outside Geofence'
                person_detected = False

            # Draw bounding box and label
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            if person_detected:
                print("Person detected in the zone!")
                cv2.putText(frame, 'Person detected in the zone!', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                url = save_to_minio(image_bytes, "lintasarta-surveillance-management", f"Detected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                if url:
                    resource_data.append({
                        'msg': 'Person in the Zone',
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'url': url
                    })
                    insert_into_db('Person in the Zone', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)

    # Draw geofence area
    cv2.polylines(frame, [geofence_area], isClosed=True, color=(255, 0, 0), thickness=2)
    return frame

def generate_frames(camera_type='webcam', webcam_index=0, ip_address=None, username=None, password=None):
    if camera_type == 'webcam':
        cap = cv2.VideoCapture(webcam_index)
    elif camera_type == 'ip_cam':
        # cap = cv2.VideoCapture(f'rtsp://{username}:{password}@{ip_address}')
        cap = cv2.VideoCapture(f'rtsp://{username}:{password}@{ip_address}/stream?resolution=256x144')

    else:
        raise ValueError("Invalid camera type or missing IP camera credentials")
    
    if not cap.isOpened():
        print("Error: Cannot open video source")
        return
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to capture frame")
                time.sleep(1)  # Wait for a second before trying again
                cap.release()
                cap = cv2.VideoCapture(webcam_index) if camera_type == 'webcam' else cv2.VideoCapture(f'rtsp://{username}:{password}@{ip_address}/stream?resolution=256x144')
                if not cap.isOpened():
                    print("Error: Cannot reopen video source")
                    continue
                continue

            frame = process_frame(frame)
            if frame is None:
                continue

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("Error: Failed to encode frame")
                continue

            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    except Exception as e:
        print(f"Error: {str(e)}")
    
    finally:
        cap.release()  # Ensure the capture is released


    
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
    return render_template('resource_dashboard.html', resource_data=resource_data)