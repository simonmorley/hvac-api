"""
Caching utilities to reduce code duplication.

Provides simple in-memory cache with TTL support.
"""

from datetime import datetime, timedelta
from typing import Optional, TypeVar, Generic

T = TypeVar('T')


class SimpleCache(Generic[T]):
    """
    Simple in-memory cache with TTL.

    Thread-safe for async operations (single process).
    Not shared across multiple workers - use Redis for that.

    Example:
        cache = SimpleCache[float](ttl=timedelta(minutes=10))

        # Check cache
        if value := cache.get():
            return value

        # Cache miss - fetch and store
        value = await expensive_operation()
        cache.set(value)
        return value
    """

    def __init__(self, ttl: timedelta):
        """
        Initialize cache with TTL.

        Args:
            ttl: Time-to-live for cached values
        """
        self.ttl = ttl
        self._value: Optional[T] = None
        self._expires_at: Optional[datetime] = None

    def get(self) -> Optional[T]:
        """
        Get cached value if not expired.

        Returns:
            Cached value or None if expired/empty
        """
        # Guard clause: no value cached
        if self._value is None or self._expires_at is None:
            return None

        # Guard clause: expired
        if datetime.now() >= self._expires_at:
            return None

        return self._value

    def set(self, value: T) -> None:
        """
        Store value with TTL.

        Args:
            value: Value to cache
        """
        self._value = value
        self._expires_at = datetime.now() + self.ttl

    def clear(self) -> None:
        """Clear cache immediately."""
        self._value = None
        self._expires_at = None

    @property
    def is_valid(self) -> bool:
        """Check if cache has valid (non-expired) data."""
        return self.get() is not None
