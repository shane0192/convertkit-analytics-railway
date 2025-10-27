"""Service for interacting with the ConvertKit API."""
import requests
import time
from typing import List, Dict, Optional, Any
from utils.constants import (
    PER_PAGE_PARAM, MAX_RETRIES, RETRY_DELAY,
    TAG_VARIATIONS, DEFAULT_FACEBOOK_TAG, DEFAULT_CREATOR_TAG, DEFAULT_SPARKLOOP_TAG
)


class ConvertKitService:
    """Handles all interactions with the ConvertKit API."""

    def __init__(self, api_key: str, base_url: str = "https://api.kit.com/v4/"):
        """
        Initialize the ConvertKit service.

        Args:
            api_key: ConvertKit API access token
            base_url: Base URL for the API (default: Kit v4 API)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {'Authorization': f'Bearer {api_key}'}

    def _rate_limited_request(self, url: str, params: Optional[Dict] = None) -> requests.Response:
        """
        Make a rate-limited request to the ConvertKit API with retry logic.

        Args:
            url: The API endpoint URL
            params: Optional query parameters

        Returns:
            Response object from the API
        """
        for attempt in range(MAX_RETRIES):
            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code == 429:  # Too Many Requests
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue

            return response

        return response  # Return last response if all retries failed

    def get_subscribers(self, start_date: str, end_date: str, count_only: bool = False) -> Any:
        """
        Get all subscribers between two dates using cursor-based pagination.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            count_only: If True, only return the count, not the full list

        Returns:
            Total count if count_only=True, otherwise list of subscribers
        """
        url = f"{self.base_url}subscribers"
        params = {
            'created_after': f"{start_date}T00:00:00Z",
            'created_before': f"{end_date}T23:59:59Z",
            'include_total_count': 'true'
        }

        print(f"\n=== Getting Subscribers for Date Range ===")
        print(f"Start Date: {start_date}")
        print(f"End Date: {end_date}")

        # If we only need the count, use minimal pagination
        if count_only:
            params['per_page'] = 1
            response = self._rate_limited_request(url, params=params)
            if response.status_code == 200:
                data = response.json()
                total_count = data.get('pagination', {}).get('total_count', 0)
                print(f"Total count from API: {total_count}")
                return total_count
            return 0

        # If we need the full subscriber data, proceed with pagination
        params['per_page'] = PER_PAGE_PARAM
        params['sort_order'] = 'desc'
        subscribers = []

        # Get first page
        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            current_subscribers = data.get('subscribers', [])
            subscribers.extend(current_subscribers)
            total_count = data.get('pagination', {}).get('total_count', 0)
            print(f"First page count: {len(current_subscribers)}")
            print(f"Total count from pagination: {total_count}")

            # Process subsequent pages
            while data.get('pagination', {}).get('has_next_page'):
                params['after'] = data['pagination']['end_cursor']
                response = self._rate_limited_request(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    current_subscribers = data.get('subscribers', [])
                    subscribers.extend(current_subscribers)
                    print(f"Page count: {len(current_subscribers)}")
                else:
                    print(f"Error getting page: {response.text}")
                    break

        return subscribers

    def get_tagged_subscribers(self, tag_id: int, start_date: str, end_date: str) -> List[Dict]:
        """
        Get subscribers with a specific tag within a date range.

        Args:
            tag_id: The tag ID to filter by
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of tagged subscribers
        """
        if not tag_id:
            return []

        url = f"{self.base_url}tags/{tag_id}/subscribers"
        params = {
            'created_after': f"{start_date}T00:00:00Z",
            'created_before': f"{end_date}T23:59:59Z",
            'per_page': PER_PAGE_PARAM,
            'sort_order': 'desc'
        }

        tagged_subscribers = []

        # Get first page
        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            tagged_subscribers.extend(data.get('subscribers', []))
            print(f"First page count for tag {tag_id}: {len(tagged_subscribers)}")

            # Process subsequent pages
            while data.get('pagination', {}).get('has_next_page'):
                params['after'] = data['pagination']['end_cursor']
                response = self._rate_limited_request(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    current_subscribers = data.get('subscribers', [])
                    tagged_subscribers.extend(current_subscribers)
                else:
                    print(f"Error getting page: {response.text}")
                    break

            print(f"Total tagged subscribers for tag {tag_id}: {len(tagged_subscribers)}")

        return tagged_subscribers

    def get_all_tags(self) -> Dict[str, Any]:
        """
        Get all tags from ConvertKit.

        Returns:
            Dictionary with all_tags list and suggested tags
        """
        try:
            response = self._rate_limited_request(f'{self.base_url}tags')

            if response.status_code == 200:
                tags = response.json().get('tags', [])

                # Find suggested tags
                facebook_tag = self._find_closest_tag(tags, 'facebook')
                creator_tag = self._find_closest_tag(tags, 'creator')
                sparkloop_tag = self._find_closest_tag(tags, 'sparkloop')

                return {
                    'all_tags': tags,
                    'suggested': {
                        'facebook': facebook_tag,
                        'creator': creator_tag,
                        'sparkloop': sparkloop_tag
                    }
                }

            return {'error': 'Failed to fetch tags', 'all_tags': [], 'suggested': {}}

        except Exception as e:
            print(f"Error getting tags: {str(e)}")
            return {'error': str(e), 'all_tags': [], 'suggested': {}}

    def _find_closest_tag(self, tags: List[Dict], tag_type: str) -> Optional[int]:
        """
        Find the closest matching tag from common variations.

        Args:
            tags: List of tag dictionaries from ConvertKit
            tag_type: Type of tag to find ('facebook', 'creator', or 'sparkloop')

        Returns:
            Tag ID if found, otherwise default tag ID
        """
        print(f"\n=== Finding {tag_type} tag ===")

        # Convert all tag names to lowercase for comparison
        tag_map = {tag['name'].lower(): tag for tag in tags}

        # Check each variation against the tags
        for variation in TAG_VARIATIONS[tag_type]:
            for tag_name, tag in tag_map.items():
                if variation in tag_name.lower():
                    print(f"Found match! Tag: {tag['name']} (ID: {tag['id']})")
                    return tag['id']

        print("No match found, using default tag")
        # Return default tags if no match found
        default_tags = {
            'facebook': DEFAULT_FACEBOOK_TAG,
            'creator': DEFAULT_CREATOR_TAG,
            'sparkloop': DEFAULT_SPARKLOOP_TAG
        }
        return default_tags.get(tag_type)

    def get_current_total_subscribers(self) -> int:
        """
        Get the current total subscriber count.

        Returns:
            Total number of subscribers
        """
        url = f"{self.base_url}subscribers"
        params = {
            'include_total_count': 'true',
            'per_page': 1  # Minimize data transfer since we only need the count
        }

        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            total_count = data.get('pagination', {}).get('total_count', 0)
            print(f"Current total subscribers: {total_count}")
            return total_count
        return 0

    def get_subscriber_count_at_date(self, date: str) -> int:
        """
        Get total subscriber count up to a specific date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Total subscriber count at that date
        """
        url = f"{self.base_url}subscribers"
        params = {
            'created_before': f"{date}T23:59:59Z",
            'include_total_count': 'true',
            'per_page': 1
        }

        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return data.get('pagination', {}).get('total_count', 0)
        return 0

    def get_broadcasts(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Get all broadcasts sent within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of broadcast dictionaries
        """
        url = f"{self.base_url}broadcasts"
        params = {
            'per_page': PER_PAGE_PARAM,
            'sort_order': 'desc'
        }

        broadcasts = []

        # Get first page
        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            all_broadcasts = data.get('broadcasts', [])

            # Filter by date range
            from dateutil import parser as date_parser
            from datetime import datetime

            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')

            for broadcast in all_broadcasts:
                # Parse the published_at date
                published_at = broadcast.get('published_at')
                if published_at:
                    broadcast_dt = date_parser.parse(published_at).replace(tzinfo=None)
                    if start_dt <= broadcast_dt <= end_dt:
                        broadcasts.append(broadcast)

            # Process subsequent pages
            while data.get('pagination', {}).get('has_next_page'):
                params['after'] = data['pagination']['end_cursor']
                response = self._rate_limited_request(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    all_broadcasts = data.get('broadcasts', [])

                    for broadcast in all_broadcasts:
                        published_at = broadcast.get('published_at')
                        if published_at:
                            broadcast_dt = date_parser.parse(published_at).replace(tzinfo=None)
                            if start_dt <= broadcast_dt <= end_dt:
                                broadcasts.append(broadcast)
                else:
                    print(f"Error getting broadcasts page: {response.text}")
                    break

        print(f"Found {len(broadcasts)} broadcasts in date range")
        return broadcasts

    def get_broadcast_stats(self, broadcast_id: int) -> Optional[Dict]:
        """
        Get statistics for a specific broadcast.

        Args:
            broadcast_id: The broadcast ID

        Returns:
            Dictionary with stats (recipients, open_rate, click_rate, etc.) or None
        """
        url = f"{self.base_url}broadcasts/{broadcast_id}/stats"

        response = self._rate_limited_request(url)
        if response.status_code == 200:
            return response.json().get('broadcast', {}).get('stats', {})

        print(f"Error getting broadcast stats: {response.text}")
        return None

    def get_broadcast_subscribers(self, broadcast_id: int, filter_type: str = None) -> List[Dict]:
        """
        Get subscribers who received/opened/clicked a broadcast.

        Args:
            broadcast_id: The broadcast ID
            filter_type: Optional filter ('opened', 'clicked', 'unsubscribed')

        Returns:
            List of subscriber dictionaries
        """
        url = f"{self.base_url}broadcasts/{broadcast_id}/subscribers"
        params = {'per_page': PER_PAGE_PARAM}

        if filter_type:
            params['subscriber_state'] = filter_type
            print(f"DEBUG: Fetching broadcast {broadcast_id} subscribers with filter '{filter_type}'")

        subscribers = []

        # Get first page
        response = self._rate_limited_request(url, params=params)
        if response.status_code == 200:
            data = response.json()
            subscribers.extend(data.get('subscribers', []))
            print(f"DEBUG: First page returned {len(data.get('subscribers', []))} subscribers")

            # Process subsequent pages
            while data.get('pagination', {}).get('has_next_page'):
                params['after'] = data['pagination']['end_cursor']
                response = self._rate_limited_request(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    subscribers.extend(data.get('subscribers', []))
                else:
                    print(f"Error getting broadcast subscribers page: {response.text}")
                    break
        else:
            print(f"ERROR: Failed to fetch broadcast subscribers. Status: {response.status_code}, Response: {response.text}")

        print(f"DEBUG: Total subscribers fetched for broadcast {broadcast_id} with filter '{filter_type}': {len(subscribers)}")
        return subscribers
