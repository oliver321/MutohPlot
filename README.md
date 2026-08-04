# MutohPlot v0.0.18

MutohPlot konvertiert und überträgt HP-GL- und SVG-Zeichnungen für den
Mutoh XP-500.

Der aktuelle Stand der eingelesenen HP-GL-Befehle ist unter
[docs/hpgl-support.md](docs/hpgl-support.md) dokumentiert.
Stiftgruppen, Breiten, Farben, Typen und vorbereitete
Geschwindigkeitswerte sind unter
[docs/configuration.md](docs/configuration.md) beschrieben.

## Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

## Optimierte A3-Konvertierung
```bash
mutohplot svg drawing.svg drawing.hpgl \
  --paper a3 --window norm --fit --margin 5 \
  --quality normal --optimize --report --stats
```
Qualitätsprofile: `precise` 0,02 mm, `normal` 0,05 mm, `fast` 0,10 mm, `draft` 0,20 mm. Mit `--no-geometry-optimize` bleibt die Geometrie unverändert. `--optimize` entfernt außerdem mehrfach vorhandene Linien desselben Stifts, auch wenn sie in Gegenrichtung gezeichnet werden, und optimiert danach die Leerwege. Ein räumlicher Endpunktindex hält diese Optimierung auch bei mehreren Tausend Pfaden schnell; mit `--progress` wird dabei der Fortschritt angezeigt.

Bestehende HP-GL-Dateien mit dem üblichen Ursprung unten links werden mit
`--fit` proportional in die verfügbare Zeichenfläche eingepasst, zentriert und
automatisch auf die Achsen des Mutoh XP-500 umgesetzt:

```bash
mutohplot hpgl input.hpgl output_mutoh.hpgl \
  --paper a3 --window norm --fit --auto-rotate --margin 5 \
  --preview preview.svg --report --stats
```

`--auto-rotate` dreht die Zeichnung nur dann um 90 Grad, wenn sie dadurch
größer auf die verfügbare Fläche skaliert werden kann. Eine feste Drehung ist
mit `--rotate 90`, `--rotate 180` oder `--rotate 270` möglich.

Gefüllte `RA`-Rechtecke berücksichtigen die tatsächliche Stiftbreite und den
mit `--fit` berechneten Maßstab. MutohPlot lädt dafür verpflichtend die
mitinstallierte `Standard.toml`. Darin bilden Stift 1 und 2 die
0,5-mm-Bleistiftgruppe, Stift 3 und 4 die 0,3-mm-Bleistiftgruppe. Ein anderes
vollständiges Profil wird mit `--config` gewählt:

```bash
mutohplot plot input.hpgl /dev/ttyUSB0 \
  --paper a3 --window norm --fit --auto-rotate --margin 5 \
  --config Standard_draft.toml
```

`--pen-width 1=0.7` kann die Profilbreite für einen einzelnen Lauf
überschreiben. Der Linienabstand der Füllung beträgt im Standardprofil
höchstens 85 Prozent der jeweiligen Stiftbreite auf dem Papier.

Die SVG-Vorschau zeigt Blattkante, Hard-Clip-Bereich, Sicherheitsrand,
Stiftfarben und den Nullpunkt des XP-500 in der Blattmitte.

## HP-GL vor dem Plotten prüfen

```bash
mutohplot inspect input.hpgl
mutohplot inspect input.hpgl --strict
mutohplot inspect 'Input*.hpgl'
```

`inspect` meldet die vorkommenden Befehle, nicht unterstützte Befehle,
verwendete Stifte, Grenzen, Größe sowie Zeichen- und Leerweg. `--strict`
beendet die Prüfung mit Status 2, wenn nicht unterstützte Befehle oder
Zeichen in `LB`-Beschriftungen gefunden werden.

Unterstützte HP-GL-Befehle sind derzeit `IN`, `DF`, `SP`, `PA`, `PR`, `PU`,
`PD`, `AA`, `AR`, `CI`, `EA`, `RA`, `SI`, `DI`, `DR`, `SL`, `CP` und `LB`. Numerische
Befehle werden auch erkannt, wenn zwischen zwei Befehlskennungen kein
Semikolon steht, beispielsweise `PA100,400DR0,1`.

## Konvertieren und direkt plotten

`plot` verarbeitet HP-GL mit denselben A3-Einstellungen wie `hpgl` und sendet
die konvertierten Daten anschließend direkt an die serielle Schnittstelle:

```bash
mutohplot plot Input.hpgl /dev/ttyUSB0 \
  --paper a3 --window norm --fit --auto-rotate --margin 5 --optimize \
  --buffer-profile small --progress \
  --save-hpgl Input_mutoh.hpgl \
  --preview Input_preview.svg
```

