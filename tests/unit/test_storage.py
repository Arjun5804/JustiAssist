import pytest
import os
import asyncio
from pathlib import Path
from core.storage import LocalObjectStorage

@pytest.fixture
def local_storage(tmp_path):
    storage_dir = tmp_path / "storage"
    return LocalObjectStorage(str(storage_dir))

@pytest.mark.asyncio
async def test_local_storage_upload_download(local_storage, tmp_path):
    key = "documents/user_1/doc_abc/test.txt"
    content = b"Hello, World! This is a test document."
    
    # Upload
    await local_storage.upload(key, content)
    assert await local_storage.exists(key) is True
    
    # Download
    dest = tmp_path / "downloaded.txt"
    await local_storage.download_to_file(key, dest)
    assert dest.exists()
    assert dest.read_bytes() == content

@pytest.mark.asyncio
async def test_local_storage_stream(local_storage):
    key = "documents/user_2/doc_xyz/stream.txt"
    content = b"Streaming content " * 1000
    
    await local_storage.upload(key, content)
    
    streamed = b""
    async for chunk in local_storage.stream(key):
        streamed += chunk
        
    assert streamed == content

@pytest.mark.asyncio
async def test_local_storage_delete(local_storage):
    key = "documents/user_3/doc_123/delete_me.txt"
    await local_storage.upload(key, b"delete this")
    assert await local_storage.exists(key) is True
    
    await local_storage.delete(key)
    assert await local_storage.exists(key) is False

@pytest.mark.asyncio
async def test_path_traversal_prevention(local_storage):
    malicious_key = "../../../etc/passwd"
    
    with pytest.raises(ValueError, match="Path traversal detected"):
        await local_storage.upload(malicious_key, b"hacked")
        
    with pytest.raises(ValueError, match="Path traversal detected"):
        await local_storage.exists(malicious_key)
