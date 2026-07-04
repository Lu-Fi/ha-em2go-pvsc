# EM2GO Home PV Surplus Charging (pvsc)

Home Assistant custom integration that controls an **EM2GO Home wallbox** via Modbus TCP for **PV surplus charging** — the wallbox charges your EV with exactly the solar power you would otherwise export to the grid.

*Deutsche Beschreibung weiter unten.*

## Features

- Direct local Modbus TCP control of the EM2GO Home wallbox (no cloud)
- PV surplus calculation from your existing sensors (PV power, house load, grid import/export)
- Optional home battery support: SOC-based charging thresholds, battery assist, automatic correction factor
- Works **without** a home battery (fixed correction factor, no SOC gating)
- Override modes: PV automatic, manual (fixed amps/phases), stop
- Start/stop hysteresis (3 min), amp ramping with deadband, rate limiting (max. 3 switch operations per 15 min)
- Optional notifications on charge start/stop via any `notify` entity (Telegram, mobile app, …)
- Shadow mode: observe and simulate decisions without writing to the wallbox
- Companion Lovelace card (`pvsc-card.js`) included
- UI: German and English

## EM2GO Modbus quirks (handled by this integration)

These cost us some debugging, so they are documented here:

- The wallbox responds **only to unit ID 255** (unit 0 = no response, others = connection drop)
- Standard **Modbus TCP (MBAP)** framing; writes must use **FC16** (Write Multiple Registers) — FC6 is ignored and can stall the session
- Only **one Modbus TCP session** at a time; after abrupt disconnects the Modbus stack locks up for a few minutes (TCP connect accepted but no responses). The integration handles this with a persistent connection, serialized requests, exponential backoff, and transaction-ID resynchronization.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → Custom repositories → add this repository (category: Integration)
2. Install "EM2GO Home PV-Überschussladen"
3. Restart Home Assistant
4. Settings → Devices & Services → Add Integration → search "EM2GO"

### Manual

Copy `custom_components/pvsc/` into your Home Assistant `config/custom_components/` folder and restart.

## Configuration

All configuration happens in the UI. During setup you choose:

- Wallbox Modbus host/port (unit ID 255 is the default — do not change it for an EM2GO)
- Your sensor entities: PV power, house load, grid import/export (required); home battery charge/discharge/SOC, PV forecast, car SOC/location (optional)
- Whether control is active immediately after startup (default: off = shadow mode)

Runtime tuning (gear icon → Configure): notifications, max charging current (16 A for the 11 kW model, 32 A for 22 kW), max house load, battery limits, poll interval, Modbus timing.

## Entities

The integration creates a device "EM2GO Home Wallbox" with sensors (PV, load, surplus, target amps, wallbox state/power/energy, diagnostics), switches (control active, automation enabled, auto correction factor), numbers (SOC thresholds, manual correction factor, overrides), selects (override mode/phases, surplus calculation mode) and a status text sensor.

Note: the status text sensor and notification messages are currently German.

## Disclaimer

This is a community project, not affiliated with EM2GO. You are controlling real charging hardware — use at your own risk.

---

## Deutsch

Home-Assistant-Integration für **PV-Überschussladen mit der EM2GO Home Wallbox** (lokal per Modbus TCP, keine Cloud). Der Ladestrom folgt dem PV-Überschuss; optional mit Heimspeicher-Logik (SOC-Stufen, Batterie-Unterstützung, automatischer Korrekturfaktor), funktioniert aber auch ohne Hausbatterie. Override-Modi (PV/Manuell/Stop), Ein-/Ausschalt-Hysterese, Ampere-Rampe mit Totband, Rate-Limit und optionale Benachrichtigungen bei Ladestart/-stopp über eine beliebige notify-Entity. Einrichtung komplett über die UI (deutsch/englisch); eine Lovelace-Card liegt bei.

Die EM2GO-Eigenheiten (nur Unit-ID 255, Schreiben nur per FC16, nur eine Modbus-Session, mehrminütige Verriegelung nach Verbindungsabbrüchen) sind in der Integration berücksichtigt.
