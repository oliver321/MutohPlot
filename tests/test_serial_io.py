from mutohplot.serial_io import BUFFER_PROFILES,SerialSettings,send_bytes
class Fake:
    def __init__(self): self.data=bytearray(); self.flushed=False; self.closed=False
    def write(self,b): self.data.extend(b); return len(b)
    def flush(self): self.flushed=True
    def close(self): self.closed=True

def test_profiles(): assert BUFFER_PROFILES['large'].chunk_size>BUFFER_PROFILES['small'].chunk_size and BUFFER_PROFILES['small'].hpgl_command_chars<=1000
def test_send():
    f=Fake(); n=send_bytes(b'1234567890',SerialSettings('/dev/fake'),BUFFER_PROFILES['small'],connection_factory=lambda _:f)
    assert n==10 and bytes(f.data)==b'1234567890' and f.flushed and f.closed
