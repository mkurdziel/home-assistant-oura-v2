
from __future__ import annotations

DOMAIN = "oura"

OAUTH_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.ouraring.com/oauth/token"

API_BASE = "https://api.ouraring.com/v2"
SANDBOX_API_BASE = "https://api.ouraring.com/v2/sandbox"

DEFAULT_UPDATE_INTERVAL_MIN = 30

OAUTH_SCOPES_DEFAULT = [
    "email",
    "personal",
    "daily",
    "heartrate",
    "workout",
    "tag",
    "session",
    "spo2",
]

CONF_USE_SANDBOX = "use_sandbox"
CONF_ADDITIONAL_SCOPES = "additional_scopes"
CONF_UPDATE_INTERVAL = "update_interval"

# Options to toggle summary sensors
CONF_ENABLE_WORKOUT_SUMMARY = "enable_workout_summary"
CONF_ENABLE_SESSION_SUMMARY = "enable_session_summary"
