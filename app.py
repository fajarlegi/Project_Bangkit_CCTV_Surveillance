from flask import Flask,Response, request, jsonify, url_for,render_template
import cv2
from models.crime_behaviour.dashboard_crime import generate_frames as crime_video_feed
from models.resource_area.resource_dashboard import generate_frames as resource_video_feed
from models.public_area.public_dashboard import generate_frames as public_video_feed

from models.crime_behaviour.dashboard_crime import dashboard as crime_dashboard
from models.resource_area.resource_dashboard import dashboard_resource as resource_dashboard
from models.public_area.public_dashboard import dashboard_public as public_dashboard
import mysql.connector
import json
from datetime import datetime, timedelta


# from models.public_area.testing_public import dashboard_public as public_dashboard
app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure db for dashboard
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="lintasarta_cctv"
    )
    

@app.route('/chart-data')
def chart_data():
    connection = get_db_connection()
    
    cursor = connection.cursor()

    # Fetch data for the past 10 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=10)

    # Fetch crime_data
    cursor.execute("""
        SELECT DATE(created_at), COUNT(*) 
        FROM crime_data 
        WHERE created_at BETWEEN %s AND %s 
        GROUP BY DATE(created_at)
    """, (start_date, end_date))
    crime_data = cursor.fetchall()

    # Fetch resource_data
    cursor.execute("""
        SELECT DATE(created_at), COUNT(*) 
        FROM resource_data 
        WHERE created_at BETWEEN %s AND %s 
        GROUP BY DATE(created_at)
    """, (start_date, end_date))
    resource_data = cursor.fetchall()

    # Fetch public_data
    cursor.execute("""
        SELECT DATE(created_at), COUNT(*) 
        FROM public_data 
        WHERE created_at BETWEEN %s AND %s 
        GROUP BY DATE(created_at)
    """, (start_date, end_date))
    public_data = cursor.fetchall()
    
    cursor.close()
    connection.close()

    # Format data for the chart
    def format_chart_data(data):
        data_dict = {str(date): count for date, count in data}
        return [data_dict.get((start_date + timedelta(days=i)).strftime('%Y-%m-%d'), 0) for i in range(10)]
    
    crime_detections = format_chart_data(crime_data)
    resource_detections = format_chart_data(resource_data)
    public_detections = format_chart_data(public_data)

    labels = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(10)]

    return Response(json.dumps({
        "labels": labels,
        "crime_detections": crime_detections,
        "resource_detections": resource_detections,
        "public_detections": public_detections
    }), mimetype='application/json')

@app.route('/home')
def index():
    try:
        # Establish database connection
        connection = get_db_connection()

        # Use context manager to ensure cursor is properly managed
        with connection.cursor(dictionary=True) as cursor:
            # Fetch all data from crime_data table
            cursor.execute("SELECT * FROM crime_data")
            crime_data = cursor.fetchall()

            # Fetch all data from public_data table
            cursor.execute("SELECT * FROM public_data")
            public_data = cursor.fetchall()

            # Fetch all data from resource_data table
            cursor.execute("SELECT * FROM resource_data")
            resource_data = cursor.fetchall()

            # Process fetched data into dictionaries
            crime_data_processed = [
                {
                    'id': entry['id'],
                    'msg': entry['msg'],
                    'created_at': entry['created_at'],
                    'url': entry['url']
                } for entry in crime_data
            ]

            public_data_processed = [
                {
                    'id': entry['id'],
                    'msg': entry['msg'],
                    'created_at': entry['created_at'],
                    'url': entry['url']
                } for entry in public_data
            ]

            resource_data_processed = [
                {
                    'id': entry['id'],
                    'msg': entry['msg'],
                    'created_at': entry['created_at'],
                    'url': entry['url']
                } for entry in resource_data
            ]

            # Fetch 3 most recent activities for each table
            cursor.execute('SELECT created_at, msg, url FROM crime_data ORDER BY created_at DESC LIMIT 3')
            crime_new = cursor.fetchall()

            cursor.execute('SELECT created_at, msg, url FROM resource_data ORDER BY created_at DESC LIMIT 3')
            resource_new = cursor.fetchall()

            cursor.execute('SELECT created_at, msg, url FROM public_data ORDER BY created_at DESC LIMIT 3')
            public_new = cursor.fetchall()

        # Close connection outside of context manager
        connection.close()

        # Render template with processed data
        return render_template('home.html', 
                               crime_data=crime_data_processed,
                               public_data=public_data_processed,
                               resource_data=resource_data_processed,
                               recent_crime=crime_new,
                               recent_resource=resource_new,
                               recent_public=public_new
                               )

    except mysql.connector.Error as e:
        print(f"Error connecting to MySQL: {e}")
        return "Error connecting to MySQL"
    
