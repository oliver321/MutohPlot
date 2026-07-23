import argparse
from pathlib import Path
from .devices.mutoh_xp500 import MutohXP500
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform

def build_parser():
    p = argparse.ArgumentParser(prog="mutohplot")
    s = p.add_subparsers(dest="command", required=True)

    hpgl = s.add_parser("hpgl")
    hpgl.add_argument("input")
    hpgl.add_argument("output")
    hpgl.add_argument("--source-unit", type=float, default=0.025)
    hpgl.add_argument("--device-unit", type=float, default=0.01)
    hpgl.add_argument("--swap-axes", action="store_true")
    hpgl.add_argument("--flip-first", action="store_true")
    hpgl.add_argument("--flip-second", action="store_true")
    hpgl.add_argument("--offset-first", type=float, default=0.0)
    hpgl.add_argument("--offset-second", type=float, default=0.0)

    svg = s.add_parser("svg")
    svg.add_argument("input")
    svg.add_argument("output")
    svg.add_argument("--device-unit", type=float, default=0.01)
    svg.add_argument("--page-width", type=float)
    svg.add_argument("--page-height", type=float)
    svg.add_argument("--curve-steps", type=int, default=24)
    svg.add_argument("--offset-first", type=float, default=0.0)
    svg.add_argument("--offset-second", type=float, default=0.0)
    return p

def main():
    args = build_parser().parse_args()

    if args.command == "hpgl":
        text = Path(args.input).read_text(encoding="utf-8", errors="replace")
        doc = HPGLParser(args.source_unit).parse_text(text)
        if args.swap_axes:
            a,b,c,d = 0,1,1,0
        else:
            a,b,c,d = 1,0,0,1
        if args.flip_first:
            a,b = -a,-b
        if args.flip_second:
            c,d = -c,-d
        transform = CoordinateTransform(a,b,c,d,args.offset_first,args.offset_second)

    else:
        doc = SVGReader(args.curve_steps).read(args.input)
        page_w = args.page_width or float(doc.metadata["page_width_mm"])
        page_h = args.page_height or float(doc.metadata["page_height_mm"])
        transform = CoordinateTransform.svg_to_mutoh(page_w, page_h)
        transform = CoordinateTransform(
            transform.a, transform.b, transform.c, transform.d,
            transform.tx + args.offset_first,
            transform.ty + args.offset_second,
        )

    output = HPGLWriter(MutohXP500(unit_mm=args.device_unit), transform).write(doc)
    Path(args.output).write_text(output, encoding="ascii")
    print(f"Wrote {args.output}")
    print(f"Polylines: {len(doc.polylines)}")
