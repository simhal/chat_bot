"""Storage service for file operations - supports both local and S3 storage."""

import os
import logging
from typing import Optional, Tuple, BinaryIO
from abc import ABC, abstractmethod

logger = logging.getLogger("uvicorn")

# Check if S3 is configured
S3_BUCKET = os.environ.get("S3_BUCKET")
AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save_file(self, file_path: str, content: bytes) -> bool:
        """Save file content to storage."""
        pass

    @abstractmethod
    def get_file(self, file_path: str) -> Optional[bytes]:
        """Get file content from storage."""
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """Delete file from storage."""
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Check if file exists in storage."""
        pass

    @abstractmethod
    def get_file_url(self, file_path: str) -> Optional[str]:
        """Get URL or path for file access."""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: str = UPLOAD_DIR):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        logger.info(f"Storage: Using local storage at {base_dir}")

    def _full_path(self, file_path: str) -> str:
        return os.path.join(self.base_dir, file_path)

    def save_file(self, file_path: str, content: bytes) -> bool:
        try:
            full_path = self._full_path(file_path)
            # Ensure directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'wb') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Local storage save error: {e}")
            return False

    def get_file(self, file_path: str) -> Optional[bytes]:
        try:
            full_path = self._full_path(file_path)
            if not os.path.exists(full_path):
                return None
            with open(full_path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Local storage read error: {e}")
            return None

    def delete_file(self, file_path: str) -> bool:
        try:
            full_path = self._full_path(file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
            return True
        except Exception as e:
            logger.error(f"Local storage delete error: {e}")
            return False

    def file_exists(self, file_path: str) -> bool:
        return os.path.exists(self._full_path(file_path))

    def get_file_url(self, file_path: str) -> Optional[str]:
        """For local storage, return the full path."""
        return self._full_path(file_path)


class S3StorageBackend(StorageBackend):
    """AWS S3 storage backend."""

    def __init__(self, bucket: str, region: str = AWS_REGION):
        self.bucket = bucket
        self.region = region
        self._client = None
        logger.info(f"Storage: Using S3 bucket '{bucket}' in region '{region}'")

    @property
    def client(self):
        """Lazy initialization of S3 client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client('s3', region_name=self.region)
            except ImportError:
                logger.error("boto3 not installed - S3 storage will not work")
                raise
        return self._client

    def save_file(self, file_path: str, content: bytes) -> bool:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=file_path,
                Body=content
            )
            logger.debug(f"S3: Saved file {file_path}")
            return True
        except Exception as e:
            logger.error(f"S3 storage save error: {e}")
            return False

    def get_file(self, file_path: str) -> Optional[bytes]:
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=file_path
            )
            return response['Body'].read()
        except self.client.exceptions.NoSuchKey:
            logger.warning(f"S3: File not found {file_path}")
            return None
        except Exception as e:
            logger.error(f"S3 storage read error: {e}")
            return None

    def delete_file(self, file_path: str) -> bool:
        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=file_path
            )
            logger.debug(f"S3: Deleted file {file_path}")
            return True
        except Exception as e:
            logger.error(f"S3 storage delete error: {e}")
            return False

    def file_exists(self, file_path: str) -> bool:
        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=file_path
            )
            return True
        except:
            return False

    def get_file_url(self, file_path: str) -> Optional[str]:
        """Generate a presigned URL for file access (valid for 1 hour)."""
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': file_path},
                ExpiresIn=3600
            )
            return url
        except Exception as e:
            logger.error(f"S3 presigned URL error: {e}")
            return None

    def save_file_with_metadata(
        self,
        file_path: str,
        content: bytes,
        content_type: str,
        metadata: Optional[dict] = None
    ) -> bool:
        """Save file with content type and metadata."""
        try:
            extra_args = {'ContentType': content_type}
            if metadata:
                extra_args['Metadata'] = metadata

            self.client.put_object(
                Bucket=self.bucket,
                Key=file_path,
                Body=content,
                **extra_args
            )
            logger.debug(f"S3: Saved file {file_path} with metadata")
            return True
        except Exception as e:
            logger.error(f"S3 storage save error: {e}")
            return False


class StorageService:
    """
    Unified storage service that automatically uses S3 or local storage
    based on environment configuration.

    Usage:
        storage = StorageService.get_instance()
        storage.save_file("path/to/file.pdf", content)
        content = storage.get_file("path/to/file.pdf")
    """

    _instance: Optional['StorageService'] = None
    _backend: Optional[StorageBackend] = None

    def __init__(self):
        if S3_BUCKET:
            self._backend = S3StorageBackend(S3_BUCKET, AWS_REGION)
        else:
            self._backend = LocalStorageBackend(UPLOAD_DIR)

    @classmethod
    def get_instance(cls) -> 'StorageService':
        """Get singleton instance of StorageService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)."""
        cls._instance = None

    @property
    def is_s3(self) -> bool:
        """Check if using S3 storage."""
        return isinstance(self._backend, S3StorageBackend)

    @property
    def is_local(self) -> bool:
        """Check if using local storage."""
        return isinstance(self._backend, LocalStorageBackend)

    def save_file(self, file_path: str, content: bytes) -> bool:
        """Save file to storage."""
        return self._backend.save_file(file_path, content)

    def get_file(self, file_path: str) -> Optional[bytes]:
        """Get file content from storage."""
        return self._backend.get_file(file_path)

    def delete_file(self, file_path: str) -> bool:
        """Delete file from storage."""
        return self._backend.delete_file(file_path)

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        return self._backend.file_exists(file_path)

    def get_file_path(self, file_path: str) -> Optional[str]:
        """
        Get the actual file path or URL for direct access.

        For local storage: returns filesystem path
        For S3: returns presigned URL
        """
        return self._backend.get_file_url(file_path)

    def save_file_with_metadata(
        self,
        file_path: str,
        content: bytes,
        content_type: str,
        metadata: Optional[dict] = None
    ) -> bool:
        """Save file with content type and metadata (S3 only, falls back to regular save for local)."""
        if isinstance(self._backend, S3StorageBackend):
            return self._backend.save_file_with_metadata(file_path, content, content_type, metadata)
        else:
            return self._backend.save_file(file_path, content)


# Convenience function for getting storage instance
def get_storage() -> StorageService:
    """Get the storage service instance."""
    return StorageService.get_instance()
