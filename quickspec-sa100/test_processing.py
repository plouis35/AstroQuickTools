"""Focused tests for the NumPy image and SA100 processing classes."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image as PillowImage

from image_processing import Image
from spectra_processing import Spectra, compute_dispersion


class ImageProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def save_png(self, name, data):
        path = self.directory / name
        PillowImage.fromarray(np.asarray(data)).save(path)
        return path

    def test_load_grayscale_png_preserves_pixel_values(self):
        expected = np.array([[0, 1000], [30000, 65535]], dtype=np.uint16)
        path = self.save_png("gray16.png", expected)

        result = Image().load([path])

        np.testing.assert_array_equal(result, expected.astype(np.float32))

    def test_load_rejects_non_png_and_different_dimensions(self):
        processor = Image()
        not_png = self.directory / "image.jpg"
        not_png.touch()
        with self.assertRaises(ValueError):
            processor.load([not_png])

        first = self.save_png("first.png", np.ones((3, 4), dtype=np.uint8))
        second = self.save_png("second.png", np.ones((4, 3), dtype=np.uint8))
        with self.assertRaisesRegex(ValueError, "identical dimensions"):
            processor.load([first, second])

    def test_reduce_subtracts_offset_and_dark_and_normalizes_flat(self):
        processor = Image()
        processor.load([
            self.save_png("science.png", np.full((2, 2), 100, dtype=np.uint8))
        ])

        result = processor.reduce(
            offset=np.full((2, 2), 10),
            dark=np.full((2, 2), 20),
            flat=np.array([[1, 2], [1, 2]], dtype=np.float32),
        )

        np.testing.assert_allclose(result, [[105, 52.5], [105, 52.5]])

    def test_registration_aligns_a_shifted_frame(self):
        reference = np.zeros((32, 32), dtype=np.uint8)
        reference[8:14, 11:17] = 200
        moving = np.roll(reference, shift=(3, -2), axis=(0, 1))
        first = self.save_png("reference.png", reference)
        second = self.save_png("moving.png", moving)
        processor = Image()
        processor.load([first, second])

        registered_sum = processor.register()

        np.testing.assert_allclose(
            registered_sum,
            reference.astype(np.float32) * 2,
            atol=1.5,
        )


class Sa100ProcessingTests(unittest.TestCase):
    def test_extracts_background_subtracted_spectrum(self):
        image = np.full((100, 240), 2.0, dtype=np.float32)
        image[38:42, 50:] += 10.0
        processor = Spectra(
            half_height=2,
            sky_half_height=5,
            lambda_min=0,
            lambda_max=10000,
        )

        result = processor.process(
            image,
            order_zero=(50, 40),
            dispersion_point=(180, 40),
            sky_point=(180, 20),
        )

        self.assertEqual(result.flux.size, 189)
        np.testing.assert_allclose(result.flux, 40.0, atol=1e-4)
        self.assertAlmostEqual(result.angle_degrees, 0)
        self.assertTrue(np.all(np.diff(result.wavelengths) > 0))

    def test_rectification_aligns_a_slanted_spectrum(self):
        image = np.zeros((180, 260), dtype=np.float32)
        for x in range(40, 220):
            center = round(40 + 0.25 * (x - 40))
            image[center - 2:center + 2, x] = 100
        processor = Spectra(
            half_height=4,
            sky_half_height=5,
            lambda_min=0,
            lambda_max=10000,
        )

        result = processor.process(
            image,
            order_zero=(40, 40),
            dispersion_point=(180, 75),
            sky_point=(180, 20),
        )

        peak_rows = [
            np.argmax(result.rectified_image[:, x])
            for x in range(70, 190)
        ]
        self.assertAlmostEqual(result.angle_degrees, np.degrees(np.arctan(0.25)))
        self.assertLess(np.std(peak_rows), 1.0)

    def test_rejects_invalid_selection_or_wavelength_range(self):
        image = np.ones((32, 32), dtype=np.float32)
        processor = Spectra(lambda_min=9000, lambda_max=10000)
        with self.assertRaisesRegex(ValueError, "different"):
            processor.process(image, (10, 10), (10, 10), (10, 20))
        with self.assertRaisesRegex(ValueError, "No pixels"):
            processor.process(image, (5, 16), (25, 16), (25, 5))

    def test_dispersion_is_positive(self):
        self.assertGreater(compute_dispersion(35, 4.65), 0)


if __name__ == "__main__":
    unittest.main()
