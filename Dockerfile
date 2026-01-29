# =============================================================================
# Airflow 3.x Dockerfile
# =============================================================================
#
# Architecture: Use @task.virtualenv to isolate SQLAlchemy 2.x packages from
# Airflow's environment (which requires SQLAlchemy 1.4.x).
#
# Key pattern:
# - Install packages with --no-deps (avoids SQLAlchemy 2.x contamination)
# - Manually install only non-conflicting dependencies
# - DAGs use @task.virtualenv with requirements=["sqlalchemy>=2.0.0"]

FROM apache/airflow:3.1.3-python3.12

USER root

# Create directories with correct permissions for airflow user (uid 50000)
RUN mkdir -p /opt/airflow/logs /opt/airflow/venv_cache && \
    chown -R airflow:root /opt/airflow/logs /opt/airflow/venv_cache && \
    chmod -R 775 /opt/airflow/logs /opt/airflow/venv_cache

# Copy our packages
COPY --chown=airflow:root packages/ /opt/airflow/packages/

USER airflow

# Install virtualenv and cloudpickle (required for @task.virtualenv)
# Install our packages with --no-deps (avoid SQLAlchemy 2.x contamination)
# Manually install non-conflicting dependencies
RUN pip install --no-cache-dir virtualenv cloudpickle && \
    pip install --no-cache-dir --no-deps \
        /opt/airflow/packages/utils \
        /opt/airflow/packages/db \
        /opt/airflow/packages/storage \
        /opt/airflow/packages/vectordb && \
    pip install --no-cache-dir \
        httpx \
        "psycopg[binary]" \
        pydantic-settings \
        structlog \
        boto3 \
        chromadb \
        pypdf \
        python-dotenv

# Install PyTorch CPU-only and sentence-transformers (avoid 2GB+ CUDA downloads)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir sentence-transformers

# Copy DAGs (changes most frequently)
COPY --chown=airflow:root dags/ /opt/airflow/dags/

WORKDIR /opt/airflow
