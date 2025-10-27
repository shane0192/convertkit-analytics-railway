"""Celery task for calculating open rates by tag in the background."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery_app import celery_app
from services.convertkit_service import ConvertKitService
from services.open_rate_service import OpenRateService


@celery_app.task(bind=True, name='tasks.calculate_open_rates_by_tag')
def calculate_open_rates_by_tag(self, api_key, base_url, start_date, end_date, tags):
    """
    Background task to calculate open rates segmented by tags.

    Args:
        self: Celery task instance
        api_key: ConvertKit API key
        base_url: ConvertKit API base URL
        start_date: Start date for report
        end_date: End date for report
        tags: List of tag dicts with 'id' and 'name'

    Returns:
        Dict with open rate statistics
    """
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={'status': 'Initializing services...'})

        # Initialize services
        ck_service = ConvertKitService(api_key, base_url)
        open_rate_service = OpenRateService(ck_service)

        # Calculate open rates
        self.update_state(state='PROGRESS', meta={'status': 'Calculating open rates...'})

        result = open_rate_service.calculate_open_rates_for_multiple_tags(
            start_date, end_date, tags
        )

        return {
            'status': 'completed',
            'data': result
        }

    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