@app.route('/configure_crime', methods=['GET','POST'])
def configure_crime():
    camera_type = request.form.get('camera_type')
    if camera_type == 'webcam':
        feed_url= url_for('video_feed_crime', camera_type='webcam')
    else:
        ip_address = request.form.get('ip_address')
        username = request.form.get('username')
        password = request.form.get('password')
        # Include IP camera configuration logic here, such as generating the feed URL
        feed_url = url_for('video_feed_crime', camera_type='ip_cam', ip_address=ip_address, username=username, password=password)
        
    
    return jsonify({
        'status': 'success',
        'feed_url': feed_url,
    })

   
@app.route('/video_feed/crime')
def video_feed_crime():
    camera_type = request.args.get('camera_type')
    webcam_index = request.args.get('webcam_index', default=0, type=int)
    ip_address = request.args.get('ip_address')
    username = request.args.get('username')
    password = request.args.get('password')
    crime_feed = crime_video_feed(camera_type, webcam_index, ip_address, username, password)

    return Response(crime_feed, mimetype='multipart/x-mixed-replace; boundary=frame')
# Feature Switch camera
@app.route('/configure_resource', methods=['GET','POST'])
def configure_resource():
    camera_type = request.form.get('camera_type')
    if camera_type == 'webcam':
        feed_url_resource = url_for('video_feed_resource', camera_type='webcam')
    else:
        ip_address = request.form.get('ip_address')
        username = request.form.get('username')
        password = request.form.get('password')
        # Include IP camera configuration logic here, such as generating the feed URL
        feed_url_resource = url_for('video_feed_resource', camera_type='ip_cam', ip_address=ip_address, username=username, password=password)
     
    return jsonify({
        'status': 'success',
        'feed_url_resource': feed_url_resource,
    })

@app.route('/video_feed/resource')
def video_feed_resource():
    camera_type = request.args.get('camera_type')
    webcam_index = request.args.get('webcam_index', default=0, type=int)
    ip_address = request.args.get('ip_address')
    username = request.args.get('username')
    password = request.args.get('password')
    video_feed = resource_video_feed(camera_type, webcam_index, ip_address, username, password)

    return Response(video_feed, mimetype='multipart/x-mixed-replace; boundary=frame')

# @app.route('/configure_camera', methods=['POST'])
@app.route('/video_feed_public')
def video_feed_public():
    camera_type = request.args.get('camera_type')
    webcam_index = request.args.get('webcam_index', default=0, type=int)
    ip_address = request.args.get('ip_address')
    username = request.args.get('username')
    password = request.args.get('password')
    
    # Call function to get the video feed based on camera_type
    video_feed = public_video_feed(camera_type, webcam_index, ip_address, username, password)
    
    return Response(video_feed, mimetype='multipart/x-mixed-replace; boundary=frame')


# Feature Switch camera
@app.route('/configure_camera', methods=['GET','POST'])
def configure_camera():
    camera_type = request.form.get('camera_type')
    if camera_type == 'webcam':
        feed_url_public = url_for('video_feed_public', camera_type='webcam')
    else:
        ip_address = request.form.get('ip_address')
        username = request.form.get('username')
        password = request.form.get('password')
        # Include IP camera configuration logic here, such as generating the feed URL
        feed_url_public = url_for('video_feed_public', camera_type='ip_cam', ip_address=ip_address, username=username, password=password)
        
    
    return jsonify({
        'status': 'success',
        'feed_url_public': feed_url_public,
    })

@app.route('/dashboard/crime')
def dashboard_crime():
    return crime_dashboard()

@app.route('/dashboard/resource')
def dashboard_resource():
    return resource_dashboard()

@app.route('/dashboard/public')
def dashboard_public():
    return public_dashboard()


if __name__ == '__main__':
    app.run(debug=True, port=5001)
