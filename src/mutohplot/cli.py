import argparse
import glob
import json
import sys
from collections import Counter
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from .calibration import create_a3_calibration
from .devices.mutoh_xp500 import MutohXP500
from .document import PlotDocument
from .geometry.point import Point
from .geometry.polyline import Polyline
from .hard_clip import DrawableArea, drawable_area, get_hard_clip
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .optimize.geometry import QUALITY_PROFILES, optimize_geometry
from .optimize.paths import optimize_nearest
from .paper import get_paper
from .pen_config import (
    SUPPORTED_PEN_WIDTHS_MM,
    PenConfigError,
    apply_pen_colors,
    load_pen_profile,
)
from .report import check_bounds, transformation_report
from .serial_io import (
    BUFFER_PROFILES,
    SerialSettings,
    list_serial_ports,
    send_bytes,
    send_file,
    serial_status,
)
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.fit import apply_fit, fit_document_to_area, rotate_document
from .transform.hard_clip import hard_clip_center_correction


def program_version() -> str:
    try:
        return package_version("mutohplot")
    except PackageNotFoundError:
        return "development"


def parser():
    version = program_version()
    p = argparse.ArgumentParser(
        prog="mutohplot",
        description=f"MutohPlot {version} - Modern HPGL and SVG toolkit for vintage pen plotters",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
        help="show the installed version and exit",
    )
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
    hpgl.add_argument("--paper", choices=["a3", "a2", "a1", "a0"], default="a3")
    hpgl.add_argument("--landscape", action="store_true")
    hpgl.add_argument("--window", choices=["none", "norm", "exp", "type1", "type3"], default="norm")
    hpgl.add_argument("--fit", action="store_true")
    rotation = hpgl.add_mutually_exclusive_group()
    rotation.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0)
    rotation.add_argument(
        "--auto-rotate",
        action="store_true",
        help="rotate by 90 degrees when that produces a larger fitted drawing",
    )
    hpgl.add_argument("--margin", type=float, default=0.0)
    hpgl.add_argument("--no-hardclip-correction", action="store_true")
    hpgl.add_argument("--report", action="store_true")
    hpgl.add_argument(
        "--optimize",
        action="store_true",
        help="remove duplicate same-pen lines and optimize pen-up travel",
    )
    hpgl.add_argument("--no-reverse", action="store_true")
    hpgl.add_argument("--stats", action="store_true")
    add_pen_width_arguments(hpgl)
    hpgl.add_argument(
        "--preview",
        help="write an SVG preview with paper, clip areas, pens, and plotter origin",
    )

    inspect = sub.add_parser("inspect", help="inspect an HP-GL file without converting it")
    inspect.add_argument("input", help="HP-GL file or quoted wildcard pattern")
    inspect.add_argument("--source-unit", type=float, default=0.025)
    add_pen_config_argument(inspect)
    inspect.add_argument(
        "--strict",
        action="store_true",
        help="exit with status 2 when unsupported commands or label characters are found",
    )

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
    svg.add_argument(
        "--optimize",
        action="store_true",
        help="remove duplicate same-pen lines and optimize pen-up travel",
    )
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

    sub.add_parser("ports")

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
    send.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="maximum write pause in seconds; default: wait indefinitely for XON",
    )
    send.add_argument("--progress", action="store_true")
    send.add_argument("--dry-run", action="store_true")

    plot = sub.add_parser(
        "plot",
        help="convert HP-GL and optionally send it directly to the plotter",
    )
    plot.add_argument("input", help="HP-GL file or quoted wildcard pattern")
    plot.add_argument("port", nargs="?", help="serial port, for example /dev/ttyUSB0")
    plot.add_argument("--source-unit", type=float, default=0.025)
    plot.add_argument("--device-unit", type=float, default=0.01)
    plot.add_argument("--paper", choices=["a3", "a2", "a1", "a0"], default="a3")
    plot.add_argument("--landscape", action="store_true")
    plot.add_argument("--window", choices=["none", "norm", "exp", "type1", "type3"], default="norm")
    plot.add_argument("--fit", action="store_true")
    plot_rotation = plot.add_mutually_exclusive_group()
    plot_rotation.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], default=0)
    plot_rotation.add_argument("--auto-rotate", action="store_true")
    plot.add_argument("--margin", type=float, default=0.0)
    plot.add_argument("--offset-first", type=float, default=0.0)
    plot.add_argument("--offset-second", type=float, default=0.0)
    plot.add_argument("--no-hardclip-correction", action="store_true")
    plot.add_argument(
        "--optimize",
        action="store_true",
        help="remove duplicate same-pen lines and optimize pen-up travel",
    )
    plot.add_argument("--no-reverse", action="store_true")
    plot.add_argument("--report", action="store_true")
    plot.add_argument("--stats", action="store_true")
    add_pen_width_arguments(plot)
    plot.add_argument("--preview", help="single SVG path, or output directory in batch mode")
    save = plot.add_mutually_exclusive_group()
    save.add_argument("--save-hpgl", help="save converted HP-GL (single input only)")
    save.add_argument("--save-hpgl-dir", help="save name_mutoh.hpgl files in this directory")
    plot.add_argument("--no-send", action="store_true", help="convert without serial transmission")
    plot.add_argument(
        "--batch-send",
        action="store_true",
        help="explicitly allow sending every file matched by a wildcard",
    )
    plot.add_argument("--baud", type=int, default=19200)
    plot.add_argument("--buffer-profile", choices=sorted(BUFFER_PROFILES), default="large")
    plot.add_argument("--no-xonxoff", action="store_true")
    plot.add_argument("--rtscts", action="store_true")
    plot.add_argument("--dsrdtr", action="store_true")
    plot.add_argument("--timeout", type=float, default=None)
    plot.add_argument("--progress", action="store_true")
    plot.add_argument("--dry-run", action="store_true")

    return p


