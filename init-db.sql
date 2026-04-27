-- Initialize PostgreSQL database for Crowd Detection App
-- This file is executed automatically when PostgreSQL container starts

-- Ensure crowd_detection_db exists
SELECT 'CREATE DATABASE crowd_detection_db' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crowd_detection_db')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE crowd_detection_db TO crowd_user;
