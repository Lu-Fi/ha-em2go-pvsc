# EM2GO Home PV-Überschussladen (pvsc) – Anleitung

Integration `pvsc` (Nachbau des Node-RED Flows „PV Überschussladen") für die EM2GO Home Wallbox. Stand: 04.07.2026. Diese Anleitung ist auch über den Link „Dokumentation" auf der Integrationsseite erreichbar (`/local/pvsc_anleitung.html`) und liegt als `README.md` im Integrationsordner.

## 1. Grundprinzip

Die Integration liest den Wallbox-Zustand **immer direkt per Modbus TCP** (192.168.15.2:502, Unit-ID 255, MBAP). Der Schalter `switch.pvsc_control_enabled` bestimmt nur, ob auch **geschrieben** wird:

- **Steuerung AUS**: Nur lesen und beobachten. Die Regel-Logik rechnet mit und zeigt im Status an, was sie tun *würde* – schreibt aber nie auf die Wallbox (Status-Präfix „Steuerung aus:").
- **Steuerung AN**: Die Integration **schreibt aktiv** (Start/Stopp, Ampere, Phasen).

Wichtig: Die Wallbox verträgt nur **eine** Modbus-Verbindung gleichzeitig – es darf kein zweites System (z. B. Node-RED) parallel mit ihr sprechen, auch nicht nur lesend.

## 2. Modbus-Kommunikation

**Lesen:** Alle **7 Sekunden** (Poll-Intervall, einstellbar über „Konfigurieren") wird ein kompletter Durchlauf gemacht: 12 Registerblöcke (Status/Stecker/Fehler, Leistung, L1–L3, Zählerstand, Session-kWh, Ladezeit, Fehler-Limit, Ampere, Modus, Phasen), nacheinander mit je 150 ms Pause – ein Durchlauf dauert also ca. 2 s. Die TCP-Verbindung bleibt dauerhaft offen (wie die Warteschlange in Node-RED: alle Aufträge laufen seriell über eine Verbindung).

**Schreiben:** Nur bei Bedarf, per FC16 (wie Node-RED), und gedrosselt:

| Wert | Register | Wann geschrieben |
|---|---|---|
| Start/Stopp (Action 1/2) | 95 | Nur nach 3 Min stabiler Entscheidung, mind. 3 Min Abstand, max. 3 Schaltungen pro 15 Min |
| Ampere (Wert × 10) | 91 | Wenn Soll ≥ Totband (0,1 A) vom Ist abweicht, 30 s stabil, mind. 30 s Abstand |
| Phasen (1/3) | 200 | **Sofort**, sobald Ist ≠ Soll (im PV-Modus 1, mit aktiver Phasenautomatik 1 oder 3) |
| Fehler-Limit (fix 60 = 6 A) | 87 | Sofort, wenn Register ≠ 60 |

**Fehlerverhalten:** Bei einem Fehler wird die Verbindung geschlossen und erst nach einem Cool-down neu aufgebaut: 10 s, verdoppelnd pro Folgefehler, max. 120 s. Ein fehlgeschlagener Schreibversuch wird nicht wiederholt, sondern beim nächsten Regelzyklus neu berechnet. Wichtig: Die EM2GO verriegelt ihren Modbus-Stack nach abrupten Verbindungsabbrüchen für einige Minuten – einzelne Reconnect-Timeouts im Log sind daher normal und heilen sich selbst.

## 3. Schalter

| Entity | Bedeutung |
|---|---|
| `switch.pvsc_control_enabled` | „Steuerung aktiv (schreibt auf Wallbox)" – **Sicherheits-Freigabe.** AN = schreibt auf die Wallbox. AUS = nur lesen/beobachten |
| `switch.pvsc_enabled` | „Überschuss-Automatik aktiviert" – Regelung grundsätzlich an/aus (bei AUS wird nie geladen, auch im Live-Modus) |
| `switch.pvsc_correction_auto` | „Korrekturfaktor automatisch berechnen (statt manuell)" – AN = Faktor aus Speicher-SOC. AUS = manueller Wert (`number.pvsc_correction_factor`) gilt |
| `switch.pvsc_phase_auto` | „Automatische Phasenumschaltung (1↔3) im PV-Modus" – AN = bei Überschuss > 4,83 kW für 5 Min wird auf 3 Phasen hochgeschaltet, bei < 4,14 kW für 5 Min zurück auf 1 Phase (Hysterese). Das Stopp-Kriterium rechnet dann mit dem 1-phasigen Minimum, damit runtergeschaltet statt gestoppt wird. AUS (Standard) = im PV-Modus immer 1-phasig |

## 4. Einstellwerte (Number)

| Entity | Default | Bedeutung |
|---|---|---|
| `number.pvsc_min_soc` | 40 % | Unter diesem Heimspeicher-SOC wird nicht geladen (Korrekturfaktor 0) |
| `number.pvsc_optimal_soc` | 80 % | Ab hier Korrekturfaktor 0,9 |
| `number.pvsc_high_soc` | 90 % | Ab hier Korrekturfaktor 1,05 (bzw. 1,0 bei aktiver Batterie-Unterstützung) |
| `number.pvsc_correction_factor` | 75 | Manueller Korrekturfaktor in % – gilt nur, wenn `correction_auto` AUS ist |
| `number.pvsc_ampere_deadband` | 0,1 A | Totband: kleinere Soll/Ist-Abweichungen werden nicht geschrieben |
| `number.pvsc_override_ampere` | 6 A | Fester Ladestrom im Override-Modus „manual" |
| `number.pvsc_forced_ampere` | 0 | Test: >0 erzwingt Laden mit 16 A (Zielzustand AN), 0 = aus |

Hinweis Prognose: Ist die PV-Restprognose kleiner als das Doppelte der noch fehlenden Speicherkapazität, gelten automatisch strengere Grenzen (80/90/95 %). Ab 15 Uhr bei Prognose < 5 kWh: Faktor 0,9, keine Batterie-Unterstützung.

## 5. Auswahlen (Select) und Button

| Entity | Optionen | Bedeutung |
|---|---|---|
| `select.pvsc_override_mode` | `pv` / `manual` / `stop` | `pv` = normale Überschussregelung. `manual` = fester Strom (`override_ampere`) und feste Phasen (`override_phases`). `stop` = Laden sofort beenden und gesperrt lassen |
| `select.pvsc_override_phases` | `1` / `3` | Phasenzahl im manual-Modus. Im pv-Modus wird immer auf 1 Phase gestellt |
| `select.pvsc_surplus_mode` | `load` / `saldo` | Überschussberechnung: `load` = PV − (Hauslast − Wallboxleistung). `saldo` = aus Netz-Import/-Export und Batterieladung/-entladung (fällt bei unplausiblen Werten automatisch auf `load` zurück) |
| `button.pvsc_reset_stop_cause` | – | Abbruchgrund manuell löschen (wird sonst nachts 0–5 Uhr automatisch zurückgesetzt) |

## 6. Sensoren

**Regelung:** `pvsc_pv` (PV-Leistung), `pvsc_load` (Hauslast), `pvsc_surplus` (Überschuss Haus), `pvsc_car_surplus` (Überschuss fürs Auto inkl. Korrekturfaktor und Batterie-Unterstützung), `pvsc_target_ampere` (Soll), `pvsc_ampere` (zuletzt geschriebene Vorgabe), `pvsc_correction_faktor`, `pvsc_battery_support_watts`, `pvsc_battery_avg` (Ø Batterienutzung 15 min), `pvsc_stop_cause` (Kein Abbruch / Hohe Batterienutzung / SOC zu niedrig), `pvsc_status_text` (kurzer Klartext-Status, z. B. „Lädt mit 13.9 A, Ziel 11 A", „Wartet auf PV-Überschuss", „Gestoppt: SOC zu niedrig"; bei inaktiver Steuerung mit Präfix „Steuerung aus:").

**Wallbox (per Modbus gelesen):** `pvsc_em2go_state` (Code 0–6) und `pvsc_em2go_state_text` (Unbekannt/Bereit/Verbunden/Starte…/Lädt/Fehler/Laden beendet), `pvsc_em2go_power` (W), `pvsc_em2go_ampere` (Ist-Strombegrenzung), `pvsc_em2go_phases`, `pvsc_em2go_energy` (Zählerstand Wh), `pvsc_em2go_session_kwh`.

**Auto:** `pvsc_car_soc`, `pvsc_car_end` (geplantes Ladeende).

**Diagnose:** `binary_sensor.pvsc_modbus_connected` („Modbus verbunden" – die Quelle der Meldung „Wallbox getrennt"), `pvsc_modbus_status` (Klartext, auch letzter Fehler), `pvsc_modbus_consecutive_failures`, `pvsc_modbus_retry_in` (Sekunden bis zum nächsten Verbindungsversuch), `binary_sensor.pvsc_plug_connected`, `binary_sensor.pvsc_charging` (Ist), `binary_sensor.pvsc_target_charging` (Soll laut Logik), `binary_sensor.pvsc_car_home`.

## 7. Wann wird geladen?

Alle Bedingungen müssen gleichzeitig erfüllt sein: Auto-Überschuss ≥ Mindestleistung (6–7 A × Phasen × 230 V) oder Override manual/forced, Heimspeicher-SOC ≥ min_soc, Stecker eingesteckt, Auto zuhause, `pvsc_enabled` AN, Wallbox-Status ≠ „Laden beendet", und alle Kern-Sensoren haben nach dem HA-Start mindestens einmal echte Werte geliefert (Sicherheits-Gate gegen Fehlentscheidungen direkt nach einem Neustart).

Der Ladestrom ergibt sich aus: Überschuss × Korrekturfaktor + Batterie-Unterstützung, geteilt durch (230 V × Phasen), begrenzt auf 6–16 A. Batterie-Unterstützung: Fehlt wenig zum Mindeststrom und der Speicher ist voll genug (≥ high_soc), stützt der Heimspeicher die Differenz – begrenzt durch Wechselrichter-Maximum (4800 W), maximale Entladeleistung (3000 W) und maximale Hauslast (4200 W); bei Ø-Batterienutzung über dem Mindestwert wird sie wieder abgeschaltet.

## 8. Szenario: Wallbox startet neu und lädt im Default 3-phasig mit voller Leistung

Vorausgesetzt der Live-Modus ist aktiv, passiert Folgendes:

1. **Innerhalb von max. 7 s** (nächster Poll) liest PVSC den echten Zustand: Phasen = 3, Ampere z. B. 16, Status „Lädt". Die interne Logik übernimmt „lädt" als Ist-Zustand.
2. **Sofort im selben Zyklus** wird Phasen = 1 geschrieben (im PV-Modus ohne Verzögerung) und das Fehler-Limit auf 60 korrigiert. Damit fällt die Leistung schlagartig von bis zu ~11 kW auf maximal ~3,7 kW (16 A × 1 × 230 V).
3. **Nach ca. 30–60 s** wird der Ladestrom auf den berechneten Sollwert geregelt (Ampere-Änderung braucht 30 s stabile Abweichung).
4. **Wenn gar nicht geladen werden soll** (kein Überschuss, SOC zu niedrig, Auto nicht zuhause …), stoppt PVSC das Laden – wegen der Ein-/Ausschaltverzögerung aber erst nach ca. 3 Minuten. Bis dahin lädt sie einphasig weiter.

Wichtige Einschränkungen:

- Ist `switch.pvsc_control_enabled` AUS, greift **nichts** davon – die Integration liest zwar mit, aber die Wallbox lädt unkontrolliert weiter, bis jemand eingreift.
- Ob „Steuerung aktiv" nach einem HA-(Neu-)Start an ist, bestimmt das Setup-Feld `control_on_start` – bei dieser Installation steht es auf AN, PVSC übernimmt also nach jedem Neustart automatisch wieder die Kontrolle (Neuinstallationen starten aus Sicherheitsgründen mit inaktiver Steuerung). Alle übrigen Schalter/Regler (SOC-Grenzen, manueller Korrekturfaktor, Override …) starten nach einem HA-Neustart weiterhin mit ihren Defaults (kein Restore).
- Seit v0.3.0 ist die Integration auch **ohne Hausbatterie** nutzbar (Batterie-Felder beim Setup leer lassen: keine SOC-Stufen, Korrekturfaktor fix 1,0) und die Entity-Namen liegen auf Deutsch und Englisch vor. Statustexte und Meldungen sind weiterhin deutsch.
- Nach einem Wallbox-Neustart braucht der Modbus-Stack der Box manchmal 1–2 Minuten, bis er Verbindungen annimmt; PVSC versucht es mit Backoff automatisch weiter.

## 9. Technische Optionen (Zahnrad „Konfigurieren" an der Integration)

notify_enabled (Meldungen an/aus), notify_entity (Ziel für Ladestart/-stopp-Meldungen), max_ampere (maximaler Ladestrom, 16 A bei der 11-kW-, 32 A bei der 22-kW-Version), max_load 4200 W (maximale Hauslast inkl. Batterie-Unterstützung), battery_kwh 6,9 (Speichergröße für die Prognose-Regel), max_battery_discharge 3000 W, inverter_max_output 4800 W, poll_interval 7 s, modbus_timeout 1,5 s, modbus_command_delay 0,15 s, modbus_reconnect_backoff 10 s, modbus_connect_settle_delay 0,25 s, modbus_framing mbap (rtu nur als Test-Fallback – die Box spricht MBAP).

## 10. Telegram-/Notify-Meldungen

Wie früher in Node-RED verschickt die Integration selbst Meldungen bei Ladestart und Ladestopp. Konfiguration über das Zahnrad „Konfigurieren" an der Integration: „Benachrichtigung bei Ladestart/-stopp senden" (an/aus) und „Notify-Entity für Meldungen" (Auswahlfeld, Standard: Telegram-Bot „LFB_HomeAssistant", `notify.keller_lfb_homeassistant_lufi` – jede beliebige notify-Entity möglich, z. B. auch `notify.lutz_handy`). Start-Meldung: Zählerstand, Strom, Auto-SOC. Stopp-Meldung: geladene kWh, Zählerstand, Abbruchgrund, Auto-SOC. Kein Versand beim allerersten Poll nach einem HA-Neustart und beim Stopp ohne gesteckten Stecker (verhindert Fehlmeldungen bei Wallbox-Neustarts).

## 11. Bekannte Eigenheiten der EM2GO

Nur eine Modbus-TCP-Verbindung gleichzeitig (Node-RED und PVSC-Live-Modus schließen sich aus). Antwortet ausschließlich auf Unit-ID 255. Schreibbefehle nur per FC16 (Write Multiple Registers), FC6 wird ignoriert und stört die Session. Nach abrupten Verbindungsabbrüchen ist der Modbus-Stack einige Minuten blockiert (TCP-Connect wird angenommen, aber nicht beantwortet).
