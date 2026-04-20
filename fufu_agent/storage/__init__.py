"""Persistent storage layer (local JSON files)."""

from .file_store import FileStore, default_file_store

__all__ = ["FileStore", "default_file_store"]
