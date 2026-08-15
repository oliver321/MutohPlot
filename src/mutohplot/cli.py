import argparse
import json
from pathlib import Path

from .calibration import create_a3_calibration
from .devices.mutoh_xp500 import MutohXP500
from .hard_clip import drawable_area, get_hard_clip
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .optimize.paths import optimize_nearest
from .optimize.geometry import QUALITY_PROFILES, optimize_geometry
from .serial_io import BUFFER_PROFILES, SerialSettings, list_serial_ports, send_file, serial_status
from .paper import Paper, get_paper
from .report import check_bounds, transformation_report
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.hard_clip import hard_clip_center_correction
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
    svg.add_argument("--no-hardclip-correction", action="store_true")
    svg.add_argument("--optimize", action="store_true")
    svg.add_argument("--quality", choices=sorted(QUALITY_PROFILES), default="normal")
    svg.add_argument("--no-geometry-optimize", action="store_true")
    svg.add_argument("--max-command-chars", type=int)
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
    cal.add_argument("--offset-first", type=float, default=0.0)
    cal.add_argument("--offset-second", type=float, default=0.0)
    cal.add_argument("--no-hardclip-correction", action="store_true")
    cal.add_argument("--preview")
    cal.add_argument("--report", action="store_true")

    ports = sub.add_parser("ports")

    status = sub.add_parser("serial-status")
    status.add_argument("port")
    status.add_argument("--baud", type=int, default=19200)
    status.add_argument("--no-xonxoff", action="store_true")
    status.add_argument("--rtscts", action="store_true")
    status.add_argument("--dsrdtr", action="store_true")
    status.add_argument("--timeout", type=float, default=3.0)

    send = sub.add_parser("send")
    send.add_argument("input")
    send.add_argument("port")
    send.add_argument("--baud", type=int, default=19200)
    send.add_argument("--buffer-profile", choices=sorted(BUFFER_PROFILES), default="large")
    send.add_argument("--no-xonxoff", action="store_true")
    send.add_argument("--rtscts", action="store_true")
    send.add_argument("--dsrdtr", action="store_true")
    send.add_argument("--timeout", type=float, default=30.0)
    send.add_argument("--progress", action="store_true")
    send.add_argument("--dry-run", action="store_true")

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

    if args.command == "ports":
        items=list_serial_ports()
        if not items: print("No serial ports found")
        for item in items: print(f"{item['device']}: {item['description']} {item['hwid']}".strip())
        return
    if args.command == "serial-status":
        s=SerialSettings(args.port,args.baud,xonxoff=not args.no_xonxoff,rtscts=args.rtscts,dsrdtr=args.dsrdtr,timeout_s=args.timeout,write_timeout_s=args.timeout)
        for k,v in serial_status(s).items(): print(f"{k}: {v}")
        return
    if args.command == "send":
        s=SerialSettings(args.port,args.baud,xonxoff=not args.no_xonxoff,rtscts=args.rtscts,dsrdtr=args.dsrdtr,timeout_s=args.timeout,write_timeout_s=args.timeout)
        profile=BUFFER_PROFILES[args.buffer_profile]; size=Path(args.input).stat().st_size
        print(f"Port={args.port}, baud={args.baud}, 8N1, XON/XOFF={s.xonxoff}, RTS/CTS={s.rtscts}, DTR/DSR={s.dsrdtr}, profile={profile.name}, chunk={profile.chunk_size}")
        if args.dry_run: print(f"Dry run: {size} bytes would be sent"); return
        def progress(sent,total):
            if args.progress: print(f"\rSending: {int(sent*100/total):3d}% ({sent}/{total})",end="",flush=True)
        sent=send_file(args.input,s,args.buffer_profile,progress)
        if args.progress: print()
        print(f"Sent {sent} bytes")
        return

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
        base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        correction = hard_clip_center_correction(profile)
        auto_first = 0.0 if args.no_hardclip_correction else correction.first_mm
        auto_second = 0.0 if args.no_hardclip_correction else correction.second_mm
        transform = CoordinateTransform(
            base.a, base.b, base.c, base.d,
            base.tx + auto_first + args.offset_first,
            base.ty + auto_second + args.offset_second,
        )
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

        base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        correction = hard_clip_center_correction(profile)
        auto_first = 0.0 if args.no_hardclip_correction else correction.first_mm
        auto_second = 0.0 if args.no_hardclip_correction else correction.second_mm
        transform = CoordinateTransform(
            base.a, base.b, base.c, base.d,
            base.tx + auto_first + args.offset_first,
            base.ty + auto_second + args.offset_second,
        )

        if args.preview:
            write_preview(document, args.preview, paper=paper, hard_clip=hard, safe_area=area)
        if args.report:
            print(transformation_report(document, paper, profile, area, args.margin, fit_scale))

    if args.command == "svg" and not args.no_geometry_optimize:
        document, gs = optimize_geometry(document, args.quality)
        print(f"Geometry optimization: {gs.points_before} -> {gs.points_after} points ({gs.reduction_percent:.1f}% reduction, quality={args.quality})")

    if getattr(args, "optimize", False):
        before = document.pen_up_distance_mm()
        document = optimize_nearest(document, not args.no_reverse)
        print(f"Pen-up optimization: {before:.1f} mm -> {document.pen_up_distance_mm():.1f} mm")

    max_chars = args.max_command_chars if args.command == "svg" and args.max_command_chars else BUFFER_PROFILES["large"].hpgl_command_chars
    output = HPGLWriter(MutohXP500(unit_mm=args.device_unit), transform, max_command_chars=max_chars).write(document)
    Path(args.output).write_text(output, encoding="ascii")
    print(f"Wrote {args.output}")

    if getattr(args, "stats", False):
        stats(document)


if __name__ == "__main__":
    main()
