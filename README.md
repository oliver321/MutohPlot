# MutohPlot v0.0.15

MutohPlot konvertiert und überträgt HP-GL- und SVG-Zeichnungen für den
Mutoh XP-500.

Der aktuelle Stand der eingelesenen HP-GL-Befehle ist unter
[docs/hpgl-support.md](docs/hpgl-support.md) dokumentiert.

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
Qualitätsprofile: `precise` 0,02 mm, `normal` 0,05 mm, `fast` 0,10 mm, `draft` 0,20 mm. Mit `--no-geometry-optimize` bleibt die Geometrie unverändert.

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
`large`: 16384-Byte-Blöcke. `small`: 512-Byte-Blöcke mit 20 ms Pause. Test ohne Senden: `--dry-run`. Die Übertragung kann mit `Ctrl+C` sicher abgebrochen werden; der serielle Port wird dabei geschlossen.\n\nDer vollständige Ablauf für den A3-Hardwaretest steht unter [docs/a3-serial-hardware-test.md](docs/a3-serial-hardware-test.md).

A3 bleibt Standard. Die bestätigte Hard-Clip-Korrektur aus v0.0.8 ist unverändert.
