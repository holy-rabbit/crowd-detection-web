from flask import Flask, request, render_template, jsonify, url_for, send_from_directory, redirect, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import cv2
import torch
import numpy as np
import threading
import subprocess
import shutil
from sort import Sort
from datetime import datetime
from base64 import b64encode

# Configure matplotlib for headless operation
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

app = Flask(__name__)

# Secret key for session management
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://crowd_user:crowd_password@localhost:5432/crowd_detection_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# User Model
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    videos = db.relationship('Video', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Video Model
class Video(db.Model):
    __tablename__ = 'videos'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    process_date = db.Column(db.DateTime)
    total_count = db.Column(db.Integer)  # Total people count detected
    video_data = db.Column(db.LargeBinary)  # Binary data of processed video
    input_data = db.Column(db.LargeBinary)  # Binary data of input video
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    error_message = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Video {self.id}: {self.filename}>'

# Create tables
with app.app_context():
    db.create_all()

UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

progress_lock = threading.Lock()
progress_status = {
    "phase": "idle",
    "percent": 0,
    "message": "Ready to upload",
    "video_url": None
}

# Load YOLOv5 model once
print("Loading YOLOv5 model...")
from ultralytics import YOLO
model = YOLO('yolov5s.pt')  # This will download yolov5s.pt if not present
print("Model loaded!")

# Initialize tracker
tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.3)


