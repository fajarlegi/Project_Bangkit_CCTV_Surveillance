from flask import Flask, render_template, Response
# from models.crime_behaviour.testing_cam import video_feed as crime_video_feed
from models.crime_behaviour.testing_cam import generate_frames as crime_video_feed
from models.resource_area.custom_detect import generate_frames as resource_video_feed
# from models.resource_area.testing_resources import video_feed as resource_video_feed
# from models.resource_area.yolov5_ultralytics.testing_resources import generate_frames as resource_video_feed
# from models.crime_behaviour.testing_cam import insert_json_to_db as insert_crime_json_to_db
# from models.resource_area.custom_detect import insert_json_to_db as insert_resource_json_to_db
# from models.crime_behaviour.testing_cam import dashboard as crime_dashboard
# from models.resource_area.custom_detect import dashboard_resource as resource_dashboard


app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure route for HTML

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/crime_cam')
def crime_cam():
    return render_template('crime_cam.html')

@app.route('/geofencing_cam')
def geofencing_cam():
    return render_template('geofencing_cam.html')

@app.route('/public_cam')
def public_cam():
    return render_template('public_cam.html')

# Configure route for program python

@app.route('/video_feed/crime')
def video_feed_crime():
    return Response(crime_video_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed/resource')
def video_feed_resource():
    return Response(resource_video_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')


# Configure route for program Json

# @app.route('/insert_crime_json_to_db')
# def insert_crime_data():
#     return insert_crime_json_to_db()

# @app.route('/dashboard-crime')
# def dashboard_crime():
#     return crime_dashboard()

# @app.route('/insert_resource_json_to_db')
# def insert_resource_data():
#     return insert_resource_json_to_db()

# @app.route('/dashboard-resource')
# def dashboard_resource():
#     return resource_dashboard()

if __name__ == '__main__':
    app.run(debug=True)
