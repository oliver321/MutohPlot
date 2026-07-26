from .tokens import Command


NUMERIC_COMMANDS = {
    "AA",
    "AR",
    "CI",
    "CP",
    "DF",
    "DI",
    "DR",
    "IN",
    "PA",
    "PD",
    "PR",
    "PU",
    "SI",
    "SL",
    "SP",
}


class HPGLTokenizer:
    def tokenize(self, text: str) -> list[Command]:
        cleaned = text.replace("\r", "").replace("\n", "")
        commands = []
        index = 0
        while index < len(cleaned):
            while index < len(cleaned) and (cleaned[index].isspace() or cleaned[index] == ";"):
                index += 1
            if index >= len(cleaned):
                break
            if len(cleaned) - index < 2:
                raise ValueError(f"Invalid HPGL command: {cleaned[index:]!r}")

            name = cleaned[index:index + 2].upper()
            index += 2
            if name == "LB":
                payload_start = index
                etx = cleaned.find("\x03", index)
                semicolon = cleaned.find(";", index)
                if etx >= 0:
                    end = etx
                    index = etx + 1
                elif semicolon >= 0:
                    # Compatibility with files that incorrectly terminate LB
                    # with a semicolon instead of the HP-GL default ETX byte.
                    end = semicolon
                    index = semicolon + 1
                else:
                    end = len(cleaned)
                    index = end
                commands.append(Command(name, cleaned[payload_start:end]))
                continue

            end = self._command_end(cleaned, index, name)
            raw = (name + cleaned[index:end]).strip()
            index = end + 1 if end < len(cleaned) and cleaned[end] == ";" else end
            raw = raw.strip()
            if not raw:
                continue
            if len(raw) < 2:
                raise ValueError(f"Invalid HPGL command: {raw!r}")
            commands.append(Command(raw[:2].upper(), raw[2:].strip()))
        return commands

    @staticmethod
    def _command_end(text: str, start: int, name: str) -> int:
        """Find a command boundary, including omitted semicolons.

        Numeric HP-GL commands may be followed immediately by the next
        two-letter mnemonic. Text-bearing commands keep their historical
        semicolon-delimited behaviour; LB is handled separately above.
        """
        semicolon = text.find(";", start)
        if name not in NUMERIC_COMMANDS:
            return len(text) if semicolon < 0 else semicolon

        limit = len(text) if semicolon < 0 else semicolon
        index = start
        while index + 1 < limit:
            if text[index].isalpha() and text[index + 1].isalpha():
                return index
            index += 1
        return limit
