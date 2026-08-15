from dataclasses import dataclass
from pathlib import Path
from time import sleep

@dataclass(frozen=True, slots=True)
class BufferProfile:
    name:str; chunk_size:int; inter_chunk_delay_s:float; hpgl_command_chars:int
BUFFER_PROFILES={
    "large":BufferProfile("large",16384,0.0,16384),
    "small":BufferProfile("small",512,0.02,800),
}
@dataclass(frozen=True, slots=True)
class SerialSettings:
    port:str; baudrate:int=19200; bytesize:int=8; parity:str="N"; stopbits:float=1; xonxoff:bool=True; rtscts:bool=False; dsrdtr:bool=False; timeout_s:float=30.0; write_timeout_s:float=30.0

def require_pyserial():
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as e:
        raise RuntimeError("Serial support requires pyserial: pip install pyserial") from e
    return serial,list_ports

def list_serial_ports():
    _,lp=require_pyserial(); return [{"device":p.device,"description":p.description or "","hwid":p.hwid or ""} for p in lp.comports()]

def open_serial(s):
    serial,_=require_pyserial(); parity={"N":serial.PARITY_NONE,"E":serial.PARITY_EVEN,"O":serial.PARITY_ODD}[s.parity.upper()]
    return serial.Serial(port=s.port,baudrate=s.baudrate,bytesize=s.bytesize,parity=parity,stopbits=s.stopbits,timeout=s.timeout_s,write_timeout=s.write_timeout_s,xonxoff=s.xonxoff,rtscts=s.rtscts,dsrdtr=s.dsrdtr)

def serial_status(s):
    c=open_serial(s)
    try: return {"port":c.port,"baudrate":c.baudrate,"xonxoff":c.xonxoff,"rtscts":c.rtscts,"dsrdtr":c.dsrdtr,"cts":bool(c.cts),"dsr":bool(c.dsr),"cd":bool(c.cd),"ri":bool(c.ri)}
    finally: c.close()

def send_bytes(data,s,profile,progress=None,connection_factory=None):
    c=(connection_factory or open_serial)(s); sent=0
    try:
        while sent<len(data):
            block=data[sent:sent+profile.chunk_size]; n=c.write(block)
            if n is None: n=len(block)
            if n<=0: raise TimeoutError("Serial transmission made no progress")
            sent+=n
            if progress: progress(sent,len(data))
            if profile.inter_chunk_delay_s: sleep(profile.inter_chunk_delay_s)
        c.flush(); return sent
    finally: c.close()

def send_file(path,s,profile_name='large',progress=None,connection_factory=None):
    return send_bytes(Path(path).read_bytes(),s,BUFFER_PROFILES[profile_name],progress,connection_factory)
