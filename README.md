
# Oura Ring for Home Assistant (HACS)

A full OAuth2 Home Assistant integration for Oura Ring **API v2** with support for multiple accounts, all major daily metrics (sleep, readiness, activity, SpO2), heart rate time‑series, stress & resilience (if available), workouts and sessions.

> **Highlights**
>
> - OAuth2 via Home Assistant **Application Credentials**
> - **Multiple accounts**: add one config entry per Oura user
> - **UI-first** setup (no YAML needed; optional options via UI)
> - Sensors for: readiness score, sleep score, activity score, steps, total calories, SpO2 average, resting HR, heart rate min/max/latest, plus **per-metric** packs below.
> - HACS-compatible repository

## Install (HACS)

1. In HACS, add this repository as **Custom repositories** → Type: *Integration*.
2. Click **Install**.
3. **Restart** Home Assistant.

## Create an Oura OAuth app

1. Create an OAuth2 application in the Oura developer portal.
   - **Authorize URL**: `https://cloud.ouraring.com/oauth/authorize`
   - **Token URL**: `https://api.ouraring.com/oauth/token`
2. Set redirect URI to **My Home Assistant OAuth redirect**: `https://my.home-assistant.io/redirect/oauth`  
   Or: `https://<YOUR_HA_URL>/auth/external/callback`.
3. Copy the **Client ID** and **Client Secret**.

## Link in Home Assistant

1. **Settings → Devices & services → + Add integration → Oura Ring**.
2. When prompted for credentials, paste the Client ID/Secret.
3. Approve in the popup and finish the flow.
4. Repeat to add more Oura users (one entry per account).

## Options

- **Scan interval**: default 30 min
- **Sandbox**: use Oura sandbox
- **Additional scopes**: space-separated list
- **Per-metric packs** (toggle on/off):
  - **Sleep details**: total/deep/REM/light durations, efficiency, latency, bedtime start/end
  - **Readiness contributors**: HRV balance, temperature deviation, recovery index, sleep/activity balance
  - **Activity details**: active calories, eq. walking distance, inactivity/non-wear time; contributor scores (meet daily targets, move every hour, stay active, training frequency/volume, recovery time)
  - **Vitals**: respiratory rate, HRV (RMSSD)

## Notes

- The integration polls a small rolling window (yesterday → now). Some endpoints may not be available to all accounts.
- Oura app sync timing affects when new data appears.

