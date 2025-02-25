import os
import logging
from datetime import datetime
from PyQt5.QtGui import QIcon

class IconCache:
    def __init__(self, max_size=1000, timeout=300):
        self.cache = {}
        self.max_size = max_size
        self.timeout = timeout  # in seconds
        
    def get(self, key):
        """Get an icon from the cache if it exists and is not expired."""
        if key in self.cache:
            icon, timestamp = self.cache[key]
            if (datetime.now() - timestamp).total_seconds() < self.timeout:
                return icon
        return None
        
    def put(self, key, icon):
        """Add or update an icon in the cache."""
        self.cache[key] = (icon, datetime.now())
        self.cleanup()
        
    def cleanup(self):
        """Remove old entries if cache exceeds max size."""
        if len(self.cache) > self.max_size:
            current_time = datetime.now()
            # Sort by timestamp and keep only newest entries
            sorted_cache = sorted(self.cache.items(), 
                               key=lambda x: x[1][1], reverse=True)
            self.cache = dict(sorted_cache[:self.max_size])
            
    def clear(self):
        """Clear the entire cache."""
        self.cache.clear()
        
    def __len__(self):
        return len(self.cache)