# pyriksdagen

Python module for interacting with the Swedish Parliamentary Corpus

The use of the module is demonstrated in the [Example Jupyter Notebook](https://github.com/swerik-project/pyriksdagen/blob/main/examples/corpus-walkthrough.ipynb), which can also be run on [Google Colab](https://colab.research.google.com/github/swerik-project/pyriksdagen/blob/main/examples/corpus-walkthrough.ipynb).


## Chair seating plans

Render the source-specific chair plans in `riksdagen-persons/data`:

```python
from pyriksdagen.chair_seating import render_chair_seating_plan

figure = render_chair_seating_plan(
    "../riksdagen-persons/data", "EK1985", "EK1985.png"
)
figure.clear()
```

The first argument is the **data directory**, not the repository root. Select
a `chair_seating_plan_id` or a unique `source_locator` such as `AK1965`.
PNG, SVG and PDF output are supported; `dpi=180` is the raster default.
Omit the output argument to obtain a Matplotlib figure for a notebook or
further customization. This does not change the global plotting backend.

The function reads `chair_seating_plans.csv`, `chair_groups.csv`,
`chair_seat_positions.csv` and `chair_seat_numbering.csv`. It needs no source
images, Swift installation, network connection or occupancy data. Matplotlib
is already a package dependency.

All figure titles use **SWERIK schematic**, including older tables labelled
"potmo schematic". Source attribution is retained in the footer and metadata.
Scan-based global plans, such as the two Samlingsrum reconstructions, use the
same function; their coordinates and cell dimensions come from the CSVs.

- **Schematic plans:** preserve source centres, rotations, dimensions and
  corner radii in drawing units, not metres.
- **Local-grid plans:** show grouped bank panels with local row/column order.
  Panel placement is for readability, **not a reconstructed room layout**.
- Numbered labels and unnumbered chairs are retained; hidden slots are not
  drawn and do not close gaps. Dashed `?` cells mark unresolved slots, not
  confirmed physical chairs. None of these states describes occupancy.

To render every plan, use each ID from `chair_seating_plans.csv`:

```python
import csv
from pathlib import Path

data = Path("../riksdagen-persons/data")
with (data / "chair_seating_plans.csv").open(encoding="utf-8", newline="") as stream:
    for plan in csv.DictReader(stream):
        plan_id = plan["chair_seating_plan_id"]
        figure = render_chair_seating_plan(data, plan_id, Path("previews") / f"{plan_id}.png")
        figure.clear()
```

The public function docstring documents selection errors and rendering
semantics and is included in the normal pdoc documentation build. Historical
source verification, date validity and full data-integrity validation remain
the responsibility of the persons repository. The renderer does not infer
neighbours or aisle widths from schematic gaps.

# Mailing list

For updates right to your email, join our mailing list for parliamentary research infrastructure [here](https://lists.uu.se/sympa/subscribe/parliamentary-research-infrastructure).
