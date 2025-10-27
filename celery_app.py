"""Celery configuration for background tasks."""
from celery import Celery
import os

# Configure Celery to use Redis (Railway provides Redis)
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'convertkit_analytics',
    broker=redis_url,
    backend=redis_url,
    include=['tasks.open_rate_tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes max
    result_expires=3600,  # Results expire after 1 hour
)
