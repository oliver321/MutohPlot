from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Paper:
    name: str
    width_mm: float
    height_mm: float


PAPERS = {
    "a3": Paper("A3", 297.0, 420.0),
    "a2": Paper("A2", 420.0, 594.0),
    "a1": Paper("A1", 594.0, 841.0),
    "a0": Paper("A0", 841.0, 1189.0),
}


def get_paper(name: str, landscape: bool = False) -> Paper:
    try:
        paper = PAPERS[name.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown paper size: {name}") from exc
    if landscape:
        return Paper(paper.name + " landscape", paper.height_mm, paper.width_mm)
    return paper
