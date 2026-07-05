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

## Status texts & stop-cause reference

`sensor.pvsc_status_text` shows the current state as short German plain text, evaluated top to bottom (first match wins):

- **Warte auf Sensordaten** – waiting for sensor data: at least one required core sensor (PV, load, import/export, battery, home SOC) hasn't delivered a real value yet (e.g. right after a restart).
- **Gestoppt (Override)** – the override select is set to "stop".
- **Kein Fahrzeug angeschlossen** – no car plugged in.
- **Lädt [manuell] mit X A[, Ziel Y A]** – actively charging; "manuell" if override mode is "manual"; the target current is only shown while it differs from the current one (ampere ramps up/down gradually).
- **Start geplant** – conditions for charging are met, waiting out the start hysteresis (3 min) before switching on.
- **Automatik deaktiviert** – the "Überschuss-Automatik" switch is off.
- **Gestoppt: `<stop cause>`** – charging just stopped; see the stop-cause table below for the reason.
- **Laden beendet** – the wallbox itself reports the charging session as finished (state code 6).
- **Wartet: Heimspeicher-SOC zu niedrig** – home battery SOC is below `min_soc`, so charging is held back by design (the true safety floor from setup).
- **Wartet auf PV-Überschuss** – everything else: simply not enough PV surplus right now.

If "Steuerung aktiv" (`switch.pvsc_control_enabled`) is off, every text is prefixed with **"Steuerung aus: "** — the integration only reads and calculates, it isn't writing to the wallbox.

`sensor.pvsc_stop_cause` (and the "Grund" field in charge-stop notifications) records **why charging was last stopped**, decided in this order at the moment charging switches off:

| Value | Meaning |
|---|---|
| Kein Abbruch | No stop event yet, or the stop was due to something with its own status text (automation switched off mid-charge, wallbox reported "charging finished", car left the configured location, or a core sensor dropped out) rather than a PV/battery limit. |
| Hohe Batterienutzung | The home battery had been discharging heavily (>500 W average over the last 15 min) to help feed the car — considered a critical draw regardless of SOC. |
| SOC zu niedrig | Home battery SOC dropped below `min_soc` — the actual configured floor below which charging is blocked outright. |
| Zu wenig PV-Überschuss | Plain and simple: not enough PV surplus to keep the car's minimum current (6 A × phases × 230 V) fed. This is also shown when SOC sits between `min_soc` and `optimal_soc` — in that band the battery is deliberately not allowed to top up the car (see below), so a shortfall there is a PV problem, not a battery-SOC problem. |

**Why the distinction matters:** before version 0.5.1, any shortfall while SOC was below `optimal_soc` (default 80 %, not the real floor `min_soc`, default 40 %) was reported as "SOC zu niedrig" as long as there had recently been a meaningful calculated battery contribution (`battery_avg` > 50 W). That made "SOC zu niedrig" show up for what was really just a PV dip — the home battery's SOC was fine, it was simply not *allowed* (by the `min_soc`/`optimal_soc` policy) to bridge the gap. "SOC zu niedrig" is now reserved for an actual `soc < min_soc` situation; everything else that boils down to "not enough power available" is labelled "Zu wenig PV-Überschuss".

One more subtlety worth knowing: `sensor.pvsc_battery_avg` (used for the "Hohe Batterienutzung" threshold) is a 15-minute rolling average of the *calculated* shortfall (`min_watts - car_surplus`) sampled every tick — including ticks where the SOC band already forced actual battery support back to 0. So `battery_avg` can read high even in ticks where the battery wasn't really asked to contribute; treat it as "how much extra power would have been needed", not as a literal battery discharge measurement.

## Branding

The integration ships its own brand images (`custom_components/pvsc/brand/`) — supported since Home Assistant 2026.3, no `home-assistant/brands` submission required. On older HA versions the tile simply falls back to the default icon.

## Disclaimer

This is a community project, not affiliated with EM2GO. You are controlling real charging hardware — use at your own risk.

---

## Deutsch

Home-Assistant-Integration für **PV-Überschussladen mit der EM2GO Home Wallbox** (lokal per Modbus TCP, keine Cloud). Der Ladestrom folgt dem PV-Überschuss; optional mit Heimspeicher-Logik (SOC-Stufen, Batterie-Unterstützung, automatischer Korrekturfaktor), funktioniert aber auch ohne Hausbatterie. Override-Modi (PV/Manuell/Stop), Ein-/Ausschalt-Hysterese, Ampere-Rampe mit Totband, Rate-Limit und optionale Benachrichtigungen bei Ladestart/-stopp über eine beliebige notify-Entity. Einrichtung komplett über die UI (deutsch/englisch); eine Lovelace-Card liegt bei.

Alle über die Schalter/Zahlen/Auswahl-Entities gesetzten Werte (SOC-Stufen, Korrekturfaktor, Ampere-Totband, Phasen-Automatik, Überschussmodus, Override, Automatik an/aus) werden gespeichert und überstehen HA-Neustarts sowie Updates der Integration. Der Button "Auf Werkseinstellungen zurücksetzen" setzt sie mit einem Klick auf die Werksdefaults zurück (der Sicherheits-Schalter "Steuerung aktiv" bleibt davon bewusst unberührt).

