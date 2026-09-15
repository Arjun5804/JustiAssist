import abc
import asyncio
from typing import AsyncGenerator
from pathlib import Path
import os

from config import settings

class ObjectStorage(abc.ABC):
    """Abstract base class for object storage."""
    
    @abc.abstractmethod
    async def upload(self, key: str, data: bytes) -> None:
        """Upload raw bytes to object storage."""
        pass
    
    @abc.abstractmethod
    async def download_to_file(self, key: str, destination: Path) -> None:
        """Download object to a specific file destination."""
        pass
    
    @abc.abstractmethod
    async def stream(self, key: str) -> AsyncGenerator[bytes, None]:
        """Return an async generator suitable for StreamingResponse."""
        pass
    
    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete object from storage."""
        pass
    
    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if an object exists."""
        pass

class LocalObjectStorage(ObjectStorage):
    """Local filesystem implementation of object storage for testing/development."""
    
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_path(self, key: str) -> Path:
        # Prevent path traversal
        clean_key = key.lstrip("/")
        # Path resolution
        resolved_path = (self.root_dir / clean_key).resolve()
        # Verify it's within root dir
        if self.root_dir.resolve() not in resolved_path.parents:
            raise ValueError(f"Invalid key '{key}': Path traversal detected.")
        return resolved_path
    
    async def upload(self, key: str, data: bytes) -> None:
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        def _write():
            with open(path, 'wb') as f:
                f.write(data)
        await asyncio.to_thread(_write)
            
    async def download_to_file(self, key: str, destination: Path) -> None:
        path = self._get_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
        # Copy file
        def _copy():
            with open(path, 'rb') as src, open(destination, 'wb') as dst:
                while True:
                    chunk = src.read(8192)
                    if not chunk:
                        break
                    dst.write(chunk)
        await asyncio.to_thread(_copy)
                
    async def stream(self, key: str) -> AsyncGenerator[bytes, None]:
        path = self._get_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
            
        def _read_chunk(f):
            return f.read(8192)
            
        f = open(path, 'rb')
        try:
            while True:
                chunk = await asyncio.to_thread(_read_chunk, f)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(f.close)
                
    async def delete(self, key: str) -> None:
        path = self._get_path(key)
        if path.exists():
            os.remove(path)
            
    async def exists(self, key: str) -> bool:
        path = self._get_path(key)
        return path.exists()

class S3ObjectStorage(ObjectStorage):
    """S3-compatible implementation using boto3 wrapped in asyncio.to_thread."""
    
    def __init__(self):
        import boto3
        from botocore.config import Config
        
        # Access secrets properly
        access_key = settings.S3_ACCESS_KEY.get_secret_value() if settings.S3_ACCESS_KEY else None
        secret_key = settings.S3_SECRET_KEY.get_secret_value() if settings.S3_SECRET_KEY else None
        
        boto_config = Config(
            region_name=settings.S3_REGION,
            signature_version='s3v4'
        )
        
        self.bucket = settings.S3_BUCKET
        if not self.bucket:
            raise ValueError("S3_BUCKET must be set when STORAGE_PROVIDER is 's3'")
            
        self.client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=boto_config
        )
        
    async def upload(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data
        )
        
    async def download_to_file(self, key: str, destination: Path) -> None:
        await asyncio.to_thread(
            self.client.download_file,
            self.bucket,
            key,
            str(destination)
        )
        
    async def stream(self, key: str) -> AsyncGenerator[bytes, None]:
        # botocore streams are synchronous, we'll read them in a thread pool
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket,
            Key=key
        )
        body = response['Body']
        
        def read_chunk():
            return body.read(8192)
            
        try:
            while True:
                chunk = await asyncio.to_thread(read_chunk)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(body.close)
            
    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=self.bucket,
            Key=key
        )
        
    async def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=key
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise

def get_storage() -> ObjectStorage:
    """Factory function to get the configured storage provider."""
    if settings.STORAGE_PROVIDER == "s3":
        return S3ObjectStorage()
    return LocalObjectStorage(settings.LOCAL_STORAGE_ROOT)

# Global storage instance
storage = get_storage()
