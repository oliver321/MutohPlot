import argparse
from pathlib import Path
from .devices.mutoh_xp500 import MutohXP500
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .transform.coordinate import CoordinateTransform

def build_parser():
    parser = argparse.ArgumentParser(prog="mutohplot")
    subs = parser.add_subparsers(dest="command", required=True)
    convert = subs.add_parser("convert")
    convert.add_argument("input")
    convert.add_argument("output")
    convert.add_argument("--source-unit", type=float, default=0.025)
    convert.add_argument("--device-unit", type=float, default=0.01)
    convert.add_argument("--swap-axes", action="store_true")
    convert.add_argument("--flip-first", action="store_true")
    convert.add_argument("--flip-second", action="store_true")
    convert.add_argument("--offset-first", type=float, default=0.0)
    convert.add_argument("--offset-second", type=float, default=0.0)
    return parser

def main():
    args = build_parser().parse_args()
    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    doc = HPGLParser(args.source_unit).parse_text(text)

    if args.swap_axes:
        a, b, c, d = 0.0, 1.0, 1.0, 0.0
    else:
        a, b, c, d = 1.0, 0.0, 0.0, 1.0
    if args.flip_first:
        a, b = -a, -b
    if args.flip_second:
        c, d = -c, -d

    transform = CoordinateTransform(a, b, c, d, args.offset_first, args.offset_second)
    device = MutohXP500(unit_mm=args.device_unit)
    output = HPGLWriter(device, transform).write(doc)
    Path(args.output).write_text(output, encoding="ascii")

    print(f"Wrote {args.output}")
    print(f"Polylines: {len(doc.polylines)}")
    unsupported = doc.metadata.get("unsupported_commands", [])
    if unsupported:
        print("Unsupported commands:", ", ".join(sorted(set(unsupported))))
