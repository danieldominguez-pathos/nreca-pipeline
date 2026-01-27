-- Initialize PostgreSQL databases for Airflow template
--
-- This script creates two separate databases:
-- 1. airflow - Airflow metadata (DAG runs, task instances, etc.)
-- 2. app - Application data (your models, business data)
--
-- This separation keeps Airflow's metadata isolated from your app data.

-- Create airflow database and user
CREATE USER airflow WITH PASSWORD 'airflow';
CREATE DATABASE airflow OWNER airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;

-- Create app database and user
CREATE USER app WITH PASSWORD 'app';
CREATE DATABASE app OWNER app;
GRANT ALL PRIVILEGES ON DATABASE app TO app;

-- Grant schema permissions (required for PostgreSQL 15+)
\c airflow
GRANT ALL ON SCHEMA public TO airflow;

\c app
GRANT ALL ON SCHEMA public TO app;
