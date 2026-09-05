# Changelog

All notable changes to this integration are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.6.0b1] - 2026-09-05 (prerelease)

Safety and correctness pass over the charging control loop. Several of these
fixes change when and what the integration writes to the wallbox — released
as a beta first, to be watched over real charging cycles (a sunny day for the
1↔3-phase switch, a partly-cloudy one for start/stop cycling, and a manual
stop override while charging) before promoting to stable.

### Fixed

- **A single `unavailable` blip of the house-load sensor could drive the wallbox towards maximum current.** `_to_float()` returns the sentinel `-1` for `unavailable`/`unknown` states, and that sentinel flowed straight into the load-mode surplus calculation: `load = -1 - P_car` turned into a fictitious surplus of `pv + P_car + 1 W`. Charging at 13 A with 3 kW of PV, a 40-second reconnect of the load sensor's own integration was enough to write 16 A — real grid import — followed by an unnecessary stop once the sensor came back. The safety gate (`core_ready`) only ever guarded the start/stop decision, never the current. The surplus now falls back to 0 W whenever the PV or house-load reading is a sentinel, and the target current is frozen at the last commanded value for as long as any configured core sensor is missing, so a short outage changes nothing at all. A longer one still stops charging through the normal stop hysteresis.
- **The switch rate limit could block a stop — including the user's own "Stop" override — and failed writes consumed its budget.** Attempts were counted *before* the Modbus write was even attempted, so during a wallbox connection outage the repeated stop attempts used up all three slots of the 15-minute window; the real stop was then refused once the link came back, while the car kept drawing from the grid. Even without an outage, a plug-in → cloud → sun sequence exhausted the budget and a deliberate manual "Stop" was rejected for up to 12 more minutes. Stopping is now never rate-limited (it is always the safe direction), only starting is, and only a *confirmed* write counts against the budget.
- **A 1→3-phase up-switch kept the old single-phase current setpoint for the entire current-adjustment delay.** The target current is computed from the phase count of the current tick, so the tick that writes the phase change still carried the 1-phase value (up to `max_ampere`), which then flowed on three phases — up to three times the intended power, for up to `ampere_change_delay` (configurable to 10 minutes). The current is now forced down to the minimum in the same tick as any automatic phase change, deliberately in preference to recomputing it for the new phase count: the wallbox and car need several seconds for the switch itself, and the minimum is harmless in every intermediate combination. Normal hysteresis ramps back up afterwards.
- **After a stop, the wallbox kept its last commanded current and the next start ran at that stale value.** On a stop the integration set its internal current shadow to the minimum but never wrote it, and no code path wrote the current alongside a start — so a charge that had ended at 16 A restarted at 16 A and stayed there until the current hysteresis expired. The freshly computed target current is now written in the same tick as the start command.
- **A failed current write was silently never retried.** The internal shadow value was updated before the write was confirmed, so the deadband check immediately considered the new target reached. Both the state and current shadow values (including their rate-limit timestamps) are now rolled back when a write is refused or fails.
- **After a Home Assistant restart mid-charge, the integration assumed the wallbox was at 6 A.** The shadow value is now seeded once from the wallbox's own read-back register on the first successful poll. Deliberately only once — a continuous sync would also adopt changes made elsewhere.
- **Without the optional PV forecast sensor, the configured SOC levels were silently replaced by 80/90/95 and the correction factor was forced down every afternoon.** `pv_forecast` stays exactly `0.0` when the entity is not configured (an explicitly supported setup), which made both "poor forecast" conditions permanently true: a configured `min_soc` of 40 % never applied, charging never started below 80 % home-battery SOC, the correction factor dropped to 0 below that — and the status text just said "Waiting for PV surplus". Both forecast-dependent tightenings now only apply when a forecast entity is actually configured.
- **A wallbox overridden to "stop" blocked lower-priority wallboxes forever.** The stop-override path returned before `target_state` was updated, leaving it frozen at its pre-override value; a lower-priority box then waited indefinitely for a "higher-priority wallbox" that would never start. The override path now clears `target_state` and the arbitration flags, and the priority check additionally ignores peers whose "Control active" switch is off, since those can never turn their intent into an actual charge either.
- **The minimum interval between two switching operations was effectively a no-op.** It was measured from the moment the hysteresis wait *started* rather than from the actual change, so it was always already satisfied by the time the change happened. It is now measured from the real change — and, consistent with the rate limit above, applied to starts only. The German comment in `const.py` describing the old, unimplemented behaviour is corrected.
- Manual override below the home-battery SOC floor now says so ("Manual override blocked: home battery SOC too low") instead of the misleading "Waiting for PV surplus". The floor itself is intentional and unchanged — it protects the home battery. The generic SOC status text and the card colour also use the *effective* threshold now, so a forecast-tightened limit is reported honestly.
- A truncated Modbus response (e.g. byte count 0) raised an `IndexError` halfway through updating the wallbox state, leaving it partly stale and escaping the tick as an unhandled exception. Short responses are now reported as a regular `ModbusError`, so the poll is cleanly marked as failed.
- Modbus error messages always claimed the failure happened during "Verbindungsaufbau" (connection setup), even for read/write timeouts on an established connection, because the phase was tracked in a variable local to the framing helper. Timeouts now name the actual step.
- Unloading or reloading the entry could race with an in-flight poll and reopen the connection right after `close()`. Since the wallbox accepts only one Modbus TCP connection, the orphaned connection then locked out the new coordinator. The client now refuses to reconnect once closed.
- Notifications (charging start/stop, Modbus connection loss) no longer run inside the control tick. A slow or hanging Telegram API stalled the charging loop for that duration, including a due stop. The call is still awaited with `blocking=True` and its failures still logged — the 0.5.2 fix for silently swallowed send errors is preserved — just in its own task.
- `poll_interval`, `modbus_timeout` and `modbus_command_delay` had no range validation, unlike every other numeric option in the same dialog; a `poll_interval` of 0 made the scheduler fire on every event-loop iteration and log an overlap warning each time.
- The manual override current was capped at 16 A in both the number entity and the card, even on a 22 kW wallbox with `max_ampere` set to 32. Both now follow the configured maximum.
- Translations: `already_configured` was German in the English file; the `modbus_framing` hint still recommended `rtu` in German while English already had the corrected `mbap` recommendation; the optional battery/SOC sensors were only marked optional in English. The PV forecast field now states what happens without it.

