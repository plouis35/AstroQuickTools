"""Kivy GUI smoke tests for navigation and SA100 selection."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kivy.graphics.texture import Texture
from kivy.uix.image import Image as KivyImage
from kivy.uix.tabbedpanel import TabbedPanel

from gui import ImageViewport, QuickSpecGUI, SpectrumPlot
from spectra_processing import Spectra


class QuickSpecGuiTests(unittest.TestCase):
    def setUp(self):
        self.app = QuickSpecGUI()
        self.root = self.app.build()

    def test_builds_full_screen_image_and_spectrum_tabs(self):
        self.assertIsInstance(self.root, TabbedPanel)
        self.assertEqual(self.app.image_tab.text, "Image")
        self.assertEqual(self.app.spectrum_tab.text, "Spectre")
        self.assertIs(self.root.current_tab, self.app.image_tab)
        self.assertIs(self.app.image_tab.content, self.app.image_panel)
        self.assertIs(self.app.spectrum_tab.content, self.app.spectrum_panel)

    def test_selection_button_callback_is_defined_and_updates_status(self):
        self.app.image_panel.image_shape = (100, 200)

        self.app.image_panel.select_button.dispatch("on_release")

        self.assertTrue(self.app.image_panel.selecting)
        self.assertEqual(self.app.image_panel.status.text, "Clique l’ordre zéro (1/3).")

    def test_successful_extraction_navigates_to_spectrum_tab(self):
        import numpy as np

        image = np.full((100, 240), 2.0, dtype=np.float32)
        image[38:42, 50:] += 10.0
        self.app.spectra_processor = Spectra(
            half_height=2,
            sky_half_height=5,
            lambda_min=0,
            lambda_max=10000,
        )
        self.app.image_processor.data = image
        self.app.image_panel.image_shape = image.shape
        self.app._begin_sa100_selection()

        for point in ((50, 40), (180, 40), (180, 20)):
            self.app._on_image_point(point)

        self.assertIs(self.root.current_tab, self.app.spectrum_tab)
        self.assertTrue(self.app.spectrum_panel.plot.x_values)

    def test_image_coordinates_remain_correct_after_zoom(self):
        viewport = ImageViewport(on_image_tap=lambda _point: None)
        viewport.pos = (20, 30)
        viewport.size = (300, 200)
        image = KivyImage(
            size_hint=(None, None),
            size=(200, 100),
            pos=(70, 80),
        )
        image.texture = Texture.create(size=(200, 100), colorfmt="rgba")
        viewport.add_widget(image)
        viewport.image_widget = image
        viewport.layout_image()

        pixel_fraction = (0.25, 0.25)
        window_point = (
            image.x + image.width * pixel_fraction[0],
            image.y + image.height * pixel_fraction[1],
        )
        before_zoom = viewport.image_point_from_window(*window_point)
        viewport.zoom_by(2)
        window_point = (
            image.x + image.width * pixel_fraction[0],
            image.y + image.height * pixel_fraction[1],
        )
        after_zoom = viewport.image_point_from_window(*window_point)

        self.assertAlmostEqual(before_zoom[0], 50)
        self.assertAlmostEqual(before_zoom[1], 75)
        self.assertAlmostEqual(after_zoom[0], before_zoom[0])
        self.assertAlmostEqual(after_zoom[1], before_zoom[1])

    def test_empty_image_widget_is_hidden_and_zoom_is_responsive(self):
        image_panel = self.app.image_panel
        self.assertEqual(image_panel.image_widget.opacity, 0)
        image_panel.preview.size = (300, 200)
        image_panel.image_widget.texture = Texture.create(
            size=(200, 100),
            colorfmt="rgba",
        )
        image_panel.image_widget.opacity = 1
        image_panel.preview.layout_image()
        initial_size = tuple(image_panel.image_widget.size)

        image_panel.zoom_in_button.dispatch("on_release")

        self.assertEqual(tuple(image_panel.image_widget.size), (
            initial_size[0] * 1.5,
            initial_size[1] * 1.5,
        ))
        self.assertEqual(image_panel.preview.scale, 1.5)
        image_panel.fit_image()
        self.assertEqual(image_panel.preview.scale, 1.0)
        self.assertEqual(tuple(image_panel.image_widget.size), initial_size)

    def test_sa100_selection_adds_colored_markers_that_follow_zoom(self):
        image_panel = self.app.image_panel
        image_panel.image_shape = (100, 200)
        image_panel.preview.size = (300, 200)
        image_panel.image_widget.texture = Texture.create(
            size=(200, 100),
            colorfmt="rgba",
        )
        image_panel.preview.layout_image()
        image_panel.on_point = lambda _point: None
        image_panel.begin_selection()

        for point in ((40, 50), (100, 50), (100, 20)):
            image_panel._on_image_tap(point)

        markers = image_panel.preview.markers
        self.assertEqual(len(markers), 3)
        self.assertEqual(
            [color for _, color in markers],
            [
                (1, 0.1, 0.1, 1),
                (0.1, 1, 0.2, 1),
                (0.2, 0.45, 1, 1),
            ],
        )
        first_center = image_panel.preview.marker_center(markers[0][0])
        image_panel.zoom_by(1.5)
        zoomed_center = image_panel.preview.marker_center(markers[0][0])
        self.assertNotEqual(zoomed_center, first_center)

        image_panel.image_widget.pos = (
            image_panel.image_widget.x + 35,
            image_panel.image_widget.y + 20,
        )
        moved_center = image_panel.preview.marker_center(markers[0][0])
        self.assertEqual(moved_center, (zoomed_center[0] + 35, zoomed_center[1] + 20))
        self.assertEqual(
            len(image_panel.image_widget.canvas.after.children),
            3 * 10,
        )

        image_panel.begin_selection()
        self.assertEqual(image_panel.preview.markers, [])

    def test_spectrum_plot_displays_x_and_y_axis_scales(self):
        plot = SpectrumPlot(pos=(0, 0), size=(600, 360))

        plot.set_data([400, 500, 600], [-10, 0, 10])

        self.assertEqual(len(plot.x_tick_labels), 6)
        self.assertEqual(len(plot.y_tick_labels), 5)
        self.assertEqual(plot.x_tick_labels[0], "400")
        self.assertEqual(plot.x_tick_labels[-1], "600")
        self.assertEqual(plot.y_tick_labels[0], "-10")
        self.assertEqual(plot.y_tick_labels[-1], "10")
        self.assertEqual(plot.x_axis_label, "Longueur d’onde (Å)")
        self.assertEqual(plot.y_axis_label, "Flux")

    def test_spectrum_plot_handles_constant_flux_and_empty_data(self):
        plot = SpectrumPlot(pos=(0, 0), size=(600, 360))

        plot.set_data([500, 600], [25, 25])

        self.assertTrue(all(plot.x_tick_labels))
        self.assertTrue(all(plot.y_tick_labels))
        self.assertNotEqual(plot.y_tick_labels[0], plot.y_tick_labels[-1])

        plot.clear()

        self.assertEqual(plot.x_tick_labels, [])
        self.assertEqual(plot.y_tick_labels, [])

    def test_last_picker_location_is_persisted(self):
        with TemporaryDirectory() as directory:
            location_file = Path(directory) / "last-location.txt"
            self.app._location_file = location_file

            self.app._save_picker_location(directory)

            self.assertEqual(self.app._read_picker_location(), directory)
            self.assertEqual(self.app._last_picker_location, directory)


if __name__ == "__main__":
    unittest.main()
