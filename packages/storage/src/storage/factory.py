"""Storage backend factory."""

from storage.base import StorageBackend
from storage.config import StorageSettings, get_storage_settings
from storage.local import LocalStorageBackend
from storage.s3 import S3StorageBackend


def get_storage(settings: StorageSettings | None = None) -> StorageBackend:
    """Get the appropriate storage backend based on environment.

    Factory function that returns either LocalStorageBackend or S3StorageBackend
    depending on the APP_ENV configuration.

    Args:
        settings: Optional storage settings. If not provided, loads from environment.

    Returns:
        StorageBackend instance configured for the current environment

    Example:
        >>> storage = get_storage()
        >>> content = storage.read("document.pdf")
        >>> path = storage.get_path("document.pdf")
        # Returns "localpath/document.pdf" or "s3://bucket/documents/document.pdf"
    """
    if settings is None:
        settings = get_storage_settings()

    if settings.is_local:
        return LocalStorageBackend(base_path=settings.local_path)

    return S3StorageBackend(
        bucket=settings.s3_bucket,
        prefix=settings.s3_prefix,
        region=settings.s3_region,
    )
