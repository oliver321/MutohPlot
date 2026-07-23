# MutohPlot v0.0.5

Zusätzlich zu v0.0.4:

- Papierpresets A3, A2, A1, A0
- Hoch-/Querformat
- automatische Einpassung mit frei wählbarem Rand
- strenge Seitengrenzprüfung
- explizite Farb-zu-Stift-Zuordnung per JSON
- Inkscape-Layernamen wie `Pen 3` oder `Stift 3` wählen automatisch den Stift

## Beispiel

```bash
mutohplot svg drawing.svg drawing.hpgl \
  --paper a2 \
  --fit \
  --margin 10 \
  --device-unit 0.01 \
  --pen-map examples/pen-map.json \
  --optimize \
  --strict-bounds \
  --stats \
  --preview preview.svg
```

Ohne `--fit` bleibt die bewährte 1:1-Geometrie aus v0.0.3/v0.0.4 erhalten.
