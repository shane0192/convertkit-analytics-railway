"""Optimized service for calculating email open rates using broadcast stats API."""
from typing import List, Dict
from services.convertkit_service import ConvertKitService


class OpenRateService:
    """Handles calculation of email open rates using efficient API calls."""

    def __init__(self, convertkit_service: ConvertKitService):
        """
        Initialize the open rate service.

        Args:
            convertkit_service: Instance of ConvertKitService for API calls
        """
        self.ck_service = convertkit_service

    def calculate_overall_open_rate(self, start_date: str, end_date: str) -> Dict:
        """
        Calculate overall open rate for all broadcasts in a date range.
        Uses broadcast stats API - much faster than fetching all subscribers!

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dictionary with open rate statistics
        """
        broadcasts = self.ck_service.get_broadcasts(start_date, end_date)

        if not broadcasts:
            return {
                'average_open_rate': 0,
                'total_broadcasts': 0,
                'total_recipients': 0,
                'total_opens': 0
            }

        total_recipients = 0
        total_unique_opens = 0
        broadcast_count = 0

        for broadcast in broadcasts:
            stats = self.ck_service.get_broadcast_stats(broadcast['id'])
            if stats:
                # Use the stats from the API
                recipients = stats.get('recipients', 0)
                # Use unique_opens if available, otherwise fall back to opens
                opens = stats.get('unique_opens', stats.get('opens', 0))

                total_recipients += recipients
                total_unique_opens += opens
                broadcast_count += 1

        average_open_rate = round((total_unique_opens / total_recipients * 100), 1) if total_recipients > 0 else 0

        return {
            'average_open_rate': average_open_rate,
            'total_broadcasts': broadcast_count,
            'total_recipients': total_recipients,
            'total_opens': total_unique_opens
        }

    def calculate_open_rates_for_tags(self, start_date: str, end_date: str,
                                     tags: List[Dict[str, any]]) -> Dict:
        """
        Calculate open rates - overall stats only.

        Note: Per-tag open rates are NOT available via Kit API without fetching
        all subscribers. We return overall stats and a note explaining this.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            tags: List of tag dictionaries with 'id' and 'name'

        Returns:
            Dictionary with overall stats and explanation
        """
        overall_stats = self.calculate_overall_open_rate(start_date, end_date)

        # For now, we can't calculate per-tag open rates efficiently
        # The Kit API doesn't provide this data directly
        tag_stats = [
            {
                'tag_name': tag['name'],
                'tag_id': tag['id'],
                'note': 'Per-tag open rates require fetching all subscribers. Use overall rate as estimate.',
                'average_open_rate': overall_stats['average_open_rate'],  # Use overall as estimate
                'total_recipients': 0,
                'total_opens': 0
            }
            for tag in tags if tag.get('id')
        ]

        return {
            'overall': overall_stats,
            'by_tag': tag_stats,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            },
            'note': 'Kit API does not provide per-tag open rates. Showing overall open rate for all broadcasts.'
        }
