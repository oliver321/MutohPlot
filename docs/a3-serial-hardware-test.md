# A3-Serial-Hardwaretest

Dieser Ablauf prüft MutohPlot mit dem Mutoh XP-500, ohne die bestätigte Kalibrierung zu verändern.

## Voraussetzungen

- Raspberry Pi mit ausgechecktem Branch `agent/serial-hardware-test`
- Mutoh XP-500 mit A3-Papier
- serielle Verbindung mit 19200 Baud, 8N1 und XON/XOFF
- am Plotter gewählter Empfangspuffer: 1 MB oder 1000 Zeichen

## Installation auf dem Raspberry Pi

```bash
cd ~/MutohPlot
git fetch origin
git switch --force-create agent/serial-hardware-test origin/agent/serial-hardware-test
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
mutohplot --version
```

Erwartet wird `mutohplot 0.0.11`.

## Testdatei erzeugen

```bash
source ~/MutohPlot/.venv/bin/activate
cd ~/MutohPlot
mutohplot calibrate a3_serial_test.hpgl --paper a3 --window norm --margin 5 --report
```

## Schnittstelle prüfen

```bash
mutohplot ports
mutohplot serial-status /dev/ttyUSB0
```

Falls der Adapter einen anderen Gerätenamen hat, diesen in allen folgenden Befehlen ersetzen.

## Trockenlauf

```bash
mutohplot send a3_serial_test.hpgl /dev/ttyUSB0 --buffer-profile large --progress --dry-run
```

## 1-MB-Puffer testen

Am Plotter den 1-MB-Puffer auswählen:

```bash
mutohplot send a3_serial_test.hpgl /dev/ttyUSB0 --buffer-profile large --progress
```

Prüfen:

- Übertragung erreicht 100 Prozent.
- Plot startet und endet vollständig.
- A3-Rahmen und Kalibriermarken liegen wie beim bestätigten Stand.
- Es gibt keine Unterbrechung oder fehlende HP-GL-Segmente.

## 1000-Zeichen-Puffer testen

Am Plotter den 1000-Zeichen-Puffer auswählen. Die Testdatei erneut mit begrenzten HP-GL-Befehlen erzeugen, falls eine SVG-Datei verwendet wird:

```bash
mutohplot svg drawing.svg drawing_small.hpgl \
  --paper a3 --window norm --fit --margin 5 \
  --quality normal --optimize --max-command-chars 800 --report --stats
mutohplot send drawing_small.hpgl /dev/ttyUSB0 --buffer-profile small --progress
```

Prüfen:

- Übertragung erreicht 100 Prozent.
- Der Plot ist vollständig.
- Der Plotter bleibt während der Übertragung empfangsbereit.
- Es treten keine Pufferüberläufe oder abgeschnittenen Befehle auf.

## Sicheren Abbruch testen

Eine Übertragung starten und währenddessen `Ctrl+C` drücken:

```bash
mutohplot send a3_serial_test.hpgl /dev/ttyUSB0 --buffer-profile small --progress
```

Erwartet wird `Transmission cancelled by user (serial port closed)`. Danach muss dieser Befehl wieder funktionieren:

```bash
mutohplot serial-status /dev/ttyUSB0
```

Die Beobachtungen für beide Pufferprofile vor Merge und Release-Tag im Pull Request dokumentieren.


## XON/XOFF-Pause mit LOCAL/REMOTE testen

Für diesen Test den Plotter mit dem 1000-Zeichen-Puffer zunächst auf LOCAL stellen und eine ausreichend große HP-GL-Datei senden:

```bash
mutohplot send drawing_small.hpgl /dev/ttyUSB0 --buffer-profile small --progress
```

Erwartetes Verhalten:

- Der Fortschritt bleibt stehen, sobald die nachgelagerten Puffer gefüllt sind.
- MutohPlot meldet keinen Schreib-Timeout, sondern wartet auf XON.
- Nach dem Umschalten auf REMOTE wird dieselbe Übertragung automatisch fortgesetzt.
- `Ctrl+C` bricht die wartende Übertragung kontrolliert ab und schließt den Port.

Nur wenn ausdrücklich ein zeitlich begrenzter Schreibstillstand gewünscht ist, kann `--timeout SEKUNDEN` angegeben werden.
