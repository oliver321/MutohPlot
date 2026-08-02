import pytest

from mutohplot.serial_io import (
    BUFFER_PROFILES,
    SerialSettings,
    SerialTransmissionError,
    send_bytes,
)


class Fake:
    def __init__(self, write_sizes=None):
        self.data = bytearray()
        self.input_buffer_reset = False
        self.output_flow_control = []
        self.flushed = False
        self.closed = False
        self.write_sizes = iter(write_sizes or [])

    def reset_input_buffer(self):
        self.input_buffer_reset = True

    def set_output_flow_control(self, enable=True):
        self.output_flow_control.append(enable)

    def write(self, block):
        try:
            size = next(self.write_sizes)
        except StopIteration:
            size = len(block)
        if size > 0:
            self.data.extend(block[:size])
        return size

    def flush(self):
        self.flushed = True

    def close(self):
        self.closed = True


def test_profiles_match_xp500_buffers():
    assert BUFFER_PROFILES["large"].chunk_size > BUFFER_PROFILES["small"].chunk_size
    assert BUFFER_PROFILES["small"].chunk_size < 1000
    assert BUFFER_PROFILES["small"].hpgl_command_chars <= 1000


def test_send_and_progress():
    fake = Fake()
    progress = []
    sent = send_bytes(
        b"1234567890",
        SerialSettings("/dev/fake"),
        BUFFER_PROFILES["small"],
        progress=lambda current, total: progress.append((current, total)),
        connection_factory=lambda _: fake,
        sleeper=lambda _: None,
    )
    assert sent == 10
    assert bytes(fake.data) == b"1234567890"
    assert progress == [(10, 10)]
    assert fake.input_buffer_reset
    assert fake.output_flow_control == [True]
    assert fake.flushed and fake.closed


def test_partial_writes_continue_without_losing_data():
    fake = Fake([3, 2])
    sent = send_bytes(
        b"1234567890",
        SerialSettings("/dev/fake"),
        BUFFER_PROFILES["small"],
        connection_factory=lambda _: fake,
        sleeper=lambda _: None,
    )
    assert sent == 10
    assert bytes(fake.data) == b"1234567890"
    assert fake.closed


def test_no_progress_has_context_and_closes_port():
    fake = Fake([0])
    with pytest.raises(SerialTransmissionError, match=r"/dev/fake.*0/3 bytes"):
        send_bytes(
            b"123",
            SerialSettings("/dev/fake"),
            BUFFER_PROFILES["small"],
            connection_factory=lambda _: fake,
            sleeper=lambda _: None,
        )
    assert fake.closed
    assert not fake.flushed


def test_write_failure_has_context_and_closes_port():
    class Broken(Fake):
        def write(self, block):
            raise OSError("adapter disconnected")

    fake = Broken()
    with pytest.raises(SerialTransmissionError, match=r"0/3 bytes.*adapter disconnected"):
        send_bytes(
            b"123",
            SerialSettings("/dev/fake"),
            BUFFER_PROFILES["small"],
            connection_factory=lambda _: fake,
            sleeper=lambda _: None,
        )
    assert fake.closed


def test_keyboard_interrupt_closes_port():
    class Interrupted(Fake):
        def write(self, block):
            raise KeyboardInterrupt

    fake = Interrupted()
    with pytest.raises(KeyboardInterrupt):
        send_bytes(
            b"123",
            SerialSettings("/dev/fake"),
            BUFFER_PROFILES["small"],
            connection_factory=lambda _: fake,
            sleeper=lambda _: None,
        )
    assert fake.closed


def test_default_write_timeout_allows_indefinite_xoff_pause():
    assert SerialSettings("/dev/fake").write_timeout_s is None


def test_disabled_xonxoff_does_not_touch_software_flow_control():
    fake = Fake()

    send_bytes(
        b"123",
        SerialSettings("/dev/fake", xonxoff=False),
        BUFFER_PROFILES["small"],
        connection_factory=lambda _: fake,
        sleeper=lambda _: None,
    )

    assert not fake.input_buffer_reset
    assert fake.output_flow_control == []


def test_xonxoff_reset_failure_closes_port_with_context():
    class BrokenReset(Fake):
        def set_output_flow_control(self, enable=True):
            raise OSError("flow-control reset failed")

    fake = BrokenReset()

    with pytest.raises(
        SerialTransmissionError,
        match=r"reset XON/XOFF state on /dev/fake.*flow-control reset failed",
    ):
        send_bytes(
            b"123",
            SerialSettings("/dev/fake"),
            BUFFER_PROFILES["small"],
            connection_factory=lambda _: fake,
            sleeper=lambda _: None,
        )

    assert fake.closed
    assert not fake.data
