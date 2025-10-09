"""
Response caching to reduce AI API costs
Caches common queries and their responses.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from config.ai_config import AI_CONFIG


class ResponseCache:
    """Cache for AI responses to reduce costs."""
    
    def __init__(self, cache_file: str = "ai_cache.json"):
        """
        Initialize cache.
        
        Args:
            cache_file: Path to cache file
        """
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.enabled = AI_CONFIG.get('cache_responses', True)
        self.duration = AI_CONFIG.get('cache_duration', 3600)  # seconds
    
    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass  # Silently fail
    
    def _make_key(self, message: str, system_prompt: str = None) -> str:
        """
        Create a cache key from message and system prompt.
        
        Args:
            message: User message
            system_prompt: System prompt
            
        Returns:
            Hash key for cache lookup
        """
        combined = f"{system_prompt or ''}|||{message}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _is_expired(self, timestamp: str) -> bool:
        """Check if cache entry is expired."""
        try:
            cached_time = datetime.fromisoformat(timestamp)
            expiry_time = cached_time + timedelta(seconds=self.duration)
            return datetime.now() > expiry_time
        except Exception:
            return True
    
    def get(self, message: str, system_prompt: str = None) -> Optional[Dict[str, Any]]:
        """
        Get cached response if available and not expired.
        
        Args:
            message: User message
            system_prompt: System prompt
            
        Returns:
            Cached response dict or None
        """
        if not self.enabled:
            return None
        
        key = self._make_key(message, system_prompt)
        
        if key in self.cache:
            entry = self.cache[key]
            
            if not self._is_expired(entry['timestamp']):
                # Update access time
                entry['last_accessed'] = datetime.now().isoformat()
                entry['access_count'] = entry.get('access_count', 0) + 1
                self._save_cache()
                
                return entry['response']
        
        return None
    
    def set(self, message: str, response: Dict[str, Any], system_prompt: str = None):
        """
        Cache a response.
        
        Args:
            message: User message
            response: AI response dict
            system_prompt: System prompt
        """
        if not self.enabled:
            return
        
        key = self._make_key(message, system_prompt)
        
        self.cache[key] = {
            'timestamp': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat(),
            'access_count': 1,
            'message': message,
            'response': response
        }
        
        self._save_cache()
    
    def clear_expired(self):
        """Remove expired entries from cache."""
        expired_keys = [
            key for key, entry in self.cache.items()
            if self._is_expired(entry['timestamp'])
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            self._save_cache()
        
        return len(expired_keys)
    
    def clear_all(self):
        """Clear entire cache."""
        self.cache = {}
        self._save_cache()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_entries = len(self.cache)
        expired_count = sum(1 for entry in self.cache.values() 
                          if self._is_expired(entry['timestamp']))
        active_count = total_entries - expired_count
        
        total_accesses = sum(entry.get('access_count', 0) 
                           for entry in self.cache.values())
        
        # Calculate estimated savings
        estimated_savings = 0
        for entry in self.cache.values():
            access_count = entry.get('access_count', 0)
            if access_count > 1:
                # Saved (access_count - 1) API calls
                response = entry.get('response', {})
                cost = response.get('cost', 0)
                estimated_savings += cost * (access_count - 1)
        
        return {
            'total_entries': total_entries,
            'active_entries': active_count,
            'expired_entries': expired_count,
            'total_accesses': total_accesses,
            'estimated_savings': estimated_savings,
            'enabled': self.enabled,
            'duration_hours': self.duration / 3600
        }
    
    def get_summary(self) -> str:
        """Get human-readable cache summary."""
        stats = self.get_stats()
        
        summary = f"""
Cache Statistics:
----------------
Status: {'Enabled' if stats['enabled'] else 'Disabled'}
Cache Duration: {stats['duration_hours']:.1f} hours

Entries:
  Total: {stats['total_entries']}
  Active: {stats['active_entries']}
  Expired: {stats['expired_entries']}

Performance:
  Total Cache Hits: {stats['total_accesses']}
  Estimated Cost Savings: ${stats['estimated_savings']:.4f}
"""
        return summary.strip()


# Global cache instance
_cache = None

def get_cache() -> ResponseCache:
    """Get global cache instance."""
    global _cache
    if _cache is None:
        _cache = ResponseCache()
    return _cache


if __name__ == "__main__":
    # Test cache
    cache = ResponseCache()
    
    print("Cache Statistics:")
    print(cache.get_summary())
    
    # Test set/get
    test_response = {
        'content': 'Test response',
        'cost': 0.01,
        'usage': {'input_tokens': 100, 'output_tokens': 50}
    }
    
    cache.set("Test message", test_response, "Test system prompt")
    
    # Try to get it back
    cached = cache.get("Test message", "Test system prompt")
    
    if cached:
        print("\n✓ Cache test successful")
        print(f"Cached content: {cached['content']}")
    else:
        print("\n✗ Cache test failed")