def pen_width(value: str) -> tuple[int, float]:
    try:
        pen_text, width_text = value.split("=", 1)
        pen = int(pen_text)
        width = float(width_text)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("expected PEN=MM, for example 1=0.5") from error
    if not 1 <= pen <= 8:
        raise argparse.ArgumentTypeError("pen number must be between 1 and 8")
    if width not in SUPPORTED_PEN_WIDTHS_MM:
        choices = ", ".join(f"{item:g}" for item in SUPPORTED_PEN_WIDTHS_MM)
        raise argparse.ArgumentTypeError(f"pen width must be one of: {choices} mm")
    return pen, width


def add_pen_width_arguments(command_parser) -> None:
    add_pen_config_argument(command_parser)
    command_parser.add_argument(
        "--pen-width",
        action="append",
        type=pen_width,
        metavar="PEN=MM",
        default=[],
        help=("override a physical pen width from the selected profile; repeat as needed"),
    )
    command_parser.add_argument(
        "--default-pen-width",
        type=float,
        choices=SUPPORTED_PEN_WIDTHS_MM,
        default=None,
        metavar="MM",
        help="override the profile width for pens in the default group",
    )


def add_pen_config_argument(command_parser) -> None:
    command_parser.add_argument(
        "--config",
        metavar="FILE",
        help="use FILE instead of the required installed Standard.toml profile",
    )


def pen_profile(args):
    profile = getattr(args, "_pen_profile", None)
    if profile is None:
        profile = load_pen_profile(getattr(args, "config", None))
        args._pen_profile = profile
    return profile


def configured_pen_widths(args) -> dict[int, float]:
    profile = pen_profile(args)
    widths = {number: pen.width_mm for number, pen in profile.pens.items()}
    default_override = getattr(args, "default_pen_width", None)
    if default_override is not None:
        for number, pen in profile.pens.items():
            if pen.group == "default":
                widths[number] = default_override
    widths.update(dict(getattr(args, "pen_width", [])))
    return widths


