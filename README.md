# MutohPlot v0.0.6

Modern SVG/HPGL toolkit for the Mutoh XP-500.

## New: hardware hard-clip windows

The XP-500 manual defines four hardware clip profiles. They are now used for
**A3, A2, A1 and A0**, in portrait and landscape:

| Profile | A top | B bottom | C left | D right |
|---|---:|---:|---:|---:|
| `norm` | 35 mm | 15 mm | 15 mm | 15 mm |
| `exp` | 25 mm | 5 mm | 5 mm | 5 mm |
| `type1` | 25 mm | 5 mm | 11 mm | 11 mm |
| `type3` | 25 mm | 10 mm | 10 mm | 10 mm |
| `none` | 0 mm | 0 mm | 0 mm | 0 mm |

The default is `norm`. The manual specifies roughly ±1 mm tolerance.

`--margin` adds an extra safety margin **inside** the selected hardware clip area.

## Recommended A2 command

```bash
mutohplot svg examples/drawing.svg drawing.hpgl \
  --paper a2 \
  --window norm \
  --fit \
  --margin 10 \
  --device-unit 0.01 \
  --optimize \
  --strict-bounds \
  --stats \
  --preview preview.svg
```

## Other modes

```bash
--window exp
--window type1
--window type3
--window none
```

## Landscape

```bash
mutohplot svg drawing.svg drawing_landscape.hpgl \
  --paper a1 \
  --landscape \
  --window norm \
  --fit \
  --margin 10
```

A/B always apply along the media-feed axis; C/D apply across the media.

## Important compatibility decision

The SVG-to-Mutoh coordinate transformation that produced the successful plots
in v0.0.3 is unchanged. Hard-clip values affect automatic fitting and strict
boundary checking; they are not silently added as another coordinate offset.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```
