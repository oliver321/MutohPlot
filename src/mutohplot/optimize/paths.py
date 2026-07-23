from math import hypot
from ..document import PlotDocument

def dist(a,b): return hypot(b.x-a.x,b.y-a.y)

def optimize_nearest(document: PlotDocument, allow_reverse: bool=True) -> PlotDocument:
    groups={}
    for p in document.polylines: groups.setdefault(p.pen,[]).append(p)
    out=[]
    for pen in sorted(groups):
        rem=groups[pen][:]; cur=None
        while rem:
            best=(float('inf'),0,False)
            for i,p in enumerate(rem):
                ds=0 if cur is None else dist(cur,p.points[0])
                de=0 if cur is None else dist(cur,p.points[-1])
                if ds<best[0]: best=(ds,i,False)
                if allow_reverse and de<best[0]: best=(de,i,True)
            _,i,rev=best; p=rem.pop(i)
            if rev: p=p.reversed_copy()
            out.append(p); cur=p.points[-1]
    return PlotDocument(out,dict(document.metadata))