Die EM2GO-Eigenheiten (nur Unit-ID 255, Schreiben nur per FC16, nur eine Modbus-Session, mehrminütige Verriegelung nach Verbindungsabbrüchen) sind in der Integration berücksichtigt.

### Status- und Abbruchgrund-Texte

`sensor.pvsc_status_text` zeigt den aktuellen Zustand als kurzen Klartext, von oben nach unten geprüft (der erste zutreffende Fall gewinnt):

- **Warte auf Sensordaten** – mindestens ein benötigter Kern-Sensor (PV, Last, Netzbezug/-einspeisung, Batterie, Heimspeicher-SOC) hat noch keinen echten Wert geliefert (z. B. direkt nach einem Neustart).
- **Gestoppt (Override)** – der Override-Modus steht auf "stop".
- **Kein Fahrzeug angeschlossen** – kein Auto eingesteckt.
- **Lädt [manuell] mit X A[, Ziel Y A]** – lädt aktiv; "manuell" bei Override-Modus "manual"; die Ziel-Ampere werden nur angezeigt, solange sie vom aktuellen Wert abweichen (die Rampe passt sich schrittweise an).
- **Start geplant** – Ladebedingungen sind erfüllt, die Start-Hysterese (3 Min.) läuft noch ab, bevor tatsächlich eingeschaltet wird.
- **Automatik deaktiviert** – der Schalter "Überschuss-Automatik" ist aus.
- **Gestoppt: `<Abbruchgrund>`** – Ladung wurde gerade beendet; siehe Tabelle unten für den Grund.
- **Laden beendet** – die Wallbox selbst meldet den Ladevorgang als abgeschlossen (Status-Code 6).
- **Wartet: Heimspeicher-SOC zu niedrig** – Heimspeicher-SOC liegt unter `min_soc`, Laden wird bewusst zurückgehalten (die echte Sicherheitsgrenze aus dem Setup).
- **Wartet auf PV-Überschuss** – alles andere: schlicht (noch) nicht genug PV-Überschuss.

Ist "Steuerung aktiv" (`switch.pvsc_control_enabled`) aus, wird jedem Text **"Steuerung aus: "** vorangestellt – die Integration liest und rechnet dann nur, schreibt aber nicht auf die Wallbox.

`sensor.pvsc_stop_cause` (und das Feld "Grund" in den Ladestopp-Benachrichtigungen) hält fest, **warum die Ladung zuletzt gestoppt wurde** – entschieden in dieser Reihenfolge in dem Moment, in dem die Ladung endet:

| Wert | Bedeutung |
|---|---|
| Kein Abbruch | Noch kein Stopp-Ereignis, oder der Stopp hatte einen eigenen Status-Text als Ursache (Automatik während des Ladens ausgeschaltet, Wallbox meldet "Laden beendet", Auto hat den konfigurierten Standort verlassen, oder ein Kern-Sensor ist ausgefallen) statt eines PV-/Batterie-Limits. |
| Hohe Batterienutzung | Der Heimspeicher hat stark entladen (> 500 W im Schnitt der letzten 15 Min.), um das Auto mitzuversorgen – das gilt unabhängig vom SOC als kritische Belastung. |
| SOC zu niedrig | Heimspeicher-SOC ist unter `min_soc` gefallen – die tatsächlich konfigurierte Untergrenze, unter der gar nicht mehr geladen wird. |
| Zu wenig PV-Überschuss | Schlicht: der PV-Überschuss reicht nicht für den Mindeststrom des Autos (6 A × Phasen × 230 V). Das gilt auch, wenn der SOC zwischen `min_soc` und `optimal_soc` liegt – in diesem Band darf die Batterie das Auto bewusst nicht mehr unterstützen (siehe unten), ein Engpass dort ist also ein PV-Problem, kein Batterie-SOC-Problem. |

**Warum die Unterscheidung wichtig ist:** Vor Version 0.5.1 wurde jeder Engpass, während der SOC unter `optimal_soc` lag (Standard 80 %, NICHT die echte Untergrenze `min_soc`, Standard 40 %), als "SOC zu niedrig" gemeldet, sofern kurz zuvor ein nennenswerter rechnerischer Batterie-Anteil (`battery_avg` > 50 W) vorlag. Dadurch erschien "SOC zu niedrig" auch dann, wenn es eigentlich nur eine PV-Flaute war – der Heimspeicher war völlig in Ordnung, durfte laut `min_soc`/`optimal_soc`-Politik nur nicht mehr einspringen. "SOC zu niedrig" ist jetzt ausschließlich für den Fall `soc < min_soc` reserviert; alles andere, was auf "zu wenig verfügbare Leistung" hinausläuft, heißt "Zu wenig PV-Überschuss".

Noch eine Feinheit: `sensor.pvsc_battery_avg` (Basis für die "Hohe Batterienutzung"-Schwelle) ist ein gleitender 15-Minuten-Schnitt des *rechnerischen* Fehlbetrags (`min_watts - car_surplus`), der in jedem Tick erfasst wird – auch in Ticks, in denen das SOC-Band die tatsächliche Batterie-Unterstützung schon auf 0 zurückgesetzt hat. `battery_avg` kann also auch dann hoch sein, wenn die Batterie real gar nicht gebraucht wurde; eher als "wie viel zusätzliche Leistung wäre nötig gewesen" lesen, nicht als echte Entlade-Messung.
