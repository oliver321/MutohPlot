def write_preview(document, path):
    width = float(document.metadata.get("page_width_mm", 100))
    height = float(document.metadata.get("page_height_mm", 100))
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for polyline in document.polylines:
        points = " ".join(f"{point.x:.4f},{point.y:.4f}" for point in polyline.points)
        color = polyline.source_color or "black"
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="0.3"/>'
        )
    lines.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
