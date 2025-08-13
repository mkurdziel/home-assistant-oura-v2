
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
