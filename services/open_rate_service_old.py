"""Service for calculating email open rates."""
from typing import List, Dict, Set
from services.convertkit_service import ConvertKitService


class OpenRateService:
    """Handles calculation of email open rates, including segmentation by tags."""

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
        total_opens = 0
        broadcast_count = 0

        for broadcast in broadcasts:
            stats = self.ck_service.get_broadcast_stats(broadcast['id'])
            if stats:
                recipients = stats.get('recipients', 0)
                opens = stats.get('opens', 0)

                total_recipients += recipients
                total_opens += opens
                broadcast_count += 1

        average_open_rate = round((total_opens / total_recipients * 100), 1) if total_recipients > 0 else 0

        return {
            'average_open_rate': average_open_rate,
            'total_broadcasts': broadcast_count,
            'total_recipients': total_recipients,
            'total_opens': total_opens
        }

    def calculate_open_rate_by_tag(self, start_date: str, end_date: str,
                                   tag_id: int, tag_name: str) -> Dict:
        """
        Calculate open rate for subscribers with a specific tag.

        This works by:
        1. Getting all broadcasts in the date range
        2. Getting all subscribers with the tag
        3. For each broadcast, counting how many tag subscribers opened it
        4. Calculating the open rate

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            tag_id: The tag ID to filter by
            tag_name: The tag name (for display)

        Returns:
            Dictionary with open rate statistics for this tag
        """
        print(f"\n=== Calculating Open Rate for Tag: {tag_name} (ID: {tag_id}) ===")

        # Get all broadcasts in date range
        broadcasts = self.ck_service.get_broadcasts(start_date, end_date)

        if not broadcasts:
            return {
                'tag_name': tag_name,
                'tag_id': tag_id,
                'average_open_rate': 0,
                'total_recipients': 0,
                'total_opens': 0
            }

        # Get all subscribers with this tag (created before end_date)
        # We need to get all tagged subscribers, not just from this period
        tagged_subscribers = self.ck_service.get_tagged_subscribers(
            tag_id, "2000-01-01", end_date  # Get all historical tagged subscribers
        )

        # Create a set of tagged subscriber IDs for fast lookup
        tagged_subscriber_ids: Set[int] = {sub['id'] for sub in tagged_subscribers}
        print(f"Found {len(tagged_subscriber_ids)} subscribers with tag {tag_name}")

        if not tagged_subscriber_ids:
            return {
                'tag_name': tag_name,
                'tag_id': tag_id,
                'average_open_rate': 0,
                'total_recipients': 0,
                'total_opens': 0
            }

        total_tag_recipients = 0
        total_tag_opens = 0

        # For each broadcast, count tagged subscribers who received and opened
        for i, broadcast in enumerate(broadcasts):
            print(f"Processing broadcast {i+1}/{len(broadcasts)}: {broadcast.get('subject', 'No subject')}")

            # Get all recipients for this broadcast
            all_recipients = self.ck_service.get_broadcast_subscribers(broadcast['id'])
            recipient_ids = {sub['id'] for sub in all_recipients}

            # Find intersection: which tagged subscribers received this broadcast
            tag_recipients_for_broadcast = recipient_ids & tagged_subscriber_ids
            total_tag_recipients += len(tag_recipients_for_broadcast)

            # Get all subscribers who opened this broadcast
            opened_subscribers = self.ck_service.get_broadcast_subscribers(
                broadcast['id'], filter_type='opened'
            )
            opened_ids = {sub['id'] for sub in opened_subscribers}

            # Find intersection: which tagged subscribers opened this broadcast
            tag_opens_for_broadcast = opened_ids & tagged_subscriber_ids
            total_tag_opens += len(tag_opens_for_broadcast)

            print(f"  - Tagged recipients: {len(tag_recipients_for_broadcast)}")
            print(f"  - Tagged opens: {len(tag_opens_for_broadcast)}")

        average_open_rate = round((total_tag_opens / total_tag_recipients * 100), 1) if total_tag_recipients > 0 else 0

        print(f"\nFinal stats for {tag_name}:")
        print(f"  - Total recipients: {total_tag_recipients}")
        print(f"  - Total opens: {total_tag_opens}")
        print(f"  - Open rate: {average_open_rate}%")

        return {
            'tag_name': tag_name,
            'tag_id': tag_id,
            'average_open_rate': average_open_rate,
            'total_recipients': total_tag_recipients,
            'total_opens': total_tag_opens
        }

    def calculate_open_rates_for_multiple_tags(self, start_date: str, end_date: str,
                                               tags: List[Dict[str, any]]) -> Dict:
        """
        Calculate open rates for multiple tags at once.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            tags: List of tag dictionaries with 'id' and 'name'

        Returns:
            Dictionary with overall stats and per-tag stats
        """
        overall_stats = self.calculate_overall_open_rate(start_date, end_date)

        tag_stats = []
        for tag in tags:
            if tag.get('id'):  # Only process if tag has an ID
                stats = self.calculate_open_rate_by_tag(
                    start_date, end_date, tag['id'], tag['name']
                )
                tag_stats.append(stats)

        return {
            'overall': overall_stats,
            'by_tag': tag_stats,
            'date_range': {
                'start_date': start_date,
                'end_date': end_date
            }
        }
