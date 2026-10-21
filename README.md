# Oura V2 for Home Assistant

A custom integration for the Oura Cloud API v2 with OAuth2, multiple accounts, 80 sensors, three binary sensors, and a refresh button per account. Requires Home Assistant **2024.9.0 or later**. Compatibility tests run against 2024.9.0 and 2026.10.2.

## Installation and authorization

1. In HACS, add `https://github.com/mkurdziel/home-assistant-oura-v2` as a custom **Integration** repository and download Oura V2. Alternatively, copy `custom_components/oura/` into your Home Assistant configuration's `custom_components/` directory.
2. Restart Home Assistant.
3. Create an OAuth application in the [Oura developer console](https://cloud.ouraring.com/oauth/applications). Register the callback URL shown by Home Assistant, normally `https://my.home-assistant.io/redirect/oauth` when My Home Assistant is enabled.
4. Open **Settings → Devices & services → Add integration → Oura V2**, enter the application's client ID and secret, and authorize your account.

The integration explicitly requests `email personal daily heartrate workout session tag spo2 heart_health`. Personal information access is required to identify the account. Optional permissions may be declined; affected entities become unavailable while the remaining collections continue updating. Applications are subject to Oura's user limits and approval process. API data availability also depends on membership, ring features, and consent. Personal access tokens are no longer supported.

Each account has a stable Oura user ID. Adding the same account twice is prevented. Reauthentication checks the original account and updates its entry, preserving entity identifiers. Existing installations without a stored user ID are adopted during setup; an expired legacy entry can recover identity from its existing Oura device. Use Home Assistant's **Reauthenticate** action to renew consent when enabling additional data permissions.

## Available data

- Readiness, sleep, and activity scores and contributors; steps, calories, distances, and activity durations.
- Main sleep duration and phases, efficiency, heart rate, HRV, respiration, temperatures, and bedtime timestamps.
- Latest synced heart rate and the minimum/maximum over the preceding 30 hours, plus a source timestamp.
- SpO₂, breathing disturbances, stress, resilience, cardiovascular age, and VO₂ max.
- Workout/session summaries, today's counts and durations, simple tags, and enhanced tags.
- Suggested bedtime windows, interpreted using Oura's day, timezone offset, and offsets from midnight.
- Ring battery percentage, charging and charger-presence binary sensors, firmware and hardware metadata, and a rest-mode binary sensor.

Existing sensor keys and unique IDs are preserved. New entities are added separately. Firmware metadata also updates the account's device information. The account device represents the user's cloud data; battery information is the latest sample supplied by Oura rather than a direct Bluetooth connection.

## Updates and data freshness

The default polling interval is **30 minutes**. Integration options accept 300–86400 seconds and apply changes automatically. The refresh button and `oura.request_refresh` action request an immediate coordinator refresh; normal debouncing and API cooldowns still apply.

```yaml
action: oura.request_refresh
data: {}
```

To refresh one account, supply its Home Assistant config-entry ID as `entry_id`. Omitting it refreshes all loaded Oura accounts. The action reports an error for an entry that is not loaded.

Daily entities select the newest available day and expose `source_day`; this may be an earlier day until the user syncs. Nightly metrics select main sleep and exclude short naps, deleted sleep, and rejected sleep. Today's workout/session/tag totals use Home Assistant's configured timezone. A successful empty collection gives a zero count; missing permissions, failed requests, and null measurements do not become zero.

Daily and sleep collections use a seven-day lookback. Occasional measurements, workouts, sessions, and tags use 90 days. Rest-mode history is fetched from 2000 onward so long-running periods are included. Heart-rate and battery windows cover 30 hours. Collection pagination is followed automatically. Data older than these windows is not imported into Home Assistant history.

Oura must receive data from the mobile app before it becomes available to this integration. Sleep and readiness may require opening and syncing the Oura app. Repeated polling cannot force a ring sync. Membership and permission failures are distinct from invalid tokens; they do not trigger a login loop. Temporary failures mark affected entities unavailable, and a full outage fails the coordinator update. Rate-limit responses establish a cooldown using `Retry-After`.

## Optional webhooks

Webhooks are **disabled by default**. To enable them:

1. Configure an externally reachable **HTTPS** Home Assistant URL under **Settings → System → Network** and ensure Oura can reach it.
2. Enable **Oura webhooks** in the integration's options.

The integration creates its own account-specific callback and subscriptions for supported create/update/delete events. It verifies Oura's challenge, checks HMAC signatures and timestamp freshness, ignores other accounts, and suppresses duplicate or older events. Verified events fetch the affected document instead of refreshing every collection. Heart rate and battery remain polled because Oura's documented webhook types do not include them.

Subscriptions are saved after creation, renewed before expiry, and retained across reloads. Disabling webhooks or removing the integration deletes only subscriptions owned by that entry. If cleanup fails, stored IDs are retained for retry on a later load; Oura subscriptions also expire. Subscription setup/renewal failures keep polling active and retry hourly. External URL or local credential configuration errors must be corrected before webhook setup can proceed.

## Troubleshooting and diagnostics

- **Unavailable entity:** check its required permissions, Oura membership, and whether that feature is available for the account. Optional collections can be unavailable without breaking the integration.
- **Unknown entity:** the API returned no usable measurement in the lookback window. For example, no recent VO₂ estimate, bedtime recommendation, or completed main sleep may exist.
- **Old values:** inspect `source_day` or `sample_time` and sync the Oura app.
- **Authorization failure:** reconnect the same account using Home Assistant's reauthentication flow.
- **Webhook failure:** verify the external HTTPS URL is reachable and inspect integration diagnostics. Polling continues during remote subscription failures.

Download diagnostics from the integration menu to see collection availability, record counts, polling status, and webhook health. Diagnostics omit credentials, account identifiers, callback secrets, tag contents, and biometric payloads. Debug logging uses `custom_components.oura` and does not include API response bodies or credentials.

Version 1.1.0 fixes SpO₂, VO₂ endpoint naming, bedtime and tag mappings, daily/main-sleep selection, reauthentication, and failure handling. Previously unitless heart-rate and calorie sensors now report `bpm` and `kcal`; existing installations may need to resolve statistics-unit changes through Home Assistant's statistics tools.

## Removal

Remove the integration from **Settings → Devices & services**. Its owned webhook subscriptions are removed when Oura is reachable. Revoke the application's access in Oura if desired, then uninstall the custom integration through HACS or remove its directory and restart Home Assistant.

## Development and verification

Tests use synthetic fixtures, isolated Home Assistant instances, and disabled network sockets. They do not use a live Oura account, Home Assistant token, or Keychain credential.

Current compatibility target (Python 3.14):

```sh
python3.14 -m venv .venv-test
.venv-test/bin/python -m pip install -r requirements-test.txt
.venv-test/bin/python -m pytest --cov=custom_components.oura --cov-report=term-missing
.venv-test/bin/ruff check custom_components tests
.venv-test/bin/ruff format --check custom_components tests
```

Minimum compatibility target: create a separate Python 3.12 environment, install `requirements-test-min.txt`, and run the same pytest suite. The legacy dependency pin is required by Home Assistant 2024.9's ACME stack.

GitHub Actions runs both compatibility targets, Ruff, the official hassfest validator, and HACS repository validation. To run hassfest locally with Docker:

```sh
docker run --rm --network none -v "$PWD":/github/workspace:ro ghcr.io/home-assistant/hassfest
```

Reference: [Oura API v2](https://cloud.ouraring.com/v2/docs), [Oura authentication](https://cloud.ouraring.com/docs/authentication), [Home Assistant integration documentation](https://contributors.home-assistant.io/core/integrations/).

## License

Licensed under the [Apache License 2.0](LICENSE), restored from the original repository license.
