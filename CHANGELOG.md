# Changelog

All notable changes to this integration are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.0b8] - 2026-07-05 (prerelease)

### Added

- **Multi-wallbox support**: each config entry now has an **entity ID prefix** (setup/reconfigure field `id_prefix`, default `pvsc`). A second wallbox gets its own prefix (e.g. `pvsc_garage`), so its entities become `sensor.pvsc_garage_status_text` etc. instead of colliding `_2`-suffixed IDs. The prefix must be unique across entries; changing it via Reconfigure renames the entry's existing entities in the registry (manually renamed entities are left alone).
- New entries are titled **"EM2GO Home PV-Überschussladen (\<host\>)"** so multiple entries are distinguishable on the integrations page.
- The bundled Lovelace card accepts a **`prefix`** option (default `pvsc`) to bind a card to a specific wallbox; individual `*_entity` options still override.

### Unchanged / migration notes

- Existing single-wallbox installations keep their entity IDs (`sensor.pvsc_*`): the default prefix is `pvsc` and the entity registry pins IDs by unique_id. Dashboards, automations, and the energy dashboard keep working without changes.

## [0.5.0b7] - 2026-07-05 (prerelease)

### Added

- **Reconfigure support**: the setup values (Modbus host/IP, port, unit ID, and all sensor entities) can now be changed later via the config entry's **"Reconfigure"** menu item — no more removing and re-adding the integration. The form comes pre-filled with the current values; optional entities can be cleared to remove them. Live settings (SOC thresholds, delays, overrides, …) are preserved, since the entry keeps its identity. Switching to the address of another already-configured wallbox is rejected.

## [0.5.0b6] - 2026-07-05 (prerelease)

### Changed

- **Start delay**, **Stop delay**, and **Current adjustment delay** moved from the Options dialog to per-wallbox **number entities** (`number.pvsc_state_change_on_delay`, `number.pvsc_state_change_off_delay`, `number.pvsc_ampere_change_delay`, config category on the wallbox device). They are now adjustable live per wallbox, persist across restarts/updates like the other live settings, and are covered by the "Reset to defaults" button. Values previously set via Options are migrated automatically on first startup; the Options fields are gone. Allowed ranges are unchanged (start/stop 60–1800 s, current adjustment 30–600 s), as are the fixed extra rate limits (`STATE_CHANGE_INTERVAL`, `AMPERE_CHANGE_INTERVAL`).
- README: new complete reference of every value shown in the UI — all sensors, binary sensors, and diagnostic entities are now documented, in addition to the existing switch/number/select/button tables.

## [0.5.0b5] - 2026-07-05 (prerelease)

### Added

- Three previously hardcoded timing constants are now configurable via Options ("Configure"): **Start delay** (`state_change_on_delay`), **Stop delay** (`state_change_off_delay`), and **Current adjustment delay** (`ampere_change_delay`). Start/stop delay accept 60–1800 s (1–30 min), current adjustment delay accepts 30–600 s — the minimums are enforced to avoid flappy switching and excessive Modbus writes to the wallbox.

### Changed

- Default **Stop delay** reduced from 3 minutes to **1 minute**. Charging now reacts noticeably faster to a genuine surplus shortfall (e.g. a house-load spike) instead of holding minimum current for a full 3 minutes before actually stopping. Start delay and current-adjustment delay defaults are unchanged (3 min / 30 s).
- The fixed 3-minute rate limit between two state changes (`STATE_CHANGE_INTERVAL`) and the fixed 30-second rate limit between two current adjustments (`AMPERE_CHANGE_INTERVAL`) remain hardcoded and still apply on top of the configurable delays above.

## [0.5.0b4] - 2026-07-05 (prerelease)

### Changed

- README rewritten in English only (the previous duplicated German section is gone); added a full settings reference table explaining every setup-wizard field, every option, and every live switch/number/select/button entity, including their defaults and how they actually affect charging behaviour.
- Documented the general Home Assistant behaviour where entity *names* are fixed to the backend language active at first creation and don't retroactively re-translate, as opposed to this integration's dynamically generated text (status, stop cause, notifications), which does follow the system language live.

### Added

- `CHANGELOG.md` (this file).

## [0.5.0b3] - 2026-07-05 (prerelease)

### Added

- `status_text`, `stop_cause`, and `em2go_state_text` sensors, and the charge start/stop notifications, now follow Home Assistant's system language (Settings → System → Home information → Language). German and English are supported; any other language falls back to German. No restart needed — re-evaluated on every poll.

## [0.5.0b2] - 2026-07-05 (prerelease)

### Fixed

- The "SOC too low" stop cause was reported for any charging shortfall while the home battery SOC was below `optimal_soc` (default 80 %) — even though the actually configured safety floor is `min_soc` (default 40 %). This made ordinary PV dips show up as an SOC problem when the home battery was perfectly fine, just not *allowed* to top up the car in that band.

### Added

- New stop cause, "Insufficient PV surplus", for genuine PV shortfalls — including the `min_soc`–`optimal_soc` band described above.
- Stop cause is no longer left at a stale "No stop" for cases that have their own status text (automation switched off mid-charge, car left the configured location, wallbox reported "charging finished", or a core sensor dropped out); those cases are now excluded from the PV/battery cause logic instead of being mislabeled.

## [0.5.0b1] - 2026-07-05 (prerelease)

### Added

- All "live" settings (SOC thresholds, correction factor, ampere deadband, automatic phase switching, surplus calculation mode, override mode/amps/phases, surplus-automation on/off, and the "Control active" state) are now persisted to storage and survive Home Assistant restarts and integration updates. Previously these silently reset to hardcoded defaults every time the coordinator was re-created.
- New "Reset to defaults" button (`button.pvsc_reset_defaults`) to restore the settings above to their factory values in one step. Deliberately excludes "Control active" so the button can't accidentally switch real wallbox control on or off.

## [0.4.2] - 2026-07-04

### Changed

- Removed duplicate `www/pvsc-card.js` and `www/pvsc_icon.svg` files that had been left in the repository root after the card was properly bundled inside `custom_components/pvsc/www/`.

## [0.4.1] - 2026-07-04

### Changed

- `hacs.json`: enabled `render_readme` so HACS shows this README directly in the store instead of just a summary.
- Added HACS/GitHub badges to the README.
- Fixed `manifest.json` key order to satisfy Home Assistant's `hassfest` validation.

## [0.4.0] - 2026-07-04

### Added

- Bundled Lovelace card (`custom_components/pvsc/www/pvsc-card.js`) is now shipped and auto-registered by the integration itself — add a `custom:pvsc-card` card to any dashboard with no manual resource setup.

## [0.3.0] - 2026-07-04

Initial HACS-conformant release. Includes automatic 1↔3 phase switching with hysteresis, the custom icon, and general HACS packaging fixes on top of the initial PV-surplus-charging logic (ported from an existing Node-RED flow).
