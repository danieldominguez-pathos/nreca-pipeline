"""Airflow REST API client for triggering DAGs.

Airflow 3.x uses JWT tokens for v2 API authentication.
"""

from datetime import UTC, datetime
from functools import lru_cache

import httpx
from utils import get_logger

from api.config import APISettings, get_api_settings

log = get_logger("api.services.airflow")


class AirflowClient:
    """Client for Airflow REST API with JWT authentication."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._base_url = settings.airflow_api_url.rstrip("/")
        self._username = settings.airflow_username
        self._password = settings.airflow_password.get_secret_value()
        self._token: str | None = None

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        """Get JWT token from Airflow auth endpoint."""
        if self._token:
            return self._token

        # Extract base URL without /api/v2
        auth_base = self._base_url.replace("/api/v2", "")
        token_url = f"{auth_base}/auth/token"

        response = await client.post(
            token_url,
            data={
                "username": self._username,
                "password": self._password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        response.raise_for_status()

        data = response.json()
        self._token = data["access_token"]
        log.info("airflow_token_acquired")

        return self._token

    async def trigger_dag(
        self,
        dag_id: str,
        conf: dict | None = None,
    ) -> dict:
        """Trigger an Airflow DAG.

        Args:
            dag_id: The DAG ID to trigger
            conf: Optional configuration dict to pass to the DAG

        Returns:
            Dict with dag_run_id and other info

        Raises:
            httpx.HTTPStatusError: If the request fails
        """
        url = f"{self._base_url}/dags/{dag_id}/dagRuns"

        # Airflow v2 API requires logical_date
        logical_date = datetime.now(UTC).isoformat()

        payload = {
            "logical_date": logical_date,
            "conf": conf or {},
        }

        log.info("triggering_dag", dag_id=dag_id, conf=conf)

        async with httpx.AsyncClient() as client:
            # Get JWT token
            token = await self._get_token(client)

            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
            response.raise_for_status()

            data = response.json()
            dag_run_id = data.get("dag_run_id", "unknown")

            log.info("dag_triggered", dag_id=dag_id, dag_run_id=dag_run_id)

            return {
                "dag_run_id": dag_run_id,
                "dag_id": dag_id,
                "state": data.get("state"),
                "execution_date": data.get("execution_date"),
            }


@lru_cache(maxsize=1)
def get_airflow_client() -> AirflowClient:
    """Get cached Airflow client singleton."""
    return AirflowClient(get_api_settings())
