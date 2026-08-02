import pytest

from mutohplot.serial_io import (
    BUFFER_PROFILES,
    SerialSettings,
    SerialTransmissionError,
    send_bytes,
    wait_until_resumed,
)


class Fake:
    def __init__(self, write_sizes=None, incoming=b""):
        self.data = bytearray()
        self.incoming = bytearray(incoming)
        self.input_buffer_reset = False
        self.flushed = False
        self.closed = False
        self.write_sizes = iter(write_sizes or [])

    def reset_input_buffer(self):
        self.input_buffer_reset = True

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, size):
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result

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


def test_disabled_xonxoff_still_starts_with_clean_input():
    fake = Fake()

    send_bytes(
        b"123",
        SerialSettings("/dev/fake", xonxoff=False),
        BUFFER_PROFILES["small"],
        connection_factory=lambda _: fake,
        sleeper=lambda _: None,
    )

    assert fake.input_buffer_reset
    assert fake.closed


def test_xonxoff_reset_failure_closes_port_with_context():
    class BrokenReset(Fake):
        def reset_input_buffer(self):
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


def test_userspace_xoff_pauses_until_xon():
    fake = Fake(incoming=b"\x13")
    sleeps = []

    def resume_after_first_poll(delay):
        sleeps.append(delay)
        fake.incoming.append(0x11)

    sent = send_bytes(
        b"123",
        SerialSettings("/dev/fake"),
        BUFFER_PROFILES["large"],
        connection_factory=lambda _: fake,
        sleeper=resume_after_first_poll,
    )

    assert sent == 3
    assert sleeps == [0.05]
    assert bytes(fake.data) == b"123"


def test_latest_flow_control_character_wins():
    fake = Fake(incoming=b"\x13\x11")

    sent = send_bytes(
        b"123",
        SerialSettings("/dev/fake"),
        BUFFER_PROFILES["large"],
        connection_factory=lambda _: fake,
        sleeper=lambda _: pytest.fail("XON should have resumed transmission"),
    )

    assert sent == 3


def test_userspace_xoff_honors_configured_timeout():
    fake = Fake(incoming=b"\x13")
    times = iter((0.0, 0.0, 1.0))

    with pytest.raises(
        SerialTransmissionError,
        match=r"XOFF pause on /dev/fake exceeded write timeout of 1 seconds",
    ):
        wait_until_resumed(
            fake,
            False,
            timeout_s=1.0,
            port="/dev/fake",
            sleeper=lambda _: None,
            clock=lambda: next(times),
        )
