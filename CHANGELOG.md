# Changelog

All notable changes to this integration are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.0] - 2026-07-05

Stable release consolidating prereleases 0.5.0b1–0.5.0b12. Highlights since 0.4.2:

### Added

- **Reconfigure support**: Modbus host/IP, port, unit ID and all sensor entities changeable via the entry's "Reconfigure" menu — no more remove & re-add; live settings survive.
- **Multi-wallbox support**: per-entry entity ID prefix (`id_prefix`) for clean unique entity IDs, entry titles with host, and **priority-based load sharing** (`charge_priority`) with an optional **fleet power limit** (`fleet_max_watts`) across all boxes.
- Lovelace card: **visual editor** with wallbox dropdown and a `prefix` option; card auto-registered.
- New diagnostic sensor **"Modbus errors (24 h)"**; localized integration name (DE/EN); localized dynamic texts (status, stop cause, notifications) following the HA system language; optional charge start/stop notifications via any `notify` entity.
- All live settings persist across restarts/updates, with a "Reset to defaults" button.
- `CHANGELOG.md`, full README settings & sensor reference covering every UI value.

### Changed

- Start/stop/current-adjustment delays and amps deadband are **options** ("Configure"), per wallbox; default stop delay reduced to 1 minute.
- Stop-cause reporting fixed: "SOC too low" only for a real `min_soc` breach; everything else reports "Insufficient PV surplus".

### Removed

- "Test: forced amps" entity and its calculation logic (use override mode "manual" instead).

## [0.5.0b12] - 2026-07-05 (prerelease)

### Added

- The **integration name** shown in the UI is now localized via the top-level `title` key in the translation files (German "EM2GO Home PV-Überschussladen", English "EM2GO Home PV surplus charging"). The `manifest.json` name is now the English fallback (used in logs and non-translated contexts). Note: config-entry titles and the device name are stored values created once and are not affected by language switches — rename them via the pencil icon if desired.

## [0.5.0b11] - 2026-07-05 (prerelease)

### Added

- **Priority-based load sharing between multiple wallboxes** (new options `charge_priority`, 1 = highest, and `fleet_max_watts`, 0 = off): a lower-priority box doesn't start while a higher-priority one is waiting to start, and yields first when surplus drops (its consumption counts as reclaimable for higher priorities). The optional fleet power limit caps the combined draw of all boxes — budget goes to higher priorities first and also constrains the manual override. New status texts "Waiting for higher-priority wallbox" / "Waiting: fleet power limit reached". Boxes with equal priority behave as before (independent). Single-wallbox installations are unaffected.

## [0.5.0b10] - 2026-07-05 (prerelease)

### Changed

- **Start delay, stop delay, current-adjustment delay and amps deadband** moved from number entities back into the entry's **Options dialog** ("Configure") — these are set-and-forget parameters, not daily controls. They remain per wallbox (one config entry per wallbox). Values previously set via the number entities keep working as fallback until the Options dialog is saved once; the old number entities are removed from the registry automatically.
- "Reset to defaults" consequently no longer touches delays/deadband (they are options now).

### Removed

- **"Test: forced amps"** (`number.pvsc_forced_ampere`) removed entirely, including its logic in the charging calculation. For a fixed-current test, use override mode "manual" instead.

### Added

- New diagnostic sensor **"Modbus errors (24 h)"** (`sensor.pvsc_modbus_errors_24h`): counts real Modbus errors in the last 24 hours (cool-down ticks don't count). In-memory — resets on HA restart.

## [0.5.0b9] - 2026-07-05 (prerelease)

### Added

- The Lovelace card now has a **visual editor**: clicking "Edit" on the card shows a form with a title field and a **wallbox dropdown** (available wallboxes are auto-detected from the `sensor.<prefix>_em2go_state` entities, one per config entry) — no YAML needed to bind a card to a wallbox.

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
