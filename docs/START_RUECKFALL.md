# START/SOLL und autonomer Rückfall

Spätere Arbeit, kein Bestandteil des Monitoring-Releases und keine Schreibfreigabe.
Echte Temperaturmessungen bleiben unverändert.

## Belegt und nicht belegt

Benutzerbeobachtung: Absenken von START hält den Kessel aus. Kein protokollierter
Modbus-Schreibtest durch Codex. Statische private Quellenanalyse: Touch-START und
Modbus-START ändern denselben persistenten Basisparameter. Eine eigene temporäre
Fernvorgabe oder autonomer Ablauf auf den Touch-Wert ist im untersuchten Pfad
nicht nachgewiesen. Das ist kein vollständiger Ausschluss aller Herstellerfunktionen.

START intern 9040 hex / Projekt-Offset 36928; SOLL 9020 hex / 36896.
Beide sind jetzt ausdrücklich als lesbare Basisparameter im Leseprofil verfügbar.
Die Gerätetabelle wurde laut Betreiber installiert; eigener Geräteabgleich offen.
Diese Adressen nicht als einsatzbereiten Stellweg verwenden. Im analysierten FC06-Pfad ist die Dezimaltext-/Hex-
Umwandlung problematisch; Werte/Kodierung nicht ungeprüft als Standard annehmen.
Eine neue Zuordnungstabelle allein ergänzt keinen Rückfalltimer.

START wirkt bei dieser Pufferlogik am oberen Fühler, SOLL im Zweifühlerbetrieb am
unteren. Zeit-/Wettermodifikatoren können wirksame Schwellen verändern; andere
Wärmeanforderungen können ebenfalls starten. Keine globale Startsperre behaupten.

## Zielanforderung

Wenn kein gültiger externer Verzögerungs-/Zielwert mehr kommt, gilt spätestens nach
X Minuten wieder der aktuelle am Touch eingestellte Basiswert. X ist offen und
getrennt von der maximal erlaubten gesamten Aufschubdauer.

Aktuelle Betreiberentscheidung vom 18.10.2026: Eine spätere START-Ansteuerung
soll mit externem Alerting und gegebenenfalls manueller Rückstellung am Touch
weitergeplant werden. Das ist eine bewusste betriebliche Entscheidung, keine
technische Garantie für autonomen Rückfall. Alerting, Schreibkodierung,
konkrete Werte/Rückstellplan und Geräteprüfung bleiben spätere Arbeit.
Die App kann START/SOLL jetzt lesend als Temperatur-Basisparameter erfassen.
Eine spätere Schreibnutzung bleibt ein getrennter Kandidat; weiterhin kein Schreibadapter oder Schreibendpunkt.

Benötigte Semantik, noch kein vorhandenes Gerätefeature:

- Empfänger hält Basiswert und vorübergehende Fernvorgabe getrennt.
- Nur frischer gültiger Auftrag verlängert eine begrenzte Gültigkeit; alter Auftrag,
  erneutes Dateilesen oder bloßer Heartbeat tun dies nicht.
- Ohne Auftrag, nach Ablauf, Storno und Neustart gilt der Basiswert; kein Wiederaufleben
  alter Fernvorgaben. Bedienung am Touch hat Vorrang und beendet die Episode.
- Monotone Zeitbasis, Duplikate/verspätete Aufträge, Gesamtaufschub und Neustartfälle
  definieren. Warmwasser-/Heizbedarf und laufende Brennerzyklen berücksichtigen.
- Rückfall lässt reguläre Kesselregelung wieder zu; er erzwingt keinen Brennerstart.
- Einstellungen der App, gewünschter Gerätewert und tatsächlich bestätigter Wert
  separat; Änderung mit Ursprung, Vorwert, Ziel, Bestätigung und Rückfall auditieren.

Ein Python-Timer kann bei laufendem Rechner und bestehender Verbindung zurückstellen.
Er garantiert den Rückfall nicht beim eigenen Hostausfall oder Verbindungsausfall.
Auch externer Wächter/Modbus-Proxy löst den fehlenden Rückstellweg bei Netzverlust
nicht automatisch. Ein geeigneter unabhängiger Ablauf muss nachgewiesen werden.

Nächste spätere Arbeit: unterstützten Empfänger-/Integrationsweg nachweisen,
Ausfallmatrix und Offline-Zustandsmodell bauen. Ist keiner belegt, Fähigkeit als
offen dokumentieren und nicht durch einen schwächeren Timer als erfüllt ausgeben.
Jegliche Aktivierung/Import/Schreibprüfung erst mit konkreter Betreibererlaubnis.
