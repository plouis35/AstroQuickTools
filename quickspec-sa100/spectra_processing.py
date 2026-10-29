"""SA100 geometry, extraction and wavelength calibration."""

from dataclasses import dataclass
import logging
import math

import numpy as np

from image_processing import _bilinear_sample

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpectrumResult:
    wavelengths: np.ndarray
    flux: np.ndarray
    rectified_image: np.ndarray
    spectrum_strip: np.ndarray
    sky_strip: np.ndarray
    angle_degrees: float
    dispersion_angstrom_per_pixel: float


class Spectra:
    """SA100 image rectification and linear spectrum extraction."""

    def __init__(
        self,
        distance_mm=35.0,
        pixel_size_um=4.65,
        grating_period_nm=5000.0,
        half_height=5,
        sky_half_height=10,
        lambda_min=3500.0,
        lambda_max=7500.0,
        order_zero_offset_px=0,
    ):
        self.distance_mm = float(distance_mm)
        self.pixel_size_um = float(pixel_size_um)
        self.grating_period_nm = float(grating_period_nm)
        self.half_height = int(half_height)
        self.sky_half_height = int(sky_half_height)
        self.lambda_min = float(lambda_min)
        self.lambda_max = float(lambda_max)
        self.order_zero_offset_px = int(order_zero_offset_px)
        self.result = None
        self._validate_settings()

    def process(self, image, order_zero, dispersion_point, sky_point):
        """Rectify an image, subtract a sky strip, extract and calibrate."""
        data = np.asarray(image, dtype=np.float32)
        if data.ndim != 2 or min(data.shape) < 10:
            raise ValueError("SA100 processing requires a 2D image at least 10x10.")

        x0, y0 = _point(order_zero, "order-zero point")
        x1, y1 = _point(dispersion_point, "dispersion point")
        xs, ys = _point(sky_point, "sky point")
        angle = compute_angle(x0, y0, x1, y1)

        rectified = _rotate_image(data, angle)

        height, width = rectified.shape
        x0_rotated, y0_rotated = rotate_point(
            x0, y0, (width - 1) / 2.0, (height - 1) / 2.0, angle
        )
        _, sky_y_rotated = rotate_point(
            xs, ys, (width - 1) / 2.0, (height - 1) / 2.0, angle
        )

        spectrum_strip, sky_strip = crop_spectrum(
            rectified,
            x0_rotated,
            y0_rotated,
            sky_y_rotated,
            self.half_height,
            self.sky_half_height,
        )
        if spectrum_strip.shape[0] == 0 or sky_strip.shape[0] == 0:
            raise ValueError("The spectrum or sky selection lies outside the image.")

        spectrum_1d = np.sum(spectrum_strip, axis=0, dtype=np.float64)
        sky_1d = np.sum(sky_strip, axis=0, dtype=np.float64)
        flux = spectrum_1d - sky_1d * (
            spectrum_strip.shape[0] / sky_strip.shape[0]
        )
        flux = np.clip(flux, 0.0, None)

        dispersion = compute_dispersion(
            self.distance_mm,
            self.pixel_size_um,
            self.grating_period_nm,
        )
        wavelengths = (
            np.arange(flux.size, dtype=np.float64) - self.order_zero_offset_px
        ) * dispersion
        keep = (wavelengths > self.lambda_min) & (wavelengths < self.lambda_max)
        if not np.any(keep):
            raise ValueError(
                "No pixels fall in the configured wavelength range; "
                "check the SA100 parameters and image."
            )

        self.result = SpectrumResult(
            wavelengths=wavelengths[keep],
            flux=flux[keep].astype(np.float32),
            rectified_image=rectified,
            spectrum_strip=spectrum_strip,
            sky_strip=sky_strip,
            angle_degrees=angle,
            dispersion_angstrom_per_pixel=dispersion,
        )
        logger.info(
            "SA100 extraction: %d samples, %.2f Å/px, rotation %.2f°",
            self.result.flux.size,
            dispersion,
            angle,
        )
        return self.result

    def _validate_settings(self):
        if self.distance_mm <= 0 or self.pixel_size_um <= 0:
            raise ValueError("Distance and pixel size must be positive.")
        if self.grating_period_nm <= 0:
            raise ValueError("Grating period must be positive.")
        if self.half_height < 1 or self.sky_half_height < 1:
            raise ValueError("Extraction strip half-heights must be positive.")
        if self.lambda_max <= self.lambda_min:
            raise ValueError("lambda_max must be greater than lambda_min.")


def compute_angle(x0, y0, x1, y1):
    if x0 == x1 and y0 == y1:
        raise ValueError("Order zero and dispersion point must be different.")
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
    logger.info("SA100 dispersion angle: %.2f degrees", angle)
    return angle


def rotate_point(x, y, center_x, center_y, angle_degrees):
    """Map a point using the same image-coordinate convention as rectification."""
    radians = math.radians(-angle_degrees)
    dx, dy = x - center_x, y - center_y
    return (
        center_x + dx * math.cos(radians) - dy * math.sin(radians),
        center_y + dx * math.sin(radians) + dy * math.cos(radians),
    )


def crop_spectrum(
    image,
    x0_rotated,
    y0_rotated,
    sky_y_rotated,
    half_height,
    sky_half_height,
):
    height, width = image.shape
    x_start = int(round(x0_rotated))
    if not 0 <= x_start < width:
        raise ValueError("The order-zero point is outside the image.")

    spectrum_center = int(round(y0_rotated))
    sky_center = int(round(sky_y_rotated))
    spectrum_low = max(0, spectrum_center - half_height)
    spectrum_high = min(height, spectrum_center + half_height)
    sky_low = max(0, sky_center - sky_half_height)
    sky_high = min(height, sky_center + sky_half_height)

    return (
        image[spectrum_low:spectrum_high, x_start:].copy(),
        image[sky_low:sky_high, x_start:].copy(),
    )


def compute_dispersion(distance_mm, pixel_size_um, grating_period_nm=5000.0):
    """Return the linear SA100 dispersion in Angstroms per pixel."""
    if distance_mm <= 0 or pixel_size_um <= 0 or grating_period_nm <= 0:
        raise ValueError("Distance, pixel size and grating period must be positive.")
    sin_theta = 550.0 / grating_period_nm
    if not 0 < sin_theta < 1:
        raise ValueError("Grating period must be greater than 550 nm.")
    cos_theta = math.sqrt(1.0 - sin_theta**2)
    return grating_period_nm * cos_theta * (pixel_size_um / 1000.0) / distance_mm * 10.0


def _rotate_image(image, angle_degrees, block_rows=64):
    """Rotate a 2D image in place-sized bounds using bilinear interpolation."""
    height, width = image.shape
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    radians = math.radians(angle_degrees)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    output = np.zeros_like(image, dtype=np.float32)
    output_x = np.arange(width, dtype=np.float32)[None, :] - center_x

    for row_start in range(0, height, block_rows):
        row_end = min(row_start + block_rows, height)
        output_y = (
            np.arange(row_start, row_end, dtype=np.float32)[:, None] - center_y
        )
        source_x = center_x + cos_angle * output_x - sin_angle * output_y
        source_y = center_y + sin_angle * output_x + cos_angle * output_y
        output[row_start:row_end] = _bilinear_sample(
            image,
            source_x,
            source_y,
        )
    return output


def _point(point, name):
    if len(point) != 2:
        raise ValueError(f"{name} must contain x and y coordinates.")
    x, y = float(point[0]), float(point[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError(f"{name} coordinates must be finite.")
    return x, y
