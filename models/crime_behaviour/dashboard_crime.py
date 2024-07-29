from flask import Flask, render_template, Response
from ultralytics import YOLO
import cv2
import numpy as np
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

# Load the models
object_model = YOLO("models\crime_behaviour\weights\helm.pt")
# sunglasses_model = YOLO("models\crime_behaviour\weights\sunglasses.pt")
pose_model = YOLO("models\crime_behaviour\weights\yolov8n-pose.pt")

app = Flask(__name__, template_folder='../../templates', static_folder='../../static')

# Function to calculate angle between three points
def calculate_angle(a, b, c):
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(radians * 180.0 / np.pi)
    if angle > 180.0:
        angle = 360 - angle
    return angle

# Function to draw text on the frame
def put_text(frame, text, x_offset, y_offset, font_scale=0.7, thickness=2, color=(0, 255, 0)):
    cv2.putText(
        frame, text, (x_offset, y_offset), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, lineType=cv2.LINE_AA
    )

# List json
crime_data = []
last_detection_time = {}
cooldown_seconds = 10  # Cooldown period to prevent duplicate logging
detection_radius = 50  # Radius in pixels to consider as the same object

# Database connection
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
    cursor.execute("INSERT INTO crime_data (msg, created_at, url) VALUES (%s, %s, %s)", (msg, created_at, url))
    connection.commit()
    cursor.close()
    connection.close()

def is_within_radius(x1, y1, x2, y2, radius):
    return (x1 - x2) ** 2 + (y1 - y2) ** 2 <= radius ** 2

def should_log_detection(det, detection_type):
    x1, y1, x2, y2 = map(int, det[:4])
    current_time = datetime.now()
    detection_key = f"{detection_type}_{x1}_{y1}_{x2}_{y2}"

    if detection_key in last_detection_time:
        last_time = last_detection_time[detection_key]
        if (current_time - last_time).total_seconds() < cooldown_seconds:
            return False
    
    last_detection_time[detection_key] = current_time
    return True

def save_to_minio(image_bytes, bucket_name, object_name):
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
        minio_client.put_object(bucket_name, object_name, io.BytesIO(image_bytes), len(image_bytes), content_type='image/jpeg')
        return minio_client.get_presigned_url("GET", bucket_name, object_name)
    except Exception as e:
        print(f"Error uploading to MinIO: {e}")
        return None

def process_frame(frame):
    if frame is None:
        print("Error: Frame is None")
        return None

    global crime_data

    # Perform object detection
    object_results = object_model.predict(source=frame, show=False)

    # Check if any person with or without helmet is detected
    detected_helmets = [det for det in object_results[0].boxes.data if int(det[5]) == 0]  # Assuming class 0 is with helmet

    # Check if any sunglasses are detected
    # sunglasses_object = sunglasses_model.predict(source=frame, show=False)
    # detected_sunglasses = [det for det in sunglasses_object[0].boxes.data if int(det[5]) == 0]  # Assuming class 0 is for sunglasses

    # # Draw bounding boxes for detected sunglasses
    # for det in detected_sunglasses:
    #     x1, y1, x2, y2 = map(int, det[:4])
    #     if should_log_detection(det, "Sunglasses"):
    #         cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)  # Yellow box for sunglasses
    #         put_text(frame, "Sunglasses", x1, y1 - 10, color=(0, 255, 255))
    #         image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
    #         url = save_to_minio(image_bytes, "lintasarta-surveillance-management", f"sunglasses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    #         if url:
    #             crime_data.append({
    #                 'msg': 'Sunglasses Detected',
    #                 'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    #                 'url': url
    #             })
    #             insert_into_db('Sunglasses Detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)

    # Draw bounding boxes for detected objects
    for det in detected_helmets:
        x1, y1, x2, y2 = map(int, det[:4])
        if should_log_detection(det, "Helmet"):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)  
            put_text(frame, "Helmet", x1, y1 - 10, color=(255, 0, 0))
            image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
            url = save_to_minio(image_bytes, "lintasarta-surveillance-management", f"helmet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            if url:
                crime_data.append({
                    'msg': 'Helmet Detected',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'url': url
                })
                insert_into_db('Helmet Detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)

    # Perform pose estimation
    pose_results = pose_model.predict(source=frame, show=False)
    for pose in pose_results[0].keypoints.data:
        # Ensure there are enough keypoints detected
        if pose.shape[0] >= 17:
            # Extract keypoints for hips, knees, and ankles
            left_hip = pose[11][:2]
            right_hip = pose[12][:2]
            left_knee = pose[13][:2]
            right_knee = pose[14][:2]
            left_ankle = pose[15][:2]
            right_ankle = pose[16][:2]

            # Calculate angles for both legs
            left_leg_angle = calculate_angle(left_hip, left_knee, left_ankle)
            right_leg_angle = calculate_angle(right_hip, right_knee, right_ankle)

            # Check if the angles indicate a squat (usually less than 90 degrees)
            if left_leg_angle < 90 and right_leg_angle < 90:
                status = 'Squat Detected'
                image_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                url = save_to_minio(image_bytes, "lintasarta-surveillance-management", f"squat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                if url:
                    crime_data.append({
                        'msg': 'Squat Detected',
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'url': url
                    })
                    # insert_into_db('Squat Detected', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), url)
            else:
                status = 'Not Squat'

            # Draw text indicating squat detection
            put_text(frame, f'Status: {status}', 20, 100, font_scale=1, color=(0, 0, 0))    

            # Plot pose estimation results on the frame
            frame = pose_results[0].plot()

    # Determine the JSON filename based on the current date
    json_filename = datetime.now().strftime('%Y-%m-%d') + '_crime_data.json'
    
    # Load existing data from JSON file
    if os.path.exists(json_filename):
        with open(json_filename, 'r') as json_file:
            existing_data = json.load(json_file)
    else:
        existing_data = {"crime_data": []}

    # Append new data to existing data
    existing_data["crime_data"].extend(crime_data)

    # Write updated data back to JSON file
    with open(json_filename, 'w') as json_file:
        json.dump(existing_data, json_file)
    
    # Clear crime_data list for next frame
    crime_data = []
        
    return frame



def generate_frames(camera_type='webcam', webcam_index=0, ip_address=None, username=None, password=None):
    if camera_type == 'webcam':
        cap = cv2.VideoCapture(webcam_index)
    elif camera_type == 'ip_cam':
        cap = cv2.VideoCapture(f'800x448:rtsp://{username}:{password}@{ip_address}')
    else:
        raise ValueError("Invalid camera type or missing IP camera credentials")
    
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


@app.route('/crime-cam')
def dashboard():
    # Fetch crime data from the database
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM crime_data")
    fetched_data = cursor.fetchall()
    cursor.close()
    connection.close()

    # Prepare crime data for rendering
    crime_data = [{'id': entry[0],'msg': entry[1], 'created_at': entry[2],'url': entry[3]} for entry in fetched_data]
    return render_template('crime_dashboard.html', crime_data=crime_data)

# Teardown function to release camera when Flask app is shut down
@app.teardown_appcontext
def release_camera(exception):
    global cap
    if cap is not None:
        cap.release()


