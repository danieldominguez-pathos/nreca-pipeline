"""S3 storage backend."""

import boto3
from botocore.exceptions import ClientError

from storage.base import StorageBackend


class S3StorageBackend(StorageBackend):
    """Storage backend for AWS S3.

    Files are stored in an S3 bucket with an optional prefix.
    Paths are returned in the format 's3://<bucket>/<key>'.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
    ) -> None:
        """Initialize S3 storage backend.

        Args:
            bucket: S3 bucket name
            prefix: Optional key prefix for all objects
            region: AWS region
        """
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._region = region
        self._client = boto3.client("s3", region_name=region)

    @property
    def bucket(self) -> str:
        """Get the S3 bucket name."""
        return self._bucket

    @property
    def prefix(self) -> str:
        """Get the S3 key prefix."""
        return self._prefix

    def _resolve_key(self, filename: str) -> str:
        """Resolve filename to full S3 key.

        Args:
            filename: File name

        Returns:
            Full S3 key including prefix
        """
        return f"{self._prefix}{filename}"

    def exists(self, filename: str) -> bool:
        """Check if a file exists in S3.

        Args:
            filename: Name of the file

        Returns:
            True if file exists, False otherwise
        """
        key = self._resolve_key(filename)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def read(self, filename: str) -> bytes:
        """Read file content from S3.

        Args:
            filename: Name of the file to read

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file does not exist
        """
        key = self._resolve_key(filename)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found in S3: {filename}")
            raise

    def get_path(self, filename: str) -> str:
        """Get the canonical S3 URI for a file.

        Returns path in format 's3://<bucket>/<key>' as specified
        in the metadata contract.

        Args:
            filename: Name of the file

        Returns:
            S3 URI in format 's3://<bucket>/<key>'
        """
        key = self._resolve_key(filename)
        return f"s3://{self._bucket}/{key}"

    def list_files(self, prefix: str = "") -> list[str]:
        """List files in S3 with optional prefix filter.

        Args:
            prefix: Optional additional prefix to filter files

        Returns:
            List of filenames (keys without the base prefix)
        """
        full_prefix = f"{self._prefix}{prefix}" if prefix else self._prefix
        files: list[str] = []

        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Remove base prefix to get relative filename
                if self._prefix and key.startswith(self._prefix):
                    filename = key[len(self._prefix) :]
                else:
                    filename = key
                if filename:  # Skip empty keys (e.g., prefix itself)
                    files.append(filename)

        return sorted(files)

    def list_files_with_info(self, prefix: str = "") -> list[dict]:
        """List files with metadata (filename, path, size).

        Optimized for S3 - uses list_objects_v2 Size field instead of
        reading full content.

        Args:
            prefix: Optional additional prefix to filter files

        Returns:
            List of dicts with keys: filename, path, size
        """
        full_prefix = f"{self._prefix}{prefix}" if prefix else self._prefix
        files: list[dict] = []

        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Remove base prefix to get relative filename
                if self._prefix and key.startswith(self._prefix):
                    filename = key[len(self._prefix) :]
                else:
                    filename = key
                if filename:  # Skip empty keys
                    files.append({
                        "filename": filename,
                        "path": f"s3://{self._bucket}/{key}",
                        "size": obj.get("Size", 0),
                    })

        return sorted(files, key=lambda x: x["filename"])
