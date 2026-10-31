"""Unit tests for seating-plan rendering using self-contained CSV fixtures."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from pyriksdagen.chair_seating import render_chair_seating_plan


class TestChairSeating(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.plans = [dict(chair_seating_plan_id="plan-1", coordinate_system="schematic",
                           label="Example seating plan", start=None, end=None)]
        self.groups = [dict(chair_seating_plan_id="plan-1", chair_group_id="root",
                            parent_group_id=None, label="Chamber"),
                       dict(chair_seating_plan_id="plan-1", chair_group_id="bank",
                            parent_group_id="root", label="Bank 1")]
        self.positions = []
        self.numbering = []
        for i, status in enumerate(("numbered", "hidden", "unnumbered", "unknown"), 1):
            self.positions.append(dict(
                chair_seating_plan_id="plan-1", chair_seat_position_id="seat-" + str(i),
                chair_group_id="bank", row="1", column=str(i), x=str(i * 2), y="3",
                orientation="90"))
            self.numbering.append(dict(
                chair_seating_plan_id="plan-1", chair_seat_position_id="seat-" + str(i),
                status=status, label="042" if status == "numbered" else None, chair_id=None))

    def write_fixture(self):
        for filename, rows in (("chair_seating_plans.csv", self.plans),
                               ("chair_groups.csv", self.groups),
                               ("chair_seat_positions.csv", self.positions),
                               ("chair_seat_numbering.csv", self.numbering)):
            pl.DataFrame(rows).write_csv(self.data / filename)

    def render(self, selector="plan-1", output=None, **style):
        self.write_fixture()
        figure = render_chair_seating_plan(self.data, selector, output, **style)
        self.addCleanup(figure.clear)
        return figure

    def use_local_grids(self):
        self.plans[0]["coordinate_system"] = "local_grid"
        for position in self.positions:
            for field in ("x", "y", "orientation"):
                position[field] = None

    def test_numbered_and_unnumbered_states_are_not_confused(self):
        """Only numbered chairs receive source labels."""
        ax = self.render().axes[0]
        labels = {text.get_gid(): text.get_text() for text in ax.texts}
        self.assertEqual(labels, {"seat-1-label": "042", "seat-4-label": "?"})
        self.assertIn("seat-3", [patch.get_gid() for patch in ax.patches])

    def test_hidden_slots_do_not_shift_other_chairs(self):
        """Hidden slots are omitted without changing visible chair centres."""
        ax = self.render().axes[0]
        patches = {patch.get_gid(): patch for patch in ax.patches}
        self.assertNotIn("seat-2", patches)
        centre = ax.transData.inverted().transform(patches["seat-3"].get_transform().transform((0, 0)))
        np.testing.assert_allclose(centre, (6, 3))

    def test_top_and_bottom_corner_radii_can_be_configured(self):
        """Top and bottom corner radii can be set independently."""
        vertices = self.render(width=1, height=2, top_radius=0.1, bottom_radius=0.3,
                               fit_symbols=False).axes[0].patches[0].get_path().vertices
        np.testing.assert_allclose(vertices[0], (-0.5, -0.9))
        np.testing.assert_allclose(vertices[8], (0.5, 0.7))
    def test_unknown_slots_are_visually_distinct(self):
        """Unknown slots use dashed outlines and a distinct fill colour."""
        patches = {patch.get_gid(): patch for patch in self.render().axes[0].patches}
        self.assertEqual(patches["seat-4"].get_linestyle(), "--")
        self.assertNotEqual(patches["seat-4"].get_facecolor(), patches["seat-1"].get_facecolor())

    def test_local_group_hierarchy_is_visible(self):
        """Local grid panels display ancestor group labels."""
        self.use_local_grids()
        self.groups.append(dict(chair_seating_plan_id="plan-1", chair_group_id="section",
                                parent_group_id="root", label="Left section"))
        self.groups[1]["parent_group_id"] = "section"
        self.assertIn("Left section", [text.get_text() for text in self.render().axes[0].texts])

    def test_ambiguous_label_is_rejected(self):
        """Selecting a label shared by multiple plans raises ValueError."""
        self.plans.append(dict(self.plans[0], chair_seating_plan_id="plan-2"))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.render("Example seating plan")

    def test_unique_label_selects_the_plan(self):
        """An exact unique label selects a plan without source columns."""
        self.assertEqual(len(self.render("Example seating plan").axes[0].patches), 3)

    def test_unknown_selector_is_rejected_without_source_columns(self):
        """An unknown selector raises ValueError without requiring source columns."""
        with self.assertRaisesRegex(ValueError, "unique chair_seating_plan_id or label"):
            self.render("missing-plan")

    def test_missing_numbering_is_rejected(self):
        """A position without a numbering record raises ValueError."""
        self.numbering.pop()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render()

    def test_duplicate_numbering_is_rejected(self):
        """Duplicate numbering records raise ValueError."""
        self.numbering.append(dict(self.numbering[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.render()

    def test_unknown_state_is_rejected(self):
        """An unsupported numbering status raises ValueError."""
        self.numbering[0]["status"] = "vacant"
        with self.assertRaisesRegex(ValueError, "Invalid numbering"):
            self.render()

    def test_nonfinite_geometry_is_rejected(self):
        """A nonfinite coordinate raises ValueError identifying the seat."""
        self.positions[0]["x"] = "nan"
        with self.assertRaisesRegex(ValueError, "Invalid geometry.*seat-1"):
            self.render()

    def test_missing_geometry_is_rejected(self):
        """A missing schematic coordinate raises ValueError identifying the seat."""
        self.positions[0]["x"] = None
        with self.assertRaisesRegex(ValueError, "Incomplete geometry.*seat-1"):
            self.render()

    def test_cross_plan_group_is_rejected(self):
        """A position referencing a group from another plan raises ValueError."""
        self.groups[1]["chair_seating_plan_id"] = "another-plan"
        with self.assertRaisesRegex(ValueError, "cross-plan"):
            self.render()

    def test_local_grid_cannot_claim_global_geometry(self):
        """Global coordinates in a local grid raise ValueError."""
        self.use_local_grids()
        self.positions[0]["x"] = "3"
        with self.assertRaisesRegex(ValueError, "must not have global geometry"):
            self.render()
    def test_png_output_contains_visible_pixels(self):
        """PNG export creates the output directory and writes a nonblank image."""
        from PIL import Image
        output = self.data / "nested/plan.png"
        self.render(output=output)
        with Image.open(output) as image:
            self.assertGreater(image.width, 100)
            self.assertGreater(np.count_nonzero(np.asarray(image)[:, :, :3].min(axis=2) < 100), 100)

    def test_vector_outputs_are_supported(self):
        """SVG and PDF exports have the expected file signatures."""
        for suffix, signature in (("svg", b"<?xml"), ("pdf", b"%PDF")):
            with self.subTest(suffix=suffix):
                output = self.data / ("plan." + suffix)
                self.render(output=output)
                self.assertTrue(output.read_bytes().startswith(signature))

if __name__ == "__main__":
    unittest.main()
