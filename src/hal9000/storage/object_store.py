"""Object storage abstraction with local and S3-compatible backends."""

import hashlib
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, Protocol


class ObjectNotFoundError(FileNotFoundError):
    """Raised when an object key does not exist."""


@dataclass(frozen=True)
class StoredObject:
    """Metadata for an object stored by HAL."""

    key: str
    uri: str
    size_bytes: int
    sha256: str
    content_type: str = "application/octet-stream"


class ObjectStore(Protocol):
    """Protocol for object storage backends."""

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store bytes at a key."""
        ...

    def put_file(
        self,
        key: str,
        source_path: Path,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store a file at a key."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read object bytes."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open an object for binary reading."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether an object exists."""
        ...

    def delete(self, key: str) -> None:
        """Delete an object if it exists."""
        ...

    def uri_for(self, key: str) -> str:
        """Return the backend URI for a key."""
        ...


class LocalObjectStore:
    """Local filesystem implementation of the object store protocol."""

    def __init__(self, root_path: str | Path, uri_scheme: str = "hal-local"):
        """Initialize the local object store."""
        self.root_path = Path(root_path).expanduser().resolve()
        self.uri_scheme = uri_scheme
        self.root_path.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store bytes at a key."""
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self._stored_object(key, path, content_type)

    def put_file(
        self,
        key: str,
        source_path: Path,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store a file at a key."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        return self._stored_object(key, path, content_type)

    def get_bytes(self, key: str) -> bytes:
        """Read object bytes."""
        path = self._path_for_key(key)
        if not path.exists():
            raise ObjectNotFoundError(key)
        return path.read_bytes()

    def open(self, key: str) -> BinaryIO:
        """Open an object for binary reading."""
        path = self._path_for_key(key)
        if not path.exists():
            raise ObjectNotFoundError(key)
        return path.open("rb")

    def exists(self, key: str) -> bool:
        """Return whether an object exists."""
        return self._path_for_key(key).exists()

    def delete(self, key: str) -> None:
        """Delete an object if it exists."""
        path = self._path_for_key(key)
        if path.exists():
            path.unlink()

    def uri_for(self, key: str) -> str:
        """Return the local object URI for a key."""
        normalized = self._normalize_key(key)
        return f"{self.uri_scheme}://{normalized}"

    def path_for(self, key: str) -> Path:
        """Return the local path for a key."""
        return self._path_for_key(key)

    def _stored_object(self, key: str, path: Path, content_type: str) -> StoredObject:
        data = path.read_bytes()
        return StoredObject(
            key=self._normalize_key(key),
            uri=self.uri_for(key),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
        )

    def _path_for_key(self, key: str) -> Path:
        normalized = self._normalize_key(key)
        path = (self.root_path / normalized).resolve()
        if self.root_path not in path.parents and path != self.root_path:
            raise ValueError(f"Object key escapes storage root: {key}")
        return path

    def _normalize_key(self, key: str) -> str:
        normalized = key.replace("\\", "/").strip("/")
        if not normalized:
            raise ValueError("Object key must not be empty")
        parts = Path(normalized).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"Invalid object key: {key}")
        return "/".join(parts)


class S3ObjectStore:
    """S3-compatible implementation of the object store protocol."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        client=None,
    ):
        """Initialize the S3-compatible object store."""
        if not bucket:
            raise ValueError("S3 object store requires a bucket")
        self.bucket = bucket
        self.prefix = self._normalize_prefix(prefix)
        self.region = region
        self.endpoint_url = endpoint_url
        self.client = client or self._create_client()

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store bytes at a key."""
        normalized = self._normalize_key(key)
        s3_key = self._s3_key(normalized)
        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
        )
        return StoredObject(
            key=normalized,
            uri=self.uri_for(normalized),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
        )

    def put_file(
        self,
        key: str,
        source_path: Path,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Store a file at a key."""
        data = Path(source_path).read_bytes()
        return self.put_bytes(key, data, content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        """Read object bytes."""
        normalized = self._normalize_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._s3_key(normalized))
        except Exception as exc:
            if self._is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise
        return response["Body"].read()

    def open(self, key: str) -> BinaryIO:
        """Open an object for binary reading."""
        return BytesIO(self.get_bytes(key))

    def exists(self, key: str) -> bool:
        """Return whether an object exists."""
        normalized = self._normalize_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._s3_key(normalized))
            return True
        except Exception as exc:
            if self._is_not_found(exc):
                return False
            raise

    def delete(self, key: str) -> None:
        """Delete an object if it exists."""
        normalized = self._normalize_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=self._s3_key(normalized))

    def uri_for(self, key: str) -> str:
        """Return the S3 URI for a key."""
        normalized = self._normalize_key(key)
        return f"s3://{self.bucket}/{self._s3_key(normalized)}"

    def _create_client(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "S3 object storage requires the 's3' optional dependency: pip install -e '.[s3]'"
            ) from exc
        return boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint_url,
        )

    def _s3_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _normalize_key(self, key: str) -> str:
        normalized = key.replace("\\", "/").strip("/")
        if not normalized:
            raise ValueError("Object key must not be empty")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"Invalid object key: {key}")
        return "/".join(parts)

    def _normalize_prefix(self, prefix: str) -> str:
        if not prefix:
            return ""
        normalized = prefix.replace("\\", "/").strip("/")
        if not normalized:
            return ""
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"Invalid object prefix: {prefix}")
        return "/".join(parts) + "/"

    def _is_not_found(self, exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = response.get("Error", {}).get("Code")
            return str(code) in {"404", "NoSuchKey", "NotFound"}
        return False


def create_object_store(
    backend: str,
    root_path: str | Path,
    bucket: Optional[str] = None,
    prefix: str = "",
    region: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    client=None,
) -> ObjectStore:
    """Create an object store backend."""
    if backend == "local":
        return LocalObjectStore(root_path)
    if backend == "s3":
        return S3ObjectStore(
            bucket=bucket or "",
            prefix=prefix,
            region=region,
            endpoint_url=endpoint_url,
            client=client,
        )
    raise ValueError(f"Unsupported object store backend: {backend}")


def create_object_store_from_settings(settings) -> ObjectStore:
    """Create an object store from HAL settings."""
    return create_object_store(
        backend=settings.storage.backend,
        root_path=settings.get_storage_path(),
        bucket=settings.storage.bucket,
        prefix=settings.storage.prefix,
        region=settings.storage.region,
        endpoint_url=settings.storage.endpoint_url,
    )
