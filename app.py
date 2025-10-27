"""
ConvertKit Analytics App - Refactored
Main Flask application with route handlers only.
"""
import json
import os
import sys
import random
import string
import traceback
from datetime import timedelta
from urllib.parse import urlencode

# Add current directory to Python path for Railway deployment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for, jsonify)
from requests_oauthlib import OAuth2Session

# Import our new services
from services.convertkit_service import ConvertKitService
from services.report_service import ReportService
from services.open_rate_service import OpenRateService
from services.background_tasks import BackgroundTask
from utils.date_utils import get_default_date_range

# Configuration
try:
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        API_KEY = os.getenv('CONVERTKIT_API_KEY', config.get("api_key"))
        BASE_URL = os.getenv('CONVERTKIT_BASE_URL', config.get("base_url"))
except FileNotFoundError:
    API_KEY = os.getenv('CONVERTKIT_API_KEY')
    BASE_URL = os.getenv('CONVERTKIT_BASE_URL', 'https://api.kit.com/v4/')

REDIRECT_URI = os.getenv('CONVERTKIT_REDIRECT_URI', 'https://reporting.paperboystudios.co/oauth/callback')
TOKEN_URL = 'https://app.convertkit.com/oauth/token'
CLIENT_ID = os.getenv('CONVERTKIT_CLIENT_ID')
CLIENT_SECRET = os.getenv('CONVERTKIT_CLIENT_SECRET')

# Client data storage
CLIENT_DATA = {}

# Load existing client data
try:
    with open('client_data.json', 'r') as f:
        CLIENT_DATA.update(json.load(f))
except FileNotFoundError:
    pass

# Flask app setup
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', '2cea766fa92b5c9eac492053de73dc47'),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)
)


