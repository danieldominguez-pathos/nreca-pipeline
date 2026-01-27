# =============================================================================
# Stage 1: Dependencies Builder
# =============================================================================
# This stage generates requirements.txt from uv.lock
# Only rebuilds when pyproject.toml or uv.lock changes

FROM apache/airflow:3.0.1-python3.12 AS deps-builder

# Install uv via pip (must run as airflow user)
USER airflow
RUN pip install --no-cache-dir uv

WORKDIR /tmp/build

# Copy only dependency files (changes rarely)
COPY --chown=airflow:root pyproject.toml uv.lock ./

# Generate requirements.txt from uv.lock with precise versions
# Filter out local packages, airflow (already in base image), and SQLAlchemy (conflicts with Airflow 1.4.x)
RUN uv export --no-hashes --no-emit-project --frozen 2>&1 | \
    grep -v "^-e " | \
    grep -v "^utils==" | \
    grep -v "^db==" | \
    grep -v "^apache-airflow" | \
    grep -v "^sqlalchemy==" | \
    grep -v "^# " | \
    grep -v "^warning:" > /tmp/requirements.txt && \
    echo "Generated requirements.txt with $(wc -l < /tmp/requirements.txt) lines"


# =============================================================================
# Stage 2: Package Builder
# =============================================================================
# This stage prepares our custom packages
# Only rebuilds when packages/ directory changes

FROM apache/airflow:3.0.1-python3.12 AS pkg-builder

USER root

WORKDIR /build

# Copy our packages (changes more often than deps)
COPY packages/ ./packages/


# =============================================================================
# Stage 3: Final Runtime Image
# =============================================================================
# Combines dependencies and packages with DAGs

FROM apache/airflow:3.0.1-python3.12

USER root

# Create directories with correct permissions for airflow user (uid 50000)
RUN mkdir -p /opt/airflow/logs /opt/airflow/venv_cache && \
    chown -R airflow:root /opt/airflow/logs /opt/airflow/venv_cache && \
    chmod -R 775 /opt/airflow/logs /opt/airflow/venv_cache

# Copy requirements.txt from builder (cached if unchanged)
COPY --from=deps-builder /tmp/requirements.txt /tmp/requirements.txt

# Copy packages from builder
COPY --from=pkg-builder --chown=airflow:root /build/packages/ /opt/airflow/packages/

USER airflow

# Layer 1: Install virtualenv and cloudpickle (rarely changes)
# Required for @task.virtualenv functionality
RUN pip install --no-cache-dir virtualenv cloudpickle

# Layer 2: Install third-party dependencies (changes occasionally)
# This layer is cached as long as pyproject.toml/uv.lock don't change
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Layer 3: Install our packages (changes more often)
# Using --no-deps to avoid SQLAlchemy conflicts
# Packages are installed but their dependencies (including SQLAlchemy 2.0+) are NOT
# Instead, SQLAlchemy 2.0+ is installed at runtime via @task.virtualenv requirements
RUN pip install --no-cache-dir --no-deps \
    /opt/airflow/packages/utils \
    /opt/airflow/packages/db

# Layer 4: Copy DAGs (changes most frequently)
COPY --chown=airflow:root dags/ /opt/airflow/dags/

WORKDIR /opt/airflow
