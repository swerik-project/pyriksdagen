"""Render source-specific chair plans from the riksdagen-persons CSV model.

The drawings describe source evidence, not measured distances or occupancy.
Local grids are displayed as separate banks; their placement on the output
page never asserts a physical relationship between banks.
"""

import csv
import math
import re
import textwrap
from collections import Counter, defaultdict
from pathlib import Path


_GEOMETRY = ("x", "y", "orientation", "width", "height", "top_radius", "bottom_radius")
_STATES = ("numbered", "unnumbered", "hidden", "unknown")


def _read_rows(data_dir, name):
    with (data_dir / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _index(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if not value or value in result:
            raise ValueError("Missing or duplicate {}: {!r}".format(key, value))
        result[value] = row
    return result


def _natural_key(value):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", value)]


def _chair_patch(ax, seat, geometry, unknown=False):
    from matplotlib.path import Path as DrawingPath
    from matplotlib.patches import PathPatch
    from matplotlib.transforms import Affine2D

    x, y, angle, width, height, top, bottom = geometry
    left, right, upper, lower = -width / 2, width / 2, -height / 2, height / 2
    # Cubic quarter-circles retain the source's separate top/bottom radii.
    k = 0.5522847498307936
    vertices = [
        (left, upper + top),
        (left, upper + top * (1 - k)), (left + top * (1 - k), upper), (left + top, upper),
        (right - top, upper),
        (right - top * (1 - k), upper), (right, upper + top * (1 - k)), (right, upper + top),
        (right, lower - bottom),
        (right, lower - bottom * (1 - k)), (right - bottom * (1 - k), lower), (right - bottom, lower),
        (left + bottom, lower),
        (left + bottom * (1 - k), lower), (left, lower - bottom * (1 - k)), (left, lower - bottom),
        (left, upper + top),
    ]
    codes = [DrawingPath.MOVETO, *([DrawingPath.CURVE4] * 3), DrawingPath.LINETO,
             *([DrawingPath.CURVE4] * 3), DrawingPath.LINETO, *([DrawingPath.CURVE4] * 3),
             DrawingPath.LINETO, *([DrawingPath.CURVE4] * 3), DrawingPath.CLOSEPOLY]
    patch = PathPatch(
        DrawingPath(vertices, codes),
        facecolor="#f1f2f4" if unknown else "white",
        edgecolor="#90959d" if unknown else "#30343b",
        linewidth=0.65, linestyle="--" if unknown else "-",
        transform=Affine2D().rotate_deg(angle).translate(x, y) + ax.transData,
    )
    patch.set_gid(seat["chair_seat_position_id"])
    ax.add_patch(patch)


def _draw_seat(ax, seat, state, geometry):
    if state["status"] == "hidden":
        return
    unknown = state["status"] == "unknown"
    _chair_patch(ax, seat, geometry, unknown=unknown)
    label = "?" if unknown else state["label"]
    if label:
        x, y, angle = geometry[:3]
        ax.text(x, y, label, ha="center", va="center", rotation=-angle,
                fontsize=5.5, color="#68717c" if unknown else "#172b4d",
                family="DejaVu Sans", gid=seat["chair_seat_position_id"] + "-label")


def _schematic(ax, positions, numbering):
    for seat in positions:
        try:
            geometry = tuple(float(seat[key]) for key in _GEOMETRY)
        except (TypeError, ValueError) as error:
            raise ValueError("Incomplete geometry for " + seat["chair_seat_position_id"]) from error
        x, y, angle, width, height, top, bottom = geometry
        if (not all(math.isfinite(value) for value in geometry)
                or not 0 <= angle < 360 or width <= 0 or height <= 0
                or not 0 <= top <= min(width, height) / 2
                or not 0 <= bottom <= min(width, height) / 2):
            raise ValueError("Invalid geometry for " + seat["chair_seat_position_id"])
        _draw_seat(ax, seat, numbering[seat["chair_seat_position_id"]], geometry)
    ax.autoscale_view()
    ax.margins(0.04)


def _local_grids(ax, positions, numbering, groups):
    banks = defaultdict(list)
    paths = {}
    cells = set()
    for seat in positions:
        if any(seat[key] for key in _GEOMETRY):
            raise ValueError("Local-grid positions must not have global geometry")
        group_id = seat["chair_group_id"]
        path, seen, current = [], set(), group_id
        while current:
            if current in seen or current not in groups:
                raise ValueError("Cyclic or missing group ancestor for " + group_id)
            seen.add(current)
            group = groups[current]
            if group["parent_group_id"]:
                path.append(group["label"])
            current = group["parent_group_id"]
        paths[group_id] = tuple(reversed(path)) or (groups[group_id]["label"],)
        row, column = int(seat["row"]), int(seat["column"])
        cell = (group_id, row, column)
        if row < 1 or column < 1 or cell in cells:
            raise ValueError("Invalid or duplicate local cell for " + seat["chair_seat_position_id"])
        cells.add(cell)
        banks[group_id].append(seat)

    sections = defaultdict(list)
    for group_id in banks:
        sections[paths[group_id][:-1]].append(group_id)
    # Pack panels for legibility only. These offsets are never source geometry.
    page_width, y = 50, 0
    for section in sorted(sections, key=lambda p: _natural_key(" / ".join(p))):
        heading = textwrap.fill(" / ".join(section) or "Local banks", width=100)
        ax.text(0, y, heading, va="top", fontsize=9, fontweight="bold", color="#283b46")
        y += 1.1 * len(heading.splitlines()) + 0.7
        x, line_height = 0, 0
        for group_id in sorted(sections[section], key=lambda g: (_natural_key(paths[g][-1]), g)):
            seats = banks[group_id]
            width = max(4, max(int(seat["column"]) for seat in seats))
            height = max(int(seat["row"]) for seat in seats) + 2
            if x and x + width > page_width:
                y += line_height + 1
                x, line_height = 0, 0
            page_width = max(page_width, width)
            ax.text(x, y, paths[group_id][-1], fontsize=6.5, va="top", color="#56636c")
            for seat in seats:
                geometry = (x + int(seat["column"]) - 0.5,
                            y + int(seat["row"]) + 0.6, 0, 0.85, 0.85, 0, 0)
                _draw_seat(ax, seat, numbering[seat["chair_seat_position_id"]], geometry)
            x += width + 1.25
            line_height = max(line_height, height)
        y += line_height + 2
    ax.set_xlim(-0.75, page_width + 0.75)
    ax.set_ylim(-0.75, max(y - 1, 1))
    return page_width, y


def render_chair_seating_plan(data_dir, plan_id, output=None, *, dpi=180):
    """Create a chair-plan figure using only the four seating CSV tables.

    Args:
        data_dir (str or pathlib.Path): Directory containing
            ``chair_seating_plans.csv``, ``chair_groups.csv``,
            ``chair_seat_positions.csv`` and ``chair_seat_numbering.csv``.
        plan_id (str): Exact ``chair_seating_plan_id``, or a unique
            ``source_locator`` such as ``EK1985``. Ambiguous locators fail.
        output (str or pathlib.Path, optional): Save as PNG, SVG or PDF.
            Parent directories are created and an existing file is overwritten.
            Omit to obtain a figure without writing a file.
        dpi (int): Raster resolution when saving; defaults to 180.

    Returns:
        matplotlib.figure.Figure: Figure for display, inspection or saving.
            No pyplot window is opened and the global backend is not changed.
            Call ``figure.clear()`` when finished with a large batch.

    Raises:
        ValueError: The selector is missing/ambiguous, output format unsupported,
            or the selected plan has inconsistent states, groups or geometry.
        FileNotFoundError: A required CSV table does not exist.

    Schematic plans use centre coordinates (x right, y down), clockwise
    orientation, symbol dimensions and corner radii in source drawing units.
    Figures are titled "SWERIK schematic"; source attribution stays in the
    footer and the underlying data, including for contributor-derived plans.
    Local-grid plans are **not floor plans**: separate bank panels preserve
    local row/column and group paths, without asserting angles, aisle widths,
    relative bank placement or distances. Display order is by group label.

    Numbered chairs retain their labels, unnumbered chairs have no text,
    hidden slots are omitted without closing gaps, and unknown slots appear
    as dashed boxes with ``?`` (not evidence of a physical chair). States are
    not occupancy. Full corpus integrity validation remains the data repo's
    responsibility; this renderer does not verify sources or date occupants.

    Example:
        >>> from pyriksdagen.chair_seating import render_chair_seating_plan
        >>> figure = render_chair_seating_plan(
        ...     "../riksdagen-persons/data", "EK1985", "EK1985.png")
        >>> figure.clear()
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    data_dir = Path(data_dir)
    if output is not None and Path(output).suffix.lower() not in (".png", ".svg", ".pdf"):
        raise ValueError("Output must end in .png, .svg or .pdf")
    plans = _read_rows(data_dir, "chair_seating_plans.csv")
    matches = [p for p in plans if p["chair_seating_plan_id"] == plan_id]
    if not matches:
        matches = [p for p in plans if p["source_locator"] == plan_id]
    if len(matches) != 1:
        raise ValueError("Select a unique chair_seating_plan_id or source_locator: " + str(plan_id))
    plan = matches[0]
    system = plan["coordinate_system"]
    if system not in ("schematic", "local_grid"):
        raise ValueError("Unsupported coordinate_system: " + system)

    def selected(name):
        return [row for row in _read_rows(data_dir, name)
                if row["chair_seating_plan_id"] == plan["chair_seating_plan_id"]]

    positions = selected("chair_seat_positions.csv")
    numbering = _index(selected("chair_seat_numbering.csv"), "chair_seat_position_id")
    position_ids = _index(positions, "chair_seat_position_id")
    if not positions or set(position_ids) != set(numbering):
        raise ValueError("Every position must have exactly one numbering state, and vice versa")
    groups = _index(selected("chair_groups.csv"), "chair_group_id")
    for seat in positions:
        if seat["chair_group_id"] not in groups:
            raise ValueError("Position references a missing or cross-plan group: " + seat["chair_seat_position_id"])
    for state in numbering.values():
        if state["status"] not in _STATES or bool(state["label"]) != (state["status"] == "numbered"):
            raise ValueError("Invalid numbering state for " + state["chair_seat_position_id"])

    figure = Figure(figsize=(16, 12), facecolor="white")
    FigureCanvasAgg(figure)
    ax = figure.add_axes([0.04, 0.09, 0.92, 0.80])
    if system == "schematic":
        _schematic(ax, positions, numbering)
        subtitle = "SCHEMATIC RECONSTRUCTION | Source drawing units, not measured distances"
        note = "Group membership is retained in the CSVs. Gaps do not establish aisles or aisle widths."
    else:
        width, height = _local_grids(ax, positions, numbering, groups)
        figure.set_size_inches(max(14, width * 0.28), max(8, height * 0.28 + 2))
        subtitle = "LOCAL GRIDS ONLY | Partial reconstruction, not a chamber floor plan"
        note = "Banks are separate panels; panel placement and spacing do not represent the room."
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.set_axis_off()
    title = plan["label"].replace("potmo schematic", "SWERIK schematic")
    if "SWERIK schematic" not in title:
        title += ": SWERIK schematic"
    figure.text(0.5, 0.975, textwrap.fill(title, 95), ha="center", va="top", fontsize=14)
    figure.text(0.5, 0.925, subtitle, ha="center", fontsize=10, color="#8b4626")
    counts = Counter(state["status"] for state in numbering.values())
    legend = " | ".join("{} {}".format(counts[state], state) for state in _STATES)
    figure.text(0.5, 0.070, legend + " | ? = unresolved slot, not a confirmed chair", ha="center", fontsize=8)
    figure.text(0.5, 0.051, note, ha="center", fontsize=8)
    figure.text(0.5, 0.032, "Plan: " + plan["chair_seating_plan_id"], ha="center", fontsize=7, color="#56636c")
    source = "Source: {} ({})".format(Path(plan["source"]).name, plan["source_locator"])
    figure.text(0.5, 0.013, textwrap.fill(source, 145), ha="center", va="top", fontsize=7, color="#56636c")
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=dpi, bbox_inches="tight", facecolor="white")
    return figure
