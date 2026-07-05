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
- Start/stop hysteresis (3 min), amp ramping with deadband, rate limiting (max. 3 switch operations per 15 min)
- Optional notifications on charge start/stop via any `notify` entity (Telegram, mobile app, …)
- Safe observation: the wallbox state is always read via Modbus, but the integration only writes while the "Control active" switch is on — turn it off to watch and simulate decisions without touching the hardware
- Companion Lovelace card included and auto-registered — just add a card of type `custom:pvsc-card` to any dashboard (no manual resource setup needed)
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

### Setup wizard (one-time)

Set when you first add the integration (**Settings → Devices & Services → Add Integration**). There is currently no "reconfigure" step, so changing any of these later means removing and re-adding the integration.

| Setting | Description |
|---|---|
| Wallbox Modbus TCP host | IP address or hostname of the EM2GO Home wallbox. |
| Modbus TCP port | Default `502`, the standard Modbus TCP port. |
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
| Start delay (s) | How long the surplus must exceed the minimum before charging actually starts (hysteresis against brief spikes), default `180` (3 min), range `60`–`1800` (1–30 min). |
| Stop delay (s) | How long the surplus must be insufficient before charging actually stops, default `60` (1 min, reduced from 3 min in 0.5.0b5 — reacts faster to a genuine drop, e.g. a house-load spike, instead of holding minimum current for 3 minutes first), range `60`–`1800` (1–30 min). |
| Current adjustment delay (s) | How long the target current must differ from the current setpoint before the wallbox is actually told to change it, default `30`, range `30`–`600` (0.5–10 min). |

Note: an additional fixed 3-minute rate limit between two state changes, and a fixed 30-second rate limit between two current adjustments, apply on top of the delays above regardless of how you configure them — see the code comments in `const.py` (`STATE_CHANGE_INTERVAL`, `AMPERE_CHANGE_INTERVAL`) if you need to change those too.

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
| Amps deadband (`number.pvsc_ampere_deadband`, default `0.1 A`) | Minimum change in the target current before the wallbox setpoint is actually adjusted — avoids constant micro-adjustments. |
| Override: amps / Override phases (`number.pvsc_override_ampere`, `select.pvsc_override_phases`) | Fixed current/phase count used only while override mode is "manual". |
| Test: forced amps (`number.pvsc_forced_ampere`, default `0` = off) | When set above 0, forces the maximum configured current regardless of actual surplus — for testing the wallbox/wiring, not for normal use. |
| Override mode (`select.pvsc_override_mode`) | `pv` (default, automatic PV-surplus logic), `manual` (fixed current/phases from the two settings above), or `stop` (force charging off, ignoring everything else). |
| Surplus calculation (`select.pvsc_surplus_mode`) | `load` (default): surplus = PV power − house load, both from your configured sensors. `saldo`: surplus derived instead from grid export/import plus battery charge/discharge and the wallbox's own current draw — useful if you don't have a clean whole-house load sensor but do have reliable grid meters. Falls back to `load` automatically if any of the saldo inputs report a negative/invalid reading. |
| Reset stop cause (`button.pvsc_reset_stop_cause`) | Clears the current stop-cause value (also happens automatically overnight, 0:00–5:00). |
| Reset to defaults (`button.pvsc_reset_defaults`) | Resets all of the above (except "Control active") to the factory defaults listed in this table. |


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
