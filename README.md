# EM2GO Home PV Surplus Charging (pvsc)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/Lu-Fi/ha-em2go-pvsc.svg)](https://github.com/Lu-Fi/ha-em2go-pvsc/releases)
[![Downloads](https://img.shields.io/github/downloads/Lu-Fi/ha-em2go-pvsc/total.svg)](https://github.com/Lu-Fi/ha-em2go-pvsc/releases)

Home Assistant custom integration that controls an **EM2GO Home wallbox** via Modbus TCP for **PV surplus charging** — the wallbox charges your EV with exactly the solar power you would otherwise export to the grid.

*Deutsche Beschreibung weiter unten.*

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
- UI: German and English

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

---

### Manual (without HACS)

Copy the `custom_components/pvsc/` folder into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

---

## Configuration

All configuration happens in the UI. During setup you choose:

- Wallbox Modbus host/port (unit ID 255 is the default — do not change it for an EM2GO)
- Your sensor entities: PV power, house load, grid import/export (required); home battery charge/discharge/SOC, PV forecast, car SOC/location (optional)
- Whether control is active immediately after startup (default: off = shadow mode)

Runtime tuning (gear icon → Configure): notifications, max charging current (16 A for the 11 kW model, 32 A for 22 kW), max house load, battery limits, poll interval, Modbus timing.

All values set via the switch/number/select entities below (SOC thresholds, correction factor, ampere deadband, phase-switch automation, surplus mode, override mode/amps/phases, automation on/off) are persisted to storage and survive Home Assistant restarts and integration updates. Use the "Reset to defaults" button to restore them to their factory values in one step (the "Control active" safety switch is intentionally left untouched by this button).

## Entities

The integration creates a device "EM2GO Home Wallbox" with sensors (PV, load, surplus, target amps, wallbox state/power/energy, diagnostics), switches (control active, automation enabled, auto correction factor), numbers (SOC thresholds, manual correction factor, overrides), selects (override mode/phases, surplus calculation mode), a status text sensor, and buttons (reset stop cause, reset to defaults).

Note: the status text sensor and notification messages are currently German.

## Branding

The integration ships its own brand images (`custom_components/pvsc/brand/`) — supported since Home Assistant 2026.3, no `home-assistant/brands` submission required. On older HA versions the tile simply falls back to the default icon.

## Disclaimer

This is a community project, not affiliated with EM2GO. You are controlling real charging hardware — use at your own risk.

---

## Deutsch

Home-Assistant-Integration für **PV-Überschussladen mit der EM2GO Home Wallbox** (lokal per Modbus TCP, keine Cloud). Der Ladestrom folgt dem PV-Überschuss; optional mit Heimspeicher-Logik (SOC-Stufen, Batterie-Unterstützung, automatischer Korrekturfaktor), funktioniert aber auch ohne Hausbatterie. Override-Modi (PV/Manuell/Stop), Ein-/Ausschalt-Hysterese, Ampere-Rampe mit Totband, Rate-Limit und optionale Benachrichtigungen bei Ladestart/-stopp über eine beliebige notify-Entity. Einrichtung komplett über die UI (deutsch/englisch); eine Lovelace-Card liegt bei.

Alle über die Schalter/Zahlen/Auswahl-Entities gesetzten Werte (SOC-Stufen, Korrekturfaktor, Ampere-Totband, Phasen-Automatik, Überschussmodus, Override, Automatik an/aus) werden gespeichert und überstehen HA-Neustarts sowie Updates der Integration. Der Button "Auf Werkseinstellungen zurücksetzen" setzt sie mit einem Klick auf die Werksdefaults zurück (der Sicherheits-Schalter "Steuerung aktiv" bleibt davon bewusst unberührt).

Die EM2GO-Eigenheiten (nur Unit-ID 255, Schreiben nur per FC16, nur eine Modbus-Session, mehrminütige Verriegelung nach Verbindungsabbrüchen) sind in der Integration berücksichtigt.
