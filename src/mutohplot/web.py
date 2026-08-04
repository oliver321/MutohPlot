"""Small local web interface for previewing and sending HP-GL plots."""

from __future__ import annotations

import argparse
import json
import signal
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .cli import convert_hpgl, ra_fill_spacings
from .devices.mutoh_xp500 import MutohXP500
from .hard_clip import drawable_area, get_hard_clip
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .optimize.geometry import optimize_geometry
from .optimize.paths import optimize_nearest
from .paper import get_paper
from .report import check_bounds
from .serial_io import BUFFER_PROFILES, SerialSettings, list_serial_ports, send_bytes
from .svg.preview import write_preview
from .svg.reader import SVGReader
from .transform.coordinate import CoordinateTransform
from .transform.fit import apply_fit, fit_document_to_area, rotate_document
from .transform.hard_clip import hard_clip_center_correction
from .web_profiles import TYPE_LABELS, PenProfileStore

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# JSON escaping adds overhead. The actual file-size limit is checked separately.
MAX_REQUEST_BYTES = 40 * 1024 * 1024


@dataclass(slots=True)
class PreparedPlot:
    token: str
    name: str
    data: bytes
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


class PlotState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.prepared: dict[str, PreparedPlot] = {}
        self.status = "idle"
        self.sent = 0
        self.total = 0
        self.message = "Bereit"
        self.transmission_done = threading.Event()
        self.transmission_done.set()
        self.shutdown_requested = False

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "sent": self.sent,
                "total": self.total,
                "message": self.message,
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
    def __init__(self, sender: Callable = send_bytes, profile_store=None) -> None:
        self.state = PlotState()
        self.sender = sender
        self.profiles = profile_store or PenProfileStore()

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
        paper = get_paper(args.paper, args.landscape)
        profile = get_hard_clip("norm")
        hard = drawable_area(paper, profile, 0)
        safe = drawable_area(paper, profile, args.margin)
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
        correction = hard_clip_center_correction(profile)
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
        if not source.strip():
            raise ValueError("Die Plotdatei ist leer")
        if len(source.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise ValueError("Die Plotdatei ist größer als 20 MB")
        args = _conversion_args(options)
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
        with self.state.lock:
            self.state.prepared = {token: prepared}
            self.state.message = f"{prepared.name} geprüft und bereit"
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
            "source_type": prepared.source_type,
            "pens": prepared.pens,
            "warnings": prepared.warnings,
            "profile_name": prepared.profile_name,
            "mapping_type": prepared.mapping_type,
            "profile_pens": prepared.profile_pens,
        }

    def start(self, token: str, port: str, buffer_profile: str) -> None:
        if buffer_profile not in BUFFER_PROFILES:
            raise ValueError("Unbekanntes Pufferprofil")
        if not port:
            raise ValueError("Bitte eine serielle Schnittstelle auswählen")
        with self.state.lock:
            if self.state.shutdown_requested:
                raise RuntimeError("Der Webdienst wartet auf einen sicheren Neustart")
            if self.state.status in {"sending", "paused"}:
                raise RuntimeError("Es läuft bereits ein Plotauftrag")
            prepared = self.state.prepared.get(token)
            if prepared is None:
                raise ValueError("Die Vorschau ist nicht mehr aktuell; bitte erneut prüfen")
            self.state.status = "sending"
            self.state.sent = 0
            self.state.total = len(prepared.data)
            self.state.message = f"Sende {prepared.name}"
            self.state.transmission_done.clear()

        settings = SerialSettings(port=port, baudrate=19200, xonxoff=True)

        def progress(sent: int, total: int) -> None:
            with self.state.lock:
                self.state.sent = sent
                self.state.total = total

        def transmit() -> None:
            try:
                self.sender(
                    prepared.data,
                    settings,
                    BUFFER_PROFILES[buffer_profile],
                    progress,
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
                self.state.transmission_done.set()

        threading.Thread(target=transmit, name="mutohplot-send", daemon=False).start()

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
        if path == "/":
            body = PAGE.encode("utf-8")
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
            self._json(result)
        elif path == "/api/profiles":
            result = self.app.profiles.snapshot()
            result["pen_types"] = TYPE_LABELS
            result["pen_widths"] = [0.3, 0.5, 0.7, 1.0, 1.5]
            self._json(result)
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
            elif path == "/api/plot":
                self.app.start(
                    str(payload.get("token", "")),
                    str(payload.get("port", "")),
                    str(payload.get("buffer_profile", "small")),
                )
                self._json({"status": "sending"}, HTTPStatus.ACCEPTED)
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
body{margin:0}header{background:#183e31;color:white;padding:1.2rem 5vw}header h1{margin:0;font-size:1.4rem}
main{max-width:1100px;margin:2rem auto;padding:0 1rem;display:grid;grid-template-columns:320px 1fr;gap:1rem}
.card{background:white;border-radius:12px;padding:1rem;box-shadow:0 2px 10px #0001}label{display:block;margin:.8rem 0 .3rem}
input,select,button{width:100%;padding:.7rem;border:1px solid #aab6af;border-radius:7px;background:white}
button{margin-top:1rem;background:#176b4c;color:white;border:0;font-weight:650;cursor:pointer}button:disabled{opacity:.45}
.preview{min-height:480px;display:grid;place-items:center;overflow:auto}.preview img{display:block;max-width:100%;max-height:70vh}
.checks{display:flex;gap:.5rem;align-items:center}.checks input{width:auto}.status{padding:.7rem;border-radius:7px;background:#e7eee9;margin-top:1rem}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:.4rem;font-size:.9rem;margin-top:1rem}.facts span:nth-child(odd){color:#64736b}
.profile-actions{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}.profile-actions button{margin-top:.4rem}.pen-row{border-top:1px solid #dde3df;padding:.5rem 0}.pen-row strong{display:block}.pen-row .checks{margin:.3rem 0}.pen-row input,.pen-row select{padding:.4rem}
@media(max-width:760px){main{grid-template-columns:1fr}.preview{min-height:300px}}
</style></head><body><header><h1>MutohPlot · XP-500 <small>Web 0.6</small></h1></header><main>
<section class="card"><h2>Plot vorbereiten</h2><label>HP-GL- oder SVG-Datei</label><input id="file" type="file" accept=".hpgl,.plt,.svg,image/svg+xml"><small>Die Vorschau wird direkt nach der Auswahl erzeugt. Maximal 20 MB.</small><div id="selection" class="status">Noch keine Datei ausgewählt</div>
<label>Stiftprofil</label><select id="profile"></select>
<details><summary>Stifte konfigurieren</summary><div class="profile-actions"><button id="newprofile">Neues Profil</button><button id="saveprofile">Speichern</button><button id="defaultprofile">Als Standard</button><button id="deleteprofile">Löschen</button></div><div id="peneditor"></div></details>
<label>Papierformat</label><select id="paper"><option value="a3">A3 · Standard</option><option value="a2">A2</option><option value="a1">A1</option><option value="a0">A0</option></select>
<label class="checks"><input id="landscape" type="checkbox"> Querformat</label>
<label>Sicherheitsrand</label><select id="margin"><option value="5">5 mm</option><option value="10">10 mm</option><option value="0">Kein zusätzlicher Rand</option></select>
<label class="checks"><input id="fit" type="checkbox" checked> Auf sicheren Bereich einpassen</label>
<label>Drehung</label><select id="rotation"><option value="auto">Automatisch · beste Ausnutzung</option><option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option></select>
<label class="checks"><input id="optimize" type="checkbox" checked> Leerwege optimieren</label>
<button id="check">Datei prüfen und anzeigen</button><hr><label>Serielle Schnittstelle</label><select id="port"><option value="">Keine gefunden</option></select>
<label>Empfangspuffer des Plotters</label><select id="buffer"><option value="small">1000 Zeichen · sicher</option><option value="large">1 MB · schnell</option></select>
<div id="penmap"></div>
<button id="plot" disabled>Geprüften Plot starten</button><div id="status" class="status">Bereit</div><div id="facts" class="facts"></div></section>
<section class="card preview" id="preview"><p>Hier erscheint die A3-Vorschau.</p></section></main><script>
let token=null,localMessage='',penMap={},mappingType='',mappingProfilePens={},profileData=null,editingOriginal=null; const $=id=>document.getElementById(id);
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):null});const j=await r.json();if(!r.ok)throw Error(j.error||'Fehler');return j}
function currentProfile(){return profileData?.profiles[$('profile').value]}
function renderProfile(){const profile=currentProfile(),box=$('peneditor');box.replaceChildren();if(!profile)return;for(let n=1;n<=8;n++){const pen=profile.pens[n],row=document.createElement('div');row.className='pen-row';const title=document.createElement('strong');title.textContent=`Stift ${n}`;const label=document.createElement('input');label.value=pen.label;label.onchange=()=>pen.label=label.value;const line=document.createElement('div');line.className='checks';const type=document.createElement('select');for(const [value,text] of Object.entries(profileData.pen_types)){const option=document.createElement('option');option.value=value;option.textContent=text;option.selected=value===pen.type;type.append(option)}type.onchange=()=>pen.type=type.value;const width=document.createElement('select');for(const value of profileData.pen_widths){const option=document.createElement('option');option.value=value;option.textContent=`${String(value).replace('.',',')} mm`;option.selected=value===pen.width_mm;width.append(option)}width.onchange=()=>pen.width_mm=+width.value;const color=document.createElement('input');color.type='color';color.value=/^#[0-9a-f]{6}$/i.test(pen.color)?pen.color:'#000000';color.onchange=()=>pen.color=color.value;line.append(type,width,color);row.append(title,label,line);box.append(row)}}
async function loadProfiles(selected){profileData=await api('/api/profiles');const select=$('profile');select.replaceChildren();for(const name of Object.keys(profileData.profiles)){const option=document.createElement('option');option.value=name;option.textContent=name+(name===profileData.default?' · Standard':'');select.append(option)}select.value=selected&&profileData.profiles[selected]?selected:profileData.default;editingOriginal=select.value;renderProfile()}
function renderPenMap(){const box=$('penmap');box.replaceChildren();const entries=Object.entries(penMap);if(!entries.length)return;const title=document.createElement('label');title.textContent='Quelldarstellung → tatsächlicher Stift';box.append(title);for(const [source,pen] of entries){const actual=mappingProfilePens[pen]||{},row=document.createElement('label');row.className='checks';const swatch=document.createElement('span');swatch.style.cssText='width:1.2rem;height:1.2rem;border:1px solid #777;border-radius:50%;flex:none';swatch.style.backgroundColor=actual.color||'#000000';const text=document.createElement('span');text.textContent=mappingType==='hpgl-pen'?`HP-GL Stift ${source} →`:`SVG ${source} →`;const select=document.createElement('select');select.style.width='auto';for(let n=1;n<=8;n++){const configured=mappingProfilePens[n]||{};const option=document.createElement('option');option.value=n;option.textContent=`Stift ${n} · ${configured.label||''} · ${configured.color||''}`;option.selected=n===pen;select.append(option)}select.onchange=()=>{penMap[source]=+select.value;$('check').click()};row.append(swatch,text,select);box.append(row)}}
async function status(){try{const s=await api('/api/status');if(!localMessage)$('status').textContent=s.message+(s.total?` · ${Math.round(s.sent*100/s.total)} %`:'');const old=$('port').value;$('port').innerHTML=s.ports.length?s.ports.map(p=>`<option value="${p.device}">${p.device} · ${p.description}</option>`).join(''):'<option value="">Keine gefunden</option>';$('port').value=old||($('port').options[0]?.value||'');}catch(e){$('status').textContent=e.message}}
$('check').onclick=async()=>{const f=$('file').files[0];if(!f){localMessage='Bitte eine HP-GL- oder SVG-Datei auswählen';return $('status').textContent=localMessage}if(f.size>20*1024*1024){localMessage=`${f.name} ist ${(f.size/1024/1024).toFixed(1)} MB groß; erlaubt sind 20 MB`;$('status').textContent=localMessage;return}$('check').disabled=true;localMessage='Prüfe und konvertiere Datei …';$('status').textContent=localMessage;try{const isSvg=f.name.toLowerCase().endsWith('.svg');const j=await api('/api/preview',{name:f.name,source:await f.text(),options:{profile:$('profile').value,paper:$('paper').value,landscape:$('landscape').checked,margin:+$('margin').value,fit:$('fit').checked,rotation:$('rotation').value,optimize:$('optimize').checked,buffer_profile:$('buffer').value,pen_map:isSvg?penMap:{},hpgl_pen_map:isSvg?{}:penMap}});token=j.token;$('preview').innerHTML=`<img src="${j.preview_url}" alt="Plotvorschau">`;penMap=j.pens||{};mappingType=j.mapping_type;mappingProfilePens=j.profile_pens||{};renderPenMap();const pens=Object.keys(penMap).length?Object.entries(penMap).map(([c,p])=>`${c} → ${p}`).join(', '):'Keine Stiftwahl erkannt';const format=$('paper').value.toUpperCase()+($('landscape').checked?' quer':' hoch');const warnings=(j.warnings||[]).join(' · ')||'Keine';$('facts').innerHTML=`<span>Quelle</span><span>${j.source_type}</span><span>Profil</span><span>${j.profile_name}</span><span>Format</span><span>${format}</span><span>Einpassen</span><span>${$('fit').checked?'Ja':'Nein'}</span><span>Linienzüge</span><span>${j.polylines}</span><span>Zeichenweg</span><span>${j.drawing_mm} mm</span><span>Leerweg</span><span>${j.pen_up_mm} mm</span><span>Zuordnung</span><span>${pens}</span><span>Hinweise</span><span>${warnings}</span><span>Drehung</span><span>${j.rotation}°</span><span>Daten</span><span>${j.bytes} Bytes</span>`;$('plot').disabled=false;localMessage='';$('status').textContent=`${j.name} geprüft und bereit`;}catch(e){token=null;$('plot').disabled=true;localMessage=e.message;$('status').textContent=localMessage}finally{$('check').disabled=false}}
$('file').onchange=()=>{const f=$('file').files[0];if(!f)return;penMap={};renderPenMap();$('selection').textContent=`Ausgewählt: ${f.name} · ${(f.size/1024/1024).toFixed(2)} MB`;localMessage='';$('check').click()};
$('paper').onchange=()=>{if($('file').files[0])$('check').click()};
$('landscape').onchange=()=>{if($('file').files[0])$('check').click()};
$('fit').onchange=()=>{if(!$('fit').checked){$('rotation').value='0';$('rotation').disabled=true}else{$('rotation').disabled=false;$('rotation').value='auto'}if($('file').files[0])$('check').click()};
$('rotation').onchange=()=>{if($('file').files[0])$('check').click()};
$('profile').onchange=()=>{editingOriginal=$('profile').value;renderProfile();if($('file').files[0])$('check').click()};
$('newprofile').onclick=()=>{const name=prompt('Name des neuen Stiftprofils');if(!name)return;const copy=JSON.parse(JSON.stringify(currentProfile()));copy.name=name.trim();profileData.profiles[copy.name]=copy;const option=document.createElement('option');option.value=copy.name;option.textContent=copy.name;$('profile').append(option);$('profile').value=copy.name;editingOriginal=null;renderProfile()};
$('saveprofile').onclick=async()=>{try{const profile=currentProfile();await api('/api/profiles/save',{profile,previous_name:editingOriginal});await loadProfiles(profile.name);localMessage='';$('status').textContent=`Profil ${profile.name} gespeichert`;if($('file').files[0])$('check').click()}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('defaultprofile').onclick=async()=>{try{await api('/api/profiles/default',{name:$('profile').value});await loadProfiles($('profile').value);$('status').textContent='Standardprofil geändert'}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('deleteprofile').onclick=async()=>{const name=$('profile').value;if(!confirm(`Profil ${name} wirklich löschen?`))return;try{await api('/api/profiles/delete',{name});await loadProfiles();$('status').textContent=`Profil ${name} gelöscht`}catch(e){localMessage=e.message;$('status').textContent=e.message}};
$('plot').onclick=async()=>{if(!confirm('Der Plotter beginnt sich zu bewegen. Ist das Blatt eingelegt und der Stift frei?'))return;try{await api('/api/plot',{token,port:$('port').value,buffer_profile:$('buffer').value});$('plot').disabled=true;}catch(e){$('status').textContent=e.message}}
loadProfiles().catch(e=>{localMessage=e.message;$('status').textContent=e.message});status();setInterval(status,1000);
</script></body></html>"""
