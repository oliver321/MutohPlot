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
| Labels | `LB`, `SI`, `DI`, `DR` | Built-in 5x7 vector font, size and direction |

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

## Not yet interpreted

Commands outside the table above are listed in
`document.metadata["unsupported_commands"]`, and the `mutohplot hpgl` command
prints a warning with each command name and occurrence count. They are not
emitted by the current polyline writer.

The next compatibility block is additional label state (`DT`, `SR`),
followed by rectangles and scaling (`EA`, `ER`, `RA`, `RR`, `IP`, `IR`, `SC`).
