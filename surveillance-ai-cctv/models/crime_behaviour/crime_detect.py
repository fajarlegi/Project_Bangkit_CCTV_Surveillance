from flask import Flask, render_template, Response
from ultralytics import YOLO
import cv2
import numpy as np
import time
import os
import json
from datetime import datetime

# Load the models
object_model = YOLO("weights/helm.pt")
sunglasses_model = YOLO("weights/sunglasses.pt")
pose_model = YOLO("weights/yolov8n-pose.pt")

app = Flask(__name__, template_folder='../../templates', static_folder='../../static')

# Function to calculate angle between three points
def calculate_angle(a, b, c):
    a = np.array(a)  # First point
    b = np.array(b)  # Mid point
    c = np.array(c)  # End point

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

# Function to open the CCTV feed with reconnection logic
def open_cctv_feed(url, attempts=5):
    cap = cv2.VideoCapture(url)
    if not cap.isOpened() and attempts > 0:
        print(f"Error: Could not open CCTV feed. Retrying... Attempts left: {attempts}")
        time.sleep(5)  # Wait before retrying
        return open_cctv_feed(url, attempts - 1)
    if not cap.isOpened():
        print("Error: Could not open CCTV feed. No more attempts left.")
    return cap

# Open the CCTV feed
cctv_url = 'rtsp://192.168.18.53'
cap = open_cctv_feed(cctv_url)

# List json
crime_data = []


def process_frame(frame):
    if frame is None:
        print("Error: Frame is None")
        return None

    # Perform object detection
    object_results = object_model.predict(source=frame, show=False)

    # Check if any person with or without helmet is detected
    detected_helmets = [det for det in object_results[0].boxes.data if int(det[5]) == 0]  # Assuming class 0 is with helmet

    # Check if any sunglasses are detected
    sunglasses_object = sunglasses_model.predict(source=frame, show=False)
    detected_sunglasses = [det for det in sunglasses_object[0].boxes.data if int(det[5]) == 0]  # Assuming class 0 is for sunglasses

    # Draw bounding boxes for detected sunglasses
    for det in detected_sunglasses:
        x1, y1, x2, y2 = map(int, det[:4])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)  # Yellow box for sunglasses
        put_text(frame, "Sunglasses", x1, y1 - 10, color=(0, 255, 255))
        crime_data.append({
            'msg': 'Sunglasses Detected',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    # Draw bounding boxes for detected objects
    for det in detected_helmets:
        x1, y1, x2, y2 = map(int, det[:4])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)  
        put_text(frame, "Helmet", x1, y1 - 10, color=(255, 0, 0))
        crime_data.append({
            'msg': 'Helmet Detected',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

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
                crime_data.append({
                    'msg': 'Squat Detected',
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            else:
                status = 'Not Squat'

            # Draw text indicating squat detection
            put_text(frame, f'Status: {status}', 20, 100, font_scale=1, color=(0, 0, 0))    

            # Plot pose estimation results on the frame
            frame = pose_results[0].plot()
    # Load existing data from JSON file
    json_filename = 'crime_data.json'
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
        
    return frame

def generate_frames():
    global cap
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture image")
            cap.release()
            cap = open_cctv_feed(cctv_url)
            continue

        frame = process_frame(frame)
        if frame is None:
            continue

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            print("Error: Failed to encode frame")
            continue

        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


# @app.route('/crime_cam')
# def index():
#     return render_template('crime_cam.html')

# @app.route('/video_feed')
# def video_feed():
#     return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# if __name__ == '__main__':
#     app.run(debug=True, port=5001)  