from dataclasses import dataclass
from pathlib import Path
from time import sleep


@dataclass(frozen=True, slots=True)
class BufferProfile:
    name: str
    chunk_size: int
    inter_chunk_delay_s: float
    hpgl_command_chars: int


BUFFER_PROFILES = {
    "large": BufferProfile("large", 16384, 0.0, 16384),
    "small": BufferProfile("small", 512, 0.02, 800),
}


@dataclass(frozen=True, slots=True)
class SerialSettings:
    port: str
    baudrate: int = 19200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    xonxoff: bool = True
    rtscts: bool = False
    dsrdtr: bool = False
    timeout_s: float = 30.0
    write_timeout_s: float = 30.0


class SerialTransmissionError(RuntimeError):
    """A serial transmission failed after the port was opened."""


def require_pyserial():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise RuntimeError("Serial support requires pyserial: pip install pyserial") from error
    return serial, list_ports


def list_serial_ports():
    _, list_ports = require_pyserial()
    return [
        {"device": port.device, "description": port.description or "", "hwid": port.hwid or ""}
        for port in list_ports.comports()
    ]


def open_serial(settings):
    serial, _ = require_pyserial()
    parity = {
        "N": serial.PARITY_NONE,
        "E": serial.PARITY_EVEN,
        "O": serial.PARITY_ODD,
    }[settings.parity.upper()]
    return serial.Serial(
        port=settings.port,
        baudrate=settings.baudrate,
        bytesize=settings.bytesize,
        parity=parity,
        stopbits=settings.stopbits,
        timeout=settings.timeout_s,
        write_timeout=settings.write_timeout_s,
        xonxoff=settings.xonxoff,
        rtscts=settings.rtscts,
        dsrdtr=settings.dsrdtr,
    )


def serial_status(settings):
    connection = open_serial(settings)
    try:
        return {
            "port": connection.port,
            "baudrate": connection.baudrate,
            "xonxoff": connection.xonxoff,
            "rtscts": connection.rtscts,
            "dsrdtr": connection.dsrdtr,
            "cts": bool(connection.cts),
            "dsr": bool(connection.dsr),
            "cd": bool(connection.cd),
            "ri": bool(connection.ri),
        }
    finally:
        connection.close()


def send_bytes(data, settings, profile, progress=None, connection_factory=None, sleeper=sleep):
    connection = (connection_factory or open_serial)(settings)
    sent = 0
    try:
        while sent < len(data):
            block = data[sent : sent + profile.chunk_size]
            try:
                written = connection.write(block)
            except (OSError, TimeoutError) as error:
                raise SerialTransmissionError(
                    f"Serial transmission to {settings.port} failed after "
                    f"{sent}/{len(data)} bytes: {error}"
                ) from error
            if written is None:
                written = len(block)
            if written <= 0:
                raise SerialTransmissionError(
                    f"Serial transmission to {settings.port} made no progress "
                    f"after {sent}/{len(data)} bytes"
                )
            sent += written
            if progress:
                progress(sent, len(data))
            if profile.inter_chunk_delay_s:
                sleeper(profile.inter_chunk_delay_s)
        try:
            connection.flush()
        except (OSError, TimeoutError) as error:
            raise SerialTransmissionError(
                f"Serial flush on {settings.port} failed after {sent}/{len(data)} bytes: {error}"
            ) from error
        return sent
    finally:
        connection.close()


def send_file(path, settings, profile_name="large", progress=None, connection_factory=None):
    return send_bytes(
        Path(path).read_bytes(),
        settings,
        BUFFER_PROFILES[profile_name],
        progress,
        connection_factory,
    )