def check_environment():
    """Check that required environment variables are set."""
    required_vars = ['CONVERTKIT_CLIENT_ID', 'CONVERTKIT_CLIENT_SECRET', 'FLASK_SECRET_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")


def token_required(f):
    """Decorator to require valid API token in session."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = session.get('api_key')
        if not api_key:
            print("No API key in session, redirecting to login")
            return redirect(url_for('oauth_authorize'))
        return f(*args, **kwargs)

    return decorated_function


def save_client_data():
    """Save client data to a JSON file."""
    try:
        print(f"Attempting to save client data: {CLIENT_DATA}")
        with open('client_data.json', 'w') as f:
            json.dump(CLIENT_DATA, f)
        print("Client data saved successfully")

        # Verify the save by reading back
        with open('client_data.json', 'r') as f:
            saved_data = json.load(f)
        print(f"Verified saved data: {saved_data}")

        return True
    except Exception as e:
        print(f"Error saving client data: {str(e)}")
        traceback.print_exc()
        return False


@app.route('/health')
def health():
    """Health check endpoint for Railway."""
    return jsonify({'status': 'healthy', 'service': 'convertkit-analytics'}), 200


@app.route('/', methods=['GET', 'POST'])
@token_required
def index():
    """Main dashboard route."""
    api_key = session.get('api_key')
    client_name = session.get('selected_client')

    if not api_key or not client_name:
        return redirect(url_for('oauth_authorize'))

    # Initialize services
    ck_service = ConvertKitService(api_key, BASE_URL)
    report_service = ReportService(ck_service)

    # Get current total subscribers
    current_total = ck_service.get_current_total_subscribers()

    # Set default dates
    start_date, end_date = get_default_date_range(30)

    try:
        # Get tags data
        tags_data = ck_service.get_all_tags()
        tag_options = tags_data.get('all_tags', [])
        suggested_tags = tags_data.get('suggested', {})

        if request.method == 'POST':
            if 'paperboy_start_date' in request.form:
                # Handle client data form
                paperboy_start_date = request.form.get('paperboy_start_date')
                initial_subscriber_count = request.form.get('initial_subscriber_count')

                if paperboy_start_date and initial_subscriber_count:
                    try:
                        initial_subscriber_count = int(initial_subscriber_count)
                        CLIENT_DATA[client_name] = {
                            'paperboy_start_date': paperboy_start_date,
                            'initial_subscriber_count': initial_subscriber_count
                        }
                        save_client_data()
                        flash('Client data saved successfully!', 'success')
                    except ValueError:
                        flash('Please enter a valid number for initial subscriber count', 'error')
                else:
                    flash('Please fill in all required fields', 'error')

                return redirect(url_for('index'))
            else:
                # Handle report generation form
                facebook_tag = request.form.get('facebook_tag')
                creator_tag = request.form.get('creator_tag')
                sparkloop_tag = request.form.get('sparkloop_tag')
                start_date = request.form.get('start_date')
                end_date = request.form.get('end_date')
                include_open_rates = request.form.get('include_open_rates') == 'true'

                # Convert tag IDs to integers
                facebook_tag = int(facebook_tag) if facebook_tag else None
                creator_tag = int(creator_tag) if creator_tag else None
                sparkloop_tag = int(sparkloop_tag) if sparkloop_tag else None

                # Generate basic report (always fast)
                results = report_service.generate_subscriber_report(
                    facebook_tag, creator_tag, sparkloop_tag,
                    start_date, end_date, current_total, CLIENT_DATA.get(client_name)
                )

                # If open rates requested, start background task
                task_id = None
                if include_open_rates:
                    tags_to_analyze = []
                    if facebook_tag:
                        tags_to_analyze.append({'id': facebook_tag, 'name': 'Facebook Ads'})
                    if creator_tag:
                        tags_to_analyze.append({'id': creator_tag, 'name': 'Creator Network'})
                    if sparkloop_tag:
                        tags_to_analyze.append({'id': sparkloop_tag, 'name': 'SparkLoop'})

                    # Start background task
                    task_id = BackgroundTask.generate_task_id(client_name)
                    BackgroundTask.save_task_status(task_id, 'pending')

                    open_rate_service = OpenRateService(ck_service)
                    BackgroundTask.run_open_rate_calculation(
                        task_id, ck_service, open_rate_service,
                        start_date, end_date, tags_to_analyze
                    )

                    flash(f'Open rates calculation started in background. Task ID: {task_id}. Refresh page to check status.', 'info')
                    results['open_rates_task_id'] = task_id

                return render_template('index.html',
                                     client_name=client_name,
                                     tags=tag_options,
                                     suggested_tags=suggested_tags,
                                     default_start_date=start_date,
                                     default_end_date=end_date,
                                     selected_client=client_name,
                                     client_data=CLIENT_DATA.get(client_name),
                                     results=results)

        # GET request
        return render_template('index.html',
                             client_name=client_name,
                             tags=tag_options,
                             suggested_tags=suggested_tags,
                             default_start_date=start_date,
                             default_end_date=end_date,
                             selected_client=client_name,
                             client_data=CLIENT_DATA.get(client_name),
                             current_total=current_total)

    except Exception as e:
        print(f"Error in index route: {str(e)}")
        flash('An error occurred while loading the page. Please try again.', 'error')
        return redirect(url_for('oauth_authorize'))


@app.route('/oauth/authorize')
def oauth_authorize():
    """Initiate OAuth flow."""
    print("\n=== OAuth Authorize Route ===")
    session.clear()

    # Generate new state parameter
    state = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    session['oauth_state'] = state

    # Build authorization URL
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': 'public',
        'state': state
    }

    auth_url = f'https://app.convertkit.com/oauth/authorize?{urlencode(params)}'
    print(f"Generated authorization URL: {auth_url}")

    return redirect(auth_url)


@app.route('/oauth/callback')
def oauth_callback():
    """Handle OAuth callback."""
    print("=== OAuth Callback Route ===")
    try:
        oauth = OAuth2Session(
            CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            state=session.get('oauth_state')
        )

        token = oauth.fetch_token(
            TOKEN_URL,
            client_secret=CLIENT_SECRET,
            authorization_response=request.url
        )

        # Get the selected account info from ConvertKit
        headers = {'Authorization': f'Bearer {token["access_token"]}'}
        account_response = requests.get('https://api.convertkit.com/v4/account', headers=headers)

        if account_response.status_code == 200:
            account_data = account_response.json()
            print(f"Account data received: {account_data}")

            # Get account info
            client_name = account_data['account']['name']
            print(f"Selected client: {client_name}")

            # Load existing data from file
            try:
                with open('client_data.json', 'r') as f:
                    CLIENT_DATA.update(json.load(f))
            except FileNotFoundError:
                print("No existing client data file found")

            # Only initialize if client doesn't exist at all
            if client_name not in CLIENT_DATA:
                print(f"New client detected: {client_name}")
                CLIENT_DATA[client_name] = {}
                save_client_data()
            else:
                print(f"Existing client found: {client_name}")
                print(f"Client data: {CLIENT_DATA[client_name]}")

            session['api_key'] = token["access_token"]
            session['selected_client'] = client_name

            print(f"Session data set - API Key: {'Present' if 'api_key' in session else 'Missing'}")
            print(f"Session data set - Client: {session.get('selected_client')}")

            return redirect(url_for('index'))

        else:
            print(f"Error getting account data: {account_response.text}")
            flash('Error getting account data', 'error')
            return redirect(url_for('oauth_authorize'))

    except Exception as e:
        print(f"OAuth Error: {str(e)}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('oauth_authorize'))


@app.route('/logout')
def logout():
    """Logout and clear session."""
    print("=== Logout Route ===")
    session.clear()
    return redirect(url_for('oauth_authorize'))


@app.route('/task_status/<task_id>')
@token_required
def task_status(task_id):
    """API endpoint to check task status."""
    status = BackgroundTask.get_task_status(task_id)
    if not status:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(status)


@app.route('/get_tags')
@token_required
def get_tags():
    """API endpoint to get all tags."""
    api_key = session.get('api_key')
    if not api_key:
        return jsonify({'error': 'No API key found'})

    try:
        ck_service = ConvertKitService(api_key, BASE_URL)
        tags_data = ck_service.get_all_tags()
        return jsonify(tags_data)

    except Exception as e:
        print(f"Error getting tags: {str(e)}")
        return jsonify({'error': str(e)})


# Initialize the app (only check environment when running directly, not when imported by gunicorn)
if __name__ == '__main__':
    check_environment()
    app.run(ssl_context='adhoc')
else:
    # When running under gunicorn, check environment but allow Railway's variables
    try:
        check_environment()
    except EnvironmentError as e:
        print(f"Warning: {e}")
        print("Continuing with Railway environment variables...")
