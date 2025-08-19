import requests
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import time
import os
from requests_oauthlib import OAuth2Session
from functools import wraps
from dateutil import parser as parse
import traceback
import random
import string
from urllib.parse import urlencode

# Load configuration from environment variables (fallback to config.json for local development)
try:
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        API_KEY = os.getenv('CONVERTKIT_API_KEY', config.get("api_key"))
        BASE_URL = os.getenv('CONVERTKIT_BASE_URL', config.get("base_url"))
except FileNotFoundError:
    # Production environment - use only environment variables
    API_KEY = os.getenv('CONVERTKIT_API_KEY')
    BASE_URL = os.getenv('CONVERTKIT_BASE_URL', 'https://api.kit.com/v4/')
PER_PAGE_PARAM = 1000
REDIRECT_URI = os.getenv('CONVERTKIT_REDIRECT_URI', 'https://reporting.paperboystudios.co/oauth/callback')
TOKEN_URL = 'https://app.convertkit.com/oauth/token'
CLIENT_ID = os.getenv('CONVERTKIT_CLIENT_ID')
CLIENT_SECRET = os.getenv('CONVERTKIT_CLIENT_SECRET')
DEFAULT_FACEBOOK_TAG = 4155625
DEFAULT_CREATOR_TAG = 4090509
DEFAULT_SPARKLOOP_TAG = 5023500

# Update the client data structure to use names
CLIENT_DATA = {
    'Sieva Kozinsky': {  # Using name as identifier
        'paperboy_start_date': '2024-02-09',
        'initial_subscriber_count': 41000
    }
    # Other clients will be added here as they're onboarded
}

def get_client_data(email):
    """Get client data if it exists"""
    return CLIENT_DATA.get(email)

app = Flask(__name__)

# Set up session configuration
app.config.update(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', '2cea766fa92b5c9eac492053de73dc47'),
    SESSION_COOKIE_SECURE=True,  # Only send cookie over HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE='Lax',  # Protect against CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)  # Session expires after 1 hour
)

# Cache configuration
CACHE_TIMEOUT = 3600  # 1 hour in seconds
CACHE_SIZE = 100     # Store up to 100 different queries