def ra_fill_spacings(args, fit_scale: float = 1.0) -> dict[int, float]:
    if fit_scale <= 0:
        raise ValueError("Fit scale must be greater than zero")
    profile = pen_profile(args)
    return {
        pen: width * profile.fill_spacing_factor / fit_scale
        for pen, width in configured_pen_widths(args).items()
    }


def report_ra_fill(document, args) -> None:
    profile = pen_profile(args)
    print(f"Pen profile: {profile.name} ({profile.source})")
    used_pens = sorted({polyline.pen for polyline in document.polylines})
    widths = configured_pen_widths(args)
    for number in used_pens:
        pen = profile.pen(number)
        details = (
            f"Pen {number}: group={pen.group}, type={pen.pen_type}, "
            f"width={widths[number]:.1f} mm, color={pen.color}"
        )
        if pen.speed_mm_s is not None:
            details += f", configured speed={pen.speed_mm_s:g} mm/s (not yet applied)"
        print(details)
    ra_pens = sorted(set(document.metadata.get("ra_pens", [])))
    if not ra_pens:
        return
    for pen in ra_pens:
        width = widths[pen]
        spacing = width * profile.fill_spacing_factor
        print(f"RA fill: pen {pen}, width={width:.1f} mm, paper spacing<={spacing:.3f} mm")


def stats(document, transform, original_bounds=None, fit_scale=None, fit_rotation=0):
    print(f"Polylines: {len(document.polylines)}")
    print(f"Drawing distance: {document.drawing_distance_mm():.1f} mm")
    print(f"Pen-up distance: {document.pen_up_distance_mm():.1f} mm")
    if document.bounds():
        x0, y0, x1, y1 = document.bounds()
        if original_bounds is not None:
            ox0, oy0, ox1, oy1 = original_bounds
            print(f"Original input bounds: x={ox0:.2f}..{ox1:.2f} mm, y={oy0:.2f}..{oy1:.2f} mm")
            print(f"Fit scale: {fit_scale:.6f} ({fit_scale * 100:.2f}%)")
            print(f"Fit rotation: {fit_rotation} degrees")
            print(f"Fitted page bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")
        else:
            print(f"Input bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")
        output_points = [
            transform.apply(point) for polyline in document.polylines for point in polyline.points
        ]
        first_values = [point.x for point in output_points]
        second_values = [point.y for point in output_points]
        output_label = "Mutoh output bounds" if original_bounds is not None else "Output bounds"
        print(
            f"{output_label}: first={min(first_values):.2f}..{max(first_values):.2f} mm, "
            f"second={min(second_values):.2f}..{max(second_values):.2f} mm"
        )


def _counter_summary(items):
    counts = Counter(items)
    return ", ".join(f"{name} ({count})" for name, count in counts.items())


def inspect_document(path, document):
    commands = document.metadata.get("hpgl_commands", [])
    unsupported = document.metadata.get("unsupported_commands", [])
    unsupported_characters = document.metadata.get("unsupported_label_characters", [])
    pens = sorted({polyline.pen for polyline in document.polylines})

    print(f"File: {path}")
    print(f"Commands: {_counter_summary(commands) if commands else 'none'}")
    print("Unsupported: " + (_counter_summary(unsupported) if unsupported else "none"))
    if unsupported_characters:
        print(
            "Unsupported LB characters: "
            + _counter_summary(repr(character) for character in unsupported_characters)
        )
    print(f"Pens used: {', '.join(str(pen) for pen in pens) if pens else 'none'}")
    print(f"Polylines: {len(document.polylines)}")
    bounds = document.bounds()
    if bounds is None:
        print("Bounds: none")
        print("Size: 0.00 x 0.00 mm")
    else:
        x0, y0, x1, y1 = bounds
        print(f"Bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")
        print(f"Size: {x1 - x0:.2f} x {y1 - y0:.2f} mm")
    print(f"Drawing distance: {document.drawing_distance_mm():.1f} mm")
    print(f"Pen-up distance: {document.pen_up_distance_mm():.1f} mm")


