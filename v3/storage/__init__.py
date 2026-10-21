"""
v3.storage
Unified persistence and database adapter package.
"""
from v3.storage.persistence import StorageManager, get_storage_manager

__all__ = ["StorageManager", "get_storage_manager"]
