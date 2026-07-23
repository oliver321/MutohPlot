import argparse
from pathlib import Path
from .devices.mutoh_xp500 import MutohXP500
from .hpgl.parser import HPGLParser
from .hpgl.writer import HPGLWriter
from .svg.reader import SVGReader
from .svg.preview import write_preview
from .transform.coordinate import CoordinateTransform
from .optimize.paths import optimize_nearest

def parser():
 p=argparse.ArgumentParser(prog='mutohplot');s=p.add_subparsers(dest='command',required=True)
 h=s.add_parser('hpgl'); h.add_argument('input');h.add_argument('output');h.add_argument('--source-unit',type=float,default=.025);h.add_argument('--device-unit',type=float,default=.01);h.add_argument('--swap-axes',action='store_true');h.add_argument('--flip-first',action='store_true');h.add_argument('--flip-second',action='store_true');h.add_argument('--offset-first',type=float,default=0);h.add_argument('--offset-second',type=float,default=0);h.add_argument('--optimize',action='store_true');h.add_argument('--no-reverse',action='store_true');h.add_argument('--stats',action='store_true')
 v=s.add_parser('svg');v.add_argument('input');v.add_argument('output');v.add_argument('--device-unit',type=float,default=.01);v.add_argument('--page-width',type=float);v.add_argument('--page-height',type=float);v.add_argument('--curve-steps',type=int,default=24);v.add_argument('--offset-first',type=float,default=0);v.add_argument('--offset-second',type=float,default=0);v.add_argument('--optimize',action='store_true');v.add_argument('--no-reverse',action='store_true');v.add_argument('--stats',action='store_true');v.add_argument('--preview')
 return p

def stats(d):
 print(f'Polylines: {len(d.polylines)}');print(f'Drawing distance: {d.drawing_distance_mm():.1f} mm');print(f'Pen-up distance: {d.pen_up_distance_mm():.1f} mm')
 if d.bounds():
  a,b,c,e=d.bounds();print(f'Bounds: x={a:.2f}..{c:.2f} mm, y={b:.2f}..{e:.2f} mm')
 for color,pen in d.metadata.get('color_to_pen',{}).items():print(f'{color} -> pen {pen}')

def main():
 a=parser().parse_args()
 if a.command=='hpgl':
  d=HPGLParser(a.source_unit).parse_text(Path(a.input).read_text(errors='replace')); x=(0,1,1,0) if a.swap_axes else (1,0,0,1);aa,bb,cc,dd=x
  if a.flip_first:aa,bb=-aa,-bb
  if a.flip_second:cc,dd=-cc,-dd
  t=CoordinateTransform(aa,bb,cc,dd,a.offset_first,a.offset_second)
 else:
  d=SVGReader(a.curve_steps).read(a.input);w=a.page_width or d.metadata['page_width_mm'];h=a.page_height or d.metadata['page_height_mm'];t=CoordinateTransform.svg_to_mutoh(w,h);t=CoordinateTransform(t.a,t.b,t.c,t.d,t.tx+a.offset_first,t.ty+a.offset_second)
  if a.preview:write_preview(d,a.preview)
 if a.optimize:
  before=d.pen_up_distance_mm();d=optimize_nearest(d,not a.no_reverse);print(f'Pen-up optimization: {before:.1f} mm -> {d.pen_up_distance_mm():.1f} mm')
 Path(a.output).write_text(HPGLWriter(MutohXP500(unit_mm=a.device_unit),t).write(d),encoding='ascii');print(f'Wrote {a.output}')
 if a.stats:stats(d)
