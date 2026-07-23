from dataclasses import dataclass

@dataclass(slots=True)
class Command:
    name: str
    args: list[str]

class Tokenizer:
    def tokenize(self, text:str)->list[Command]:
        out=[]
        for part in text.replace("\n","").replace("\r","").split(";"):
            part=part.strip()
            if not part:
                continue
            out.append(Command(part[:2].upper(),
                               [a.strip() for a in part[2:].split(",")] if part[2:].strip() else []))
        return out
