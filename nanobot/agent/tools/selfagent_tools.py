"""
SelfAgent专用工具 - 带文件锁的文件操作
These tools wrap standard filesystem tools with locking for safe concurrent access
"""

from pathlib import Path
from nanobot.agent.tools.filesystem import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListDirTool,
)
from nanobot.utils.file_lock import file_lock


class LockedReadFileTool(ReadFileTool):
    """File reading tool with locking (reader priority)"""
    
    def __init__(self, allowed_dir: Path, is_main_agent: bool = False):
        super().__init__(allowed_dir)
        self.is_main_agent = is_main_agent
    
    async def execute(self, path: str, limit: int = 1000, offset: int = 1) -> str:
        filepath = self._resolve_path(path)
        async with file_lock(filepath, timeout=5.0, is_main_agent=self.is_main_agent):
            return await super().execute(path, limit=limit, offset=offset)


class LockedWriteFileTool(WriteFileTool):
    """File writing tool with locking (exclusive lock)"""
    
    def __init__(self, allowed_dir: Path, is_main_agent: bool = False):
        super().__init__(allowed_dir)
        self.is_main_agent = is_main_agent
    
    async def execute(self, path: str, content: str) -> str:
        filepath = self._resolve_path(path)
        async with file_lock(filepath, timeout=10.0, is_main_agent=self.is_main_agent):
            # If writing to MEMORY.md, ensure content starts with "潜意识:"
            if "memory" in str(filepath).lower() and "MEMORY.md" in str(filepath):
                if not content.strip().startswith("潜意识:"):
                    content = f"潜意识: {content}"
            
            return await super().execute(path, content)


class LockedEditFileTool(EditFileTool):
    """File editing tool with locking (exclusive lock)"""
    
    def __init__(self, allowed_dir: Path, is_main_agent: bool = False):
        super().__init__(allowed_dir)
        self.is_main_agent = is_main_agent
    
    async def execute(self, path: str, old_string: str, new_string: str) -> str:
        filepath = self._resolve_path(path)
        async with file_lock(filepath, timeout=10.0, is_main_agent=self.is_main_agent):
            return await super().execute(path, old_string, new_string)


class LockedListDirTool(ListDirTool):
    """Directory listing tool with locking (reader priority)"""
    
    def __init__(self, allowed_dir: Path, is_main_agent: bool = False):
        super().__init__(allowed_dir)
        self.is_main_agent = is_main_agent
    
    async def execute(self, path: str) -> str:
        dirpath = self._resolve_path(path)
        async with file_lock(dirpath, timeout=5.0, is_main_agent=self.is_main_agent):
            return await super().execute(path)