def check_environment():
    required_vars = ['CONVERTKIT_CLIENT_ID', 'CONVERTKIT_CLIENT_SECRET', 'FLASK_SECRET_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Token validation decorator
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = session.get('api_key')
        if not api_key:
            print("No API key in session, redirecting to login")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Rate limiting function
def rate_limited_request(url, headers, params=None):
    """Make a rate-limited request to the ConvertKit API"""
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    
    for attempt in range(MAX_RETRIES):
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 429:  # Too Many Requests
            time.sleep(RETRY_DELAY * (attempt + 1))
            continue
            
        return response
    
    return response  # Return last response if all retries failed

# Form validation
def validate_form_data(start_date, end_date):
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if end < start:
            return False, "End date must be after start date"
            
        return True, None
    except ValueError:
        return False, "Invalid date format"

def get_subscribers(api_key, start_date, end_date, count_only=False):
    """Get all subscribers between two dates using cursor-based pagination"""
    url = f"{BASE_URL}/subscribers"
    headers = {'Authorization': f'Bearer {api_key}'}
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
        response = rate_limited_request(url, headers=headers, params=params)
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
    response = rate_limited_request(url, headers=headers, params=params)
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
            response = rate_limited_request(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                current_subscribers = data.get('subscribers', [])
                subscribers.extend(current_subscribers)
                print(f"Page count: {len(current_subscribers)}")
            else:
                print(f"Error getting page: {response.text}")
                break
    
    return subscribers

def get_tagged_subscribers(api_key, tag_id, start_date, end_date):
    """Get tagged subscriber count using optimized pagination"""
    if not tag_id:
        return []
        
    url = f"{BASE_URL}/tags/{tag_id}/subscribers"
    headers = {'Authorization': f'Bearer {api_key}'}
    params = {
        'created_after': f"{start_date}T00:00:00Z",
        'created_before': f"{end_date}T23:59:59Z",
        'per_page': PER_PAGE_PARAM,
        'sort_order': 'desc'
    }
    
    total = 0
    tagged_subscribers = []  # Still need to collect for filtering
    
    # Get first page
    response = rate_limited_request(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        tagged_subscribers.extend(data.get('subscribers', []))
        total = len(tagged_subscribers)
        print(f"First page count for tag {tag_id}: {total}")
        
        # Keep track of complete pages
        complete_pages = 0
        
        # Process subsequent pages
        while data.get('pagination', {}).get('has_next_page'):
            complete_pages += 1
            print(f"Found complete page {complete_pages} for tag {tag_id}")
            
            # Get next page cursor
            params['after'] = data['pagination']['end_cursor']
            
            # Get next page
            response = rate_limited_request(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                current_subscribers = data.get('subscribers', [])
                tagged_subscribers.extend(current_subscribers)
                if not data.get('pagination', {}).get('has_next_page'):
                    # Last page - count actual subscribers
                    total += len(current_subscribers)
                    print(f"Last page count for tag {tag_id}: {len(current_subscribers)}")
                else:
                    # Complete page - add 1000
                    total += PER_PAGE_PARAM
            else:
                print(f"Error getting page: {response.text}")
                break
                
        print(f"Total tagged subscribers: {total} (from {complete_pages} complete pages + last page)")
    
    return tagged_subscribers  # Return full list for filtering

def fetch_tags(api_key=None):
    """Get all tags from ConvertKit API"""
    api_key = api_key or session.get('api_key')
    if not api_key:
        return {'error': 'No API key found', 'all_tags': [], 'suggested': {}}
        
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = rate_limited_request(
            f'{BASE_URL}/tags',
            headers=headers
        )
        
        if response.status_code == 200:
            tags = response.json().get('tags', [])
            
            # Find suggested tags
            facebook_tag = find_closest_tag(tags, 'facebook')
            creator_tag = find_closest_tag(tags, 'creator')
            sparkloop_tag = find_closest_tag(tags, 'sparkloop')
            
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

def generate_report(api_key, facebook_tag, creator_tag, sparkloop_tag, start_date, end_date):
    try:
        current_total = int(request.form.get('current_total', 0))
        
        # Get total subscribers for the recent period using count_only
        total_count = get_subscribers(api_key, start_date, end_date, count_only=True)
        
        # Get tagged subscribers directly - no need for full subscriber list
        facebook_subscribers = get_tagged_subscribers(api_key, facebook_tag, start_date, end_date)
        creator_subscribers = get_tagged_subscribers(api_key, creator_tag, start_date, end_date)
        sparkloop_subscribers = get_tagged_subscribers(api_key, sparkloop_tag, start_date, end_date)
        
        # Calculate counts
        facebook_count = len(facebook_subscribers)
        creator_count = len(creator_subscribers)
        sparkloop_count = len(sparkloop_subscribers)
        
        # Calculate organic subscribers using the total_count
        attributed_count = facebook_count + creator_count + sparkloop_count
        organic_count = total_count - attributed_count
        
        # Get client data
        client_name = session.get('selected_client')
        client_data = CLIENT_DATA.get(client_name, {})
        paperboy_start_date = datetime.strptime(client_data.get('paperboy_start_date'), '%Y-%m-%d')
        initial_count = client_data.get('initial_subscriber_count', 0)
        
        # Calculate the three periods
        before_start = paperboy_start_date - timedelta(days=60)
        before_end = paperboy_start_date
        
        after_start = paperboy_start_date + timedelta(days=45)
        after_end = after_start + timedelta(days=60)
        
        print(f"\n=== Period Calculations ===")
        print(f"Before period: {before_start.strftime('%Y-%m-%d')} to {before_end.strftime('%Y-%m-%d')}")
        print(f"After period: {after_start.strftime('%Y-%m-%d')} to {after_end.strftime('%Y-%m-%d')}")
        
        # Get subscribers for before/after periods (using count_only)
        daily_average_before = round(
            get_subscribers(api_key, 
                          before_start.strftime('%Y-%m-%d'),
                          before_end.strftime('%Y-%m-%d'),
                          count_only=True) / 60, 1)
        
        daily_average_after = round(
            get_subscribers(api_key,
                          after_start.strftime('%Y-%m-%d'),
                          after_end.strftime('%Y-%m-%d'),
                          count_only=True) / 60, 1)
        
        print(f"\n=== Growth Calculations ===")
        print(f"Before period subscribers: {daily_average_before * 60}")  # Convert daily average back to total
        print(f"After period subscribers: {daily_average_after * 60}")   # Convert daily average back to total
        print(f"Total subscribers in period: {total_count}")
        print(f"Daily average before: {daily_average_before}")
        print(f"Daily average after: {daily_average_after}")
        
        # Calculate total growth since Paperboy
        total_growth = current_total - initial_count
        growth_rate = round((total_growth / initial_count * 100), 1)
        
        # Calculate percentages (rounded to 1 decimal place)
        facebook_percent = round((len(facebook_subscribers) / total_count * 100), 1) if total_count > 0 else 0
        creator_percent = round((len(creator_subscribers) / total_count * 100), 1) if total_count > 0 else 0
        sparkloop_percent = round((len(sparkloop_subscribers) / total_count * 100), 1) if total_count > 0 else 0
        organic_percent = round((organic_count / total_count * 100), 1) if total_count > 0 else 0
        
        # Calculate paid growth using existing numbers
        paid_count = facebook_count + sparkloop_count
        paid_percent = round((paid_count / total_count * 100), 1) if total_count > 0 else 0
        
        # Get monthly growth data
        monthly_growth = generate_monthly_growth_data(api_key, paperboy_start_date)
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_subscribers': total_count,
            'facebook_subscribers': len(facebook_subscribers),
            'facebook_percent': facebook_percent,
            'creator_subscribers': len(creator_subscribers),
            'creator_percent': creator_percent,
            'sparkloop_subscribers': len(sparkloop_subscribers),
            'sparkloop_percent': sparkloop_percent,
            'organic_subscribers': organic_count,
            'organic_percent': organic_percent,
            'total_growth': f"{total_growth:,}",  # Add comma separator
            'growth_rate': growth_rate,
            'paperboy_start_date': paperboy_start_date.strftime('%Y-%m-%d'),
            'daily_average_before': daily_average_before,
            'daily_average_after': daily_average_after,
            'before_period': f"{before_start.strftime('%Y-%m-%d')} to {before_end.strftime('%Y-%m-%d')}",
            'after_period': f"{after_start.strftime('%Y-%m-%d')} to {after_end.strftime('%Y-%m-%d')}",
            'paid_growth_percent': paid_percent,
            'paid_subscribers': paid_count,
            'monthly_growth': monthly_growth
        }
        
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return None

@app.route('/', methods=['GET', 'POST'])
@token_required
def index():
    api_key = session.get('api_key')
    client_name = session.get('selected_client')
    
    if not api_key or not client_name:
        return redirect(url_for('login'))
    
    # Get current total subscribers
    current_total = get_current_total_subscribers(api_key)
    
    # Set default dates
    today = datetime.now()
    start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    try:
        # Get tags data
        tags_data = fetch_tags(api_key)
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
                
                results = generate_report(api_key, facebook_tag, creator_tag, sparkloop_tag, start_date, end_date)
                
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
        return redirect(url_for('login'))

@app.route('/oauth/authorize')
def oauth_authorize():
    print("\n=== OAuth Authorize Route ===")
    # Clear existing session data
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
            return redirect(url_for('index'))
            
    except Exception as e:
        print(f"OAuth Error: {str(e)}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    print("=== Logout Route ===")
    session.clear()
    return redirect(url_for('index'))

@app.route('/validate_api_key', methods=['POST'])
def validate_api_key():
    data = request.get_json()
    api_key = data.get('api_key')
    
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = rate_limited_request(
            'https://api.convertkit.com/v4/tags',
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            tags = data.get('tags', [])
            return jsonify({
                'valid': True,
                'tags': [{'id': tag['id'], 'name': tag['name']} for tag in tags]
            })
        else:
            return jsonify({
                'valid': False,
                'error': 'Invalid API key'
            })
            
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        })

# Add the login route back
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        if api_key:
            session['api_key'] = api_key
            return redirect(url_for('index'))
    return render_template('index.html')  # We'll use the same template for now

# Initialize the app
check_environment()

def save_client_data():
    """Save client data to a JSON file"""
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
        traceback.print_exc()  # This will print the full error traceback
        return False

def find_closest_tag(tags, tag_type):
    """
    Find the closest matching tag from common variations
    tags: list of tag dictionaries from ConvertKit
    tag_type: 'facebook', 'creator', or 'sparkloop'
    """
    print(f"\n=== Finding {tag_type} tag ===")
    
    variations = {
        'facebook': ['facebook ads', 'facebook ad', 'fb ads', 'fb ad', 'facebook', 'paid ads', 'paid'],
        'creator': ['creator network', 'creator', 'network', 'cn', 'ambassador'],
        'sparkloop': ['sparkloop', 'spark loop', 'spark', 'loop', 'referral', 'refer']
    }
    
    # Print all available tags for debugging
    print("Available tags:")
    for tag in tags:
        print(f"- {tag['name']} (ID: {tag['id']})")
    
    # Convert all tag names to lowercase for comparison
    tag_map = {tag['name'].lower(): tag for tag in tags}
    
    # Check each variation against the tags
    for variation in variations[tag_type]:
        print(f"Checking variation: {variation}")
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

@app.route('/get_tags')
def get_tags():
    api_key = session.get('api_key')
    if not api_key:
        return jsonify({'error': 'No API key found'})
        
    try:
        print("\n=== Getting Tags ===")
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = rate_limited_request(
            f'{BASE_URL}/tags',
            headers=headers
        )
        
        if response.status_code == 200:
            tags = response.json().get('tags', [])
            
            # Find suggested tags
            facebook_tag = find_closest_tag(tags, 'facebook')
            creator_tag = find_closest_tag(tags, 'creator')
            sparkloop_tag = find_closest_tag(tags, 'sparkloop')
            
            print("Found tags:", {
                'facebook': facebook_tag,
                'creator': creator_tag,
                'sparkloop': sparkloop_tag
            })
            
            return jsonify({
                'all_tags': tags,
                'suggested': {
                    'facebook': facebook_tag,
                    'creator': creator_tag,
                    'sparkloop': sparkloop_tag
                }
            })
            
        return jsonify({'error': 'Failed to fetch tags'})
        
    except Exception as e:
        print(f"Error getting tags: {str(e)}")
        return jsonify({'error': str(e)})

def get_current_total_subscribers(api_key):
    """Get the current total subscriber count using include_total_count"""
    url = f"{BASE_URL}/subscribers"
    headers = {'Authorization': f'Bearer {api_key}'}
    params = {
        'include_total_count': 'true',
        'per_page': 1  # Minimize data transfer since we only need the count
    }
    
    response = rate_limited_request(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        total_count = data.get('pagination', {}).get('total_count', 0)
        print(f"Current total subscribers: {total_count}")
        return total_count
    return 0

def get_subscriber_count_for_date(api_key, date):
    """Get total subscriber count for a specific date using optimized query"""
    url = f"{BASE_URL}/subscribers"
    headers = {'Authorization': f'Bearer {api_key}'}
    params = {
        'created_before': f"{date}T23:59:59Z",
        'include_total_count': 'true',
        'per_page': 1  # Minimize data transfer since we only need the count
    }
    
    response = rate_limited_request(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get('pagination', {}).get('total_count', 0)
    return 0

def generate_monthly_growth_data(api_key, paperboy_start_date):
    """Generate monthly subscriber counts before and after Paperboy start date"""
    try:
        # Convert paperboy_start_date to datetime if it's a string
        if isinstance(paperboy_start_date, str):
            paperboy_start_date = datetime.strptime(paperboy_start_date, '%Y-%m-%d')
        
        # Get 3 months before Paperboy
        start_date = paperboy_start_date - timedelta(days=90)
        current_date = datetime.now()
        
        monthly_data = []
        current_month = start_date.replace(day=1)
        
        # Generate all month start dates until current date
        while current_month <= current_date:
            count = get_subscriber_count_for_date(api_key, current_month.strftime('%Y-%m-%d'))
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

if __name__ == '__main__':
    app.run(ssl_context='adhoc')