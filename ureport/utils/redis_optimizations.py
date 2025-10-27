"""
Redis-based performance optimizations for UReport database I/O reduction.

This module provides Redis-backed solutions to reduce database load by:
1. Buffering counter operations
2. Caching expensive queries  
3. Deduplicating operations
4. Rate limiting database writes
"""

import json
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from django.core.cache import cache
from django.db import transaction
from redis import Redis

logger = logging.getLogger(__name__)


class RedisCounterBuffer:
    """
    Buffers counter increments in Redis and flushes to database periodically.
    Reduces database I/O by batching counter operations.
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.buffer_key = "ureport:counter_buffer"
        self.flush_lock_key = "ureport:counter_flush_lock"
    
    def increment(self, org_id: int, counter_type: str, count: int = 1):
        """Buffer a counter increment in Redis instead of hitting database immediately."""
        counter_key = f"{org_id}:{counter_type}"
        self.redis.hincrby(self.buffer_key, counter_key, count)
        
        # Optional: Set expiration on the hash to prevent infinite growth
        self.redis.expire(self.buffer_key, 3600)  # 1 hour TTL
    
    def flush_to_database(self):
        """Flush all buffered counters to database in batch operation."""
        with self.redis.lock(self.flush_lock_key, timeout=30):
            # Get all buffered counters
            buffered_counters = self.redis.hgetall(self.buffer_key)
            
            if not buffered_counters:
                return 0
            
            # Prepare batch insert data
            counter_records = []
            for key, count in buffered_counters.items():
                org_id, counter_type = key.decode().split(':', 1)
                counter_records.append({
                    'org_id': int(org_id),
                    'type': counter_type,
                    'count': int(count)
                })
            
            # Batch insert to database
            with transaction.atomic():
                from ureport.contacts.models import ReportersCounter
                
                # Use bulk_create for better performance
                ReportersCounter.objects.bulk_create([
                    ReportersCounter(**record) for record in counter_records
                ], batch_size=1000)
            
            # Clear buffer after successful write
            self.redis.delete(self.buffer_key)
            
            logger.info(f"Flushed {len(counter_records)} counters to database")
            return len(counter_records)


class RedisQueryCache:
    """
    Caches expensive database queries in Redis to reduce repetitive I/O.
    """
    
    def __init__(self, redis_client: Redis, default_ttl: int = 300):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.cache_prefix = "ureport:query_cache"
    
    def get_or_set(self, cache_key: str, query_func, ttl: Optional[int] = None):
        """Get from cache or execute query function and cache result."""
        full_key = f"{self.cache_prefix}:{cache_key}"
        
        # Try to get from cache first
        cached_data = self.redis.get(full_key)
        if cached_data:
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in cache key {full_key}")
        
        # Execute query and cache result
        result = query_func()
        cache_ttl = ttl or self.default_ttl
        
        try:
            self.redis.setex(full_key, cache_ttl, json.dumps(result, default=str))
        except (TypeError, ValueError) as e:
            logger.warning(f"Cannot serialize result for caching: {e}")
        
        return result
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all cache keys matching a pattern."""
        full_pattern = f"{self.cache_prefix}:{pattern}"
        keys = self.redis.keys(full_pattern)
        if keys:
            self.redis.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache keys matching {pattern}")


class RedisDeduplicator:
    """
    Prevents duplicate operations within time windows using Redis sets.
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.dedup_prefix = "ureport:dedup"
    
    def should_process(self, operation_id: str, window_seconds: int = 3600) -> bool:
        """
        Check if operation should be processed or if it's a duplicate.
        Returns True if should process, False if duplicate.
        """
        key = f"{self.dedup_prefix}:{operation_id}"
        
        # Use SET with NX (only set if key doesn't exist)
        result = self.redis.set(key, "1", nx=True, ex=window_seconds)
        return result is not None
    
    def mark_processed(self, operation_id: str, window_seconds: int = 3600):
        """Mark an operation as processed."""
        key = f"{self.dedup_prefix}:{operation_id}"
        self.redis.setex(key, window_seconds, "1")


# Celery task for periodic counter flushing
def flush_redis_counters():
    """Celery task to flush Redis-buffered counters to database."""
    from django.conf import settings
    
    redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
    buffer = RedisCounterBuffer(redis_client)
    
    try:
        flushed_count = buffer.flush_to_database()
        logger.info(f"Redis counter flush completed: {flushed_count} records")
    except Exception as e:
        logger.error(f"Redis counter flush failed: {e}")


# Usage examples:

def optimized_contact_counter_increment(contact, add=True):
    """
    Optimized version of contact counter increment using Redis buffering.
    """
    redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
    buffer = RedisCounterBuffer(redis_client)
    
    count = 1 if add else -1
    
    # Buffer all counter increments instead of immediate database writes
    if contact.org_id:
        buffer.increment(contact.org_id, 'total-reporters', count)
        
        if contact.gender:
            buffer.increment(contact.org_id, f'gender:{contact.gender.lower()}', count)
        
        if contact.born:
            buffer.increment(contact.org_id, f'born:{contact.born}', count)
        
        # ... other counter types


def get_cached_org_stats(org_id: int):
    """
    Get organization statistics with Redis caching.
    """
    redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
    cache = RedisQueryCache(redis_client, ttl=600)  # 10 minutes
    
    def expensive_stats_query():
        from ureport.contacts.models import ReportersCounter
        return ReportersCounter.get_counts(org_id)
    
    return cache.get_or_set(f"org_stats:{org_id}", expensive_stats_query)


def deduplicated_contact_activity(contact_id: str, poll_id: str):
    """
    Process contact activity only if not already processed recently.
    """
    redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
    deduplicator = RedisDeduplicator(redis_client)
    
    operation_id = f"contact_activity:{contact_id}:{poll_id}"
    
    if deduplicator.should_process(operation_id, window_seconds=1800):  # 30 minutes
        # Process the activity
        process_contact_activity(contact_id, poll_id)
    else:
        logger.info(f"Skipping duplicate contact activity: {operation_id}")