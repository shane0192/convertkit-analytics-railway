"""Simple background task processing without Celery - stores results in files."""
import json
import threading
import time
from datetime import datetime
import os


class BackgroundTask:
    """Simple background task runner that stores results in files."""

    RESULTS_DIR = "task_results"

    @classmethod
    def ensure_results_dir(cls):
        """Create results directory if it doesn't exist."""
        os.makedirs(cls.RESULTS_DIR, exist_ok=True)

    @classmethod
    def generate_task_id(cls, client_name):
        """Generate a unique task ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{client_name}_{timestamp}"

    @classmethod
    def save_task_status(cls, task_id, status, data=None, error=None):
        """Save task status to a JSON file."""
        cls.ensure_results_dir()
        result = {
            'task_id': task_id,
            'status': status,  # 'pending', 'processing', 'completed', 'failed'
            'updated_at': datetime.now().isoformat(),
            'data': data,
            'error': error
        }

        filepath = os.path.join(cls.RESULTS_DIR, f"{task_id}.json")
        with open(filepath, 'w') as f:
            json.dump(result, f)

    @classmethod
    def get_task_status(cls, task_id):
        """Get task status from file."""
        filepath = os.path.join(cls.RESULTS_DIR, f"{task_id}.json")
        if not os.path.exists(filepath):
            return None

        with open(filepath, 'r') as f:
            return json.load(f)

    @classmethod
    def run_open_rate_calculation(cls, task_id, ck_service, open_rate_service,
                                  start_date, end_date, tags):
        """
        Run open rate calculation in background thread.

        Args:
            task_id: Unique task identifier
            ck_service: ConvertKitService instance
            open_rate_service: OpenRateService instance
            start_date: Start date for calculation
            end_date: End date for calculation
            tags: List of tags to analyze
        """
        def _run():
            try:
                cls.save_task_status(task_id, 'processing')

                # Calculate open rates (this will take time)
                result = open_rate_service.calculate_open_rates_for_multiple_tags(
                    start_date, end_date, tags
                )

                cls.save_task_status(task_id, 'completed', data=result)

            except Exception as e:
                cls.save_task_status(task_id, 'failed', error=str(e))

        # Start in background thread
        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

        return task_id
