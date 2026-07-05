# EM2GO Home PV Surplus Charging (pvsc)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/Lu-Fi/ha-em2go-pvsc.svg)](https://github.com/Lu-Fi/ha-em2go-pvsc/releases)
[![Downloads](https://img.shields.io/github/downloads/Lu-Fi/ha-em2go-pvsc/total.svg)](https://github.com/Lu-Fi/ha-em2go-pvsc/releases)

Home Assistant custom integration that controls an **EM2GO Home wallbox** via Modbus TCP for **PV surplus charging** — the wallbox charges your EV with exactly the solar power you would otherwise export to the grid.

## Features

- Direct local Modbus TCP control of the EM2GO Home wallbox (no cloud)
- PV surplus calculation from your existing sensors (PV power, house load, grid import/export)
- Optional home battery support: SOC-based charging thresholds, battery assist, automatic correction factor
- Works **without** a home battery (fixed correction factor, no SOC gating)
- Override modes: PV automatic, manual (fixed amps/phases), stop
- Optional automatic 1↔3 phase switching with hysteresis (5 min above ~4.8 kW → 3 phases, 5 min below ~4.1 kW → back to 1 phase)
- Start/stop hysteresis, current-adjustment delay and amps deadband, configurable per wallbox via the entry's Options dialog; amp ramping, rate limiting (max. 3 switch operations per 15 min)
- Optional notifications on charge start/stop via any `notify` entity (Telegram, mobile app, …)
- Safe observation: the wallbox state is always read via Modbus, but the integration only writes while the "Control active" switch is on — turn it off to watch and simulate decisions without touching the hardware
- Companion Lovelace card included and auto-registered — just add a card of type `custom:pvsc-card` to any dashboard (no manual resource setup needed); the card has a visual editor with a wallbox dropdown (or set the `prefix` option in YAML) to bind it to a specific wallbox
- Multiple wallboxes supported: one config entry per wallbox, each with its own entity ID prefix, its own live settings, options and delays
- Config UI and all dynamically generated texts (status, stop cause, notifications) available in German and English, following Home Assistant's system language automatically — see [Language behaviour](#language-behaviour) below
- All "live" settings (SOC thresholds, correction factor, overrides, automation on/off, …) persist across Home Assistant restarts and integration updates, with a one-click "Reset to defaults" button

## EM2GO Modbus quirks (handled by this integration)

These cost us some debugging, so they are documented here:

- The wallbox responds **only to unit ID 255** (unit 0 = no response, others = connection drop)
- Standard **Modbus TCP (MBAP)** framing; writes must use **FC16** (Write Multiple Registers) — FC6 is ignored and can stall the session
- Only **one Modbus TCP session** at a time; after abrupt disconnects the Modbus stack locks up for a few minutes (TCP connect accepted but no responses). The integration handles this with a persistent connection, serialized requests, exponential backoff, and transaction-ID resynchronization.

## Installation

### Via HACS (recommended)

> **HACS** (Home Assistant Community Store) must be installed. If not yet set up: [hacs.xyz](https://hacs.xyz)

#### Step 1 – Add the custom repository

1. Open HACS in the Home Assistant sidebar
2. Click the **three-dot menu (⋮)** in the top right → **"Custom repositories"**
3. Enter the repository URL:
   ```
   https://github.com/Lu-Fi/ha-em2go-pvsc
   ```
4. Select category **"Integration"** → click **"Add"**

#### Step 2 – Install the integration

5. In HACS → Integrations, search for **"EM2GO"**
6. Open the integration → click **"Download"**
7. **Restart Home Assistant**

#### Step 3 – Set up the integration

8. **Settings → Devices & Services → Add Integration** → search for "EM2GO"
9. Follow the setup wizard (Modbus host, sensor entities, etc.)

### Manual (without HACS)

Copy the `custom_components/pvsc/` folder into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Settings reference

Settings live in three places, with different rules for changing them later.

### Setup wizard (changeable via "Reconfigure")

Set when you first add the integration (**Settings → Devices & Services → Add Integration**). Since 0.5.0b7 they can be changed later without re-adding: open the integration entry's three-dot menu → **"Reconfigure"**. The form comes pre-filled with the current values; clearing an optional entity field removes it. Live settings (SOC thresholds, delays, overrides, …) survive a reconfigure.

| Setting | Description |
|---|---|
| Wallbox Modbus TCP host | IP address or hostname of the EM2GO Home wallbox. |
| Modbus TCP port | Default `502`, the standard Modbus TCP port. |
| Entity ID prefix | Object-ID prefix for every entity of this entry (default `pvsc` → `sensor.pvsc_status_text`, …). For a **second wallbox**, pick a distinct prefix like `pvsc_garage` so its entities get clean unique IDs instead of `_2` suffixes. Must be unique per entry. Changing it later via Reconfigure renames the entry's entities accordingly (entities you renamed by hand are left alone) — remember to update dashboards/automations that reference the old IDs. |
| Modbus unit ID | Default and required `255` — confirmed by direct testing that the EM2GO only responds on unit 255 (unit 0 gets no response, others drop the connection). Don't change this. |
| Enable control immediately after startup | Whether the "Control active" safety switch starts on or off right after this initial setup. Default is off (shadow mode: read-only, nothing is written to the wallbox until you flip the switch yourself). This only matters for the very first startup — from then on, whatever you've set the switch to is remembered across restarts and updates. |
| PV power / house load / grid import / grid export sensors | **Required.** Your existing power sensors (W) that feed the surplus calculation. |
| Home battery charge power / discharge power / SOC sensors | Optional. Enables the battery-assist logic (SOC thresholds, correction factor, battery-supported charging). Without a home-SOC sensor, the whole SOC/battery logic is neutralized — the integration behaves as if there were no home battery at all (fixed correction factor, no SOC gating). |
| PV forecast for the rest of the day (kWh) | Optional. When the forecast is low relative to the battery's remaining capacity, the SOC thresholds (`min_soc`/`optimal_soc`/`high_soc`) are temporarily tightened to 80/90/95 % to conserve the home battery. |
| Car SOC / car charge end time / car charging power | Optional, display-only sensors — no effect on charging decisions. |
| Car location (device tracker) | Optional. If set, charging additionally requires the tracker to report "home" — useful if your PV/load sensors can't otherwise tell whether the car is actually there. |

### Options (gear icon → "Configure", changeable anytime)

| Setting | Description |
|---|---|
| Send notification on charge start/stop | Turns the `notify` message on/off. |
| Notify entity | Target `notify.*` entity for those messages (Telegram, mobile app, …). Empty = no messages regardless of the toggle above. |
| Maximum total house load (W) | Upper bound used together with battery-assist watts to decide whether the home battery is allowed to help — default `4200`. |
| Battery capacity (kWh) | Your home battery's usable capacity — used only to scale the PV-forecast check above, default `6.9`. |
| Maximum battery discharge power (W) | Safety cap: battery assist is withdrawn if the home battery's own discharge is already at/above this, default `3000`. |
| Maximum inverter output power (W) | Only relevant if a separate inverter-PV sensor is configured; caps battery assist so combined inverter output doesn't exceed this, default `4800`. |
| Poll interval (s) | How often the Modbus registers are read and the surplus recalculated, default `7`. |
| Modbus timeout / command delay / reconnect backoff / connect settle delay | Low-level Modbus TCP timing, tuned to match the EM2GO's known quirks (see above) — leave these alone unless you're troubleshooting connection issues. |
| Modbus framing | `mbap` (standard Modbus TCP, correct for the EM2GO) or `rtu` (raw RTU frames) — a test fallback, not normally needed. |
| Maximum charging current (A) | `16` for the 11 kW wallbox, `32` for the 22 kW model. |
| Start delay (s) | How long the surplus must exceed the minimum before charging actually starts (hysteresis against brief spikes), default `180` (3 min), range `60`–`1800`. |
| Stop delay (s) | How long the surplus must be insufficient before charging actually stops, default `60` (1 min), range `60`–`1800`. |
| Current adjustment delay (s) | How long the target current must differ from the current setpoint before the wallbox is actually told to change it, default `30`, range `30`–`600`. |
| Amps deadband (A) | Minimum change in the target current before the wallbox setpoint is actually adjusted — avoids constant micro-adjustments. Default `0.1`, range `0.05`–`2`. |
| Charging priority | Only relevant with multiple wallboxes — see [Load sharing](#load-sharing-between-multiple-wallboxes). `1` = highest, default `1`. |
| Fleet power limit (W) | Optional cap on the combined power of **all** wallboxes, `0` = off. See [Load sharing](#load-sharing-between-multiple-wallboxes). |

Notes: an additional fixed 3-minute rate limit between two state changes, and a fixed 30-second rate limit between two current adjustments, apply on top of the delays above regardless of how you configure them (`STATE_CHANGE_INTERVAL`, `AMPERE_CHANGE_INTERVAL` in `const.py`). Between 0.5.0b6 and 0.5.0b9 the delays and deadband were number entities; values set there keep working as fallback until the Options dialog is saved once, and the old number entities are cleaned up automatically.

### Load sharing between multiple wallboxes

With several wallboxes fed by the same PV/load/grid sensors, each entry computes its surplus with only its **own** wallbox power removed — so the boxes naturally compete for the same surplus without double-counting it. Since 0.5.0b11 this competition is arbitrated via the **Charging priority** option (1 = highest):

- **Start order:** a lower-priority box does not start while a higher-priority box wants to charge but hasn't started yet (its start hysteresis is still running). Status shows *"Waiting for higher-priority wallbox"*.
- **Yield order:** power currently drawn by lower-priority boxes counts as *reclaimable* for a higher-priority box's start/stop decision. When surplus drops, the lower-priority box sees the deficit and stops first (after its stop delay); the higher-priority box holds on and picks up the freed power as its measured surplus recovers.
- **Fleet power limit:** optional cap (W) on the combined draw of all wallboxes; the budget goes to higher priorities first, and it also caps the manual override (safety before convenience). Status shows *"Waiting: fleet power limit reached"* when a box gets no budget. Since options are stored per entry, the **lowest** value configured on any entry applies — best set the same value everywhere.

Boxes with equal priority behave like before (independent, first-come-first-served). Priority arbitration applies only in PV mode; a manual override is a deliberate user decision and is only constrained by the fleet limit.

### Live entities (switches/numbers/selects — persisted, resettable)

These are the entities you'll interact with day to day. Since version 0.5.0b1 their values are saved to storage and survive restarts and integration updates; the **"Reset to defaults" button** restores them to the factory values below in one step (it deliberately leaves "Control active" untouched, see below).

| Entity | Description |
|---|---|
| Control active (`switch.pvsc_control_enabled`) | The master safety switch. While off, the integration only reads the wallbox and computes what it *would* do — nothing is written. While on, it actually starts/stops charging and adjusts current/phases. |
| Surplus automation enabled (`switch.pvsc_enabled`) | Turns the automatic PV-surplus logic on/off; charging won't start while this is off. |
| Automatic correction factor (`switch.pvsc_correction_auto`) | When on (default), the correction factor is derived automatically from home battery SOC (see below). When off, the manual "Correction factor" number is used instead. |
| Automatic phase switching (`switch.pvsc_phase_auto`) | When on, the wallbox switches 1↔3 phases automatically based on sustained surplus (5 min above ~4.8 kW → 3 phases, 5 min below ~4.1 kW → back to 1 phase). Default off: always 1-phase in PV mode. |
| Min. SOC (`number.pvsc_min_soc`, default `40 %`) | The real safety floor. Below this, charging is blocked outright and the correction factor is forced to 0 — see the [Status texts & stop-cause reference](#status-texts--stop-cause-reference) for how this is reported. |
| Optimal SOC (`number.pvsc_optimal_soc`, default `80 %`) | Between `min_soc` and this value, charging runs on PV only — the home battery is deliberately **not** allowed to top up the car (correction factor 0.75). Above it, battery assist becomes available. |
| High SOC (`number.pvsc_high_soc`, default `90 %`) | Above this, the correction factor goes up to 1.05 (using slightly more than the raw surplus, effectively also drawing a little from the battery), or down to 0.9 in the evening (after 15:00) if the PV forecast for the rest of the day is poor (<5 kWh), to avoid needlessly draining a battery that won't get refilled today. |
| Correction factor (manual) (`number.pvsc_correction_factor`, default `75 %`) | Used instead of the automatic tiers above when "Automatic correction factor" is off. |
| Override: amps / Override phases (`number.pvsc_override_ampere`, `select.pvsc_override_phases`) | Fixed current/phase count used only while override mode is "manual". |
| Override mode (`select.pvsc_override_mode`) | `pv` (default, automatic PV-surplus logic), `manual` (fixed current/phases from the two settings above), or `stop` (force charging off, ignoring everything else). |
| Surplus calculation (`select.pvsc_surplus_mode`) | `load` (default): surplus = PV power − house load, both from your configured sensors. `saldo`: surplus derived instead from grid export/import plus battery charge/discharge and the wallbox's own current draw — useful if you don't have a clean whole-house load sensor but do have reliable grid meters. Falls back to `load` automatically if any of the saldo inputs report a negative/invalid reading. |
| Reset stop cause (`button.pvsc_reset_stop_cause`) | Clears the current stop-cause value (also happens automatically overnight, 0:00–5:00). |
| Reset to defaults (`button.pvsc_reset_defaults`) | Resets all of the above (except "Control active") to the factory defaults listed in this table. Options-flow settings (delays, deadband, …) are not touched. |

## Sensor reference (all values shown in the UI)

Every sensor the integration creates, i.e. everything you can see on the device page or place on a dashboard (the bundled `custom:pvsc-card` displays a subset of these). All power/current values are refreshed every poll interval (default 7 s). Entity IDs below use the default entity ID prefix `pvsc` — with a custom prefix (multi-wallbox), substitute accordingly (e.g. `sensor.pvsc_garage_status_text`).

### Calculation sensors (own surplus logic)

| Entity | Description |
|---|---|
| PV power (`sensor.pvsc_pv`, W) | The PV production as used by the calculation — a mirror of your configured PV sensor. |
| House load (`sensor.pvsc_load`, W) | House consumption **excluding** the wallbox: configured load sensor minus current wallbox power. In `saldo` mode it is derived from PV minus the saldo surplus instead. |
| PV surplus (house) (`sensor.pvsc_surplus`, W) | Raw PV surplus before correction (PV − house load, floored at 0). While the car is charging, the portion allotted to the car (`car_surplus`) is subtracted, so this shows what's left for the house/grid. |
| Surplus for car (`sensor.pvsc_car_surplus`, W) | The power actually offered to the car: raw surplus × correction factor + battery assist. This drives the target current. |
| Target amps (`sensor.pvsc_target_ampere`, A) | The current the logic *wants* to set, derived from `car_surplus` / (230 V × phases), clamped to 6 A…max. Ramps toward it are subject to deadband and the current-adjustment delay. |
| Current amps (setpoint) (`sensor.pvsc_ampere`, A) | The setpoint the integration last committed (or will commit) to the wallbox — may lag behind the target while delays/deadband hold a change back. Note the chain: *Target amps* is what the logic wants, *Current amps (setpoint)* is what was actually commanded, and *Current limit (actual)* below is what the wallbox confirms — none of them is the actual charging current (see *Power*; the car may draw less than allowed). |
| Correction factor (`sensor.pvsc_correction_faktor`) | The factor currently applied to the raw surplus: automatic SOC tiers (0 / 0.75 / 0.9 / 1.0 / 1.05), the manual value, or fixed 1.0 without a home battery. |
| Battery assist (`sensor.pvsc_battery_support_watts`, W) | How much the home battery is currently allowed to contribute on top of the PV surplus (0 unless SOC is above the "High SOC" tier and all safety caps pass). |
| Battery usage Ø 15 min (`sensor.pvsc_battery_avg`, W) | 15-minute rolling average of the *calculated* shortfall (`min_watts − car_surplus`) — used for the "High battery usage" stop cause (> 500 W). See the subtlety note below the stop-cause table. |
| Status (`sensor.pvsc_status_text`) | Short plain-text summary of what the logic is doing — full list of possible texts in the [status table](#status-texts--stop-cause-reference) below. |
| Stop cause (`sensor.pvsc_stop_cause`) | Why charging was last stopped — full list in the [stop-cause table](#status-texts--stop-cause-reference) below. Cleared overnight (0–5 h) or via the reset button. |

### Wallbox sensors (read directly via Modbus)

| Entity | Description |
|---|---|
| Status code (`sensor.pvsc_em2go_state`) | Raw wallbox state register: `0` unknown, `1` ready, `2` connected, `3` starting, `4` charging, `5` error, `6` charging finished. |
| Status (wallbox) (`sensor.pvsc_em2go_state_text`) | The same state as human-readable text (language follows the HA system language). |
| Power (`sensor.pvsc_em2go_power`, W) | Actual charging power currently drawn through the wallbox. |
| Current limit (actual) (`sensor.pvsc_em2go_ampere`, A) | The current limit the wallbox itself reports right now — useful to verify a written setpoint actually arrived. |
| Phases (`sensor.pvsc_em2go_phases`) | Phase mode the wallbox reports (1 or 3). |
| Meter reading (`sensor.pvsc_em2go_energy`, kWh) | Lifetime energy meter of the wallbox. |
| Charged (current session) (`sensor.pvsc_em2go_session_kwh`, kWh) | Energy delivered in the current/most recent charging session; resets to 0 when a new session starts. |

### Car sensors (display-only mirrors)

Only created from your optionally configured car entities; no effect on charging decisions.

| Entity | Description |
|---|---|
| Car state of charge (`sensor.pvsc_car_soc`, %) | Mirror of the configured car-SOC sensor. |
| Car charge end (`sensor.pvsc_car_end`) | Mirror of the configured charge-end-time sensor. |

### Binary sensors

| Entity | Description |
|---|---|
| Plug connected (`binary_sensor.pvsc_plug_connected`) | A cable/vehicle is plugged in (wallbox plug register = 1). |
| Charging (actual) (`binary_sensor.pvsc_charging`) | The wallbox is actually charging right now (state 3 or 4) — reflects reality, regardless of who is controlling. |
| Should charge (own logic) (`binary_sensor.pvsc_target_charging`) | What the surplus logic has decided: on means "conditions for charging are met". Comparing this with "Charging (actual)" shows pending start/stop decisions waiting out their delay. |
| Car at home (`binary_sensor.pvsc_car_home`) | The configured car device tracker reports "home". Only meaningful if a tracker is configured. |
| Modbus connected (`binary_sensor.pvsc_modbus_connected`) | The last Modbus poll of the wallbox succeeded. |

### Diagnostic entities

| Entity | Description |
|---|---|
| Wallbox data source (`sensor.pvsc_modbus_status`) | `OK`, or the last Modbus error message while the connection is failing. |
| Modbus consecutive failures (`sensor.pvsc_modbus_consecutive_failures`) | Number of Modbus polls that have failed in a row (0 when healthy); drives the exponential reconnect backoff. |
| Modbus next retry in (`sensor.pvsc_modbus_retry_in`, s) | Seconds until the next reconnect attempt while in backoff/cool-down (0 when healthy). |
| Modbus errors (24 h) (`sensor.pvsc_modbus_errors_24h`) | Number of real Modbus errors in the last 24 hours (cool-down ticks don't count — they are consequences of an already-counted error). In-memory: resets on a Home Assistant restart. |

## Status texts & stop-cause reference

`sensor.pvsc_status_text` shows the current state as short plain text (see [Language behaviour](#language-behaviour)), evaluated top to bottom (first match wins):

| German | English | Meaning |
|---|---|---|
| Warte auf Sensordaten | Waiting for sensor data | At least one required core sensor (PV, load, import/export, battery, home SOC) hasn't delivered a real value yet (e.g. right after a restart). |
| Gestoppt (Override) | Stopped (override) | The override select is set to "stop". |
| Kein Fahrzeug angeschlossen | No vehicle connected | No car plugged in. |
| Lädt [manuell] mit X A[, Ziel Y A] | Charging [manually] at X A[, target Y A] | Actively charging; "manually" if override mode is "manual"; the target current is only shown while it differs from the current one (ampere ramps up/down gradually). |
| Start geplant | Start scheduled | Conditions for charging are met, waiting out the start hysteresis (3 min) before switching on. |
| Automatik deaktiviert | Automation disabled | The "Surplus automation enabled" switch is off. |
| Gestoppt: `<reason>` | Stopped: `<reason>` | Charging just stopped; see the stop-cause table below for the reason. |
| Laden beendet | Charging finished | The wallbox itself reports the charging session as finished (state code 6). |
| Wartet: Heimspeicher-SOC zu niedrig | Waiting: home battery SOC too low | Home battery SOC is below `min_soc`, so charging is held back by design (the true safety floor from setup). |
| Wartet auf PV-Überschuss | Waiting for PV surplus | Everything else: simply not enough PV surplus right now. |

If "Control active" (`switch.pvsc_control_enabled`) is off, every text is prefixed with **"Steuerung aus: " / "Control off: "** — the integration only reads and calculates, it isn't writing to the wallbox.

`sensor.pvsc_stop_cause` (and the "Reason" field in charge-stop notifications) records **why charging was last stopped**, decided in this order at the moment charging switches off:

| German | English | Meaning |
|---|---|---|
| Kein Abbruch | No stop | No stop event yet, or the stop was due to something with its own status text (automation switched off mid-charge, wallbox reported "charging finished", car left the configured location, or a core sensor dropped out) rather than a PV/battery limit. |
| Hohe Batterienutzung | High battery usage | The home battery had been discharging heavily (>500 W average over the last 15 min) to help feed the car — considered a critical draw regardless of SOC. |
| SOC zu niedrig | SOC too low | Home battery SOC dropped below `min_soc` — the actual configured floor below which charging is blocked outright. |
| Zu wenig PV-Überschuss | Insufficient PV surplus | Plain and simple: not enough PV surplus to keep the car's minimum current (6 A × phases × 230 V) fed. This is also shown when SOC sits between `min_soc` and `optimal_soc` — in that band the battery is deliberately not allowed to top up the car, so a shortfall there is a PV problem, not a battery-SOC problem. |

Before version 0.5.0b2, any shortfall while SOC was below `optimal_soc` was reported as "SOC too low" as long as there had recently been a meaningful calculated battery contribution — even though the real floor `min_soc` wasn't actually breached. That's fixed: "SOC too low" is now reserved for an actual `soc < min_soc` situation; everything else that boils down to "not enough power available" is labelled "Insufficient PV surplus".

One more subtlety: `sensor.pvsc_battery_avg` (used for the "High battery usage" threshold) is a 15-minute rolling average of the *calculated* shortfall (`min_watts - car_surplus`) sampled every tick — including ticks where the SOC band already forced actual battery support back to 0. So `battery_avg` can read high even in ticks where the battery wasn't really asked to contribute; treat it as "how much extra power would have been needed", not as a literal battery discharge measurement.

## Branding

The integration ships its own brand images (`custom_components/pvsc/brand/`) — supported since Home Assistant 2026.3, no `home-assistant/brands` submission required. On older HA versions the tile simply falls back to the default icon.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Disclaimer

This is a community project, not affiliated with EM2GO. You are controlling real charging hardware — use at your own risk.
