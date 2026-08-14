"""Small local web interface for previewing and sending HP-GL plots."""

from __future__ import annotations

import argparse
import json
import signal
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
from inspect import signature
from pathlib import Path
from urllib.parse import urlsplit

from .calibration import create_calibration, create_measured_calibration
from .calibration_profiles import CalibrationProfileStore
from .cli import convert_hpgl, ra_fill_spacings
from .devices.mutoh_xp500 import MutohXP500
from .hard_clip import HardClipProfile, drawable_area, get_hard_clip
from .hardware_settings import HardwareSettingsStore, validate_hardware_settings
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .job_history import JobHistory
from .optimize.geometry import optimize_geometry
from .optimize.paths import optimize_nearest
from .paper import Paper, get_paper
from .prepared_queue import PreparedQueueStore
from .report import check_bounds
from .serial_io import (
    BUFFER_PROFILES,
    SerialSettings,
    SerialTransmissionCancelled,
    list_serial_ports,
    query_hard_clip,
    send_bytes,
    serial_status,
)
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.fit import apply_fit, fit_document_to_area, rotate_document
from .transform.hard_clip import hard_clip_center_correction
from .web_profiles import TYPE_LABELS, PenProfileStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# JSON escaping adds overhead. The actual file-size limit is checked separately.
MAX_REQUEST_BYTES = 40 * 1024 * 1024
MAX_QUEUE_ITEMS = 20
WEB_PAGES = {"plot", "hardware", "calibration", "pens"}


def package_version() -> str:
    """Return the installed package version without breaking source checkouts."""
    try:
        return version("mutohplot")
    except PackageNotFoundError:
        return "development"


@dataclass(slots=True)
class PreparedPlot:
    token: str
    name: str
    data: bytes
    source_bytes: int
    preview_svg: str
    polylines: int
    drawing_mm: float
    pen_up_mm: float
    bounds: tuple[float, float, float, float] | None
    rotation: int
    scale: float | None
    source_type: str
    pens: dict[str, int]
    warnings: list[str]
    profile_name: str
    mapping_type: str
    profile_pens: dict[str, dict]
    queue_status: str = "prepared"


class PlotState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.prepared: dict[str, PreparedPlot] = {}
        self.queue: list[str] = []
        self.status = "idle"
        self.sent = 0
        self.total = 0
        self.message = "Bereit"
        self.name: str | None = None
        self.port: str | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.job_id: str | None = None
        self.transmission_done = threading.Event()
        self.transmission_done.set()
        self.transmission_resumed = threading.Event()
        self.transmission_resumed.set()
        self.transmission_cancelled = threading.Event()
        self.shutdown_requested = False

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "version": package_version(),
                "status": self.status,
                "sent": self.sent,
                "total": self.total,
                "message": self.message,
                "name": self.name,
                "port": self.port,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "job_id": self.job_id,
                "shutdown_requested": self.shutdown_requested,
            }


def _conversion_args(options: dict) -> argparse.Namespace:
    buffer_profile = options.get("buffer_profile", "small")
    if buffer_profile not in BUFFER_PROFILES:
        raise ValueError("Unbekanntes Pufferprofil")
    margin = float(options.get("margin", 5.0))
    if not 0 <= margin <= 50:
        raise ValueError("Der Sicherheitsrand muss zwischen 0 und 50 mm liegen")
    paper = str(options.get("paper", "a3")).lower()
    if paper not in {"a3", "a2", "a1", "a0"}:
        raise ValueError("Unbekanntes Papierformat")
    raw_pen_map = options.get("pen_map", {})
    if not isinstance(raw_pen_map, dict):
        raise TypeError("Ungültige SVG-Stiftzuordnung")
    try:
        pen_map = {str(color).lower(): int(pen) for color, pen in raw_pen_map.items()}
    except (TypeError, ValueError) as error:
        raise ValueError("Ungültige SVG-Stiftzuordnung") from error
    if any(pen < 1 or pen > 8 for pen in pen_map.values()):
        raise ValueError("SVG-Stiftnummern müssen zwischen 1 und 8 liegen")
    raw_hpgl_map = options.get("hpgl_pen_map", {})
    if not isinstance(raw_hpgl_map, dict):
        raise TypeError("Ungültige HP-GL-Stiftzuordnung")
    try:
        hpgl_pen_map = {int(source): int(target) for source, target in raw_hpgl_map.items()}
    except (TypeError, ValueError) as error:
        raise ValueError("Ungültige HP-GL-Stiftzuordnung") from error
    if any(not 1 <= source <= 8 or not 1 <= target <= 8 for source, target in hpgl_pen_map.items()):
        raise ValueError("HP-GL-Stiftnummern müssen zwischen 1 und 8 liegen")
    fit = bool(options.get("fit", True))
    rotation_option = options.get("rotation")
    if rotation_option is None:
        auto_rotate = bool(options.get("auto_rotate", True)) if fit else False
        rotation = 0
    elif str(rotation_option).lower() == "auto":
        auto_rotate = True
        rotation = 0
    else:
        try:
            rotation = int(rotation_option)
        except (TypeError, ValueError) as error:
            raise ValueError("Ungültige Drehung") from error
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("Drehung muss automatisch, 0°, 90°, 180° oder 270° sein")
        auto_rotate = False
    if not fit and (auto_rotate or rotation):
        raise ValueError("Drehung erfordert aktiviertes Einpassen (--fit)")
    return argparse.Namespace(
        source_unit=0.025,
        device_unit=0.01,
        paper=paper,
        landscape=bool(options.get("landscape", False)),
        window="norm",
        fit=fit,
        rotate=rotation,
        auto_rotate=auto_rotate,
        margin=margin,
        offset_first=0.0,
        offset_second=0.0,
        no_hardclip_correction=False,
        optimize=bool(options.get("optimize", True)),
        no_reverse=False,
        report=False,
        stats=False,
        config=None,
        pen_width=[],
        default_pen_width=None,
        buffer_profile=buffer_profile,
        progress=False,
        swap_axes=False,
        flip_first=False,
        flip_second=False,
        pen_map=pen_map,
        pen_remap=hpgl_pen_map,
    )


