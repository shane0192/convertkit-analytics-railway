"""Service for generating subscriber growth reports."""
from datetime import datetime
from typing import Dict, Optional
from services.convertkit_service import ConvertKitService
from services.open_rate_service import OpenRateService
from utils.date_utils import calculate_period_dates
from utils.constants import BEFORE_PERIOD_DAYS, AFTER_PERIOD_START_DAYS, AFTER_PERIOD_DAYS


class ReportService:
    """Handles generation of subscriber growth and engagement reports."""

    def __init__(self, convertkit_service: ConvertKitService):
        """
        Initialize the report service.

        Args:
            convertkit_service: Instance of ConvertKitService for API calls
        """
        self.ck_service = convertkit_service
        self.open_rate_service = OpenRateService(convertkit_service)

    def generate_subscriber_report(self, facebook_tag: int, creator_tag: int,
                                  sparkloop_tag: int, start_date: str, end_date: str,
                                  current_total: int, client_data: Dict) -> Optional[Dict]:
        """
        Generate a complete subscriber growth report.

        Args:
            facebook_tag: Facebook ads tag ID
            creator_tag: Creator network tag ID
            sparkloop_tag: SparkLoop tag ID
            start_date: Report start date in YYYY-MM-DD format
            end_date: Report end date in YYYY-MM-DD format
            current_total: Current total subscriber count
            client_data: Client-specific data (paperboy_start_date, initial_subscriber_count)

        Returns:
            Dictionary with complete report data or None if error
        """
        try:
            # Get total subscribers for the recent period using count_only
            total_count = self.ck_service.get_subscribers(start_date, end_date, count_only=True)

            # Get tagged subscribers
            facebook_subscribers = self.ck_service.get_tagged_subscribers(
                facebook_tag, start_date, end_date
            )
            creator_subscribers = self.ck_service.get_tagged_subscribers(
                creator_tag, start_date, end_date
            )
            sparkloop_subscribers = self.ck_service.get_tagged_subscribers(
                sparkloop_tag, start_date, end_date
            )

            # Calculate counts
            facebook_count = len(facebook_subscribers)
            creator_count = len(creator_subscribers)
            sparkloop_count = len(sparkloop_subscribers)

            # Calculate organic subscribers
            attributed_count = facebook_count + creator_count + sparkloop_count
            organic_count = total_count - attributed_count

            # Parse client data
            paperboy_start_date = datetime.strptime(
                client_data.get('paperboy_start_date'), '%Y-%m-%d'
            )
            initial_count = client_data.get('initial_subscriber_count', 0)

            # Calculate the before/after periods
            periods = calculate_period_dates(
                paperboy_start_date,
                BEFORE_PERIOD_DAYS,
                AFTER_PERIOD_START_DAYS,
                AFTER_PERIOD_DAYS
            )

            print(f"\n=== Period Calculations ===")
            print(f"Before period: {periods['before_start']} to {periods['before_end']}")
            print(f"After period: {periods['after_start']} to {periods['after_end']}")

            # Get subscribers for before/after periods (using count_only)
            daily_average_before = round(
                self.ck_service.get_subscribers(
                    periods['before_start'],
                    periods['before_end'],
                    count_only=True
                ) / periods['before_days'], 1
            )

            daily_average_after = round(
                self.ck_service.get_subscribers(
                    periods['after_start'],
                    periods['after_end'],
                    count_only=True
                ) / periods['after_days'], 1
            )

            # Calculate total growth since Paperboy
            total_growth = current_total - initial_count
            growth_rate = round((total_growth / initial_count * 100), 1) if initial_count > 0 else 0

            # Calculate percentages (rounded to 1 decimal place)
            facebook_percent = round((facebook_count / total_count * 100), 1) if total_count > 0 else 0
            creator_percent = round((creator_count / total_count * 100), 1) if total_count > 0 else 0
            sparkloop_percent = round((sparkloop_count / total_count * 100), 1) if total_count > 0 else 0
            organic_percent = round((organic_count / total_count * 100), 1) if total_count > 0 else 0

            # Calculate paid growth
            paid_count = facebook_count + sparkloop_count
            paid_percent = round((paid_count / total_count * 100), 1) if total_count > 0 else 0

            # Get monthly growth data (disabled for now - causes timeouts on large datasets)
            # monthly_growth = self._generate_monthly_growth_data(paperboy_start_date)
            monthly_growth = []  # Temporarily disabled to prevent worker timeout

            return {
                'start_date': start_date,
                'end_date': end_date,
                'total_subscribers': total_count,
                'facebook_subscribers': facebook_count,
                'facebook_percent': facebook_percent,
                'creator_subscribers': creator_count,
                'creator_percent': creator_percent,
                'sparkloop_subscribers': sparkloop_count,
                'sparkloop_percent': sparkloop_percent,
                'organic_subscribers': organic_count,
                'organic_percent': organic_percent,
                'total_growth': f"{total_growth:,}",
                'growth_rate': growth_rate,
                'paperboy_start_date': paperboy_start_date.strftime('%Y-%m-%d'),
                'daily_average_before': daily_average_before,
                'daily_average_after': daily_average_after,
                'before_period': f"{periods['before_start']} to {periods['before_end']}",
                'after_period': f"{periods['after_start']} to {periods['after_end']}",
                'paid_growth_percent': paid_percent,
                'paid_subscribers': paid_count,
                'monthly_growth': monthly_growth
            }

        except Exception as e:
            print(f"Error generating report: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return None

    def generate_report_with_open_rates(self, facebook_tag: int, creator_tag: int,
                                       sparkloop_tag: int, start_date: str, end_date: str,
                                       current_total: int, client_data: Dict) -> Optional[Dict]:
        """
        Generate a complete report including subscriber growth AND open rates.

        Args:
            facebook_tag: Facebook ads tag ID
            creator_tag: Creator network tag ID
            sparkloop_tag: SparkLoop tag ID
            start_date: Report start date in YYYY-MM-DD format
            end_date: Report end date in YYYY-MM-DD format
            current_total: Current total subscriber count
            client_data: Client-specific data

        Returns:
            Dictionary with complete report including open rates or None if error
        """
        # First get the standard subscriber report
        report = self.generate_subscriber_report(
            facebook_tag, creator_tag, sparkloop_tag,
            start_date, end_date, current_total, client_data
        )

        if not report:
            return None

        # Now add open rate data
        print("\n=== Calculating Open Rates ===")

        tags_to_analyze = []
        if facebook_tag:
            tags_to_analyze.append({'id': facebook_tag, 'name': 'Facebook Ads'})
        if creator_tag:
            tags_to_analyze.append({'id': creator_tag, 'name': 'Creator Network'})
        if sparkloop_tag:
            tags_to_analyze.append({'id': sparkloop_tag, 'name': 'SparkLoop'})

        open_rate_stats = self.open_rate_service.calculate_open_rates_for_multiple_tags(
            start_date, end_date, tags_to_analyze
        )

        # Add open rate data to report
        report['open_rates'] = open_rate_stats

        return report

    def _generate_monthly_growth_data(self, paperboy_start_date: datetime) -> list:
        """
        Generate monthly subscriber counts before and after Paperboy start date.

        Args:
            paperboy_start_date: The date Paperboy started working with client

        Returns:
            List of monthly data points
        """
        try:
            from datetime import timedelta

            # Get 3 months before Paperboy
            start_date = paperboy_start_date - timedelta(days=90)
            current_date = datetime.now()

            monthly_data = []
            current_month = start_date.replace(day=1)

            # Generate all month start dates until current date
            while current_month <= current_date:
                count = self.ck_service.get_subscriber_count_at_date(
                    current_month.strftime('%Y-%m-%d')
                )
                monthly_data.append({
                    'date': current_month.strftime('%b %d, %y'),
                    'count': count,
                    'is_paperboy': current_month >= paperboy_start_date
                })
                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)

            return monthly_data

        except Exception as e:
            print(f"Error generating monthly growth data: {str(e)}")
            return []