def document_in_paper_coordinates(document, transform, paper):
    polylines = []
    for polyline in document.polylines:
        points = []
        for point in polyline.points:
            mutoh = transform.apply(point)
            points.append(
                Point(
                    mutoh.y + paper.width_mm / 2.0,
                    mutoh.x + paper.height_mm / 2.0,
                )
            )
        polylines.append(
            Polyline(
                points,
                polyline.pen,
                source_color=polyline.source_color,
            )
        )
    return PlotDocument(
        polylines,
        metadata={
            **document.metadata,
            "page_width_mm": paper.width_mm,
            "page_height_mm": paper.height_mm,
        },
    )


def bottom_left_document_in_paper_coordinates(document, paper):
    return PlotDocument(
        [
            Polyline(
                [Point(point.x, paper.height_mm - point.y) for point in polyline.points],
                polyline.pen,
                source_color=polyline.source_color,
            )
            for polyline in document.polylines
        ],
        metadata={
            **document.metadata,
            "page_width_mm": paper.width_mm,
            "page_height_mm": paper.height_mm,
        },
    )


def expand_inputs(pattern):
    matches = sorted(Path(path) for path in glob.glob(pattern))
    if not matches and Path(pattern).is_file():
        matches = [Path(pattern)]
    if not matches:
        raise SystemExit(f"No input files match: {pattern}")
    return matches


def convert_hpgl(args, input_path, preview_path=None):
    source_text = Path(input_path).read_text(errors="replace")
    initial_fill_spacings = None if args.fit else ra_fill_spacings(args)
    document = HPGLParser(
        args.source_unit,
        initial_fill_spacings,
    ).parse_text(source_text)
    paper = get_paper(args.paper, args.landscape)
    profile = get_hard_clip(args.window)
    hard = drawable_area(paper, profile, 0)
    safe = drawable_area(paper, profile, args.margin)
    if not args.fit and (args.rotate or args.auto_rotate):
        raise SystemExit("--rotate and --auto-rotate require --fit")

    unsupported = Counter(document.metadata.get("unsupported_commands", []))
    if unsupported:
        summary = ", ".join(f"{name} ({count})" for name, count in sorted(unsupported.items()))
        print(f"Warning: Unsupported HP-GL commands: {summary}", file=sys.stderr)
    unsupported_characters = Counter(document.metadata.get("unsupported_label_characters", []))
    if unsupported_characters:
        summary = ", ".join(
            f"{character!r} ({count})"
            for character, count in sorted(unsupported_characters.items())
        )
        print(
            f"Warning: Unsupported LB characters replaced with '?': {summary}",
            file=sys.stderr,
        )

    original_bounds = None
    fit_scale = None
    fit_rotation = 0
    if args.fit:
        original_bounds = document.bounds()
        if (
            getattr(args, "swap_axes", False)
            or getattr(args, "flip_first", False)
            or getattr(args, "flip_second", False)
        ):
            raise SystemExit(
                "--fit determines axis swapping and direction automatically; "
                "do not combine it with --swap-axes, --flip-first, or --flip-second"
            )
        area = DrawableArea(
            safe.x_min_mm,
            paper.height_mm - safe.y_max_mm,
            safe.x_max_mm,
            paper.height_mm - safe.y_min_mm,
        )
        fit_rotation = args.rotate
        if args.auto_rotate and document.bounds() is not None:
            normal_fit = fit_document_to_area(document, area, paper.width_mm, paper.height_mm)
            rotated = rotate_document(document, 90)
            rotated_fit = fit_document_to_area(rotated, area, paper.width_mm, paper.height_mm)
            if rotated_fit.scale > normal_fit.scale:
                document = rotated
                fit_rotation = 90
        elif args.rotate:
            document = rotate_document(document, args.rotate)
        fit = fit_document_to_area(document, area, paper.width_mm, paper.height_mm)
        if "RA" in document.metadata["hpgl_commands"]:
            document = HPGLParser(
                args.source_unit,
                ra_fill_spacings(args, fit.scale),
            ).parse_text(source_text)
            if fit_rotation:
                document = rotate_document(document, fit_rotation)
            fit = fit_document_to_area(
                document,
                area,
                paper.width_mm,
                paper.height_mm,
            )
        fit_scale = fit.scale
        document = apply_fit(document, fit)
        correction = hard_clip_center_correction(profile)
        auto_first = 0.0 if args.no_hardclip_correction else correction.first_mm
        auto_second = 0.0 if args.no_hardclip_correction else correction.second_mm
        transform = CoordinateTransform(
            0.0,
            -1.0,
            1.0,
            0.0,
            paper.height_mm / 2.0 + auto_first + args.offset_first,
            -paper.width_mm / 2.0 + auto_second + args.offset_second,
        )
        if args.report:
            print(f"Fit rotation: {fit_rotation} degrees")
            report_ra_fill(document, args)
            print(transformation_report(document, paper, profile, area, args.margin, fit.scale))
    else:
        swap_axes = getattr(args, "swap_axes", False)
        a, b, c, d = (0, 1, 1, 0) if swap_axes else (1, 0, 0, 1)
        if getattr(args, "flip_first", False):
            a, b = -a, -b
        if getattr(args, "flip_second", False):
            c, d = -c, -d
        transform = CoordinateTransform(a, b, c, d, args.offset_first, args.offset_second)
        if args.report:
            report_ra_fill(document, args)

    apply_pen_colors(document, pen_profile(args))

    if preview_path:
        if args.fit:
            preview_document = bottom_left_document_in_paper_coordinates(document, paper)
        else:
            preview_document = document_in_paper_coordinates(document, transform, paper)
        Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
        write_preview(
            preview_document,
            preview_path,
            paper=paper,
            hard_clip=hard,
            safe_area=safe,
            show_origin=True,
        )

    if args.optimize:
        before = document.pen_up_distance_mm()
        document = optimize_nearest(document, not args.no_reverse)
        removed = document.metadata.get("duplicate_segments_removed", 0)
        print(f"Duplicate line segments removed: {removed}")
        print(f"Pen-up optimization: {before:.1f} mm -> {document.pen_up_distance_mm():.1f} mm")

    max_chars = BUFFER_PROFILES[getattr(args, "buffer_profile", "large")].hpgl_command_chars
    output = HPGLWriter(
        MutohXP500(unit_mm=args.device_unit),
        transform,
        max_command_chars=max_chars,
    ).write(document)
    return output, document, transform, original_bounds, fit_scale, fit_rotation


