# XP-500 hard-clip windows

MutohPlot v0.0.6 models the four hardware window settings from the XP-500 manual.
The letters match Figure 7.3:

| Window | A top | B bottom | C left | D right |
|---|---:|---:|---:|---:|
| Norm | 35 mm | 15 mm | 15 mm | 15 mm |
| Exp | 25 mm | 5 mm | 5 mm | 5 mm |
| Type 1 | 25 mm | 5 mm | 11 mm | 11 mm |
| Type 3 | 25 mm | 10 mm | 10 mm | 10 mm |

The manual states a tolerance of approximately ±1 mm.

`--margin` is an additional software safety margin inside this hardware area.
For example, A3 + Norm + 10 mm gives:

- left: 25 mm
- right: 25 mm
- top: 45 mm
- bottom: 25 mm

The proven coordinate transform from v0.0.3 is unchanged. The window profile is
used for fitting and strict boundary checking.

## Drawable areas without additional margin

### Norm

| Paper | Width | Height |
|---|---:|---:|
| A3 | 267 mm | 370 mm |
| A2 | 390 mm | 544 mm |
| A1 | 564 mm | 791 mm |
| A0 | 811 mm | 1139 mm |

The same A/B/C/D values also apply in landscape orientation relative to the
media-feed direction: A/B remain on the feed axis and C/D on the cross-feed axis.
