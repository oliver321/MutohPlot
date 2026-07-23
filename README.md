# MutohPlot

Modern HPGL toolkit with native support for center-origin plotters such as the Mutoh XP-500.

## Current status: v0.0.2

Implemented:

- Internal geometry in millimetres
- HPGL tokenizer
- Stateful HPGL parser
- `IN`, `DF`, `SP`, `PA`, `PR`, `PU`, and `PD`
- HPGL writer using absolute coordinates
- Mutoh XP-500 device profile
- Configurable coordinate transformation
- Command-line HPGL conversion
- Unit tests

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

## Convert HPGL

```bash
mutohplot convert input.hpgl output.hpgl   --source-unit 0.025   --device-unit 0.01
```

The XP-500 supports more than one coordinate resolution. Use `--device-unit`
to select the active resolution.
