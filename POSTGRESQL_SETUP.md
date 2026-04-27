# PostgreSQL Integration Guide

This project now stores videos and metadata in a PostgreSQL database for better data management and persistence.

## Setup Instructions

### Prerequisites
- Docker and Docker Compose installed
- Your PostgreSQL image already available (or it will be pulled)

### Configuration

The PostgreSQL connection is automatically configured in `docker-compose.yml`:

```yaml
- DATABASE_URL=postgresql://crowd_user:crowd_password@postgres:5432/crowd_detection_db
```

**Default Credentials:**
- Username: `crowd_user`
- Password: `crowd_password`
- Database: `crowd_detection_db`
- Port: `5432` (inside Docker), `5432` (exposed to host)

### Starting the Services

With Docker Compose:
```bash
docker-compose up --build
```

This will:
1. Start PostgreSQL container
2. Create the database automatically
3. Start the Flask application
4. The app will create database tables automatically on first run

### Local Development (without Docker)

If running locally without Docker:

1. Install PostgreSQL on your system
2. Create a database:
```sql
CREATE DATABASE crowd_detection_db;
CREATE USER crowd_user WITH PASSWORD 'crowd_password';
ALTER ROLE crowd_user SET client_encoding TO 'utf8';
GRANT ALL PRIVILEGES ON DATABASE crowd_detection_db TO crowd_user;
```

3. Set environment variable:
```bash
export DATABASE_URL="postgresql://crowd_user:crowd_password@localhost:5432/crowd_detection_db"
```

4. Run the Flask app:
```bash
python app.py
```

## Database Schema

### Videos Table

The app automatically creates a `videos` table with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Unique video identifier |
| filename | String(255) | Processed video filename |
| original_filename | String(255) | Original uploaded filename |
| upload_date | DateTime | When the video was uploaded |
| process_date | DateTime | When the video was processed |
| total_count | Integer | Total people detected in the video |
| video_data | LargeBinary | Binary data of processed video (MP4) |
| input_data | LargeBinary | Binary data of input video |
| status | String(50) | Status: pending, processing, completed, failed |
| error_message | Text | Error details if processing failed |

## API Endpoints

### Upload Video
**POST** `/upload`
```bash
curl -X POST -F "file=@video.mp4" http://localhost:5000/upload
```

Response:
```json
{
  "filename": "video.mp4",
  "video_id": 1
}
```

### Process Video
**POST** `/process`
```bash
curl -X POST -H "Content-Type: application/json" \
  -d "{\"filename\": \"video.mp4\", \"video_id\": 1}" \
  http://localhost:5000/process
```

### Get All Videos
**GET** `/videos`
```bash
curl http://localhost:5000/videos
```

Response:
```json
[
  {
    "id": 1,
    "filename": "video.mp4",
    "original_filename": "my_video.mp4",
    "upload_date": "2024-04-21T10:30:00",
    "process_date": "2024-04-21T10:35:00",
    "total_count": 42,
    "status": "completed",
    "has_processed_video": true
  }
]
```

### Get Video Details
**GET** `/video/<video_id>`
```bash
curl http://localhost:5000/video/1
```

### Download Processed Video
**GET** `/video/<video_id>/download`
```bash
curl http://localhost:5000/video/1/download -o processed_video.mp4
```

## Web Interface Features

The web UI now includes:

1. **Video Upload & Processing** - Same as before
2. **Video Database** - View all videos stored in PostgreSQL
3. **Download Videos** - Download processed videos from the database
4. **View Details** - Check video metadata and processing status
5. **Refresh** - Refresh the video list from the database

## Benefits of PostgreSQL Integration

✅ **Persistent Storage** - Videos and metadata survive application restarts
✅ **Scalability** - Handle thousands of videos efficiently
✅ **Query Support** - Search and filter videos by any attribute
✅ **Data Integrity** - Database ACID guarantees
✅ **Backup-friendly** - Easy database backups and restoration
✅ **Multiple Users** - Support concurrent access to videos

## Troubleshooting

### Connection Error: "could not connect to server"
- Check if PostgreSQL container is running: `docker ps`
- Check logs: `docker logs crowd_detection_db`
- Ensure DATABASE_URL environment variable is set correctly

### Database Error: "Table 'videos' doesn't exist"
- The app creates tables automatically on startup
- Check Flask logs for any SQL errors
- Manually run: `python -c "from app import db; db.create_all()"`

### Out of Disk Space
The `video_data` column stores binary video files. Monitor disk usage:
```sql
SELECT pg_size_pretty(pg_total_relation_size('videos'));
```

## Development Notes

- **Local file storage** still exists in `static/uploads/` and `static/output/` for temporary files
- **Binary storage** is used for long-term persistence in PostgreSQL
- **Video data stays in memory** until explicitly saved to database
- **Large files**: Up to 500MB per video (configurable via `MAX_CONTENT_LENGTH`)

## Next Steps

Consider implementing:
- Database cleanup/archival strategy for old videos
- Full-text search on video metadata
- User authentication and permission system
- S3 integration for backup storage
- Video metadata extraction (duration, resolution, etc.)
