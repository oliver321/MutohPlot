from .tokens import Command

class HPGLTokenizer:
    def tokenize(self, text: str) -> list[Command]:
        cleaned = text.replace("\r", "").replace("\n", "")
        commands: list[Command] = []
        for raw in cleaned.split(";"):
            raw = raw.strip()
            if not raw:
                continue
            if len(raw) < 2:
                raise ValueError(f"Invalid HPGL command: {raw!r}")
            commands.append(Command(raw[:2].upper(), raw[2:].strip()))
        return commands
