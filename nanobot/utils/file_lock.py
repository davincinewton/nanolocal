"""
Cross-platform file lock - Simple file-based locking mechanism
Supports both Windows and Unix systems
"""

import os
import time
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional


class FileLock:
    """
    Simple file-based locking mechanism
    
    Principle:
    1. Create .nanobot_lock file as lock marker
    2. Use file existence check + timeout mechanism
    3. Main agent priority: Main agent can override SelfAgent's lock
    """
    
    def __init__(
        self, 
        filepath: Path, 
        timeout: float = 5.0, 
        is_main_agent: bool = False
    ):
        self.filepath = filepath
        self.lockfile = Path(str(filepath) + ".nanobot_lock")
        self.timeout = timeout
        self.is_main_agent = is_main_agent
        self._acquired = False
    
    async def acquire(self) -> bool:
        """Try to acquire lock"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            # Check if lock file exists
            if not self.lockfile.exists():
                # Create lock file with process ID and timestamp
                try:
                    content = f"{os.getpid()}|{time.time()}|{'main' if self.is_main_agent else 'selfagent'}"
                    self.lockfile.write_text(content)
                    self._acquired = True
                    return True
                except Exception:
                    pass
            
            # If main agent, can force acquire lock (priority)
            if self.is_main_agent and self.lockfile.exists():
                try:
                    content = self.lockfile.read_text()
                    if "selfagent" in content:
                        # Force override lock file
                        content = f"{os.getpid()}|{time.time()}|main"
                        self.lockfile.write_text(content)
                        self._acquired = True
                        return True
                except Exception:
                    pass
            
            # Wait and retry
            await asyncio.sleep(0.1)
        
        return False
    
    async def release(self):
        """Release lock"""
        if self._acquired and self.lockfile.exists():
            try:
                self.lockfile.unlink()
            except Exception:
                pass
            self._acquired = False
    
    @asynccontextmanager
    async def __aenter__(self):
        if not await self.acquire():
            raise TimeoutError(f"Could not acquire lock for {self.filepath}")
        yield self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


@asynccontextmanager
async def file_lock(
    filepath: Path, 
    timeout: float = 5.0, 
    is_main_agent: bool = False
):
    """
    Async context manager for file locking
    
    Usage:
        async with file_lock(filepath, is_main_agent=False):
            # Do file operations
            pass
    """
    lock = FileLock(filepath, timeout, is_main_agent)
    if not await lock.acquire():
        raise TimeoutError(f"Could not acquire lock for {filepath}")
    try:
        yield lock
    finally:
        await lock.release()