Mit `--no-send` dient der Befehl zur reinen Stapelkonvertierung. Ein in
Anführungszeichen gesetztes Muster wird von MutohPlot aufgelöst:

```bash
mutohplot plot 'Input*.hpgl' \
  --paper a3 --window norm --fit --auto-rotate --margin 5 --optimize \
  --save-hpgl-dir converted \
  --preview previews \
  --no-send
```

Dabei entstehen `converted/Input1_mutoh.hpgl` und
`previews/Input1_preview.svg`. Das Senden mehrerer Treffer ist absichtlich
gesperrt und muss ausdrücklich mit `--batch-send` freigegeben werden.

Die manuellen Achsenoptionen bleiben für Konvertierungen ohne `--fit`
verfügbar. `--offset-first` und `--offset-second` können auch zusammen mit
`--fit` für eine zusätzliche Feinkorrektur verwendet werden.

Für den 1000-Zeichen-Puffer kann die HPGL-Befehlslänge begrenzt werden:
```bash
--max-command-chars 800
```

## Serielle Schnittstelle
Standard: 19200 Baud, 8N1, XON/XOFF an, RTS/CTS und DTR/DSR aus.
```bash
mutohplot ports
mutohplot serial-status /dev/ttyUSB0
mutohplot send drawing.hpgl /dev/ttyUSB0 --buffer-profile large --progress
mutohplot send drawing.hpgl /dev/ttyUSB0 --buffer-profile small --progress
```
`large`: 16384-Byte-Blöcke. `small`: 512-Byte-Blöcke mit 20 ms Pause. Test ohne Senden: `--dry-run`. Die Übertragung kann mit `Ctrl+C` sicher abgebrochen werden; der serielle Port wird dabei geschlossen.

MutohPlot behandelt XON/XOFF selbst, statt den fehleranfälligen IXON-Zustand
des Linux-PL2303-Treibers zu verwenden. Ein neuer Prozess beginnt mit einer
freigegebenen Schnittstelle, pausiert nach einem echten XOFF des Plotters aber
weiterhin beliebig lange und setzt die Übertragung erst nach XON fort. Damit
bleiben auch mehrminütige Pausen zum Auffüllen eines Stifts sicher.

Der vollständige Ablauf für den A3-Hardwaretest steht unter [docs/a3-serial-hardware-test.md](docs/a3-serial-hardware-test.md).

A3 bleibt Standard. Die bestätigte Hard-Clip-Korrektur aus v0.0.8 ist unverändert.

## Lokale Weboberfläche

Die Weboberfläche prüft eine HP-GL- oder SVG-Datei, zeigt ihre Vorschau und sendet
anschließend exakt den geprüften Datenstand. Standardmäßig ist sie nur auf dem
Raspberry Pi selbst erreichbar:

```bash
mutohplot web
```

Aufruf im Browser: `http://127.0.0.1:8040`. Für Geräte im vertrauenswürdigen
lokalen Netz kann der Dienst ausdrücklich freigegeben werden:

```bash
mutohplot web --host 0.0.0.0 --port 8040
```

Dann im Browser `http://RASPBERRY-PI-IP:8040` öffnen. A3, 19200 Baud, 8N1 und
XON/XOFF bleiben fest voreingestellt. Vor dem Start fragt die Oberfläche noch
einmal nach der mechanischen Bereitschaft. Es kann nur ein Plotauftrag zur Zeit
übertragen werden.

Wird während einer aktiven Übertragung ein Dienst-Neustart angefordert, nimmt
die Oberfläche keine neuen Aufträge an und wartet auf den vollständigen
Abschluss des laufenden Sendens. Das gilt auch während einer zeitlich
unbegrenzten XOFF-Pause. Die systemd-Unit besitzt deshalb keine feste
Abschussfrist.

SVG-Dateien werden proportional in den sicheren Bereich des gewählten Formats eingepasst. Die
Oberfläche zeigt die automatisch ermittelte Zuordnung der SVG-Strichfarben zu
den Stiften 1 bis 8. Diese Zuordnung kann in der Weboberfläche für jede Farbe
geändert werden; die Vorschau und die freigegebenen Plotdaten werden danach neu
erzeugt. Inkscape-Ebenen mit Namen wie `Pen 4` oder `Stift 4`
verwenden ausdrücklich den genannten Stift. Unterstützt werden die in
[`docs/svg-support.md`](docs/svg-support.md) aufgeführten Linien-, Pfad- und
Formelemente; reine Textobjekte müssen vor dem Upload in Pfade umgewandelt
werden.

In der Oberfläche sind A3, A2, A1 und A0 auswählbar; A3 bleibt die
Voreinstellung. Ein Formatwechsel erzeugt die Vorschau und die freigegebenen
Plotdaten neu. Hoch- und Querformat sind wählbar. Die maximale Dateigröße
beträgt 20 MB.

