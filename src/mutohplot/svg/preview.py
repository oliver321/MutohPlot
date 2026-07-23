from xml.sax.saxutils import escape


def write_preview(document, path, paper=None, hard_clip=None, safe_area=None):
    width = float(document.metadata.get("page_width_mm", paper.width_mm if paper else 100))
    height = float(document.metadata.get("page_height_mm", paper.height_mm if paper else 100))
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="white"/>',
    ]
    if paper is not None:
        lines.append(
            f'<rect x="0" y="0" width="{paper.width_mm}" height="{paper.height_mm}" '
            'fill="none" stroke="#777" stroke-width="0.5"/>'
        )
    if hard_clip is not None:
        lines.append(
            f'<rect x="{hard_clip.x_min_mm}" y="{hard_clip.y_min_mm}" '
            f'width="{hard_clip.width_mm}" height="{hard_clip.height_mm}" '
            'fill="none" stroke="#d22" stroke-width="0.6" stroke-dasharray="4 2"/>'
        )
    if safe_area is not None:
        lines.append(
            f'<rect x="{safe_area.x_min_mm}" y="{safe_area.y_min_mm}" '
            f'width="{safe_area.width_mm}" height="{safe_area.height_mm}" '
            'fill="none" stroke="#268" stroke-width="0.5" stroke-dasharray="2 2"/>'
        )
    palette = ["#000000", "#d22", "#268", "#282", "#a2a", "#d80", "#088", "#555"]
    for poly in document.polylines:
        points = " ".join(f"{p.x:.4f},{p.y:.4f}" for p in poly.points)
        color = escape(poly.source_color or palette[(poly.pen - 1) % len(palette)])
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="0.3"/>'
        )
    lines.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
