from flask import Flask, request, render_template_string
import os
import cv2
import torch
import numpy as np
from sort import Sort

app = Flask(__name__)

UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Load YOLOv5 model (loads once at startup)
print("Loading YOLOv5 model...")
model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
print("Model loaded!")

# Initialize SORT tracker
tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.3)


def process_video(input_path, output_path):
    cap = cv2.VideoCapture(input_path)

    width = int(cap.get(3))
    height = int(cap.get(4))

    out = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*'mp4v'),
        20,
        (width, height)
    )

    tracked_ids = set()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

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

            # Draw head region
            head_height = int(0.25 * (y2 - y1))
            cv2.rectangle(frame, (x1, y1), (x2, y1 + head_height), (0, 165, 255), 2)

            cv2.putText(frame, f"ID {track_id}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 2)

        # Display total count
        cv2.putText(frame, f"Total: {len(tracked_ids)}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1, (0, 255, 0), 2)

        out.write(frame)

    cap.release()
    out.release()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]

        if file.filename == "":
            return "No file selected"

        input_path = os.path.join(UPLOAD_FOLDER, file.filename)
        output_path = os.path.join(OUTPUT_FOLDER, file.filename)

        file.save(input_path)

        process_video(input_path, output_path)

        return f"""
        <h2>✅ Processed Video</h2>
        <video width="600" controls>
            <source src="/{output_path}" type="video/mp4">
        </video>
        <br><br>
        <a href="/">Upload another</a>
        """

    return """
    <h2>📤 Upload Video for Crowd Detection</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <br><br>
        <input type="submit" value="Upload & Process">
    </form>
    """


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)