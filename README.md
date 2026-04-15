# AI Crowd Detection Web App

A Flask web application that uses YOLOv5 and SORT tracking to detect and count people in videos.

## Features

- Upload videos for crowd detection
- Real-time person tracking using YOLOv5 and SORT algorithm
- Visual tracking overlays on processed videos
- Clean web interface with progress tracking
- Docker containerization for easy deployment

## Prerequisites

- Docker and Docker Compose
- Or Python 3.10+ with virtual environment

## Quick Start with Docker

### Using Docker Compose (Recommended)

1. Clone the repository
2. Navigate to the project directory
3. Run the application:

```bash
docker-compose up --build
```

The application will be available at `http://localhost:5000`

### Using Docker directly

1. Build the image:
```bash
docker build -t crowd-detection .
```

2. Run the container:
```bash
docker run -p 5000:5000 -v $(pwd)/static/uploads:/app/static/uploads -v $(pwd)/static/output:/app/static/output crowd-detection
```

## Local Development

1. Create a virtual environment:
```bash
python -m venv venv
source venv/Scripts/activate  # On Windows
# or
source venv/bin/activate     # On Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

## Usage

1. Open your browser and go to `http://localhost:5000`
2. Click "Choose Video" to select a video file
3. Click "🚀 Process Video" to start processing
4. Wait for the processing to complete
5. View the processed video with tracking overlays and crowd count

## Docker Details

- **Base Image**: Python 3.10 slim
- **System Dependencies**: OpenCV, PyTorch, FFmpeg
- **Ports**: 5000
- **Volumes**: Uploads and output directories are mounted for persistence
- **Health Check**: Automatic health monitoring

## API Endpoints

- `GET /` - Main web interface
- `POST /upload` - Upload video file
- `POST /process` - Process uploaded video
- `GET /progress` - Get processing progress
- `GET /processed/<filename>` - Serve processed video

## Architecture

- **Frontend**: HTML/CSS/JavaScript with modern glassmorphism design
- **Backend**: Flask web framework
- **AI Models**: YOLOv5 for person detection, SORT for tracking
- **Video Processing**: OpenCV with FFmpeg for format conversion

## Troubleshooting

### Common Issues

1. **FFmpeg not found**: Ensure FFmpeg is installed in the container
2. **Model download issues**: Check internet connection for YOLOv5 model download
3. **Memory issues**: Large videos may require more RAM
4. **GPU support**: For GPU acceleration, use a CUDA-enabled base image

### Logs

View container logs:
```bash
docker-compose logs -f
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with Docker
5. Submit a pull request