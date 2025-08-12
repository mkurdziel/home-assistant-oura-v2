
from __future__ import annotations

DOMAIN = "oura"

OAUTH_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://api.ouraring.com/oauth/token"

API_BASE = "https://api.ouraring.com/v2"
SANDBOX_API_BASE = "https://api.ouraring.com/v2/sandbox"

DEFAULT_UPDATE_INTERVAL_MIN = 30

# The most stable scopes documented by Oura; covers most metrics.
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

# Sensor pack option keys
CONF_ENABLE_PACK_SLEEP = "enable_pack_sleep"
CONF_ENABLE_PACK_READINESS = "enable_pack_readiness"
CONF_ENABLE_PACK_ACTIVITY = "enable_pack_activity"
CONF_ENABLE_PACK_VITALS = "enable_pack_vitals"
