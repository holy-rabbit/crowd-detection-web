from flask import Flask, request, render_template, jsonify, url_for, send_from_directory
from werkzeug.utils import secure_filename
import os
import cv2
import torch
import numpy as np
import threading
import subprocess
import shutil
from sort import Sort

app = Flask(__name__)

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
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
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

        for *xyxy, conf, cls in results.xyxy[0]:
            if int(cls) == 0:  # person class
                x1, y1, x2, y2 = map(int, xyxy)
                detections.append([x1, y1, x2, y2, float(conf)])

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
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify(error="No file selected"), 400

    filename = secure_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(input_path)
    reset_progress()
    set_progress("upload", 100, "Upload complete")

    return jsonify(filename=filename)


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json() or {}
    filename = data.get("filename")
    if not filename:
        return jsonify(error="Filename missing"), 400

    input_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(input_path):
        return jsonify(error="Uploaded file not found"), 404

    output_name = os.path.splitext(filename)[0] + ".mp4"
    output_path = os.path.join(OUTPUT_FOLDER, output_name)
    reset_progress()
    set_progress("processing", 0, "Starting video processing")
    tmp_output_path = os.path.join(OUTPUT_FOLDER, f"tmp_{output_name}")
    try:
        total_count = process_video(input_path, tmp_output_path)
        if not os.path.isfile(tmp_output_path) or os.path.getsize(tmp_output_path) == 0:
            raise ValueError("Processed video file was not produced or is empty")

        set_progress("processing", 95, "Converting processed video to H.264 MP4")
        convert_to_h264(tmp_output_path, output_path)

        if os.path.exists(tmp_output_path):
            os.remove(tmp_output_path)

        video_url = url_for('processed_video', filename=output_name)
        set_progress("done", 100, "Processing complete", video_url=video_url, count=total_count)
        print(f"Processed video saved to: {output_path} size={os.path.getsize(output_path)}")
        return jsonify(video_url=video_url, count=total_count)
    except Exception as e:
        if os.path.exists(tmp_output_path):
            try:
                os.remove(tmp_output_path)
            except OSError:
                pass
        set_progress("error", 0, f"Processing failed: {e}")
        print(f"Processing error: {e}")
        return jsonify(error="Processing failed", details=str(e)), 500
    except Exception as e:
        set_progress("error", 0, f"Processing failed: {e}")
        print(f"Processing error: {e}")
        return jsonify(error="Processing failed", details=str(e)), 500


@app.route("/progress", methods=["GET"])
def progress():
    return jsonify(get_progress())


@app.route('/processed/<filename>')
def processed_video(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", video=None, error=None)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)