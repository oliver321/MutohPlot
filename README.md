# MutohPlot v0.0.9

Diese Version ergänzt Geometrieoptimierung und direkte serielle Übertragung zum Mutoh XP-500.

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
`large`: 16384-Byte-Blöcke. `small`: 512-Byte-Blöcke mit 20 ms Pause. Test ohne Senden: `--dry-run`.

A3 bleibt Standard. Die bestätigte Hard-Clip-Korrektur aus v0.0.8 ist unverändert.
