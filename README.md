# MutohPlot v0.0.4

Neu: SVG `S/s`, `T/t`, `A/a`, Sichtbarkeitsfilter, Farb-zu-Stift-Zuordnung, Plotwegoptimierung, Statistik und SVG-Vorschau.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest

mutohplot svg examples/sample_multicolor.svg output.hpgl --device-unit 0.01 --optimize --stats --preview preview.svg
```

Die funktionierende SVG-zu-Mutoh-Transformation aus v0.0.3 wurde unverändert übernommen.
