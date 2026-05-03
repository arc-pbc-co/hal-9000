"""Tests for object storage backends."""

import pytest

from hal9000.config import Settings, StorageConfig
from hal9000.storage import (
    LocalObjectStore,
    ObjectNotFoundError,
    S3ObjectStore,
    create_object_store,
    create_object_store_from_settings,
)


class FakeS3NotFoundError(Exception):
    """Fake S3 not-found exception with a boto-style response payload."""

    response = {"Error": {"Code": "404"}}


class FakeS3Client:
    """Small in-memory stand-in for a boto3 S3 client."""

    def __init__(self):
        self.objects: dict[tuple[str, str], dict[str, object]] = {}

    def put_object(self, **kwargs):
        """Store an object payload."""
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "Body": kwargs["Body"],
            "ContentType": kwargs["ContentType"],
        }

    def get_object(self, **kwargs):
        """Fetch an object payload."""
        bucket = kwargs["Bucket"]
        key = kwargs["Key"]
        if (bucket, key) not in self.objects:
            raise FakeS3NotFoundError()
        from io import BytesIO

        return {"Body": BytesIO(self.objects[(bucket, key)]["Body"])}

    def head_object(self, **kwargs):
        """Check for object existence."""
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise FakeS3NotFoundError()
        return {}

    def delete_object(self, **kwargs):
        """Delete an object payload."""
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)


def test_local_object_store_put_get_delete_bytes(temp_directory):
    """Local object storage should round-trip bytes and metadata."""
    store = LocalObjectStore(temp_directory / "objects")

    stored = store.put_bytes(
        "papers/source.txt",
        b"hello research",
        content_type="text/plain",
    )

    assert stored.key == "papers/source.txt"
    assert stored.uri == "hal-local://papers/source.txt"
    assert stored.size_bytes == len(b"hello research")
    assert stored.content_type == "text/plain"
    assert len(stored.sha256) == 64
    assert store.exists("papers/source.txt") is True
    assert store.get_bytes("papers/source.txt") == b"hello research"

    store.delete("papers/source.txt")

    assert store.exists("papers/source.txt") is False
    with pytest.raises(ObjectNotFoundError):
        store.get_bytes("papers/source.txt")


def test_local_object_store_put_file(temp_directory):
    """Local object storage should copy source files."""
    source = temp_directory / "source.bin"
    source.write_bytes(b"file bytes")
    store = LocalObjectStore(temp_directory / "objects")

    stored = store.put_file("artifacts/source.bin", source)

    assert stored.size_bytes == len(b"file bytes")
    assert store.get_bytes("artifacts/source.bin") == b"file bytes"


def test_local_object_store_rejects_unsafe_keys(temp_directory):
    """Object keys should not escape the storage root."""
    store = LocalObjectStore(temp_directory / "objects")

    with pytest.raises(ValueError):
        store.put_bytes("../escape.txt", b"bad")
    with pytest.raises(ValueError):
        store.put_bytes("", b"bad")


def test_create_object_store_supports_local_backend(temp_directory):
    """The object store factory should create local stores."""
    store = create_object_store("local", temp_directory / "objects")

    stored = store.put_bytes("a/b.txt", b"data")

    assert stored.uri == "hal-local://a/b.txt"


def test_s3_object_store_round_trips_bytes():
    """S3-compatible object storage should round-trip bytes and metadata."""
    client = FakeS3Client()
    store = S3ObjectStore(
        bucket="hal-artifacts",
        prefix="hal9000/",
        region="us-east-1",
        endpoint_url="https://s3.example.com",
        client=client,
    )

    stored = store.put_bytes(
        "papers/source.txt",
        b"hello research",
        content_type="text/plain",
    )

    assert stored.key == "papers/source.txt"
    assert stored.uri == "s3://hal-artifacts/hal9000/papers/source.txt"
    assert stored.size_bytes == len(b"hello research")
    assert stored.content_type == "text/plain"
    assert len(stored.sha256) == 64
    assert store.exists("papers/source.txt") is True
    assert store.get_bytes("papers/source.txt") == b"hello research"

    store.delete("papers/source.txt")

    assert store.exists("papers/source.txt") is False
    with pytest.raises(ObjectNotFoundError):
        store.get_bytes("papers/source.txt")


def test_s3_object_store_rejects_unsafe_keys():
    """S3 object keys should reject traversal-like paths."""
    store = S3ObjectStore(bucket="hal-artifacts", client=FakeS3Client())

    with pytest.raises(ValueError):
        store.put_bytes("../escape.txt", b"bad")
    with pytest.raises(ValueError):
        store.put_bytes("", b"bad")


def test_create_object_store_requires_s3_bucket(temp_directory):
    """The object store factory should require a bucket for S3 storage."""
    with pytest.raises(ValueError):
        create_object_store("s3", temp_directory)


def test_create_object_store_supports_s3_backend(temp_directory):
    """The object store factory should create S3-compatible stores."""
    store = create_object_store(
        "s3",
        temp_directory,
        bucket="hal-artifacts",
        prefix="hal9000",
        client=FakeS3Client(),
    )

    assert isinstance(store, S3ObjectStore)
    assert store.uri_for("outputs/report.md") == "s3://hal-artifacts/hal9000/outputs/report.md"


def test_create_object_store_from_settings(temp_directory):
    """Object stores should be constructible from HAL settings."""
    settings = Settings(
        storage=StorageConfig(
            backend="local",
            root_path=str(temp_directory / "objects"),
        )
    )

    store = create_object_store_from_settings(settings)
    stored = store.put_bytes("outputs/report.md", b"# Report", "text/markdown")

    assert stored.uri == "hal-local://outputs/report.md"
    assert store.get_bytes("outputs/report.md") == b"# Report"