def main():
    args = parser().parse_args()

    if args.command in {"hpgl", "inspect", "plot"}:
        try:
            pen_profile(args)
        except PenConfigError as error:
            raise SystemExit(f"Pen configuration error: {error}") from error

    if args.command == "ports":
        items = list_serial_ports()
        if not items:
            print("No serial ports found")
        for item in items:
            print(f"{item['device']}: {item['description']} {item['hwid']}".strip())
        return
    if args.command == "serial-status":
        s = SerialSettings(
            args.port,
            args.baud,
            xonxoff=not args.no_xonxoff,
            rtscts=args.rtscts,
            dsrdtr=args.dsrdtr,
            timeout_s=args.timeout,
            write_timeout_s=args.timeout,
        )
        for k, v in serial_status(s).items():
            print(f"{k}: {v}")
        return
    if args.command == "send":
        s = SerialSettings(
            args.port,
            args.baud,
            xonxoff=not args.no_xonxoff,
            rtscts=args.rtscts,
            dsrdtr=args.dsrdtr,
            timeout_s=30.0,
            write_timeout_s=args.timeout,
        )
        profile = BUFFER_PROFILES[args.buffer_profile]
        size = Path(args.input).stat().st_size
        print(
            f"Port={args.port}, baud={args.baud}, 8N1, XON/XOFF={s.xonxoff}, RTS/CTS={s.rtscts}, DTR/DSR={s.dsrdtr}, profile={profile.name}, chunk={profile.chunk_size}, write-timeout={args.timeout if args.timeout is not None else 'unlimited'}"
        )
        if args.dry_run:
            print(f"Dry run: {size} bytes would be sent")
            return

        def progress(sent, total):
            if args.progress:
                print(
                    f"\rSending: {int(sent * 100 / total):3d}% ({sent}/{total})", end="", flush=True
                )

        try:
            sent = send_file(args.input, s, args.buffer_profile, progress)
        except KeyboardInterrupt:
            if args.progress:
                print()
            raise SystemExit("Transmission cancelled by user (serial port closed)")
        except (OSError, RuntimeError) as error:
            if args.progress:
                print()
            raise SystemExit(f"Transmission failed: {error}") from error
        if args.progress:
            print()
        print(f"Sent {sent} bytes")
        return
    if args.command == "inspect":
        strict_failure = False
        inputs = expand_inputs(args.input)
        for index, input_path in enumerate(inputs):
            if index:
                print()
            try:
                document = HPGLParser(
                    args.source_unit,
                    ra_fill_spacings(args),
                ).parse_text(input_path.read_text(errors="replace"))
                apply_pen_colors(document, pen_profile(args))
            except ValueError as error:
                raise SystemExit(f"Failed to inspect {input_path}: {error}") from error
            inspect_document(input_path, document)
            strict_failure = strict_failure or bool(
                document.metadata.get("unsupported_commands")
                or document.metadata.get("unsupported_label_characters")
            )
        if args.strict and strict_failure:
            raise SystemExit(2)
        return

    hpgl_original_bounds = None
    hpgl_fit_scale = None
    hpgl_fit_rotation = 0
    if args.command == "hpgl":
        (
            output,
            document,
            transform,
            hpgl_original_bounds,
            hpgl_fit_scale,
            hpgl_fit_rotation,
        ) = convert_hpgl(args, args.input, args.preview)
        Path(args.output).write_text(output, encoding="ascii")
        print(f"Wrote {args.output}")
        if args.stats:
            stats(
                document,
                transform,
                hpgl_original_bounds,
                hpgl_fit_scale,
                hpgl_fit_rotation,
            )
        return

    elif args.command == "plot":
        inputs = expand_inputs(args.input)
        batch = len(inputs) > 1
        if not args.no_send and not args.port:
            raise SystemExit("PORT is required unless --no-send is used")
        if batch and not args.no_send and not args.batch_send:
            raise SystemExit(
                f"{len(inputs)} files matched; use --batch-send to allow sending all of them"
            )
        if batch and args.save_hpgl:
            raise SystemExit("--save-hpgl is only valid for one input; use --save-hpgl-dir")
        if batch and args.preview and Path(args.preview).suffix.lower() == ".svg":
            raise SystemExit("In batch mode --preview must name an output directory")

        save_dir = Path(args.save_hpgl_dir) if args.save_hpgl_dir else None
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
        preview_dir = Path(args.preview) if batch and args.preview else None
        if preview_dir:
            preview_dir.mkdir(parents=True, exist_ok=True)

        settings = None
        profile = BUFFER_PROFILES[args.buffer_profile]
        if not args.no_send:
            settings = SerialSettings(
                args.port,
                args.baud,
                xonxoff=not args.no_xonxoff,
                rtscts=args.rtscts,
                dsrdtr=args.dsrdtr,
                timeout_s=30.0,
                write_timeout_s=args.timeout,
            )

        for index, input_path in enumerate(inputs, start=1):
            if batch:
                print(f"[{index}/{len(inputs)}] {input_path}")
            preview_path = None
            if args.preview:
                preview_path = (
                    preview_dir / f"{input_path.stem}_preview.svg" if batch else Path(args.preview)
                )
            output, document, transform, original, scale, rotation = convert_hpgl(
                args, input_path, preview_path
            )
            data = output.encode("ascii")

            saved_path = None
            if args.save_hpgl:
                saved_path = Path(args.save_hpgl)
            elif save_dir:
                saved_path = save_dir / f"{input_path.stem}_mutoh.hpgl"
            if saved_path:
                saved_path.parent.mkdir(parents=True, exist_ok=True)
                saved_path.write_bytes(data)
                print(f"Wrote {saved_path}")

            if args.stats:
                stats(document, transform, original, scale, rotation)

            if args.no_send:
                continue
            print(
                f"Port={args.port}, baud={args.baud}, 8N1, "
                f"XON/XOFF={settings.xonxoff}, RTS/CTS={settings.rtscts}, "
                f"DTR/DSR={settings.dsrdtr}, profile={profile.name}, "
                f"chunk={profile.chunk_size}, "
                f"write-timeout={args.timeout if args.timeout is not None else 'unlimited'}"
            )
            if args.dry_run:
                print(f"Dry run: {len(data)} bytes would be sent")
                continue

            def progress(sent, total):
                if args.progress:
                    print(
                        f"\rSending: {int(sent * 100 / total):3d}% ({sent}/{total})",
                        end="",
                        flush=True,
                    )

            try:
                sent = send_bytes(data, settings, profile, progress)
            except KeyboardInterrupt:
                if args.progress:
                    print()
                raise SystemExit("Transmission cancelled by user (serial port closed)")
            except (OSError, RuntimeError) as error:
                if args.progress:
                    print()
                raise SystemExit(f"Transmission failed: {error}") from error
            if args.progress:
                print()
            print(f"Sent {sent} bytes")
        return

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
            base.a,
            base.b,
            base.c,
            base.d,
            base.tx + auto_first + args.offset_first,
            base.ty + auto_second + args.offset_second,
        )
        if args.preview:
            write_preview(document, args.preview, paper=paper, hard_clip=hard, safe_area=safe)
        if args.report:
            print(transformation_report(document, paper, profile, safe, args.margin))

    else:
        pen_map = json.loads(Path(args.pen_map).read_text()) if args.pen_map else None
        document = SVGReader(
            args.curve_steps, pen_map=pen_map, layer_pens=not args.no_layer_pens
        ).read(args.input)
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
            raise SystemExit(
                transformation_report(document, paper, profile, area, args.margin, fit_scale)
            )

        base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        correction = hard_clip_center_correction(profile)
        auto_first = 0.0 if args.no_hardclip_correction else correction.first_mm
        auto_second = 0.0 if args.no_hardclip_correction else correction.second_mm
        transform = CoordinateTransform(
            base.a,
            base.b,
            base.c,
            base.d,
            base.tx + auto_first + args.offset_first,
            base.ty + auto_second + args.offset_second,
        )

        if args.preview:
            write_preview(document, args.preview, paper=paper, hard_clip=hard, safe_area=area)
        if args.report:
            print(transformation_report(document, paper, profile, area, args.margin, fit_scale))

    if args.command == "svg" and not args.no_geometry_optimize:
        document, gs = optimize_geometry(document, args.quality)
        print(
            f"Geometry optimization: {gs.points_before} -> {gs.points_after} points ({gs.reduction_percent:.1f}% reduction, quality={args.quality})"
        )

    if getattr(args, "optimize", False):
        before = document.pen_up_distance_mm()
        document = optimize_nearest(document, not args.no_reverse)
        removed = document.metadata.get("duplicate_segments_removed", 0)
        print(f"Duplicate line segments removed: {removed}")
        print(f"Pen-up optimization: {before:.1f} mm -> {document.pen_up_distance_mm():.1f} mm")

    max_chars = (
        args.max_command_chars
        if args.command == "svg" and args.max_command_chars
        else BUFFER_PROFILES["large"].hpgl_command_chars
    )
    output = HPGLWriter(
        MutohXP500(unit_mm=args.device_unit), transform, max_command_chars=max_chars
    ).write(document)
    Path(args.output).write_text(output, encoding="ascii")
    print(f"Wrote {args.output}")

    if getattr(args, "stats", False):
        stats(
            document,
            transform,
            hpgl_original_bounds,
            hpgl_fit_scale,
            hpgl_fit_rotation,
        )


if __name__ == "__main__":
    main()
