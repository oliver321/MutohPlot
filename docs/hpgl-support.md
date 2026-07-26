# HP-GL command support

MutohPlot parses HP-GL into millimetre-based polylines before applying the
configured Mutoh XP-500 coordinate transform.

## Implemented

| Group | Commands | Behaviour |
| --- | --- | --- |
| State | `IN`, `DF`, `SP` | Initialization, default marker, and pen selection |
| Linear motion | `PA`, `PR`, `PU`, `PD` | Absolute and relative movement with current pen state |
| Arcs | `AA`, `AR` | Absolute or relative centre, positive/negative sweep, optional chord angle |
| Circles | `CI` | Automatic pen-down circle, signed radius start point, optional chord angle |
| Rectangles | `EA`, `RA` | Absolute outlined rectangles and solid serpentine fills |
| Labels | `LB`, `SI`, `DI`, `DR`, `SL`, `CP` | Built-in 5x7 vector font, size, direction, slant, and cursor movement |

`AA` and `AR` update the current pen position even when the pen is up. `CI`
draws a closed polyline and restores the previous pen state and centre
position. The default chord angle is 5 degrees and explicit chord angles are
clamped to the HP-GL range of 0.5 to 180 degrees.

`LB` labels use the default ETX terminator (and accept a legacy semicolon
terminator). They are converted to ordinary polylines so that fitting,
coordinate conversion, optimisation, and bounds checks also apply to text.
The built-in font covers printable ASCII letters, digits, and common
punctuation. Lowercase letters currently use their uppercase glyphs. `SI`
selects absolute character size; `DI` and `DR` select writing direction.
`SL` shears subsequent labels, and `CP` moves the pen in character and line
cells without drawing.

`EA` draws a closed rectangle outline. `RA` converts the default solid fill to
a continuous serpentine path. For conversion, the stroke spacing is calculated
from the active `SP` pen, its physical width and fill factor from the required
TOML pen profile, and the `--fit` scale. In the installed `Standard.toml`, the
spacing on paper is at most 85 percent of the pen width. Both commands restore
the original pen position and up/down state.

## Not yet interpreted

Commands outside the table above are listed in
`document.metadata["unsupported_commands"]`, and the `mutohplot hpgl` command
prints a warning with each command name and occurrence count. They are not
emitted by the current polyline writer.

Use `mutohplot inspect file.hpgl` to list all input commands, unsupported
commands, pens, geometry bounds, and drawing distances without writing an
output file. Add `--strict` to return exit status 2 when unsupported input is
found.

The `mutohplot hpgl` command accepts `--preview preview.svg`. With `--fit`,
the preview shows the fitted drawing in paper coordinates together with the
paper edge, hard-clip area, safety margin, pen colours, and the XP-500 origin.

The next compatibility block is additional label state (`DT`, `SR`),
followed by relative rectangles and scaling (`ER`, `RR`, `IP`, `IR`, `SC`).