class WebApplication:
    def __init__(
        self,
        sender: Callable = send_bytes,
        profile_store=None,
        job_history=None,
        queue_store=None,
        calibration_store=None,
        hardware_store=None,
    ) -> None:
        self.state = PlotState()
        self.sender = sender
        self.profiles = profile_store or PenProfileStore()
        self.jobs = job_history or JobHistory()
        self.queue_store = queue_store or PreparedQueueStore()
        self.calibrations = calibration_store or CalibrationProfileStore()
        self.hardware = hardware_store or HardwareSettingsStore()
        for stored in self.queue_store.snapshot():
            stored.setdefault("source_bytes", len(stored["data"]))
            stored.setdefault("queue_status", "prepared")
            if stored.get("bounds") is not None:
                stored["bounds"] = tuple(stored["bounds"])
            prepared = PreparedPlot(**stored)
            self.state.prepared[prepared.token] = prepared
            self.state.queue.append(prepared.token)

    @staticmethod
    def _write_pen_config(profile: dict, path: Path) -> None:
        lines = [
            "[profile]",
            f"name = {json.dumps(profile['name'], ensure_ascii=False)}",
            "[fill]",
            "spacing-factor = 0.85",
            "[pens]",
            "default-width-mm = 0.5",
            'default-color = "black"',
            'default-type = "other"',
        ]
        for number, pen in profile["pens"].items():
            lines.extend(
                [
                    f"[pen-groups.web-{number}]",
                    f"pens = [{number}]",
                    f"type = {json.dumps(pen['type'])}",
                    f"width-mm = {pen['width_mm']}",
                    f"color = {json.dumps(pen['color'], ensure_ascii=False)}",
                ]
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _enqueue_prepared(self, prepared: PreparedPlot) -> None:
        with self.state.lock:
            if len(self.state.queue) >= MAX_QUEUE_ITEMS:
                raise RuntimeError("Die Warteschlange enthält bereits 20 Aufträge")
            self.state.prepared[prepared.token] = prepared
            self.state.queue.append(prepared.token)
            self.state.message = f"{prepared.name} geprüft und bereit"
        self.queue_store.append(asdict(prepared))
        self.jobs.add(
            {
                "id": prepared.token,
                "name": prepared.name,
                "status": "prepared",
                "created_at": datetime.now(UTC).isoformat(),
                "started_at": None,
                "finished_at": None,
                "port": None,
                "sent": 0,
                "total": len(prepared.data),
                "message": "Geprüft und bereit",
            }
        )

    def _prepare_hpgl(self, source: str, args, input_path: Path, preview_path: Path):
        input_path.write_text(source, encoding="utf-8")
        source_document = HPGLParser(args.source_unit, ra_fill_spacings(args)).parse_text(source)
        source_pens = sorted({polyline.pen for polyline in source_document.polylines})
        output, document, _, _, scale, rotation = convert_hpgl(args, input_path, preview_path)
        mapping = {str(pen): args.pen_remap.get(pen, pen) for pen in source_pens}
        return output, document, scale, rotation, mapping

    def _prepare_svg(self, source: str, args, preview_path: Path, profile: dict):
        document = SVGReader(curve_steps=24, pen_map=args.pen_map, layer_pens=True).read_text(
            source
        )
        if not document.polylines:
            raise ValueError("Das SVG enthält keine unterstützte, sichtbare Liniengeometrie")

        color_to_pen = dict(document.metadata.get("color_to_pen", {}))
        unsupported = sorted(set(document.metadata.get("unsupported_svg_elements", [])))
        for polyline in document.polylines:
            polyline.source_color = profile["pens"][str(polyline.pen)]["color"]
        measured = getattr(args, "measured_calibration", None)
        if measured:
            paper = Paper(measured["name"], measured["paper_width_mm"], measured["paper_height_mm"])
            hard_profile = HardClipProfile(
                measured["name"],
                measured["top_mm"],
                measured["bottom_mm"],
                measured["left_mm"],
                measured["right_mm"],
            )
        else:
            paper = get_paper(args.paper, args.landscape)
            hard_profile = get_hard_clip("norm")
        hard = drawable_area(paper, hard_profile, 0)
        safe = drawable_area(paper, hard_profile, args.margin)
        rotation = 0
        fit_scale = None
        if args.fit:
            rotation = args.rotate
            if args.auto_rotate:
                normal_fit = fit_document_to_area(document, safe, paper.width_mm, paper.height_mm)
                rotated_document = rotate_document(document, 90)
                rotated_fit = fit_document_to_area(
                    rotated_document, safe, paper.width_mm, paper.height_mm
                )
                if rotated_fit.scale > normal_fit.scale:
                    document = rotated_document
                    rotation = 90
            elif args.rotate:
                document = rotate_document(document, args.rotate)
            fit = fit_document_to_area(document, safe, paper.width_mm, paper.height_mm)
            document = apply_fit(document, fit)
            fit_scale = fit.scale
        document, _ = optimize_geometry(document, "normal")
        if args.optimize:
            document = optimize_nearest(document, allow_reverse=True)

        document.metadata["page_width_mm"] = paper.width_mm
        document.metadata["page_height_mm"] = paper.height_mm
        write_preview(document, preview_path, paper=paper, hard_clip=hard, safe_area=safe)

        base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        correction = hard_clip_center_correction(hard_profile)
        transform = CoordinateTransform(
            base.a,
            base.b,
            base.c,
            base.d,
            base.tx + correction.first_mm,
            base.ty + correction.second_mm,
        )
        max_chars = BUFFER_PROFILES[args.buffer_profile].hpgl_command_chars
        output = HPGLWriter(
            MutohXP500(unit_mm=args.device_unit), transform, max_command_chars=max_chars
        ).write(document)
        warnings = []
        if unsupported:
            warnings.append("Nicht gezeichnete SVG-Elemente: " + ", ".join(unsupported))
        bounds_check = check_bounds(document, safe)
        if not bounds_check.inside:
            warnings.append("Zeichnung liegt außerhalb des sicheren Bereichs")
        return output, document, fit_scale, rotation, color_to_pen, warnings

    def prepare(self, name: str, source: str, options: dict) -> dict:
        with self.state.lock:
            if len(self.state.queue) >= MAX_QUEUE_ITEMS:
                raise RuntimeError("Die Warteschlange enthält bereits 20 Aufträge")
        if not source.strip():
            raise ValueError("Die Plotdatei ist leer")
        if len(source.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise ValueError("Die Plotdatei ist größer als 20 MB")
        args = _conversion_args(options)
        args.measured_calibration = self.calibrations.active_profile()
        profile = self.profiles.get(str(options.get("profile", "")) or None)
        suffix = Path(name).suffix.lower()
        if suffix not in {".hpgl", ".plt", ".svg"}:
            raise ValueError("Unterstützt werden HP-GL (.hpgl, .plt) und SVG (.svg)")
        with tempfile.TemporaryDirectory(prefix="mutohplot-web-") as directory:
            input_path = Path(directory) / "input.hpgl"
            preview_path = Path(directory) / "preview.svg"
            config_path = Path(directory) / "web-profile.toml"
            self._write_pen_config(profile, config_path)
            args.config = str(config_path)
            if suffix == ".svg":
                output, document, scale, rotation, pens, warnings = self._prepare_svg(
                    source, args, preview_path, profile
                )
                source_type = "SVG"
                mapping_type = "svg-color"
            else:
                output, document, scale, rotation, pens = self._prepare_hpgl(
                    source, args, input_path, preview_path
                )
                source_type = "HP-GL"
                mapping_type = "hpgl-pen"
                warnings = []
            preview_svg = preview_path.read_text(encoding="utf-8")

        token = uuid.uuid4().hex
        prepared = PreparedPlot(
            token=token,
            name=Path(name or "zeichnung.hpgl").name,
            data=output.encode("ascii"),
            source_bytes=len(source.encode("utf-8")),
            preview_svg=preview_svg,
            polylines=len(document.polylines),
            drawing_mm=document.drawing_distance_mm(),
            pen_up_mm=document.pen_up_distance_mm(),
            bounds=document.bounds(),
            rotation=rotation,
            scale=scale,
            source_type=source_type,
            pens=pens,
            warnings=warnings,
            profile_name=profile["name"],
            mapping_type=mapping_type,
            profile_pens=profile["pens"],
        )
        self._enqueue_prepared(prepared)
        if args.measured_calibration:
            paper = Paper(
                args.measured_calibration["name"],
                args.measured_calibration["paper_width_mm"],
                args.measured_calibration["paper_height_mm"],
            )
        else:
            paper = get_paper(args.paper, args.landscape)
        return {
            "token": token,
            "name": prepared.name,
            "preview_url": f"/api/preview/{token}",
            "polylines": prepared.polylines,
            "drawing_mm": round(prepared.drawing_mm, 1),
            "pen_up_mm": round(prepared.pen_up_mm, 1),
            "bounds": prepared.bounds,
            "rotation": prepared.rotation,
            "scale": prepared.scale,
            "bytes": len(prepared.data),
            "source_bytes": prepared.source_bytes,
            "source_type": prepared.source_type,
            "paper": paper.name if args.measured_calibration else args.paper,
            "landscape": False if args.measured_calibration else args.landscape,
            "paper_width_mm": paper.width_mm,
            "paper_height_mm": paper.height_mm,
            "pens": prepared.pens,
            "warnings": prepared.warnings,
            "profile_name": prepared.profile_name,
            "mapping_type": prepared.mapping_type,
            "profile_pens": prepared.profile_pens,
            "calibration_profile": (
                args.measured_calibration["name"] if args.measured_calibration else None
            ),
        }

    def prepare_calibration(self, options: dict) -> dict:
        paper_name = str(options.get("paper", "a3")).lower()
        if paper_name not in {"a3", "a2", "a1", "a0"}:
            raise ValueError("Unbekanntes Papierformat")
        window = str(options.get("window", "norm"))
        profile = get_hard_clip(window)
        margin = float(options.get("margin", 5.0))
        if not 0 <= margin <= 50:
            raise ValueError("Der Sicherheitsrand muss zwischen 0 und 50 mm liegen")
        buffer_profile = str(options.get("buffer_profile", "small"))
        if buffer_profile not in BUFFER_PROFILES:
            raise ValueError("Unbekanntes Pufferprofil")
        pen_profile = self.profiles.get(str(options.get("profile", "")) or None)
        measured_width = options.get("measured_width_mm")
        measured_height = options.get("measured_height_mm")
        measured = measured_width is not None or measured_height is not None
        if measured:
            try:
                measured_width = float(measured_width)
                measured_height = float(measured_height)
            except (TypeError, ValueError) as error:
                raise ValueError("Ungültige gemessene Plotterfläche") from error
            if not 1 <= measured_width <= 5000 or not 1 <= measured_height <= 5000:
                raise ValueError("Gemessene Plotterfläche muss zwischen 1 und 5000 mm liegen")
            paper = Paper("XP-500 gemessen", measured_width, measured_height)
            profile = HardClipProfile("Gemessen", 0, 0, 0, 0)
            document = create_measured_calibration(measured_width, measured_height, margin)
        else:
            paper = get_paper(paper_name)
            document = create_calibration(paper_name, window, margin)
        hard = drawable_area(paper, profile, 0)
        safe = drawable_area(paper, profile, margin)
        for polyline in document.polylines:
            polyline.source_color = pen_profile["pens"][str(polyline.pen)]["color"]
        base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
        correction = hard_clip_center_correction(profile)
        transform = CoordinateTransform(
            base.a,
            base.b,
            base.c,
            base.d,
            base.tx + correction.first_mm,
            base.ty + correction.second_mm,
        )
        output = HPGLWriter(
            MutohXP500(unit_mm=0.01),
            transform,
            max_command_chars=BUFFER_PROFILES[buffer_profile].hpgl_command_chars,
        ).write(document)
        with tempfile.TemporaryDirectory(prefix="mutohplot-calibration-") as directory:
            preview_path = Path(directory) / "preview.svg"
            write_preview(document, preview_path, paper=paper, hard_clip=hard, safe_area=safe)
            preview_svg = preview_path.read_text(encoding="utf-8")
        token = uuid.uuid4().hex
        prepared = PreparedPlot(
            token=token,
            name=(
                f"Kalibrierung_gemessen_{measured_width:g}x{measured_height:g}.hpgl"
                if measured
                else f"Kalibrierung_{paper_name.upper()}_{window}.hpgl"
            ),
            data=output.encode("ascii"),
            source_bytes=len(output.encode("ascii")),
            preview_svg=preview_svg,
            polylines=len(document.polylines),
            drawing_mm=document.drawing_distance_mm(),
            pen_up_mm=document.pen_up_distance_mm(),
            bounds=document.bounds(),
            rotation=0,
            scale=None,
            source_type="Kalibrierung",
            pens={"1": 1, "2": 2, "3": 3},
            warnings=[],
            profile_name=pen_profile["name"],
            mapping_type="hpgl-pen",
            profile_pens=pen_profile["pens"],
        )
        self._enqueue_prepared(prepared)
        return {
            "token": token,
            "name": prepared.name,
            "preview_url": f"/api/preview/{token}",
            "paper": paper_name,
            "window": window,
            "margin": margin,
            "measured": measured,
            "paper_width_mm": paper.width_mm,
            "paper_height_mm": paper.height_mm,
        }

    def queue_snapshot(self) -> list[dict]:
        with self.state.lock:
            active_id = self.state.job_id
            active_status = self.state.status
            result = []
            for position, token in enumerate(self.state.queue, start=1):
                if token not in self.state.prepared:
                    continue
                prepared = self.state.prepared[token]
                bounds = prepared.bounds
                result.append(
                    {
                        "token": token,
                        "position": position,
                        "name": prepared.name,
                        "bytes": len(prepared.data),
                        "source_bytes": prepared.source_bytes,
                        "plot_width_mm": round(bounds[2] - bounds[0], 1) if bounds else None,
                        "plot_height_mm": round(bounds[3] - bounds[1], 1) if bounds else None,
                        "profile_name": prepared.profile_name,
                        "status": active_status if token == active_id else prepared.queue_status,
                    }
                )
            return result

    def change_queue(self, token: str, action: str) -> list[dict]:
        with self.state.lock:
            if token not in self.state.queue:
                raise ValueError("Auftrag ist nicht mehr in der Warteschlange")
            if token == self.state.job_id and self.state.status in {
                "sending",
                "waiting_xon",
                "paused",
                "cancelling",
            }:
                raise RuntimeError("Ein laufender Auftrag kann nicht verändert werden")
            index = self.state.queue.index(token)
            if action == "up" and index > 0:
                self.state.queue[index - 1], self.state.queue[index] = (
                    self.state.queue[index],
                    self.state.queue[index - 1],
                )
            elif action == "down" and index < len(self.state.queue) - 1:
                self.state.queue[index + 1], self.state.queue[index] = (
                    self.state.queue[index],
                    self.state.queue[index + 1],
                )
            elif action == "remove":
                self.state.queue.remove(token)
                self.state.prepared.pop(token, None)
            elif action not in {"up", "down"}:
                raise ValueError("Unbekannte Warteschlangenaktion")
        if action == "remove":
            self.queue_store.remove(token)
            now = datetime.now(UTC).isoformat()
            self.jobs.update(
                token,
                status="removed",
                message="Aus Warteschlange entfernt",
                finished_at=now,
            )
        else:
            self.queue_store.reorder([item["token"] for item in self.queue_snapshot()])
        return self.queue_snapshot()

    def start(self, token: str, port: str | None = None, buffer_profile: str | None = None) -> None:
        hardware = self.hardware.get()
        port = port or hardware["port"]
        buffer_profile = buffer_profile or hardware["buffer_profile"]
        if buffer_profile not in BUFFER_PROFILES:
            raise ValueError("Unbekanntes Pufferprofil")
        if not port:
            raise ValueError("Bitte eine serielle Schnittstelle auswählen")
        with self.state.lock:
            if self.state.shutdown_requested:
                raise RuntimeError("Der Webdienst wartet auf einen sicheren Neustart")
            if self.state.status in {"sending", "waiting_xon", "paused", "cancelling"}:
                raise RuntimeError("Es läuft bereits ein Plotauftrag")
            prepared = self.state.prepared.get(token)
            if prepared is None:
                raise ValueError("Die Vorschau ist nicht mehr aktuell; bitte erneut prüfen")
            if token not in self.state.queue:
                raise ValueError("Der Auftrag ist nicht mehr in der Warteschlange")
            if prepared.queue_status not in {"prepared", "cancelled", "error"}:
                raise RuntimeError("Der Auftrag kann in diesem Zustand nicht gestartet werden")
            self.state.status = "sending"
            self.state.sent = 0
            self.state.total = len(prepared.data)
            self.state.message = f"Sende {prepared.name}"
            self.state.name = prepared.name
            self.state.port = port
            self.state.started_at = datetime.now(UTC).isoformat()
            self.state.finished_at = None
            self.state.job_id = token
            self.state.transmission_done.clear()
            self.state.transmission_resumed.set()
            self.state.transmission_cancelled.clear()
        self.jobs.update(
            token,
            status="sending",
            port=port,
            started_at=self.state.started_at,
            message=f"Sende {prepared.name}",
        )

        settings = SerialSettings(
            port=port,
            baudrate=hardware["baudrate"],
            xonxoff=hardware["flow_control"] == "xonxoff",
        )

        def progress(sent: int, total: int) -> None:
            with self.state.lock:
                self.state.sent = sent
                self.state.total = total
            self.jobs.update(token, persist=False, sent=sent, total=total)

        def control() -> None:
            if self.state.transmission_cancelled.is_set():
                raise SerialTransmissionCancelled("Plotauftrag abgebrochen")
            while not self.state.transmission_resumed.wait(0.05):
                if self.state.transmission_cancelled.is_set():
                    raise SerialTransmissionCancelled("Plotauftrag abgebrochen")

        def flow_control(waiting: bool) -> None:
            with self.state.lock:
                if waiting and self.state.status == "sending":
                    self.state.status = "waiting_xon"
                    self.state.message = "Plotter pausiert die Übertragung · wartet auf XON"
                elif not waiting and self.state.status == "waiting_xon":
                    self.state.status = "sending"
                    self.state.message = f"Sende {prepared.name}"

        def transmit() -> None:
            try:
                sender_kwargs = {"control": control}
                if "flow_control" in signature(self.sender).parameters:
                    sender_kwargs["flow_control"] = flow_control
                self.sender(
                    prepared.data,
                    settings,
                    BUFFER_PROFILES[buffer_profile],
                    progress,
                    **sender_kwargs,
                )
            except SerialTransmissionCancelled:
                with self.state.lock:
                    self.state.status = "cancelled"
                    self.state.message = (
                        "Plotauftrag abgebrochen · Empfangspuffer am Plotter mit RESET löschen"
                    )
            except (OSError, RuntimeError, TimeoutError) as error:
                with self.state.lock:
                    self.state.status = "error"
                    self.state.message = f"Übertragung fehlgeschlagen: {error}"
            else:
                with self.state.lock:
                    self.state.status = "complete"
                    self.state.message = "Plotauftrag vollständig übertragen"
            finally:
                with self.state.lock:
                    self.state.finished_at = datetime.now(UTC).isoformat()
                    final_status = self.state.status
                    final_message = self.state.message
                    final_sent = self.state.sent
                    final_total = self.state.total
                    finished_at = self.state.finished_at
                self.jobs.update(
                    token,
                    status=final_status,
                    message=final_message,
                    sent=final_sent,
                    total=final_total,
                    finished_at=finished_at,
                )
                if final_status == "complete":
                    with self.state.lock:
                        if token in self.state.queue:
                            self.state.queue.remove(token)
                        self.state.prepared.pop(token, None)
                    self.queue_store.remove(token)
                else:
                    with self.state.lock:
                        prepared.queue_status = final_status
                    self.queue_store.update(token, queue_status=final_status)
                self.state.transmission_done.set()

        threading.Thread(target=transmit, name="mutohplot-send", daemon=False).start()

    def control(self, action: str) -> None:
        with self.state.lock:
            if action == "pause":
                if self.state.status not in {"sending", "waiting_xon"}:
                    raise RuntimeError("Der Plotauftrag kann jetzt nicht angehalten werden")
                self.state.transmission_resumed.clear()
                self.state.status = "paused"
                self.state.message = "Übertragung angehalten · Stop"
            elif action == "resume":
                if self.state.status != "paused":
                    raise RuntimeError("Der Plotauftrag ist nicht angehalten")
                self.state.transmission_resumed.set()
                self.state.status = "sending"
                self.state.message = "Übertragung fortgesetzt · Go"
            elif action == "cancel":
                if self.state.status not in {"sending", "waiting_xon", "paused"}:
                    raise RuntimeError("Es läuft kein Plotauftrag")
                self.state.status = "cancelling"
                self.state.message = "Plotauftrag wird abgebrochen"
                self.state.transmission_cancelled.set()
                self.state.transmission_resumed.set()
            else:
                raise ValueError("Unbekannte Plotsteuerung")

    def request_shutdown(self) -> threading.Event:
        with self.state.lock:
            self.state.shutdown_requested = True
            if not self.state.transmission_done.is_set():
                self.state.message = "Neustart wartet auf das Ende der Übertragung"
        return self.state.transmission_done


class MutohPlotHandler(BaseHTTPRequestHandler):
    server_version = "MutohPlotWeb/0.1"

    @property
    def app(self) -> WebApplication:
        return self.server.app  # type: ignore[attr-defined]

    def _json(self, data: dict | list, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _request_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Ungültige Anfragegröße") from error
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("Anfrage ist leer oder ungültig groß")
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Ungültige JSON-Anfrage") from error

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/plot", "/hardware", "/calibration", "/pens"}:
            page = "plot" if path == "/" else path.removeprefix("/")
            body = render_page(page).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            result = self.app.state.snapshot()
            try:
                result["ports"] = list_serial_ports()
            except RuntimeError:
                result["ports"] = []
            result["hardware"] = self.app.hardware.get()
            result["active_pen_profile"] = self.app.profiles.snapshot()["default"]
            result["active_calibration"] = self.app.calibrations.active_name()
            self._json(result)
        elif path == "/api/hardware":
            self._json(self.app.hardware.get())
        elif path == "/api/profiles":
            result = self.app.profiles.snapshot()
            result["pen_types"] = TYPE_LABELS
            result["pen_widths"] = [0.3, 0.5, 0.7, 1.0, 1.5]
            self._json(result)
        elif path == "/api/calibration/profiles":
            self._json(
                {
                    "profiles": self.app.calibrations.snapshot(),
                    "active": self.app.calibrations.active_name(),
                }
            )
        elif path == "/api/jobs":
            self._json({"jobs": self.app.jobs.snapshot()})
        elif path == "/api/queue":
            self._json({"queue": self.app.queue_snapshot(), "limit": MAX_QUEUE_ITEMS})
        elif path.startswith("/api/preview/"):
            token = path.rsplit("/", 1)[-1]
            with self.app.state.lock:
                prepared = self.app.state.prepared.get(token)
                preview = prepared.preview_svg if prepared else None
            if preview is None:
                self._json({"error": "Vorschau nicht gefunden"}, HTTPStatus.NOT_FOUND)
                return
            body = preview.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"error": "Nicht gefunden"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._request_json()
            path = urlsplit(self.path).path
            if path == "/api/preview":
                result = self.app.prepare(
                    str(payload.get("name", "zeichnung.hpgl")),
                    str(payload.get("source", payload.get("hpgl", ""))),
                    dict(payload.get("options", {})),
                )
                self._json(result)
            elif path == "/api/hardware/save":
                if self.app.state.snapshot()["status"] in {
                    "sending",
                    "waiting_xon",
                    "paused",
                    "cancelling",
                }:
                    raise RuntimeError(
                        "Hardwareeinstellungen können während eines Plots nicht geändert werden"
                    )
                self._json({"hardware": self.app.hardware.put(payload)})
            elif path == "/api/hardware/test":
                candidate = validate_hardware_settings(payload)
                result = serial_status(
                    SerialSettings(
                        port=candidate["port"],
                        baudrate=candidate["baudrate"],
                        xonxoff=candidate["flow_control"] == "xonxoff",
                    )
                )
                self._json({"hardware": candidate, "serial": result})
            elif path == "/api/calibration":
                self._json(self.app.prepare_calibration(payload), HTTPStatus.CREATED)
            elif path == "/api/calibration/measure":
                if self.app.state.snapshot()["status"] in {
                    "sending",
                    "waiting_xon",
                    "paused",
                    "cancelling",
                }:
                    raise RuntimeError("Während eines laufenden Plots ist keine Messung möglich")
                port = str(payload.get("port", ""))
                if not port:
                    raise ValueError("Keine serielle Schnittstelle ausgewählt")
                self._json(query_hard_clip(SerialSettings(port=port, timeout_s=5.0)))
            elif path == "/api/calibration/profiles/save":
                profile = self.app.calibrations.put(payload)
                self._json({"profile": profile}, HTTPStatus.CREATED)
            elif path == "/api/calibration/profiles/delete":
                self.app.calibrations.delete(str(payload.get("name", "")))
                self._json({"deleted": payload.get("name")})
            elif path == "/api/calibration/profiles/activate":
                profile = self.app.calibrations.activate(payload.get("name"))
                self._json({"active": profile["name"] if profile else None})
            elif path == "/api/plot":
                self.app.start(
                    str(payload.get("token", "")),
                    str(payload.get("port", "")) or None,
                    str(payload.get("buffer_profile", "")) or None,
                )
                self._json({"status": "sending"}, HTTPStatus.ACCEPTED)
            elif path == "/api/plot/control":
                self.app.control(str(payload.get("action", "")))
                self._json({"status": self.app.state.snapshot()["status"]}, HTTPStatus.ACCEPTED)
            elif path == "/api/queue/control":
                queue = self.app.change_queue(
                    str(payload.get("token", "")), str(payload.get("action", ""))
                )
                self._json({"queue": queue})
            elif path == "/api/profiles/save":
                profile = self.app.profiles.put(
                    payload.get("profile"), payload.get("previous_name")
                )
                self._json({"profile": profile})
            elif path == "/api/profiles/default":
                self.app.profiles.set_default(str(payload.get("name", "")))
                self._json({"default": payload.get("name")})
            elif path == "/api/profiles/delete":
                self.app.profiles.delete(str(payload.get("name", "")))
                self._json({"deleted": payload.get("name")})
            else:
                self._json({"error": "Nicht gefunden"}, HTTPStatus.NOT_FOUND)
        except (TypeError, ValueError, RuntimeError) as error:
            with self.app.state.lock:
                self.app.state.message = str(error)
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except (OSError, UnicodeError) as error:
            self._json({"error": f"Verarbeitung fehlgeschlagen: {error}"}, 500)

    def log_message(self, format: str, *args) -> None:
        pass


def serve(host: str = "127.0.0.1", port: int = 8040) -> None:
    server = ThreadingHTTPServer((host, port), MutohPlotHandler)
    server.app = WebApplication()  # type: ignore[attr-defined]
    shutdown_started = threading.Event()

    def graceful_shutdown(signum, frame) -> None:
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        done = server.app.request_shutdown()  # type: ignore[attr-defined]
        print("Sicherer Neustart angefordert; laufende Übertragung wird beendet", flush=True)

        def wait_and_stop() -> None:
            done.wait()
            server.shutdown()

        threading.Thread(target=wait_and_stop, name="mutohplot-shutdown", daemon=True).start()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, graceful_shutdown)
    print(f"MutohPlot Weboberfläche: http://{host}:{server.server_port}")
    print("Beenden mit Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeboberfläche beendet")
    finally:
        server.server_close()


PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>MutohPlot</title><style>
:root{font-family:system-ui,sans-serif;color:#17221d;background:#eef1ed}*{box-sizing:border-box}
body{margin:0}header{background:#183e31;color:white;padding:1rem 5vw}header h1{margin:0;font-size:1.4rem}.topbar{display:flex;align-items:center;justify-content:space-between;gap:1rem}.connection-summary{font-size:.85rem;color:#d9ebe3;text-align:right}
nav{background:#102d24;padding:0 5vw;display:flex;gap:.25rem}nav a{color:#d9ebe3;text-decoration:none;padding:.8rem 1rem;border-bottom:3px solid transparent}nav a:hover,body[data-page="plot"] nav a[data-nav="plot"],body[data-page="hardware"] nav a[data-nav="hardware"],body[data-page="calibration"] nav a[data-nav="calibration"],body[data-page="pens"] nav a[data-nav="pens"]{color:white;border-color:#64c49a;background:#ffffff0d}
main{max-width:1100px;margin:2rem auto;padding:0 1rem;display:grid;grid-template-columns:320px 1fr;gap:1rem}
.page-section{display:none}.page-wide{grid-column:1/-1}body[data-page="plot"] .page-plot,body[data-page="hardware"] .page-hardware,body[data-page="calibration"] .page-calibration,body[data-page="pens"] .page-pens{display:block}.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.settings-grid>*{min-width:0}.section-intro{color:#64736b;margin-top:-.4rem}.safe-note{border-left:4px solid #d29a2e;background:#fff6df;padding:.8rem;margin:1rem 0}
.card{background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 10px #0001}label{display:block;margin:.8rem 0 .3rem}
input,select,button{width:100%;padding:.7rem;border:1px solid #aab6af;border-radius:7px;background:white}
button{margin-top:1rem;background:#176b4c;color:white;border:0;font-weight:650;cursor:pointer}button:disabled{opacity:.45}
.preview-card{align-self:start;overflow:hidden}.preview{min-height:420px;display:grid;place-items:center;overflow:auto}.preview img{display:block;max-width:100%;max-height:70vh}
.plot-info{display:grid;grid-template-columns:repeat(4,1fr);gap:.6rem;margin-bottom:1rem}.plot-info div{background:#e7eee9;border-radius:8px;padding:.65rem}.plot-info strong,.plot-info span{display:block}.plot-info strong{color:#64736b;font-size:.75rem;text-transform:uppercase;letter-spacing:.03em}.plot-info span{margin-top:.25rem;font-weight:650;font-size:.9rem}
.cal-measurements{display:grid;grid-template-columns:1fr 1fr;gap:.65rem;margin:.7rem 0}.cal-measurements div{min-width:0}.cal-measurements label{margin:.2rem 0}.cal-measurements input{width:100%;font-size:1rem}
.checks{display:flex;gap:.5rem;align-items:center}.checks input{width:auto}.status{padding:.7rem;border-radius:7px;background:#e7eee9;margin-top:1rem}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:.4rem;font-size:.9rem;margin-top:1rem}.facts span:nth-child(odd){color:#64736b}
.profile-actions{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}.profile-actions button{margin-top:.4rem}.pen-row{border-top:1px solid #dde3df;padding:.5rem 0}.pen-row strong{display:block}.pen-row .checks{margin:.3rem 0}.pen-row input,.pen-row select{padding:.4rem}
.plot-actions{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}.plot-actions button{margin-top:1rem}.danger{background:#a52a2a}
.queue-card,.history-card{grid-column:1/-1}.jobs{display:grid;gap:.5rem}.queue{display:grid;gap:.5rem;overflow-x:auto}.job,.queue-item{display:grid;grid-template-columns:2fr 1fr 1.5fr auto;gap:.7rem;padding:.7rem;border-radius:8px;background:#e7eee9;align-items:center}.queue-item{min-width:860px}.job strong,.job span,.queue-item strong,.queue-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.job .complete{color:#176b4c}.job .error,.job .cancelled{color:#a52a2a}.queue-actions{display:grid;grid-template-columns:8rem 6.5rem 2.4rem 2.4rem;gap:.35rem;white-space:nowrap}.queue-actions button{width:100%;margin:0;padding:.45rem .65rem;white-space:nowrap}.queue-actions button:nth-child(3),.queue-actions button:nth-child(4){padding:.45rem}.queue-actions .remove{background:#7d4038}
@media(max-width:900px){.plot-info{grid-template-columns:1fr 1fr}}@media(max-width:760px){.topbar{display:block}.connection-summary{text-align:left;margin-top:.5rem}nav{overflow-x:auto}nav a{white-space:nowrap}main{grid-template-columns:1fr}.preview{min-height:300px}.settings-grid{grid-template-columns:1fr}}
</style></head><body data-page="__ACTIVE_PAGE__"><header><div class="topbar"><h1>MutohPlot · XP-500 <small id="version">Version wird geladen</small></h1><div class="connection-summary" id="connection-summary">Verbindung wird geladen</div></div></header><nav aria-label="Hauptnavigation"><a href="/plot" data-nav="plot">Plotten</a><a href="/hardware" data-nav="hardware">Hardware</a><a href="/calibration" data-nav="calibration">Kalibrierung</a><a href="/pens" data-nav="pens">Stifte</a></nav><main>
<section class="card page-section page-plot"><h2>Plot vorbereiten</h2><p class="section-intro">Datei, Format und Ausrichtung festlegen. Verbindung, Kalibrierung und Stifte werden aus den gespeicherten Einstellungen übernommen.</p><label>HP-GL- oder SVG-Datei</label><input id="file" type="file" accept=".hpgl,.plt,.svg,image/svg+xml"><small>Die Vorschau wird direkt nach der Auswahl erzeugt. Maximal 20 MB.</small><div id="selection" class="status">Noch keine Datei ausgewählt</div>
<label>Kalibrierungsprofil</label><select id="plotcalibration"><option value="">Standardkalibrierung</option></select><small>Die Auswahl gilt für neue Vorschauen und Plotaufträge. Messwerte werden auf der Seite „Kalibrierung“ bearbeitet.</small>
<label>Papierformat</label><select id="paper"><option value="a3">A3 · Standard</option><option value="a2">A2</option><option value="a1">A1</option><option value="a0">A0</option></select>
<label class="checks"><input id="landscape" type="checkbox"> Querformat</label>
<label>Sicherheitsrand</label><select id="margin"><option value="5">5 mm</option><option value="10">10 mm</option><option value="0">Kein zusätzlicher Rand</option></select>
<label class="checks"><input id="fit" type="checkbox" checked> Auf sicheren Bereich einpassen</label>
<label>Drehung</label><select id="rotation"><option value="auto">Automatisch · beste Ausnutzung</option><option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option></select>
<label class="checks"><input id="optimize" type="checkbox" checked> Leerwege optimieren</label>
<button id="check">Datei prüfen und anzeigen</button>
<div id="penmap"></div>
<div class="plot-actions"><button id="plot" disabled>Plot starten</button><button id="abort" class="danger" hidden>Abbruch</button></div><div id="status" class="status">Bereit</div><div id="facts" class="facts"></div></section>
<section class="card preview-card page-section page-plot"><div class="plot-info" id="plotinfo"><div><strong>Blatt</strong><span>–</span></div><div><strong>Plot</strong><span>–</span></div><div><strong>Ränder</strong><span>–</span></div><div><strong>Skalierung</strong><span>–</span></div></div><div class="preview" id="preview"><p>Hier erscheint die Vorschau.</p></div></section>
<section class="card queue-card page-section page-plot"><h2>Warteschlange</h2><p>Jeder Auftrag wird einzeln bestätigt und gestartet.</p><div class="queue" id="queue"><span>Keine vorbereiteten Aufträge</span></div></section>
<section class="card history-card page-section page-plot"><h2>Letzte Aufträge</h2><div class="jobs" id="jobs"><span>Noch keine Aufträge</span></div></section>

<section class="card page-section page-wide page-hardware"><h2>Hardware</h2><p class="section-intro">Dauerhafte Verbindungseinstellungen für den Mutoh XP-500.</p><div class="safe-note">Standard und Empfehlung: <strong>19200 Baud · 8N1 · XON/XOFF</strong>. Änderungen sind während eines laufenden Plots gesperrt.</div><div class="settings-grid"><div><label>Serielle Schnittstelle</label><select id="port"><option value="">Keine gefunden</option></select></div><div><label>Übertragungsgeschwindigkeit</label><select id="baudrate"><option value="9600">9600 Baud</option><option value="19200">19200 Baud · Standard</option><option value="38400">38400 Baud</option></select></div><div><label>Datenformat</label><select id="serialframe"><option value="8N1">8 Datenbits · keine Parität · 1 Stoppbit (8N1)</option></select></div><div><label>Protokoll / Flusssteuerung</label><select id="flowcontrol"><option value="xonxoff">XON/XOFF · Standard</option><option value="none">Keine Flusssteuerung</option></select></div><div><label>Empfangspuffer des Plotters</label><select id="buffer"><option value="small">1000 Zeichen · sicher</option><option value="large">1 MB · schnell</option></select></div></div><div class="profile-actions"><button id="hwtest">Verbindung testen</button><button id="hwsave">Als Standard speichern</button></div><div id="hwstatus" class="status">Hardwareeinstellungen werden geladen</div></section>

<section class="card page-section page-wide page-calibration"><h2>Kalibrierung</h2><p class="section-intro">Kalibrierungszeichnung erzeugen, Messwerte verwalten und ein Profil ausdrücklich aktivieren.</p><div class="safe-note">Bestehende Kalibrierungen und Koordinatenkonventionen werden nicht automatisch verändert. Erst „Für Plots aktivieren“ schaltet ein gespeichertes Profil frei.</div><div class="settings-grid"><div><label>Referenzformat</label><select id="calpaper"><option value="a3">A3 · Standard</option><option value="a2">A2</option><option value="a1">A1</option><option value="a0">A0</option></select></div><div><label>Hard-Clip-Modus</label><select id="calwindow"><option value="norm">Norm</option><option value="exp">Exp</option><option value="type1">Type 1</option><option value="type3">Type 3</option></select></div><div><label>Sicherheitsrand</label><select id="calmargin"><option value="5">5 mm</option><option value="10">10 mm</option><option value="0">Kein zusätzlicher Rand</option></select></div></div><button id="calibrate">Kalibrierungszeichnung erzeugen</button><h3>Vom Plotter gemessenes Blatt</h3><div class="cal-measurements"><div><label for="calpaperwidth">Breite (mm)</label><input id="calpaperwidth" type="number" min="1" max="5000" step="0.1" inputmode="decimal" value="297"></div><div><label for="calpaperheight">Länge (mm)</label><input id="calpaperheight" type="number" min="1" max="5000" step="0.1" inputmode="decimal" value="420"></div></div><button id="calmeasure">Zeichenfläche vom Plotter lesen</button><small>Die äußeren Blattmaße werden aus der gelesenen Zeichenfläche und den vier Rändern berechnet.</small><h3>Gemessene Abstände</h3><div class="cal-measurements"><div><label for="caltop">Oben (mm)</label><input id="caltop" type="number" min="0" step="0.1" inputmode="decimal"></div><div><label for="calbottom">Unten (mm)</label><input id="calbottom" type="number" min="0" step="0.1" inputmode="decimal"></div><div><label for="calleft">Links (mm)</label><input id="calleft" type="number" min="0" step="0.1" inputmode="decimal"></div><div><label for="calright">Rechts (mm)</label><input id="calright" type="number" min="0" step="0.1" inputmode="decimal"></div></div><button id="calcalculate">Messwerte berechnen</button><div id="calresult" class="status">Noch keine Messwerte berechnet</div><h3>Kalibrierungsprofil speichern</h3><label for="calprofilename">Profilname</label><input id="calprofilename" maxlength="60" placeholder="z. B. Zwischenformat Norm"><button id="calsave">Profil speichern</button><label for="calprofiles">Gespeicherte Profile</label><select id="calprofiles"><option value="">Keine gespeichert</option></select><div class="profile-actions"><button id="calactivate">Für Plots aktivieren</button><button id="caldeactivate">Kalibrierung ausschalten</button></div><button id="caldelete" class="danger">Profil löschen</button><small>Nur das ausdrücklich aktivierte Profil verändert Blattgröße, Zeichenfläche und Mittelpunktkorrektur neuer Plotaufträge.</small></section>

<section class="card page-section page-wide page-pens"><h2>Stifte</h2><p class="section-intro">Bestückungsprofile für die acht Stiftplätze verwalten.</p><label>Stiftprofil</label><select id="profile"></select><div class="profile-actions"><button id="newprofile">Neues Profil</button><button id="saveprofile">Speichern</button><button id="defaultprofile">Als Standard</button><button id="deleteprofile">Löschen</button></div><div id="peneditor"></div><div id="penstatus" class="status">Das Standardprofil wird für neue Plotaufträge verwendet.</div></section>
</main><script>
let token=null,localMessage='',penMap={},mappingType='',mappingProfilePens={},profileData=null,editingOriginal=null,plotStatus='idle',plotStarted=false,previewBusy=false,previewQueued=false,queueBusy=false,measuredHardClip=null,hardwareData=null; const $=id=>document.getElementById(id);
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):null});const j=await r.json();if(!r.ok)throw Error(j.error||'Fehler');return j}
function currentProfile(){return profileData?.profiles[$('profile').value]}
function renderProfile(){const profile=currentProfile(),box=$('peneditor');box.replaceChildren();if(!profile)return;for(let n=1;n<=8;n++){const pen=profile.pens[n],row=document.createElement('div');row.className='pen-row';const title=document.createElement('strong');title.textContent=`Stift ${n}`;const label=document.createElement('input');label.value=pen.label;label.onchange=()=>pen.label=label.value;const line=document.createElement('div');line.className='checks';const type=document.createElement('select');for(const [value,text] of Object.entries(profileData.pen_types)){const option=document.createElement('option');option.value=value;option.textContent=text;option.selected=value===pen.type;type.append(option)}type.onchange=()=>pen.type=type.value;const width=document.createElement('select');for(const value of profileData.pen_widths){const option=document.createElement('option');option.value=value;option.textContent=`${String(value).replace('.',',')} mm`;option.selected=value===pen.width_mm;width.append(option)}width.onchange=()=>pen.width_mm=+width.value;const color=document.createElement('input');color.type='color';color.value=/^#[0-9a-f]{6}$/i.test(pen.color)?pen.color:'#000000';color.onchange=()=>pen.color=color.value;line.append(type,width,color);row.append(title,label,line);box.append(row)}}
async function loadProfiles(selected){profileData=await api('/api/profiles');const select=$('profile');select.replaceChildren();for(const name of Object.keys(profileData.profiles)){const option=document.createElement('option');option.value=name;option.textContent=name+(name===profileData.default?' · Standard':'');select.append(option)}select.value=selected&&profileData.profiles[selected]?selected:profileData.default;editingOriginal=select.value;renderProfile()}
function renderPenMap(){const box=$('penmap');box.replaceChildren();const entries=Object.entries(penMap);if(!entries.length)return;const title=document.createElement('label');title.textContent='Quelldarstellung → tatsächlicher Stift';box.append(title);for(const [source,pen] of entries){const actual=mappingProfilePens[pen]||{},row=document.createElement('label');row.className='checks';const swatch=document.createElement('span');swatch.style.cssText='width:1.2rem;height:1.2rem;border:1px solid #777;border-radius:50%;flex:none';swatch.style.backgroundColor=actual.color||'#000000';const text=document.createElement('span');text.textContent=mappingType==='hpgl-pen'?`HP-GL Stift ${source} →`:`SVG ${source} →`;const select=document.createElement('select');select.style.width='auto';for(let n=1;n<=8;n++){const configured=mappingProfilePens[n]||{};const option=document.createElement('option');option.value=n;option.textContent=`Stift ${n} · ${configured.label||''} · ${configured.color||''}`;option.selected=n===pen;select.append(option)}select.onchange=()=>{penMap[source]=+select.value;requestPreview()};row.append(swatch,text,select);box.append(row)}}
function renderPlotControls(){const active=['sending','waiting_xon','paused','cancelling'].includes(plotStatus);$('abort').hidden=!active;$('abort').disabled=plotStatus==='cancelling';$('plot').textContent=plotStatus==='paused'?'Go':['sending','waiting_xon'].includes(plotStatus)?'Stop':'Plot starten';$('plot').disabled=plotStatus==='cancelling'||(!active&&(plotStarted||!token))}
function renderPlotInfo(j){const mm=n=>`${Number(n).toFixed(1).replace('.',',')} mm`,b=j.bounds||[0,0,0,0],plotWidth=b[2]-b[0],plotHeight=b[3]-b[1],right=j.paper_width_mm-b[2],bottom=j.paper_height_mm-b[3],scale=j.scale==null?'Originalgröße':`${(j.scale*100).toFixed(1).replace('.',',')} %`,cal=j.calibration_profile?` · Kalibrierung ${j.calibration_profile}`:'';$('plotinfo').innerHTML=`<div><strong>Blatt</strong><span>${j.paper.toUpperCase()} ${j.landscape?'quer':'hoch'} · ${mm(j.paper_width_mm)} × ${mm(j.paper_height_mm)}${cal}</span></div><div><strong>Plot</strong><span>${mm(plotWidth)} × ${mm(plotHeight)}</span></div><div><strong>Ränder</strong><span>L ${mm(b[0])} · R ${mm(right)} · O ${mm(b[1])} · U ${mm(bottom)}</span></div><div><strong>Skalierung</strong><span>${scale} · ${j.rotation}°</span></div>`}
async function loadJobs(){try{const data=await api('/api/jobs'),box=$('jobs');box.replaceChildren();if(!data.jobs.length){box.textContent='Noch keine Aufträge';return}for(const j of data.jobs.slice(0,10)){const row=document.createElement('div');row.className='job';const name=document.createElement('strong');name.textContent=j.name;const state=document.createElement('span');state.className=j.status;state.textContent=j.status;const progress=document.createElement('span');progress.textContent=j.total?`${Math.round(j.sent*100/j.total)} %`:'–';const time=document.createElement('span');time.textContent=new Date(j.started_at||j.created_at).toLocaleString('de-DE');row.append(name,state,progress,time);box.append(row)}}catch(e){$('jobs').textContent=e.message}}
function renderQueue(items){const box=$('queue');box.replaceChildren();if(!items.length){box.textContent='Keine vorbereiteten Aufträge';return}const humanBytes=n=>n<1024?`${n} B`:n<1024*1024?`${(n/1024).toFixed(1).replace('.',',')} KB`:`${(n/1024/1024).toFixed(1).replace('.',',')} MB`;for(const [index,item] of items.entries()){const row=document.createElement('div');row.className='queue-item';const name=document.createElement('strong');name.textContent=`${item.position}. ${item.name}`;const profile=document.createElement('span');profile.textContent=`${item.profile_name} · ${item.status}`;const size=document.createElement('span');const plotSize=item.plot_width_mm==null?'–':`${String(item.plot_width_mm).replace('.',',')} × ${String(item.plot_height_mm).replace('.',',')} mm`;size.textContent=`${plotSize} · Datei ${humanBytes(item.source_bytes)}`;const actions=document.createElement('div');actions.className='queue-actions';const active=['sending','waiting_xon','paused','cancelling'].includes(item.status),startable=['prepared','cancelled','error'].includes(item.status);for(const [action,label,title] of [['start',item.status==='prepared'?'Plotten':'Erneut plotten',''],['remove','Entfernen',''],['up','↑','Nach oben'],['down','↓','Nach unten']]){const button=document.createElement('button');button.textContent=label;if(title)button.title=title;if(action==='remove')button.className='remove';button.disabled=queueBusy||active||(action==='start'&&!startable)||(action==='up'&&index===0)||(action==='down'&&index===items.length-1);button.onclick=()=>queueAction(item,action).catch(e=>{$('status').textContent=e.message});actions.append(button)}row.append(name,profile,size,actions);box.append(row)}}
async function queueAction(item,action){if(queueBusy)return;queueBusy=true;try{if(action==='start'){const retry=item.status==='cancelled'||item.status==='error',question=retry?`Auftrag ${item.name} erneut plotten? Vorher den Plotter mit LOCAL und RESET leeren und das Blatt prüfen.`:`Plot ${item.name} jetzt starten? Der Plotter beginnt sich zu bewegen.`;if(!confirm(question))return;await api('/api/plot',{token:item.token});token=item.token;plotStarted=true;plotStatus='sending';renderPlotControls();queueBusy=false;await loadQueue()}else{const data=await api('/api/queue/control',{token:item.token,action});queueBusy=false;renderQueue(data.queue);localMessage=action==='remove'?`${item.name} entfernt`:'Reihenfolge gespeichert';$('status').textContent=localMessage}await loadJobs()}finally{queueBusy=false}}
async function loadQueue(){if(queueBusy)return;try{const data=await api('/api/queue');renderQueue(data.queue)}catch(e){$('queue').textContent=e.message}}
async function status(){try{const s=await api('/api/status');$('version').textContent=`v${s.version}`;plotStatus=s.status;renderPlotControls();if(!localMessage)$('status').textContent=s.message+(s.total?` · ${Math.round(s.sent*100/s.total)} %`:'');const old=$('port').value,preferred=s.ports.find(p=>p.device===s.hardware.port)||s.ports.find(p=>/ttyUSB|ttyACM/i.test(p.device)||/USB.Serial/i.test(p.description));$('port').innerHTML=s.ports.length?s.ports.map(p=>`<option value="${p.device}">${p.device} · ${p.description}</option>`).join(''):'<option value="">Keine gefunden</option>';$('port').value=(old&&s.ports.some(p=>p.device===old)?old:'')||preferred?.device||($('port').options[0]?.value||'');const flow=s.hardware.flow_control==='xonxoff'?'XON/XOFF':'ohne Flusssteuerung',cal=s.active_calibration||'Standardkalibrierung';$('connection-summary').textContent=`${s.hardware.port} · ${s.hardware.baudrate} Baud · ${flow} · ${s.hardware.buffer_profile==='small'?'1000 Zeichen':'1 MB'} · Stifte ${s.active_pen_profile} · ${cal}`}catch(e){$('status').textContent=e.message}}
function hardwarePayload(){return{port:$('port').value,baudrate:+$('baudrate').value,frame:$('serialframe').value,flow_control:$('flowcontrol').value,buffer_profile:$('buffer').value}}
async function loadHardware(){hardwareData=await api('/api/hardware');$('baudrate').value=hardwareData.baudrate;$('serialframe').value=hardwareData.frame;$('flowcontrol').value=hardwareData.flow_control;$('buffer').value=hardwareData.buffer_profile;if([...$('port').options].some(o=>o.value===hardwareData.port))$('port').value=hardwareData.port;$('hwstatus').textContent=`Gespeichert: ${hardwareData.port} · ${hardwareData.baudrate} Baud · ${hardwareData.frame} · ${hardwareData.flow_control==='xonxoff'?'XON/XOFF':'keine Flusssteuerung'} · ${hardwareData.buffer_profile==='small'?'1000 Zeichen':'1 MB'}`}
$('hwtest').onclick=async()=>{try{$('hwtest').disabled=true;$('hwstatus').textContent='Prüfe serielle Verbindung …';const data=await api('/api/hardware/test',hardwarePayload());$('hwstatus').textContent=`Verbindung zu ${data.serial.port} erfolgreich · ${data.serial.baudrate} Baud · Einstellungen noch nicht gespeichert`}catch(e){$('hwstatus').textContent=e.message}finally{$('hwtest').disabled=false}}
$('hwsave').onclick=async()=>{if(!confirm('Diese Hardwareeinstellungen als Standard für neue Plotaufträge speichern?'))return;try{const data=await api('/api/hardware/save',hardwarePayload());hardwareData=data.hardware;$('hwstatus').textContent='Hardwareeinstellungen als Standard gespeichert';await status()}catch(e){$('hwstatus').textContent=e.message}}
function requestPreview(){if(!$('file').files[0])return;token=null;plotStarted=false;renderPlotControls();if(previewBusy){previewQueued=true;localMessage='Einstellung geändert · Vorschau wird anschließend neu berechnet';$('status').textContent=localMessage;return}$('check').click()}
$('check').onclick=async()=>{const f=$('file').files[0];if(!f){localMessage='Bitte eine HP-GL- oder SVG-Datei auswählen';return $('status').textContent=localMessage}if(f.size>20*1024*1024){localMessage=`${f.name} ist ${(f.size/1024/1024).toFixed(1)} MB groß; erlaubt sind 20 MB`;$('status').textContent=localMessage;return}previewBusy=true;$('check').disabled=true;localMessage='Prüfe und konvertiere Datei …';$('status').textContent=localMessage;const isSvg=f.name.toLowerCase().endsWith('.svg'),options={profile:$('profile').value,paper:$('paper').value,landscape:$('landscape').checked,margin:+$('margin').value,fit:$('fit').checked,rotation:$('rotation').value,optimize:$('optimize').checked,buffer_profile:$('buffer').value,pen_map:isSvg?penMap:{},hpgl_pen_map:isSvg?{}:penMap};try{const j=await api('/api/preview',{name:f.name,source:await f.text(),options});if(previewQueued)return;token=j.token;plotStarted=false;renderPlotControls();renderPlotInfo(j);$('preview').innerHTML=`<img src="${j.preview_url}" alt="Plotvorschau">`;penMap=j.pens||{};mappingType=j.mapping_type;mappingProfilePens=j.profile_pens||{};renderPenMap();const pens=Object.keys(penMap).length?Object.entries(penMap).map(([c,p])=>`${c} → ${p}`).join(', '):'Keine Stiftwahl erkannt';const format=j.paper.toUpperCase()+(j.landscape?' quer':' hoch')+` · ${j.paper_width_mm} × ${j.paper_height_mm} mm`;const warnings=(j.warnings||[]).join(' · ')||'Keine';$('facts').innerHTML=`<span>Quelle</span><span>${j.source_type}</span><span>Profil</span><span>${j.profile_name}</span><span>Format</span><span>${format}</span><span>Einpassen</span><span>${options.fit?'Ja':'Nein'}</span><span>Linienzüge</span><span>${j.polylines}</span><span>Zeichenweg</span><span>${j.drawing_mm} mm</span><span>Leerweg</span><span>${j.pen_up_mm} mm</span><span>Zuordnung</span><span>${pens}</span><span>Hinweise</span><span>${warnings}</span><span>Drehung</span><span>${j.rotation}°</span><span>Daten</span><span>${j.bytes} Bytes</span>`;localMessage='';$('status').textContent=`${j.name} geprüft und bereit`;}catch(e){if(!previewQueued){token=null;renderPlotControls();localMessage=e.message;$('status').textContent=localMessage}}finally{previewBusy=false;$('check').disabled=false;if(previewQueued){previewQueued=false;requestPreview()}}}
async function readPlotterArea(){measuredHardClip=await api('/api/calibration/measure',{port:$('port').value});return measuredHardClip}
$('calibrate').onclick=async()=>{try{$('calibrate').disabled=true;$('calresult').textContent='Lese aktuelle Zeichenfläche vom Plotter …';const measured=await readPlotterArea();$('calpaperwidth').value=measured.width_mm;$('calpaperheight').value=measured.height_mm;$('calresult').textContent=`Plotter-Zeichenfläche ${String(measured.width_mm).replace('.',',')} × ${String(measured.height_mm).replace('.',',')} mm · Kalibrierungszeichnung wird darauf ausgerichtet`;const j=await api('/api/calibration',{paper:$('calpaper').value,window:$('calwindow').value,margin:+$('calmargin').value,profile:$('profile').value,buffer_profile:$('buffer').value,measured_width_mm:measured.width_mm,measured_height_mm:measured.height_mm});token=j.token;plotStarted=false;renderPlotControls();$('preview').innerHTML=`<img src="${j.preview_url}" alt="Kalibrierungsvorschau">`;localMessage=`${j.name} · ${j.paper_width_mm} × ${j.paper_height_mm} mm geprüft und in Warteschlange`;$('calresult').textContent=localMessage;await loadQueue();await loadJobs()}catch(e){$('calresult').textContent=e.message;$('status').textContent=e.message}finally{$('calibrate').disabled=false}}
$('calmeasure').onclick=async()=>{try{$('calmeasure').disabled=true;const j=await readPlotterArea(),marginFields=['caltop','calbottom','calleft','calright'];$('calpaperwidth').value=j.width_mm;$('calpaperheight').value=j.height_mm;if(marginFields.some(id=>$(id).value.trim()==='')){$('calresult').textContent=`Plotter-Zeichenfläche ${String(j.width_mm).replace('.',',')} × ${String(j.height_mm).replace('.',',')} mm als Voreinstellung übernommen · für äußere Blattmaße bitte alle vier Ränder eingeben`;return}const top=Number($('caltop').value.replace(',','.')),bottom=Number($('calbottom').value.replace(',','.')),left=Number($('calleft').value.replace(',','.')),right=Number($('calright').value.replace(',','.'));if([top,bottom,left,right].some(value=>!Number.isFinite(value)||value<0))throw Error('Bitte gültige Randwerte eingeben');$('calpaperwidth').value=(j.width_mm+left+right).toFixed(2);$('calpaperheight').value=(j.height_mm+top+bottom).toFixed(2);$('calcalculate').click()}catch(e){$('calresult').textContent=e.message}finally{$('calmeasure').disabled=false}}
$('calcalculate').onclick=()=>{const fields=['calpaperwidth','calpaperheight','caltop','calbottom','calleft','calright'];if(fields.some(id=>$(id).value.trim()===''))return $('calresult').textContent='Bitte Blattmaße und alle vier Abstände in mm eingeben';const values=fields.map(id=>Number($(id).value.replace(',','.')));if(values.some(value=>!Number.isFinite(value)||value<0))return $('calresult').textContent='Bitte nur positive Millimeterwerte eingeben';const [width,height,top,bottom,left,right]=values,drawableWidth=width-left-right,drawableHeight=height-top-bottom,first=-(top-bottom)/2,second=-(left-right)/2;if(width<=0||height<=0||drawableWidth<=0||drawableHeight<=0)return $('calresult').textContent='Die Messwerte ergeben keine gültige Zeichenfläche';$('calresult').textContent=`Blatt ${width.toFixed(1).replace('.',',')} × ${height.toFixed(1).replace('.',',')} mm · Zeichenfläche ${drawableWidth.toFixed(1).replace('.',',')} × ${drawableHeight.toFixed(1).replace('.',',')} mm · Mittelpunktkorrektur Achse 1 ${first.toFixed(2).replace('.',',')} mm · Achse 2 ${second.toFixed(2).replace('.',',')} mm`}
function calibrationPayload(){return{name:$('calprofilename').value,paper:$('calpaper').value,window:$('calwindow').value,paper_width_mm:$('calpaperwidth').value,paper_height_mm:$('calpaperheight').value,top_mm:$('caltop').value,bottom_mm:$('calbottom').value,left_mm:$('calleft').value,right_mm:$('calright').value}}
async function loadCalibrationProfiles(selected){const data=await api('/api/calibration/profiles'),select=$('calprofiles'),plotSelect=$('plotcalibration');select.replaceChildren();plotSelect.replaceChildren();const names=Object.keys(data.profiles),standard=document.createElement('option');standard.value='';standard.textContent=`Standardkalibrierung${data.active?'':' · AKTIV'}`;plotSelect.append(standard);for(const name of names){const profile=data.profiles[name],plotOption=document.createElement('option');plotOption.value=name;plotOption.textContent=`${name} · ${profile.paper_width_mm} × ${profile.paper_height_mm} mm${name===data.active?' · AKTIV':''}`;plotSelect.append(plotOption)}plotSelect.value=data.active||'';$('caldeactivate').disabled=!data.active;if(!names.length){const option=document.createElement('option');option.value='';option.textContent='Keine gespeichert';select.append(option);$('caldelete').disabled=true;$('calactivate').disabled=true;return}for(const name of names){const profile=data.profiles[name],option=document.createElement('option');option.value=name;option.textContent=`${name} · ${profile.paper_width_mm} × ${profile.paper_height_mm} mm · ${profile.window}${name===data.active?' · AKTIV':''}`;select.append(option)}select.value=selected&&data.profiles[selected]?selected:(data.active||names[0]);$('caldelete').disabled=false;$('calactivate').disabled=false;select.onchange=()=>{const p=data.profiles[select.value],active=p.name===data.active;$('calprofilename').value=p.name;$('calpaper').value=p.paper;$('calwindow').value=p.window;$('calpaperwidth').value=p.paper_width_mm;$('calpaperheight').value=p.paper_height_mm;$('caltop').value=p.top_mm;$('calbottom').value=p.bottom_mm;$('calleft').value=p.left_mm;$('calright').value=p.right_mm;$('calresult').textContent=`Gespeichert · Blatt ${String(p.paper_width_mm).replace('.',',')} × ${String(p.paper_height_mm).replace('.',',')} mm · Zeichenfläche ${String(p.drawable_width_mm).replace('.',',')} × ${String(p.drawable_height_mm).replace('.',',')} mm · ${active?'AKTIV':'nicht aktiv'}`};select.onchange()}
async function setPlotCalibration(){const name=$('plotcalibration').value;await api('/api/calibration/profiles/activate',{name:name||null});await loadCalibrationProfiles(name);localMessage=name?`Kalibrierungsprofil ${name} aktiviert`:'Standardkalibrierung aktiviert';$('status').textContent=localMessage;await status();requestPreview()}
$('calsave').onclick=async()=>{try{const data=await api('/api/calibration/profiles/save',calibrationPayload()),p=data.profile;$('calresult').textContent=`Profil ${p.name} gespeichert · Zeichenfläche ${String(p.drawable_width_mm).replace('.',',')} × ${String(p.drawable_height_mm).replace('.',',')} mm · noch nicht aktiv`;await loadCalibrationProfiles(p.name)}catch(e){$('calresult').textContent=e.message}}
$('caldelete').onclick=async()=>{const name=$('calprofiles').value;if(!name||!confirm(`Kalibrierungsprofil ${name} löschen?`))return;try{await api('/api/calibration/profiles/delete',{name});$('calresult').textContent=`Profil ${name} gelöscht`;await loadCalibrationProfiles()}catch(e){$('calresult').textContent=e.message}}
$('calactivate').onclick=async()=>{const name=$('calprofiles').value;if(!name||!confirm(`Kalibrierungsprofil ${name} für alle neuen Plotaufträge aktivieren?`))return;try{await api('/api/calibration/profiles/activate',{name});await loadCalibrationProfiles(name);$('calresult').textContent=`Profil ${name} ist AKTIV`;requestPreview()}catch(e){$('calresult').textContent=e.message}}
$('caldeactivate').onclick=async()=>{if(!confirm('Gemessene Kalibrierung ausschalten und Standardwerte verwenden?'))return;try{await api('/api/calibration/profiles/activate',{name:null});await loadCalibrationProfiles();$('calresult').textContent='Gemessene Kalibrierung ausgeschaltet';requestPreview()}catch(e){$('calresult').textContent=e.message}}
$('file').onchange=()=>{const f=$('file').files[0];if(!f)return;penMap={};renderPenMap();$('selection').textContent=`Ausgewählt: ${f.name} · ${(f.size/1024/1024).toFixed(2)} MB`;localMessage='';requestPreview()};
$('plotcalibration').onchange=()=>setPlotCalibration().catch(e=>{localMessage=e.message;$('status').textContent=e.message});
$('paper').onchange=requestPreview;
$('calpaper').onchange=()=>{const papers={a3:[297,420],a2:[420,594],a1:[594,841],a0:[841,1189]},size=papers[$('calpaper').value];$('calpaperwidth').value=size[0];$('calpaperheight').value=size[1]};
$('landscape').onchange=requestPreview;
$('fit').onchange=()=>{if(!$('fit').checked){$('rotation').value='0';$('rotation').disabled=true}else{$('rotation').disabled=false;$('rotation').value='auto'}requestPreview()};
$('rotation').onchange=requestPreview;
$('profile').onchange=()=>{editingOriginal=$('profile').value;renderProfile();requestPreview()};
$('newprofile').onclick=()=>{const name=prompt('Name des neuen Stiftprofils');if(!name)return;const copy=JSON.parse(JSON.stringify(currentProfile()));copy.name=name.trim();profileData.profiles[copy.name]=copy;const option=document.createElement('option');option.value=copy.name;option.textContent=copy.name;$('profile').append(option);$('profile').value=copy.name;editingOriginal=null;renderProfile()};
$('saveprofile').onclick=async()=>{try{const profile=currentProfile();await api('/api/profiles/save',{profile,previous_name:editingOriginal});await loadProfiles(profile.name);localMessage='';$('status').textContent=`Profil ${profile.name} gespeichert`;requestPreview()}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('defaultprofile').onclick=async()=>{try{await api('/api/profiles/default',{name:$('profile').value});await loadProfiles($('profile').value);$('status').textContent='Standardprofil geändert'}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('deleteprofile').onclick=async()=>{const name=$('profile').value;if(!confirm(`Profil ${name} wirklich löschen?`))return;try{await api('/api/profiles/delete',{name});await loadProfiles();$('status').textContent=`Profil ${name} gelöscht`}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('plot').onclick=async()=>{try{if(['sending','waiting_xon'].includes(plotStatus)){await api('/api/plot/control',{action:'pause'});plotStatus='paused'}else if(plotStatus==='paused'){await api('/api/plot/control',{action:'resume'});plotStatus='sending'}else{if(!confirm('Der Plotter beginnt sich zu bewegen. Ist das Blatt eingelegt und der Stift frei?'))return;await api('/api/plot',{token});plotStarted=true;plotStatus='sending'}renderPlotControls();await status()}catch(e){$('status').textContent=e.message}}
$('abort').onclick=async()=>{if(!confirm('Plot wirklich abbrechen? Bereits empfangene Daten müssen am Plotter mit LOCAL und RESET gelöscht werden.'))return;try{await api('/api/plot/control',{action:'cancel'});plotStatus='cancelling';renderPlotControls();await status()}catch(e){$('status').textContent=e.message}}
loadProfiles().catch(e=>{localMessage=e.message;$('status').textContent=e.message});loadCalibrationProfiles().catch(e=>{$('calresult').textContent=e.message});status();loadHardware().catch(e=>{$('hwstatus').textContent=e.message});loadQueue();loadJobs();setInterval(status,1000);setInterval(()=>{loadQueue();loadJobs()},3000);
</script></body></html>"""


def render_page(page: str) -> str:
    if page not in WEB_PAGES:
        raise ValueError(f"Unbekannte Webseite: {page}")
    return PAGE.replace("__ACTIVE_PAGE__", page)
