
from __future__ import annotations

DOMAIN = "oura"

API_BASE = "https://api.ouraring.com/v2/usercollection"
AUTH_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
AUTH_TOKEN_URL = "https://api.ouraring.com/oauth/token"

# Request the broadest available scopes so users can pick what they allow.
OAUTH_SCOPES = [
    "email",
    "personal",
    "daily",
    "heartrate",
    "workout",
    "tag",
    "session",
    "spo2",
]

DEFAULT_POLL_INTERVAL_MIN = 30          # general (daily) data
DEFAULT_HR_POLL_INTERVAL_MIN = 5        # heartrate (time series), can be disabled via options

CONF_ACCOUNT_NAME = "account_name"
CONF_ENABLE_LIVE_HR = "enable_live_hr"
CONF_HR_LOOKBACK_MIN = "hr_lookback_min"

DEFAULT_ENABLE_LIVE_HR = True
DEFAULT_HR_LOOKBACK_MIN = 180  # fetch last 3 hours of HR data for "latest" value
