"""In-memory rate limiter untuk proteksi endpoint login dan form."""
import time
from typing import Dict, List, Tuple

class RateLimiter:
    _instance = None
    _attempts: Dict[str, List[float]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RateLimiter, cls).__new__(cls)
            cls._attempts = {}
        return cls._instance

    def record_failure(self, identifier: str) -> None:
        """Mencatat satu kegagalan login untuk identifier (email atau IP)."""
        now = time.time()
        if identifier not in self._attempts:
            self._attempts[identifier] = []
        self._attempts[identifier].append(now)

    def reset(self, identifier: str) -> None:
        """Mereset catatan kegagalan untuk identifier setelah login sukses."""
        if identifier in self._attempts:
            del self._attempts[identifier]

    def check_rate_limit(self, identifier: str, max_attempts: int = 5, window_seconds: int = 900) -> Tuple[bool, int]:
        """Cek apakah identifier melampaui batas percobaan.
        
        Returns:
            (is_allowed, seconds_until_reset)
        """
        now = time.time()
        if identifier not in self._attempts:
            return True, 0

        # Filter attempts within the time window
        recent_attempts = [t for t in self._attempts[identifier] if now - t < window_seconds]
        self._attempts[identifier] = recent_attempts

        if len(recent_attempts) >= max_attempts:
            oldest_relevant = recent_attempts[0]
            wait_seconds = int(window_seconds - (now - oldest_relevant))
            return False, max(1, wait_seconds)

        return True, 0