def process_video(input_path, output_path):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError('Unable to open uploaded video file')

    width = int(cap.get(3))
    height = int(cap.get(4))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    frame_index = 0

    out = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*'mp4v'),
        20,
        (width, height)
    )
    if not out.isOpened():
        cap.release()
        raise ValueError('Unable to write processed video file')

    tracked_ids = set()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_index += 1
        results = model(frame)
        detections = []

        # Extract person detections (class 0)
        if hasattr(results, 'xyxy') and len(results.xyxy) > 0:
            for *xyxy, conf, cls in results.xyxy[0]:
                if int(cls) == 0:  # person class
                    x1, y1, x2, y2 = map(int, xyxy)
                    detections.append([x1, y1, x2, y2, float(conf)])
        else:
            # Fallback for different result formats
            for result in results:
                if hasattr(result, 'boxes'):
                    boxes = result.boxes
                    for box in boxes:
                        if hasattr(box, 'cls') and hasattr(box, 'conf') and hasattr(box, 'xyxy'):
                            cls = int(box.cls.item())
                            conf = box.conf.item()
                            xyxy = box.xyxy[0].cpu().numpy()
                            if cls == 0:  # person class
                                x1, y1, x2, y2 = map(int, xyxy)
                                detections.append([x1, y1, x2, y2, conf])

        if len(detections) > 0:
            tracked_objects = tracker.update(np.array(detections))
        else:
            tracked_objects = []

        for x1, y1, x2, y2, track_id in tracked_objects:
            x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
            track_id = int(track_id)

            tracked_ids.add(track_id)

            # Head region box
            head_height = int(0.25 * (y2 - y1))
            cv2.rectangle(frame, (x1, y1), (x2, y1 + head_height), (0, 165, 255), 2)

            cv2.putText(frame, f"ID {track_id}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 2)

        # Total count
        cv2.putText(frame, f"Total: {len(tracked_ids)}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1, (0, 255, 0), 2)

        out.write(frame)

        if total_frames:
            percent = min(100, int((frame_index / total_frames) * 100))
            with progress_lock:
                progress_status["phase"] = "processing"
                progress_status["percent"] = percent
                progress_status["message"] = f"Processing frame {frame_index} of {total_frames}"

    cap.release()
    out.release()
    return len(tracked_ids)


DEFAULT_FFMPEG_PATH = r"C:\ffmpeg-2026-04-09-git-d3d0b7a5ee-essentials_build\bin\ffmpeg.exe"


def convert_to_h264(input_path, output_path):
    ffmpeg_bin = os.getenv('FFMPEG_PATH')
    if ffmpeg_bin:
        ffmpeg_bin = ffmpeg_bin.strip('"')
        if os.path.isdir(ffmpeg_bin):
            ffmpeg_bin = os.path.join(ffmpeg_bin, 'ffmpeg.exe')
    if not ffmpeg_bin:
        ffmpeg_bin = shutil.which('ffmpeg')
    if not ffmpeg_bin:
        ffmpeg_bin = DEFAULT_FFMPEG_PATH

    if not ffmpeg_bin or not os.path.isfile(ffmpeg_bin):
        raise ValueError(
            f'ffmpeg not found. Tried PATH, FFMPEG_PATH, and default path: {DEFAULT_FFMPEG_PATH}'
        )

    print(f'Using ffmpeg executable: {ffmpeg_bin}')
    cmd = [
        ffmpeg_bin,
        '-y',
        '-i', input_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        output_path
    ]

    process = subprocess.run(cmd, capture_output=True, text=True)
    if process.returncode != 0:
        raise ValueError(f"ffmpeg conversion failed: {process.stderr.strip() or process.stdout.strip()}")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise ValueError('Converted H.264 video file is missing or empty')


def reset_progress():
    with progress_lock:
        progress_status["phase"] = "idle"
        progress_status["percent"] = 0
        progress_status["message"] = "Ready to upload"
        progress_status["video_url"] = None
        progress_status["count"] = None


def set_progress(phase, percent=0, message="", video_url=None, count=None):
    with progress_lock:
        progress_status["phase"] = phase
        progress_status["percent"] = percent
        progress_status["message"] = message
        if video_url is not None:
            progress_status["video_url"] = video_url
        if count is not None:
            progress_status["count"] = count


def get_progress():
    with progress_lock:
        return dict(progress_status)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify(error="No file selected"), 400

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    file_data = file.read()
    file.seek(0)  # Reset file pointer
    file.save(input_path)
    
    reset_progress()
    set_progress("upload", 100, "Upload complete")

    # Save to database
    try:
        video = Video(
            user_id=current_user.id,
            filename=filename,
            original_filename=filename,
            input_data=file_data,
            status='pending'
        )
        db.session.add(video)
        db.session.commit()
        return jsonify(filename=filename, video_id=video.id)
    except Exception as e:
        db.session.rollback()
        print(f"Database error during upload: {e}")
        return jsonify(error="Failed to save to database", details=str(e)), 500


@app.route("/process", methods=["POST"])
@login_required
def process():
    data = request.get_json() or {}
    filename = data.get("filename")
    video_id = data.get("video_id")
    
    if not filename:
        return jsonify(error="Filename missing"), 400

    # Verify video belongs to current user
    if video_id:
        video = Video.query.get(video_id)
        if not video or video.user_id != current_user.id:
            return jsonify(error="Video not found or unauthorized"), 404

    input_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(input_path):
        return jsonify(error="Uploaded file not found"), 404

    output_name = os.path.splitext(filename)[0] + ".mp4"
    output_path = os.path.join(OUTPUT_FOLDER, output_name)
    reset_progress()
    set_progress("processing", 0, "Starting video processing")
    tmp_output_path = os.path.join(OUTPUT_FOLDER, f"tmp_{output_name}")
    
    try:
        # Update status in database
        if video_id:
            video = Video.query.get(video_id)
            if video:
                video.status = 'processing'
                db.session.commit()
        
        total_count = process_video(input_path, tmp_output_path)
        if not os.path.isfile(tmp_output_path) or os.path.getsize(tmp_output_path) == 0:
            raise ValueError("Processed video file was not produced or is empty")

        set_progress("processing", 95, "Converting processed video to H.264 MP4")
        convert_to_h264(tmp_output_path, output_path)

        if os.path.exists(tmp_output_path):
            os.remove(tmp_output_path)

        # Read processed video data and save to database
        with open(output_path, 'rb') as f:
            video_data = f.read()
        
        if video_id:
            video = Video.query.get(video_id)
            if video:
                video.video_data = video_data
                video.total_count = total_count
                video.status = 'completed'
                video.process_date = datetime.utcnow()
                db.session.commit()
        
        video_url = url_for('processed_video', filename=output_name)
        set_progress("done", 100, "Processing complete", video_url=video_url, count=total_count)
        print(f"Processed video saved to: {output_path} size={os.path.getsize(output_path)}")
        return jsonify(video_url=video_url, count=total_count, video_id=video_id)
    except Exception as e:
        if os.path.exists(tmp_output_path):
            try:
                os.remove(tmp_output_path)
            except OSError:
                pass
        
        # Update status as failed
        if video_id:
            video = Video.query.get(video_id)
            if video:
                video.status = 'failed'
                video.error_message = str(e)
                db.session.commit()
        
        set_progress("error", 0, f"Processing failed: {e}")
        print(f"Processing error: {e}")
        return jsonify(error="Processing failed", details=str(e)), 500


@app.route("/progress", methods=["GET"])
def progress():
    return jsonify(get_progress())


@app.route('/processed/<filename>')
def processed_video(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route("/videos", methods=["GET"])
@login_required
def get_videos():
    """Get all videos from database for current user"""
    try:
        videos = Video.query.filter_by(user_id=current_user.id).all()
        videos_data = []
        for video in videos:
            videos_data.append({
                'id': video.id,
                'filename': video.filename,
                'original_filename': video.original_filename,
                'upload_date': video.upload_date.isoformat() if video.upload_date else None,
                'process_date': video.process_date.isoformat() if video.process_date else None,
                'total_count': video.total_count,
                'status': video.status,
                'has_processed_video': video.video_data is not None
            })
        return jsonify(videos_data)
    except Exception as e:
        print(f"Error retrieving videos: {e}")
        return jsonify(error="Failed to retrieve videos", details=str(e)), 500


@app.route("/video/<int:video_id>", methods=["GET"])
@login_required
def get_video(video_id):
    """Get specific video details"""
    try:
        video = Video.query.get(video_id)
        if not video or video.user_id != current_user.id:
            return jsonify(error="Video not found"), 404
        
        return jsonify({
            'id': video.id,
            'filename': video.filename,
            'original_filename': video.original_filename,
            'upload_date': video.upload_date.isoformat() if video.upload_date else None,
            'process_date': video.process_date.isoformat() if video.process_date else None,
            'total_count': video.total_count,
            'status': video.status,
            'error_message': video.error_message
        })
    except Exception as e:
        print(f"Error retrieving video: {e}")
        return jsonify(error="Failed to retrieve video", details=str(e)), 500


@app.route("/video/<int:video_id>/download", methods=["GET"])
@login_required
def download_video(video_id):
    """Download processed video from database"""
    try:
        video = Video.query.get(video_id)
        if not video or video.user_id != current_user.id:
            return jsonify(error="Video not found"), 404
        
        if not video.video_data:
            return jsonify(error="Processed video not available"), 404
        
        from flask import Response
        return Response(
            video.video_data,
            mimetype='video/mp4',
            headers={"Content-Disposition": f"attachment;filename={video.filename}"}
        )
    except Exception as e:
        print(f"Error downloading video: {e}")
        return jsonify(error="Failed to download video", details=str(e)), 500


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not username or not email or not password:
            return render_template('register.html', error='All fields are required')
        
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')
        
        if len(password) < 6:
            return render_template('register.html', error='Password must be at least 6 characters')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already exists')
        
        # Create user
        try:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            return render_template('register.html', error=f'Registration failed: {str(e)}')
    
    return render_template('register.html')


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            return render_template('login.html', error='Username and password required')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/", methods=["GET"])
@login_required
def index():
    return render_template("index.html", video=None, error=None)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)