Die Drehung ist für HP-GL und SVG einheitlich auswählbar: `Automatisch`, `0°`,
`90°`, `180°` oder `270°`. Automatisch vergleicht 0° und 90° und verwendet die
Orientierung mit dem größeren Fit-Maßstab. Eine manuelle Auswahl wird exakt auf
Vorschau und Plotdaten angewendet. Blattformat und Drehung sind unabhängig:
Querformat dreht das Blatt, die Drehungsoption dreht die Zeichnung darauf.

**Auf sicheren Bereich einpassen (`--fit`)** ist standardmäßig aktiv. Wird es
abgeschaltet, bleiben Maßstab und Position der Eingabe erhalten. Drehungen sind
dann gesperrt, weil sie ohne anschließende Zentrierung die
Koordinatenkonvention verändern würden. Die Vorschau warnt, wenn die
Originalgeometrie außerhalb des sicheren Bereichs liegt.

Nach der SVG-Prüfung nennt die Oberfläche nicht gezeichnete Elementtypen. Das
betrifft beispielsweise `text`, `image` und `use`. Enthält eine Datei daneben
unterstützte Liniengeometrie, bleibt der Plot möglich, der Hinweis muss aber vor
dem Start geprüft werden. Eine reine Datei ohne unterstützte Geometrie wird
abgewiesen.

### Stiftprofile im Webinterface

Unter **Stifte konfigurieren** verwaltet die Weboberfläche mehrere vollständige
Bestückungsprofile. Das mitgelieferte Profil `Standard` ist anfangs als
Standardprofil gesetzt. Für jeden der acht Plätze werden Bezeichnung, Art,
Breite und tatsächliche Farbe gespeichert. Neue Profile beginnen als Kopie des
gerade gewählten Profils.

Ein Profil kann ausgewählt, gespeichert, umbenannt, als Standard gesetzt oder
gelöscht werden. Das aktuell gesetzte Standardprofil kann erst gelöscht werden,
nachdem ein anderes Profil als Standard gewählt wurde. Die zentrale Datei auf
dem Raspberry Pi ist:

```text
/home/oliver/.config/mutohplot/web-pens.json
```

Die gemeinsame Zuordnung zeigt **Quelldarstellung → tatsächlicher Stift**. Bei
SVG ist die Quelle eine Strichfarbe, bei HP-GL eine mit `SP` gewählte
Stiftnummer. Beide können auf einen beliebigen Platz 1 bis 8 des gewählten
Profils gelegt werden. Die Vorschau verwendet die dort konfigurierte
tatsächliche Stiftfarbe. Bei HP-GL beeinflusst die Zielstiftbreite außerdem die
bestehende Berechnung von `RA`-Füllabständen. Ein Profilwechsel oder eine
Änderung der Zuordnung erzeugt die Vorschau und die freigegebenen Plotdaten neu.

Die frühere Farbangabe `graphite` wird beim Laden alter Profile automatisch in
das browserkompatible Graphitgrau `#41424c` überführt. Dadurch bleiben
Bleistiftlinien in der Webvorschau sichtbar.

Für einen automatischen Start auf dem Raspberry Pi liegt unter
`deploy/mutohplot-web.service` eine systemd-User-Unit bereit.

### Installation auf dem MutohPlot-Raspberry-Pi

Der derzeit verwendete Raspberry Pi ist unter `10.200.0.114` erreichbar. Die
Weboberfläche wird getrennt vom produktiven Checkout unter
`/home/oliver/MutohPlot-web` installiert. Nach der Installation ist sie im
lokalen Netz unter <http://10.200.0.114:8040> erreichbar.

```bash
cd /home/oliver/MutohPlot-web
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/python -m pytest -q
mkdir -p "$HOME/.config/systemd/user"
cp deploy/mutohplot-web.service "$HOME/.config/systemd/user/mutohplot-web.service"
systemctl --user daemon-reload
systemctl --user enable --now mutohplot-web.service
```

Status prüfen, Dienst neu starten und das laufende Protokoll anzeigen:

```bash
systemctl --user status mutohplot-web.service
systemctl --user restart mutohplot-web.service
journalctl --user -u mutohplot-web.service -f
```

Die serielle Schnittstelle des XP-500 kann so kontrolliert werden:

```bash
ls -l /dev/ttyUSB0
/home/oliver/MutohPlot-web/.venv/bin/mutohplot serial-status /dev/ttyUSB0
```

Die User-Unit startet automatisch bei der Anmeldung von `oliver`. Soll die
Weboberfläche bereits nach dem Booten und vor einer Anmeldung starten, muss
einmalig mit administrativen Rechten Linger aktiviert werden:

```bash
sudo loginctl enable-linger oliver
loginctl show-user oliver -p Linger
```
