from dataclasses import dataclass

@dataclass(frozen=True)
class MutohXP500:
    name:str="Mutoh XP-500"
    unit_mm:float=0.01
    origin:str="center"
    x_positive:str="down"
    y_positive:str="right"
    pens:int=8
