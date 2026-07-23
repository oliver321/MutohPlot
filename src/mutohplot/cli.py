import argparse
import json
from pathlib import Path

from .devices.mutoh_xp500 import MutohXP500
from .hard_clip import drawable_area, get_hard_clip, origin_offset_from_page_center
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .optimize.paths import optimize_nearest
from .paper import Paper, get_paper
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.fit import apply_fit, fit_document_to_area


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(prog="mutohplot")
    subcommands = command_parser.add_subparsers(dest="command", required=True)

    hpgl = subcommands.add_parser("hpgl")
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

    svg = subcommands.add_parser("svg")
    svg.add_argument("input")
    svg.add_argument("output")
    svg.add_argument("--device-unit", type=float, default=0.01)
    svg.add_argument("--page-width", type=float)
    svg.add_argument("--page-height", type=float)
    svg.add_argument("--paper", choices=["a3", "a2", "a1", "a0"])
    svg.add_argument("--landscape", action="store_true")
    svg.add_argument(
        "--window",
        choices=["none", "norm", "exp", "type1", "type3"],
        default="norm",
        help="XP-500 hard-clip window profile (default: norm)",
    )
    svg.add_argument(
        "--fit",
        action="store_true",
        help="Scale and centre the drawing inside the selected hard-clip area",
    )
    svg.add_argument(
        "--margin",
        type=float,
        default=0.0,
        help="Additional safety margin inside the hardware clip area, in mm",
    )
    svg.add_argument("--curve-steps", type=int, default=24)
    svg.add_argument("--offset-first", type=float, default=0.0)
    svg.add_argument("--offset-second", type=float, default=0.0)
    svg.add_argument("--optimize", action="store_true")
    svg.add_argument("--no-reverse", action="store_true")
    svg.add_argument("--stats", action="store_true")
    svg.add_argument("--preview")
    svg.add_argument("--pen-map", help="JSON file mapping stroke colors to pens")
    svg.add_argument("--no-layer-pens", action="store_true")
    svg.add_argument(
        "--strict-bounds",
        action="store_true",
        help="Fail if geometry extends beyond the selected hard-clip area",
    )

    return command_parser


def stats(document) -> None:
    print(f"Polylines: {len(document.polylines)}")
    print(f"Drawing distance: {document.drawing_distance_mm():.1f} mm")
    print(f"Pen-up distance: {document.pen_up_distance_mm():.1f} mm")
    if document.bounds():
        x0, y0, x1, y1 = document.bounds()
        print(f"Bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")
    for color, pen in document.metadata.get("color_to_pen", {}).items():
        print(f"{color} -> pen {pen}")


def _check_bounds(document, area) -> None:
    bounds = document.bounds()
    if bounds is None:
        return
    x0, y0, x1, y1 = bounds
    epsilon = 1e-7
    if (
        x0 < area.x_min_mm - epsilon
        or y0 < area.y_min_mm - epsilon
        or x1 > area.x_max_mm + epsilon
        or y1 > area.y_max_mm + epsilon
    ):
        raise SystemExit(
            "Drawing exceeds the hard-clip area: "
            f"bounds={bounds}, "
            f"allowed=({area.x_min_mm}, {area.y_min_mm}, "
            f"{area.x_max_mm}, {area.y_max_mm}) mm"
        )


def main() -> None:
    args = parser().parse_args()

    if args.command == "hpgl":
        document = HPGLParser(args.source_unit).parse_text(
            Path(args.input).read_text(errors="replace")
        )
        matrix = (0, 1, 1, 0) if args.swap_axes else (1, 0, 0, 1)
        a, b, c, d = matrix
        if args.flip_first:
            a, b = -a, -b
        if args.flip_second:
            c, d = -c, -d
        transform = CoordinateTransform(
            a,
            b,
            c,
            d,
            args.offset_first,
            args.offset_second,
        )

    else:
        pen_map = json.loads(Path(args.pen_map).read_text()) if args.pen_map else None
        document = SVGReader(
            args.curve_steps,
            pen_map=pen_map,
            layer_pens=not args.no_layer_pens,
        ).read(args.input)

        if args.paper:
            paper = get_paper(args.paper, args.landscape)
        else:
            width = args.page_width or float(document.metadata["page_width_mm"])
            height = args.page_height or float(document.metadata["page_height_mm"])
            paper = Paper("custom", float(width), float(height))

        profile = get_hard_clip(args.window)
        area = drawable_area(paper, profile, args.margin)
        vertical_offset, horizontal_offset = origin_offset_from_page_center(profile)

        print(
            f"Paper: {paper.name} {paper.width_mm:.1f} x {paper.height_mm:.1f} mm"
        )
        print(
            f"Hard clip {profile.name}: "
            f"A={profile.top_mm:.1f}, B={profile.bottom_mm:.1f}, "
            f"C={profile.left_mm:.1f}, D={profile.right_mm:.1f} mm"
        )
        print(
            f"Drawable area: {area.width_mm:.1f} x {area.height_mm:.1f} mm "
            f"at x={area.x_min_mm:.1f}..{area.x_max_mm:.1f}, "
            f"y={area.y_min_mm:.1f}..{area.y_max_mm:.1f}"
        )
        print(
            "Hard-clip centre relative to paper centre: "
            f"first={vertical_offset:+.1f} mm, second={horizontal_offset:+.1f} mm"
        )

        if args.fit:
            fit = fit_document_to_area(
                document,
                area,
                paper.width_mm,
                paper.height_mm,
            )
            document = apply_fit(document, fit)
            print(f"Fit scale: {fit.scale:.6f}")

        if args.strict_bounds:
            _check_bounds(document, area)

        # Keep the proven v0.0.3 mapping unchanged. The hard-clip profile is
        # applied to fitting and bounds, not silently added as a coordinate offset.
        transform = CoordinateTransform.svg_to_mutoh(
            paper.width_mm,
            paper.height_mm,
        )
        transform = CoordinateTransform(
            transform.a,
            transform.b,
            transform.c,
            transform.d,
            transform.tx + args.offset_first,
            transform.ty + args.offset_second,
        )

        document.metadata.update(
            {
                "paper": paper.name,
                "hard_clip_profile": profile.name,
                "hard_clip_margins_mm": {
                    "A_top": profile.top_mm,
                    "B_bottom": profile.bottom_mm,
                    "C_left": profile.left_mm,
                    "D_right": profile.right_mm,
                },
                "drawable_area_mm": (
                    area.x_min_mm,
                    area.y_min_mm,
                    area.x_max_mm,
                    area.y_max_mm,
                ),
            }
        )

        if args.preview:
            write_preview(document, args.preview)

    if args.optimize:
        before = document.pen_up_distance_mm()
        document = optimize_nearest(document, not args.no_reverse)
        print(
            f"Pen-up optimization: {before:.1f} mm -> "
            f"{document.pen_up_distance_mm():.1f} mm"
        )

    output = HPGLWriter(
        MutohXP500(unit_mm=args.device_unit),
        transform,
    ).write(document)
    Path(args.output).write_text(output, encoding="ascii")
    print(f"Wrote {args.output}")

    if args.stats:
        stats(document)
