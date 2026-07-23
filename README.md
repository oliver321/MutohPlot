# MutohPlot v0.0.7

MutohPlot converts SVG and HPGL for the Mutoh XP-500.

## Main change

A3 is now the default development and hardware-test format.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

## A3 calibration plot

```bash
mutohplot calibrate calibration_a3.hpgl   --window norm   --margin 5   --device-unit 0.01   --preview calibration_a3_preview.svg   --report
```

## A3 SVG conversion

```bash
mutohplot svg examples/a3_curves.svg curves_a3.hpgl   --fit   --margin 5   --window norm   --device-unit 0.01   --strict-bounds   --report   --preview curves_a3_preview.svg
```

Available paper formats remain A3, A2, A1 and A0, but A3 is the default.
