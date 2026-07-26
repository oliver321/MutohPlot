# Stiftprofile und `Standard.toml`

MutohPlot lädt für jede HP-GL-Konvertierung verpflichtend das mitinstallierte
Profil `Standard.toml`. Dadurch bleibt der normale Aufruf kurz:

```bash
mutohplot plot input.hpgl /dev/ttyUSB0 \
  --paper a3 --window norm --fit --auto-rotate --margin 5
```

Eine andere Datei ersetzt das Standardprofil vollständig:

```bash
cd ~/MutohPlot
cp src/mutohplot/config/Standard.toml Standard_draft.toml

mutohplot plot input.hpgl /dev/ttyUSB0 \
  --config Standard_draft.toml \
  --paper a3 --window norm --fit --auto-rotate --margin 5
```

Der Pfad hinter `--config` darf relativ zum aktuellen Verzeichnis oder absolut
sein. So können mehrere vollständige Bestückungsprofile nebeneinander
verwaltet werden, ohne den normalen Aufruf mit Einzeloptionen zu verlängern.

Fehlt die mitinstallierte `Standard.toml`, bricht MutohPlot ab. Dasselbe gilt
für eine mit `--config` gewählte Datei, die fehlt oder ungültig ist. Es gibt
keine versteckte Ersatzbelegung außerhalb der TOML-Konfiguration.

## Mitgelieferte Belegung

| Plätze | Gruppe | Typ | Breite | Farbe |
| --- | --- | --- | --- | --- |
| 1 und 2 | `pencil-05` | Bleistift | 0,5 mm | Graphit |
| 3 und 4 | `pencil-03` | Bleistift | 0,3 mm | Graphit |
| 5 bis 8 | `default` | sonstiger/nicht festgelegter Stift | 0,5 mm | Schwarz |

Die Plätze 5 bis 8 verwenden die Werte aus `[pens]`, bis sie in einem eigenen
Profil ausdrücklich einer Gruppe zugeordnet werden.

## Dateiformat

```toml
[profile]
name = "Standard"

[fill]
spacing-factor = 0.85

[pens]
default-width-mm = 0.5
default-color = "black"
default-type = "other"

[pen-groups.pencil-05]
pens = [1, 2]
type = "pencil"
width-mm = 0.5
color = "graphite"

[pen-groups.pencil-03]
pens = [3, 4]
type = "pencil"
width-mm = 0.3
color = "graphite"
```

Ein Stift darf nur einer Gruppe angehören. Gültige Plätze sind 1 bis 8.
Unterstützte Breiten sind 0,3, 0,5, 0,7, 1,0 und 1,5 mm. Unterstützte Typen:

- `technical-pen` (Tusche-/Zeichenstift)
- `fiber` (Faserstift)
- `pencil` (Bleistift)
- `ballpoint` (Kugelschreiber)
- `other`

`color` ist eine CSS-Farbe, die in der SVG-Vorschau verwendet wird.

## Geschwindigkeit

Eine spätere Geschwindigkeit kann an der Gruppe oder bei den Standardwerten
in Millimetern pro Sekunde hinterlegt werden:

```toml
[pen-groups.pencil-05]
pens = [1, 2]
type = "pencil"
width-mm = 0.5
color = "graphite"
speed-mm-s = 12.5
```

MutohPlot validiert und meldet diesen Wert bereits, sendet ihn aber noch nicht
an den XP-500. Die Geschwindigkeitssteuerung wird erst aktiviert, wenn
HP-GL-Befehl, Wertebereich und Wirkung am Plotter hardwaregetestet sind.

## CLI-Überschreibungen

Für einen einzelnen Lauf bleiben Breiten überschreibbar:

```bash
mutohplot plot input.hpgl /dev/ttyUSB0 \
  --pen-width 1=0.7
```

Die Reihenfolge ist:

```text
--pen-width / --default-pen-width > gewählte TOML-Datei
```

`--default-pen-width` betrifft nur Plätze, die im Profil zur Gruppe `default`
gehören. Der hardwaregetestete `spacing-factor = 0.85` wird aus der
Profil-Datei gelesen und bei `RA` zusammen mit Stiftbreite und Fit-Maßstab
verwendet.
