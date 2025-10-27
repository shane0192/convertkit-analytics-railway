"""Constants used throughout the application."""

# API Configuration
PER_PAGE_PARAM = 1000
CACHE_TIMEOUT = 3600  # 1 hour in seconds
CACHE_SIZE = 100  # Store up to 100 different queries

# Default tag IDs (can be overridden by client-specific tags)
DEFAULT_FACEBOOK_TAG = 4155625
DEFAULT_CREATOR_TAG = 4090509
DEFAULT_SPARKLOOP_TAG = 5023500

# API Rate Limiting
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Date calculation periods
BEFORE_PERIOD_DAYS = 60
AFTER_PERIOD_START_DAYS = 45
AFTER_PERIOD_DAYS = 60

# Tag variations for fuzzy matching
TAG_VARIATIONS = {
    'facebook': ['facebook ads', 'facebook ad', 'fb ads', 'fb ad', 'facebook', 'paid ads', 'paid'],
    'creator': ['creator network', 'creator', 'network', 'cn', 'ambassador'],
    'sparkloop': ['sparkloop', 'spark loop', 'spark', 'loop', 'referral', 'refer']
}
