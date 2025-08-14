
# Oura V2 for Home Assistant (HACS)

OAuth2 custom integration for **Oura Cloud API v2**, with multi‑account support, rich sensors (sleep/readiness/activity/vitals), HR time series, workouts/sessions summaries, and **manual refresh** (service + button).

## Install

- Copy `custom_components/oura/` to your Home Assistant `config/custom_components/` folder (or add your GitHub repo via HACS).
- Restart Home Assistant.

## OAuth App

- Authorize URL: `https://cloud.ouraring.com/oauth/authorize`
- Token URL: `https://api.ouraring.com/oauth/token`
- Redirect URI: `https://my.home-assistant.io/redirect/oauth`
- Scopes: `email personal daily heartrate workout session tag spo2`

## Manual refresh

- Service: `oura.request_refresh` (optional `entry_id`)
- Button entity: `button.oura_v2_refresh_now` (per account)

## Notes

- Some endpoints (e.g., Daily SpO2, VO2 Max, Resilience, Stress) are tenant/feature‑gated by Oura and may return no data until available on your account.
- HR time series window is last **30 hours** to better capture overnight data.