### Changed

- The "saldo" surplus mode logs a debug line naming the missing value when it falls back to load mode for a tick — previously that fallback was completely invisible.
- Stale "(Test)" naming removed from module docstrings and from the card's entry in the Lovelace card picker; the Modbus client's comments no longer describe RTU as the likely-correct framing (MBAP is, and already was, the default).

## [0.5.6] - 2026-09-05

### Fixed

- **The options dialog could not be saved at all without a notify entity configured.** Every save failed with `Entity is neither a valid entity ID nor a valid UUID` on the "Notify entity" field, no matter which setting was actually being changed. The field was declared `vol.Optional(..., default="")`: the frontend drops an empty picker from the submission, voluptuous then filled the `""` default back in, and the `EntitySelector` rejected it as an invalid entity ID. Affected everyone without a notify entity set, since the option was introduced. The field now uses `suggested_value` instead of `default`, so an empty picker is simply omitted (= no notifications, as before). Same bug and fix as [ha-lacrosse-jeelink#3](https://github.com/Lu-Fi/ha-lacrosse-jeelink/issues/3).

## [0.5.5] - 2026-08-30

### Fixed

- Screenshot images on the HACS repository page were broken (`<img src="docs/...png">` relative paths, which github.com rewrites against the repo root but HACS's own README renderer does not). Switched to absolute `raw.githubusercontent.com` URLs.

## [0.5.4] - 2026-08-30

### Fixed

- **The reconfigure flow combined a config-entry `update_listener` with `async_update_reload_and_abort()`**, which is deprecated as of HA 2026.6 (double-reload/race risk) and becomes a hard error in 2026.12. Switched to `async_update_and_abort()` — the existing `update_listener` already reloads on every entry update, for both the options flow and reconfigure.

## [0.5.3] - 2026-08-26

### Fixed

- **"Konfigurationsfehler: Custom element doesn't exist: pvsc-card" could survive a full close-and-reopen of the tab.** The card was only registered via `add_extra_js_url`, which patches the frontend's HTML shell in memory - a mechanism the frontend's own service worker can poison: it serves the app shell Stale-While-Revalidate, so any navigation that lands inside the brief window between HA answering HTTP requests again and `async_setup_entry` actually running gets cached *without* the pvsc import, and every reopened tab keeps getting served that same stale, import-less shell until the service worker's background revalidation happens to catch up. The card is now additionally (primarily) registered as a real Lovelace storage-mode resource - the same mechanism HACS cards use - which the frontend loads dynamically per dashboard render over the websocket API, independent of the cached HTML shell. `add_extra_js_url` is kept only as a fallback for YAML-mode dashboards, which don't have storage resources. The now-unnecessary "please hard-reload" persistent notification is removed.

## [0.5.2] - 2026-08-21

Stable release consolidating the 0.5.2b1–b3 prereleases below.

### Added

- **Configurable phase-switching thresholds** (`car_charge_phases` option, `2` or `3`, default `3`): automatic 1↔3-phase switching (`switch.pvsc_phase_auto`) derives its up-/down-switch thresholds from how many phases the car actually draws when charging at the "3-phase" setting, instead of always assuming 3, and now also drives the target-current/fleet-power-budget calculation itself — a 2-phase-only car no longer has its target ampere/power systematically undershot by dividing by 3 real phases instead of 2 (closes #1).
- **Modbus connection-loss notification**: sends "connection lost"/"connection restored" via the same notify target as charging start/stop when the wallbox Modbus link drops for 3 consecutive failures.

### Fixed

- Notifications (charging start/stop, Modbus connection loss) now call `telegram_bot.send_message` with `parse_mode: plain_text` and wait for completion, instead of the generic `notify.send_message` action with `blocking=False` — the latter silently swallowed Telegram's `BadRequest: can't parse entities` failures on message text containing hyphens or periods.
- The `car_charge_phases` options-flow field now uses an explicit dropdown selector so its default value is visibly pre-selected.
- `hacs.json`'s declared Home Assistant floor raised from `2024.6.0` to `2026.3.0`, matching what `StaticPathConfig`/`async_register_static_paths` and the in-tree brand icons actually require.

## [0.5.2b3] - 2026-08-21 (prerelease)

### Fixed

- **`hacs.json` declared a Home Assistant floor (`2024.6.0`) the integration couldn't actually run on.** `__init__.py` imports `StaticPathConfig` and calls `hass.http.async_register_static_paths`, both introduced in 2024.7 — on the declared floor, setup would raise `ImportError` immediately. The in-tree brand icons need 2026.3 on top of that (already noted in the README). Raised the floor to `2026.3.0` to match reality.

## [0.5.2b2] - 2026-08-06 (prerelease)

### Fixed

- **`car_charge_phases` only fixed the phase-switching thresholds, not the actual target-current calculation** (follow-up report on #1): with a 2-phase-only car and the wallbox in 3-phase mode, `target_ampere` (and the multi-wallbox fleet-power-budget calculation) still divided the desired power by 3 real phases instead of 2, so the wallbox systematically undershot the available surplus — e.g. a 5182 W surplus only resulted in ~3.45 kW of actual draw instead of ~5.2 kW. Both calculations now use `min(wallbox_phases, car_charge_phases)` instead of the raw wallbox-reported phase count. The start/stop power threshold (`min_watts`) is adjusted the same way for consistency, though it only mattered for the narrow case of a 2-phase car with automatic phase switching turned off.

## [0.5.2b1] - 2026-08-03 (prerelease)

### Added

- **Configurable phase-switching thresholds** (`car_charge_phases` option, `2` or `3`, default `3`): automatic 1↔3-phase switching (`switch.pvsc_phase_auto`) derives its up-/down-switch thresholds from how many phases the car actually draws when charging at the "3-phase" setting, instead of always assuming 3. Some cars only ever use 2 phases even when 3 are offered, for which the fixed thresholds didn't match the real achievable minimum (closes #1).
- **Modbus connection-loss notification**: sends "connection lost"/"connection restored" via the same notify target as charging start/stop when the wallbox Modbus link drops for `MODBUS_NOTIFY_THRESHOLD` (3) consecutive failures. While down, the wallbox keeps charging at its last successfully written ampere/state — PV and load keep changing in the background, but the hardware never sees the new target, which was otherwise invisible until someone checked the Modbus diagnostic sensors.

### Fixed

- Charging start/stop and the new Modbus connection notification now call `telegram_bot.send_message` with `parse_mode: plain_text` and wait for completion, instead of the generic `notify.send_message` action with `blocking=False`. That combination sent Markdown-parsed messages that silently failed (Telegram `BadRequest: can't parse entities`) whenever the text contained hyphens or periods — common in these messages — with the failure swallowed in a detached background task instead of being logged.
- The `car_charge_phases` options-flow field didn't visually pre-select its default value (rendered as radio buttons via a plain `vol.In`, unlike the sliders/number fields elsewhere in the same form). Now an explicit dropdown selector.

## [0.5.1b1] - 2026-07-08 (prerelease)

### Added

- The bundled Lovelace card (`custom:pvsc-card`) is auto-registered via `frontend.add_extra_js_url`, which only takes effect for browser tabs/apps that load the frontend *after* the registration runs — an in-memory step redone on every HA restart. Tabs/apps already open across a restart don't know about it and show "Configuration error: Custom element doesn't exist: pvsc-card" until reloaded. The integration now creates a persistent notification ("PVSC: Karte neu geladen - Browser/App neu laden") every time it (re-)registers the card at startup, explaining that a hard reload (Ctrl+Shift+R / restart the companion app) is needed — instead of silently leaving affected dashboards broken.

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
