# MutohPlot v0.0.8

MutohPlot converts SVG and HPGL for the Mutoh XP-500.

## Main change

The hard-clip centre correction is now applied automatically.

For the available window modes:

| Window | First-axis correction | Second-axis correction |
|---|---:|---:|
| norm | -10.0 mm | 0.0 mm |
| exp | -10.0 mm | 0.0 mm |
| type1 | -10.0 mm | 0.0 mm |
| type3 | -7.5 mm | 0.0 mm |
| none | 0.0 mm | 0.0 mm |

This corrects the A3 Norm measurement where the plot was approximately
10 mm too low on the paper.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```

## Recommended A3 calibration test

```bash
mutohplot calibrate calibration_a3_v008.hpgl   --window norm   --device-unit 0.01   --preview calibration_a3_v008_preview.svg   --report
```

Expected physical margins for the Norm hard-clip outline:

- top: about 35 mm
- bottom: about 15 mm
- left: about 15 mm
- right: about 15 mm

Manual fine adjustment remains possible:

```bash
--offset-first -0.5
--offset-second 0.2
```

The automatic correction can be disabled for comparison:

```bash
--no-hardclip-correction
```

A3 remains the default test format.
