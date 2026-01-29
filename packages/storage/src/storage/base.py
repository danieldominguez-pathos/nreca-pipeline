"""Abstract base for storage backends."""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract base class for storage backend implementations.

    All storage implementations (local, S3) must inherit from this class
    and implement the abstract methods.
    """

    @abstractmethod
    def exists(self, filename: str) -> bool:
        """Check if a file exists in storage.

        Args:
            filename: Name of the file (not full path)

        Returns:
            True if file exists, False otherwise
        """

    @abstractmethod
    def read(self, filename: str) -> bytes:
        """Read file content from storage.

        Args:
            filename: Name of the file to read

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file does not exist
        """

    @abstractmethod
    def get_path(self, filename: str) -> str:
        """Get the canonical path/URI for a file.

        Returns:
            - For local: 'localpath/<filename>'
            - For S3: 's3://<bucket>/<key>'
        """

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[str]:
        """List files in storage with optional prefix filter.

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of filenames (not full paths)
        """

    def list_files_with_info(self, prefix: str = "") -> list[dict]:
        """List files with metadata (filename, path, size).

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of dicts with keys: filename, path, size
        """
        files = self.list_files(prefix)
        result = []
        for filename in files:
            try:
                content = self.read(filename)
                result.append({
                    "filename": filename,
                    "path": self.get_path(filename),
                    "size": len(content),
                })
            except FileNotFoundError:
                continue
        return result
