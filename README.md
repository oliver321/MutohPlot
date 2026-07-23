# MutohPlot

Modern HPGL toolkit with native support for center-origin plotters such as the Mutoh XP-500.

## v0.0.3

Implemented:

- Internal geometry in millimetres
- HPGL tokenizer, parser, and writer
- HPGL commands: `IN`, `DF`, `SP`, `PA`, `PR`, `PU`, `PD`
- SVG import:
  - `line`
  - `polyline`
  - `polygon`
  - `rect`
  - `circle`
  - `ellipse`
  - `path` with `M`, `L`, `H`, `V`, `C`, `Q`, `Z`
- Basic SVG transforms:
  - `translate`
  - `scale`
  - `rotate`
  - `matrix`
- SVG page-size detection from `width`/`height` or `viewBox`
- Automatic mapping from SVG top-left origin to Mutoh center origin
- Configurable XP-500 coordinate resolution
- Command-line conversion
- Automated tests

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

## Convert SVG to Mutoh HPGL

```bash
mutohplot svg input.svg output.hpgl   --device-unit 0.01
```

For A2 output with forced page size:

```bash
mutohplot svg input.svg output.hpgl   --page-width 420   --page-height 594   --device-unit 0.01
```

## Convert existing HPGL

```bash
mutohplot hpgl input.hpgl output.hpgl   --source-unit 0.025   --device-unit 0.01   --swap-axes
```
