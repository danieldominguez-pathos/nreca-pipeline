"""Local filesystem storage backend."""

from pathlib import Path

from storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Storage backend for local filesystem.

    Files are stored in a base directory and paths are returned
    in the format 'localpath/<filename>'.
    """

    def __init__(self, base_path: str) -> None:
        """Initialize local storage backend.

        Args:
            base_path: Base directory for file storage
        """
        self._base_path = Path(base_path)
        if not self._base_path.exists():
            self._base_path.mkdir(parents=True, exist_ok=True)

    @property
    def base_path(self) -> Path:
        """Get the base storage path."""
        return self._base_path

    def _resolve_path(self, filename: str) -> Path:
        """Resolve filename to full path.

        Args:
            filename: File name (can include subdirectories)

        Returns:
            Full path to the file
        """
        return self._base_path / filename

    def exists(self, filename: str) -> bool:
        """Check if a file exists in local storage.

        Args:
            filename: Name of the file

        Returns:
            True if file exists, False otherwise
        """
        return self._resolve_path(filename).exists()

    def read(self, filename: str) -> bytes:
        """Read file content from local storage.

        Args:
            filename: Name of the file to read

        Returns:
            File contents as bytes

        Raises:
            FileNotFoundError: If file does not exist
        """
        file_path = self._resolve_path(filename)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        return file_path.read_bytes()

    def get_path(self, filename: str) -> str:
        """Get the canonical path for a local file.

        Returns path in format 'localpath/<filename>' as specified
        in the metadata contract.

        Args:
            filename: Name of the file

        Returns:
            Path in format 'localpath/<filename>'
        """
        return f"localpath/{filename}"

    def list_files(self, prefix: str = "") -> list[str]:
        """List files in local storage with optional prefix filter.

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of filenames relative to base path
        """
        files: list[str] = []
        search_path = self._base_path / prefix if prefix else self._base_path

        if not search_path.exists():
            return files

        for item in search_path.rglob("*"):
            if item.is_file():
                relative_path = item.relative_to(self._base_path)
                files.append(str(relative_path))

        return sorted(files)

    def list_files_with_info(self, prefix: str = "") -> list[dict]:
        """List files with metadata (filename, path, size).

        Optimized for local - uses stat() instead of reading full content.

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of dicts with keys: filename, path, size
        """
        files: list[dict] = []
        search_path = self._base_path / prefix if prefix else self._base_path

        if not search_path.exists():
            return files

        for item in search_path.rglob("*"):
            if item.is_file():
                relative_path = str(item.relative_to(self._base_path))
                files.append({
                    "filename": relative_path,
                    "path": f"localpath/{relative_path}",
                    "size": item.stat().st_size,
                })

        return sorted(files, key=lambda x: x["filename"])
