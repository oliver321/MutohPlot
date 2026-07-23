import argparse
import json
from pathlib import Path

from .calibration import create_a3_calibration
from .devices.mutoh_xp500 import MutohXP500
from .hard_clip import drawable_area, get_hard_clip
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .optimize.paths import optimize_nearest
from .paper import Paper, get_paper
from .report import check_bounds, transformation_report
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.fit import apply_fit, fit_document_to_area


def parser():
    p = argparse.ArgumentParser(prog="mutohplot")
    sub = p.add_subparsers(dest="command", required=True)

    hpgl = sub.add_parser("hpgl")
    hpgl.add_argument("input")
    hpgl.add_argument("output")
    hpgl.add_argument("--source-unit", type=float, default=0.025)
    hpgl.add_argument("--device-unit", type=float, default=0.01)
    hpgl.add_argument("--swap-axes", action="store_true")
    hpgl.add_argument("--flip-first", action="store_true")
    hpgl.add_argument("--flip-second", action="store_true")
    hpgl.add_argument("--offset-first", type=float, default=0.0)
    hpgl.add_argument("--offset-second", type=float, default=0.0)
    hpgl.add_argument("--optimize", action="store_true")
    hpgl.add_argument("--no-reverse", action="store_true")
    hpgl.add_argument("--stats", action="store_true")

    svg = sub.add_parser("svg")
    svg.add_argument("input")
    svg.add_argument("output")
    svg.add_argument("--device-unit", type=float, default=0.01)
    svg.add_argument("--page-width", type=float)
    svg.add_argument("--page-height", type=float)
    svg.add_argument("--paper", choices=["a3", "a2", "a1", "a0"], default="a3")
    svg.add_argument("--landscape", action="store_true")
    svg.add_argument("--window", choices=["none", "norm", "exp", "type1", "type3"], default="norm")
    svg.add_argument("--fit", action="store_true")
    svg.add_argument("--margin", type=float, default=0.0)
    svg.add_argument("--curve-steps", type=int, default=24)
    svg.add_argument("--offset-first", type=float, default=0.0)
    svg.add_argument("--offset-second", type=float, default=0.0)
    svg.add_argument("--optimize", action="store_true")
    svg.add_argument("--no-reverse", action="store_true")
    svg.add_argument("--stats", action="store_true")
    svg.add_argument("--report", action="store_true")
    svg.add_argument("--preview")
    svg.add_argument("--pen-map")
    svg.add_argument("--no-layer-pens", action="store_true")
    svg.add_argument("--strict-bounds", action="store_true")

    cal = sub.add_parser("calibrate")
    cal.add_argument("output")
    cal.add_argument("--paper", choices=["a3"], default="a3")
    cal.add_argument("--window", choices=["none", "norm", "exp", "type1", "type3"], default="norm")
    cal.add_argument("--margin", type=float, default=0.0)
    cal.add_argument("--device-unit", type=float, default=0.01)
    cal.add_argument("--preview")
    cal.add_argument("--report", action="store_true")

    return p


def stats(document):
    print(f"Polylines: {len(document.polylines)}")
    print(f"Drawing distance: {document.drawing_distance_mm():.1f} mm")
    print(f"Pen-up distance: {document.pen_up_distance_mm():.1f} mm")
    if document.bounds():
        x0, y0, x1, y1 = document.bounds()
        print(f"Bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")


def main():
    args = parser().parse_args()

    if args.command == "hpgl":
        document = HPGLParser(args.source_unit).parse_text(Path(args.input).read_text(errors="replace"))
        a, b, c, d = (0, 1, 1, 0) if args.swap_axes else (1, 0, 0, 1)
        if args.flip_first:
            a, b = -a, -b
        if args.flip_second:
            c, d = -c, -d
        transform = CoordinateTransform(a, b, c, d, args.offset_first, args.offset_second)

    elif args.command == "calibrate":
        paper = get_paper("a3")
        profile = get_hard_clip(args.window)
        hard = drawable_area(paper, profile, 0)
        safe = drawable_area(paper, profile, args.margin)
        document = create_a3_calibration(args.window, args.margin)
        transform = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        if args.preview:
            write_preview(document, args.preview, paper=paper, hard_clip=hard, safe_area=safe)
        if args.report:
            print(transformation_report(document, paper, profile, safe, args.margin))

    else:
        pen_map = json.loads(Path(args.pen_map).read_text()) if args.pen_map else None
        document = SVGReader(args.curve_steps, pen_map=pen_map, layer_pens=not args.no_layer_pens).read(args.input)
        paper = get_paper(args.paper, args.landscape)
        profile = get_hard_clip(args.window)
        hard = drawable_area(paper, profile, 0)
        area = drawable_area(paper, profile, args.margin)
        fit_scale = None

        if args.fit:
            fit = fit_document_to_area(document, area, paper.width_mm, paper.height_mm)
            document = apply_fit(document, fit)
            fit_scale = fit.scale

        check = check_bounds(document, area)
        if args.strict_bounds and not check.inside:
            raise SystemExit(transformation_report(document, paper, profile, area, args.margin, fit_scale))

        transform = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        transform = CoordinateTransform(
            transform.a, transform.b, transform.c, transform.d,
            transform.tx + args.offset_first, transform.ty + args.offset_second,
        )

        if args.preview:
            write_preview(document, args.preview, paper=paper, hard_clip=hard, safe_area=area)
        if args.report:
            print(transformation_report(document, paper, profile, area, args.margin, fit_scale))

    if getattr(args, "optimize", False):
        before = document.pen_up_distance_mm()
        document = optimize_nearest(document, not args.no_reverse)
        print(f"Pen-up optimization: {before:.1f} mm -> {document.pen_up_distance_mm():.1f} mm")

    output = HPGLWriter(MutohXP500(unit_mm=args.device_unit), transform).write(document)
    Path(args.output).write_text(output, encoding="ascii")
    print(f"Wrote {args.output}")

    if getattr(args, "stats", False):
        stats(document)


if __name__ == "__main__":
    main()
