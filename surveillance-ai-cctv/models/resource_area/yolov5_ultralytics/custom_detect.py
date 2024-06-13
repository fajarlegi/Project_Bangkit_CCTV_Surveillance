from flask import Flask, render_template, Response
import cv2
import numpy as np
import torch
from models.experimental import attempt_load
from utils.general import non_max_suppression, scale_boxes
from minio import Minio
from minio.error import S3Error


app = Flask(__name__, template_folder='../../templates', static_folder='../../static')


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
                if int(cls) == 0 and conf > 0.5:
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

    cap = cv2.VideoCapture('rtsp://169.254.154.192')
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

        draw_zone(frame, zone)
        draw_bounding_boxes(frame, detections)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

@app.route('/geofancing_cam')
def index():
    return render_template('geofancing.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(zone), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    # Example polygon (define your polygon as per requirement)
    zone = [(100, 200), (100, 300), (200, 800), (900, 100)]
    app.run(debug=True, port=5001)
