"""Rendering guarantees using small, self-contained seating CSV fixtures.

These are library unit tests; corpus-wide integrity checks remain in persons.
Invalid-input tests deliberately corrupt one fixture field at a time.
"""

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pyriksdagen.chair_seating import render_chair_seating_plan


class TestChairSeating(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.plans = [dict(chair_seating_plan_id="plan-1", coordinate_system="schematic",
                           label="Example seating plan", start="", end="")]
        self.groups = [dict(chair_seating_plan_id="plan-1", chair_group_id="root",
                            parent_group_id="", label="Chamber"),
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
                status=status, label="42" if status == "numbered" else "", chair_id=""))

    def write_fixture(self):
        for filename, rows in (("chair_seating_plans.csv", self.plans),
                               ("chair_groups.csv", self.groups),
                               ("chair_seat_positions.csv", self.positions),
                               ("chair_seat_numbering.csv", self.numbering)):
            with (self.data / filename).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    def render(self, selector="plan-1", output=None, **style):
        self.write_fixture()
        figure = render_chair_seating_plan(self.data, selector, output, **style)
        self.addCleanup(figure.clear)
        return figure

    def use_local_grids(self):
        self.plans[0]["coordinate_system"] = "local_grid"
        for position in self.positions:
            for field in ("x", "y", "orientation"):
                position[field] = ""

    def test_numbered_and_unnumbered_states_are_not_confused(self):
        """Guarantee: only numbered chairs receive source labels."""
        ax = self.render().axes[0]
        labels = {text.get_gid(): text.get_text() for text in ax.texts}
        self.assertEqual(labels, {"seat-1-label": "42", "seat-4-label": "?"})
        self.assertIn("seat-3", [patch.get_gid() for patch in ax.patches])

    def test_hidden_slots_do_not_shift_other_chairs(self):
        """Guarantee: hidden slots disappear without changing visible centres."""
        ax = self.render().axes[0]
        patches = {patch.get_gid(): patch for patch in ax.patches}
        self.assertNotIn("seat-2", patches)
        centre = ax.transData.inverted().transform(patches["seat-3"].get_transform().transform((0, 0)))
        np.testing.assert_allclose(centre, (6, 3))

    def test_schematic_rotation_and_dimensions_follow_page_coordinates(self):
        """Guarantee: clockwise rotation and y-down coordinates are preserved."""
        ax = self.render(width=1, height=2).axes[0]
        patch = ax.patches[0]
        points = ax.transData.inverted().transform(patch.get_transform().transform([(0, 0), (1, 0)]))
        np.testing.assert_allclose(points, [(2, 3), (2, 4)])
        self.assertTrue(ax.yaxis_inverted())
        vertices = patch.get_path().vertices
        np.testing.assert_allclose(vertices.min(axis=0), (-0.5, -1))
        np.testing.assert_allclose(vertices.max(axis=0), (0.5, 1))

    def test_top_and_bottom_corner_radii_can_be_configured(self):
        """Guarantee: caller-supplied top and bottom rounding is applied independently."""
        vertices = self.render(width=1, height=2, top_radius=0.1, bottom_radius=0.3).axes[0].patches[0].get_path().vertices
        np.testing.assert_allclose(vertices[0], (-0.5, -0.9))
        np.testing.assert_allclose(vertices[8], (0.5, 0.7))

    def test_all_plans_and_coordinate_systems_share_default_symbols(self):
        """Guarantee: every visible chair uses the same default shape without size/radius CSV columns."""
        schematic = self.render().axes[0].patches
        vertices = schematic[0].get_path().vertices
        np.testing.assert_allclose(vertices.min(axis=0), (-0.3, -0.3))
        np.testing.assert_allclose(vertices.max(axis=0), (0.3, 0.3))
        np.testing.assert_allclose(vertices[0], (-0.3, -0.3))
        np.testing.assert_allclose(vertices[8], (0.3, 0.12))
        self.use_local_grids()
        self.plans[0]["label"] = "Another plan"
        for patch in [*schematic, *self.render().axes[0].patches]:
            np.testing.assert_allclose(patch.get_path().vertices, vertices)

    def test_legacy_csv_styles_do_not_override_shared_defaults(self):
        """Guarantee: old size/radius columns cannot silently override the renderer's shared settings."""
        expected = self.render().axes[0].patches[0].get_path().vertices.copy()
        for index, position in enumerate(self.positions):
            position.update(width=str(index + 10), height="20", top_radius="1", bottom_radius="2")
        for patch in self.render().axes[0].patches:
            np.testing.assert_allclose(patch.get_path().vertices, expected)
        self.use_local_grids()
        for patch in self.render().axes[0].patches:
            np.testing.assert_allclose(patch.get_path().vertices, expected)

    def test_style_overrides_apply_to_both_coordinate_systems(self):
        """Guarantee: rendering options style every visible chair, including local grids and unknown slots."""
        style = dict(width=0.8, height=0.7, top_radius=0.1, bottom_radius=0.2)
        schematic = self.render(**style).axes[0].patches
        vertices = schematic[0].get_path().vertices
        np.testing.assert_allclose(vertices.min(axis=0), (-0.4, -0.35))
        np.testing.assert_allclose(vertices.max(axis=0), (0.4, 0.35))
        np.testing.assert_allclose(vertices[0], (-0.4, -0.25))
        np.testing.assert_allclose(vertices[8], (0.4, 0.15))
        self.use_local_grids()
        for patch in [*schematic, *self.render(**style).axes[0].patches]:
            np.testing.assert_allclose(patch.get_path().vertices, vertices)

    def test_invalid_symbol_styles_are_rejected(self):
        """Guarantee: invalid drawing options fail before producing misleading or missing symbols."""
        for style in ({"width": 0}, {"height": -1}, {"width": float("nan")},
                      {"height": float("inf")}, {"width": None}, {"height": "wide"},
                      {"top_radius": -0.1}, {"bottom_radius": 0.31}, {"top_radius": float("nan")},
                      {"bottom_radius": float("inf")}):
            with self.subTest(style=style), self.assertRaisesRegex(ValueError, "[Cc]hair-symbol"):
                self.render(**style)

    def test_seat_labels_fit_shared_symbols_in_dense_plans(self):
        """Guarantee: dense schematics shrink labels uniformly instead of overflowing the common symbols."""
        self.positions[-1]["x"] = "100"
        self.numbering[0]["label"] = "349"
        figure = self.render()
        figure.canvas.draw()
        ax = figure.axes[0]
        renderer = figure.canvas.get_renderer()
        labels = [text for text in ax.texts if (text.get_gid() or "").endswith("-label")]
        available = 0.6 * abs(ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0])
        self.assertEqual(len({text.get_fontsize() for text in labels}), 1)
        self.assertLess(labels[0].get_fontsize(), 5.5)
        for text in labels:
            width, height, descent = renderer.get_text_width_height_descent(
                text.get_text(), text.get_fontproperties(), ismath=False)
            self.assertLessEqual(max(width, height + abs(descent)), available)

    def test_unknown_slots_are_visually_distinct(self):
        """Guarantee: unresolved slots are dashed placeholders, not ordinary chairs."""
        patches = {patch.get_gid(): patch for patch in self.render().axes[0].patches}
        self.assertEqual(patches["seat-4"].get_linestyle(), "--")
        self.assertNotEqual(patches["seat-4"].get_facecolor(), patches["seat-1"].get_facecolor())

    def test_local_grids_keep_gaps_and_warn_against_geometric_use(self):
        """Guarantee: local grids retain slot order and disclaim room geometry."""
        self.use_local_grids()
        figure = self.render()
        ax = figure.axes[0]
        patches = {patch.get_gid(): patch for patch in ax.patches}
        centres = [ax.transData.inverted().transform(patches[key].get_transform().transform((0, 0)))
                   for key in ("seat-1", "seat-3")]
        np.testing.assert_allclose(centres[1] - centres[0], (2, 0))
        self.assertTrue(any("not a chamber floor plan" in text.get_text() for text in figure.texts))
        self.assertIn("Bank 1", [text.get_text() for text in ax.texts])

    def test_local_group_hierarchy_is_visible(self):
        """Guarantee: local bank panels retain their ancestor group labels."""
        self.use_local_grids()
        self.groups.append(dict(chair_seating_plan_id="plan-1", chair_group_id="section",
                                parent_group_id="root", label="Left section"))
        self.groups[1]["parent_group_id"] = "section"
        self.assertIn("Left section", [text.get_text() for text in self.render().axes[0].texts])

    def test_ambiguous_label_is_rejected(self):
        """Guarantee: shared plan labels never silently select one plan."""
        self.plans.append(dict(self.plans[0], chair_seating_plan_id="plan-2"))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.render("Example seating plan")

    def test_unique_label_selects_the_plan(self):
        """Guarantee: an exact unique label is accepted without source columns."""
        self.assertEqual(len(self.render("Example seating plan").axes[0].patches), 3)

    def test_unknown_selector_is_rejected_without_source_columns(self):
        """Guarantee: missing selectors report a selection error, not a missing source column."""
        with self.assertRaisesRegex(ValueError, "unique chair_seating_plan_id or label"):
            self.render("missing-plan")

    def test_missing_numbering_is_rejected(self):
        """Guarantee: unmatched position/state records cannot silently disappear."""
        self.numbering.pop()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.render()

    def test_duplicate_numbering_is_rejected(self):
        """Guarantee: duplicate state records cannot silently overwrite one another."""
        self.numbering.append(dict(self.numbering[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.render()

    def test_unknown_state_is_rejected(self):
        """Guarantee: unrecognized state vocabulary does not create ordinary chairs."""
        self.numbering[0]["status"] = "vacant"
        with self.assertRaisesRegex(ValueError, "Invalid numbering"):
            self.render()

    def test_nonfinite_geometry_is_rejected(self):
        """Guarantee: invalid coordinates cannot silently drop a chair from a diagram."""
        self.positions[0]["x"] = "nan"
        with self.assertRaisesRegex(ValueError, "Invalid geometry.*seat-1"):
            self.render()

    def test_missing_geometry_is_rejected(self):
        """Guarantee: schematic plans never substitute invented missing coordinates."""
        self.positions[0]["x"] = ""
        with self.assertRaisesRegex(ValueError, "Incomplete geometry.*seat-1"):
            self.render()

    def test_cross_plan_group_is_rejected(self):
        """Guarantee: a position cannot borrow a group from another source plan."""
        self.groups[1]["chair_seating_plan_id"] = "another-plan"
        with self.assertRaisesRegex(ValueError, "cross-plan"):
            self.render()

    def test_local_grid_cannot_claim_global_geometry(self):
        """Guarantee: conflicting coordinate systems fail instead of being silently mixed."""
        self.use_local_grids()
        self.positions[0]["x"] = "3"
        with self.assertRaisesRegex(ValueError, "must not have global geometry"):
            self.render()

    def test_cyclic_group_ancestry_is_rejected(self):
        """Guarantee: corrupt group ancestry fails without an infinite traversal."""
        self.use_local_grids()
        self.groups[1]["parent_group_id"] = "bank"
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            self.render()

    def test_png_output_contains_visible_pixels(self):
        """Guarantee: saved PNGs contain a nonblank diagram in a newly created folder."""
        from PIL import Image
        output = self.data / "nested/plan.png"
        self.render(output=output)
        with Image.open(output) as image:
            self.assertGreater(image.width, 100)
            self.assertGreater(np.count_nonzero(np.asarray(image)[:, :, :3].min(axis=2) < 100), 100)

    def test_vector_outputs_are_supported(self):
        """Guarantee: SVG and PDF exports preserve a usable figure."""
        for suffix, signature in (("svg", b"<?xml"), ("pdf", b"%PDF")):
            with self.subTest(suffix=suffix):
                output = self.data / ("plan." + suffix)
                self.render(output=output)
                self.assertTrue(output.read_bytes().startswith(signature))

    def test_all_figure_titles_use_swerik_and_retain_plan_identity(self):
        """Guarantee: figure titles say SWERIK schematic once and identify the plan without source columns."""
        for label in ("EXAMPLE: potmo schematic", "EXAMPLE: SWERIK schematic", "EXAMPLE"):
            with self.subTest(label=label):
                self.plans[0]["label"] = label
                figure = self.render()
                title = figure.texts[0].get_text()
                self.assertNotIn("potmo schematic", title)
                self.assertEqual(title.count("SWERIK schematic"), 1)
                self.assertIn("Plan: plan-1", figure.texts[-1].get_text())
        self.use_local_grids()
        self.assertIn("SWERIK schematic", self.render().texts[0].get_text())

    def test_rendering_does_not_change_backend_or_inputs(self):
        """Guarantee: rendering is read-only and does not switch the global backend."""
        import matplotlib
        self.write_fixture()
        before = {path.name: path.read_bytes() for path in self.data.glob("*.csv")}
        backend = matplotlib.get_backend()
        figure = render_chair_seating_plan(self.data, "plan-1")
        self.addCleanup(figure.clear)
        self.assertEqual(matplotlib.get_backend(), backend)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.data.glob("*.csv")})


if __name__ == "__main__":
    unittest.main()
