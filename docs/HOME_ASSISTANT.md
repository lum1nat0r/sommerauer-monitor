# Home Assistant über MQTT

Der Monitor veröffentlicht die aktive Aufzeichnungsauswahl als MQTT-Gerät
**Sommerauer Monitor**. Die Entitäten verwenden die Einheiten des Decoders
und enthalten `observed_at` mit der UTC-Zeit der Originalmessung. Rohwerte
und Sollwerte sind numerische Leseentitäten. Aufgezeichnete Bitmasken können
ein ganzes Abfrageintervall abbilden, wie im Monitor.

## Pelletlager

Das Gerät enthält zusätzlich drei Sensoren für den geschätzten Tankfüllstand
(Tonnen und Prozent) und den geschätzten Verbrauch seit der letzten Befüllung
(Tonnen). Lieferungen und Tankkapazität werden im Monitor gepflegt. MQTT
überträgt die berechneten Werte und die Originalzeit des Betriebszählers.

Die Schätzung benötigt mindestens zwei Lieferungen und setzt voraus, dass jede
Lieferung den Tank randvoll füllt. Der Anlagen-Betriebszähler muss aktiv
aufgezeichnet werden und im laufenden Monitor-Prozess eine gültige, frische
Beobachtung geliefert haben. Ohne diese Voraussetzungen zeigen die Sensoren
„nicht verfügbar“. Ohne Tankkapazität kann der Verbrauch weiterhin vorliegen.
Änderungen an Lieferungen oder Kapazität erscheinen beim nächsten MQTT-Update.
Der Verbrauch beginnt bei einer neuen Befüllung wieder bei null und kann sich
durch nachträgliche Korrekturen ändern.

## Aktivieren

1. In Home Assistant die MQTT-Integration mit Discovery unter `homeassistant`
   und der Startmeldung `online` auf `homeassistant/status` verwenden.
2. Einen TLS-Listener des vorhandenen Brokers für den Monitor einrichten. Der
   Servername muss im Broker-Zertifikat stehen. Der Listener verlangt ein
   Clientzertifikat. Für dessen Identität folgende Topic-Rechte vergeben
   (Beispiel für Instanz-ID und Zertifikats-CN `sommerauer-monitor`):

   ```text
   user sommerauer-monitor
   topic write homeassistant/device/sommerauer-monitor/config
   topic write sommerauer-monitor/state
   topic write sommerauer-monitor/availability
   topic read homeassistant/status
   ```

3. Die CA des Brokers, das Clientzertifikat und den Client-Schlüssel als
   `ca.crt`, `client.crt` und `client.key` in einem privaten Verzeichnis ablegen.
   Den Schlüssel nur für den Monitor-Benutzer lesbar machen und die Dateien
   schreibgeschützt einbinden. Das CA-Signierschlüsselmaterial bleibt außerhalb
   der Container. Ablaufdaten und Erneuerung von Server- und Clientzertifikat
   im Betriebsplan erfassen.
4. Das externe Docker-Netz `sommerauer-mqtt` anlegen und den Broker darin mit
   dem zum Zertifikat passenden Alias `sommerauer-mqtt` erreichbar machen.
   In der privaten Compose-Umgebung `MQTT_TLS_PATH` auf das Client-Verzeichnis
   setzen. Ab Version 1.0.1 ist MQTT in `compose.unraid.yaml` direkt eingebunden und
   standardmäßig aktiv. Mit `compose.yaml` weiterhin `-f compose.mqtt.yaml` ergänzen. Der zusätzliche Broker-Port braucht keine Host-Freigabe. Bei
   abweichenden Werten `MQTT_NETWORK`, `MQTT_HOST`, `MQTT_PORT` und
   `MQTT_INSTANCE_ID` setzen. Die Instanz-ID nach der Einrichtung beibehalten.

Direkt in der App lässt sich MQTT über `MQTT_ENABLED=true` aktivieren.
`MQTT_TLS_DIR` ist standardmäßig `/run/secrets/sommerauer-mqtt`. Ein gestarteter
Collector ist Voraussetzung.

## Verhalten und Rückbau

Der Adapter prüft alle 15 Sekunden die gespeicherten Daten. Frischegrenzen
sind dieselben wie bei der Monitor-API. Eine ungültige, fehlende, gesperrte,
pausierte oder veraltete Beobachtung erscheint als `unavailable`. Nach einem
Monitor-Neustart benötigt jeder Sensor eine neue Beobachtung. MQTT speichert
nur die Discovery-Konfiguration. Home Assistant verwirft ausbleibende Updates
nach 45 Sekunden oder früher bei einer Offline-Meldung. Bei einem Broker-Ausfall
bleibt die SQLite-Aufzeichnung aktiv. Die Wiederverbindung wartet zwischen
1 und 60 Sekunden und gleicht die aktive Auswahl erneut ab.

Für den dauerhaften Rückbau zuerst den Adapter deaktivieren. Dann mit einem
berechtigten MQTT-Client eine leere Retain-Nachricht auf
`homeassistant/device/<instanz-id>/config` senden. Home Assistant muss beim
Bereinigen mit dem Broker verbunden sein. Anschließend die Monitor-Berechtigung
und den TLS-Zugang entfernen. Den SQLite-Datenpfad weiterhin einbinden.

Quellen: [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/),
[MQTT-Sensoren](https://www.home-assistant.io/integrations/sensor.mqtt/),
[Mosquitto ACL-Plugin](https://mosquitto.org/documentation/plugins/acl-file/).
