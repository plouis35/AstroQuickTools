"""PNG image loading, calibration and registration using NumPy."""

import logging
from pathlib import Path

import numpy as np
from PIL import Image as PillowImage

logger = logging.getLogger(__name__)


class Image:
    """Load and reduce PNG frames without CCDProc or Astropy."""

    def __init__(self):
        self.paths = []
        self.frames = []
        self.raw_data = None
        self.data = None

    @staticmethod
    def read_png(path):
        """Return a PNG as a 2D float32 array, preserving grayscale values."""
        image_path = Path(path)
        if image_path.suffix.lower() != ".png":
            raise ValueError(f"Only PNG images are supported: {image_path}")
        if not image_path.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        try:
            with PillowImage.open(image_path) as source:
                source.load()
                if source.mode in ("1", "L", "I", "I;16", "I;16B", "I;16L", "F"):
                    pixels = np.asarray(source)
                else:
                    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
                    pixels = (
                        rgb[..., 0] * 0.2126
                        + rgb[..., 1] * 0.7152
                        + rgb[..., 2] * 0.0722
                    )
        except (OSError, ValueError) as exc:
            raise ValueError(f"Unable to decode PNG {image_path}: {exc}") from exc

        if pixels.ndim != 2 or not pixels.size:
            raise ValueError(f"PNG must contain a non-empty image: {image_path}")
        return np.asarray(pixels, dtype=np.float32)

    def load(self, paths, combine="sum"):
        """Load same-sized PNG frames and combine them by sum or mean."""
        paths = [str(path) for path in paths]
        if not paths:
            raise ValueError("Select at least one PNG image.")
        if combine not in ("sum", "mean"):
            raise ValueError("combine must be 'sum' or 'mean'.")

        frames = [self.read_png(path) for path in paths]
        shape = frames[0].shape
        if any(frame.shape != shape for frame in frames[1:]):
            raise ValueError("All PNG frames must have identical dimensions.")

        combined = np.zeros(shape, dtype=np.float32)
        for frame in frames:
            combined += frame
        if combine == "mean":
            combined /= len(frames)

        self.paths = paths
        self.frames = frames
        self.raw_data = combined
        self.data = combined.copy()
        logger.info("Loaded %d PNG frame(s), shape=%s", len(frames), shape)
        return self.data

    def reduce(self, offset=None, dark=None, flat=None):
        """Apply optional master offset, dark and normalized flat arrays."""
        if self.raw_data is None:
            raise RuntimeError("Load at least one PNG image before reducing.")

        reduced = self.raw_data.copy()
        if offset is not None:
            reduced -= self._master_array(offset, "offset")
        if dark is not None:
            reduced -= self._master_array(dark, "dark")
        if flat is not None:
            flat_data = self._master_array(flat, "flat")
            valid = np.isfinite(flat_data) & (flat_data != 0)
            if not np.any(valid):
                raise ValueError("Flat field contains no finite non-zero pixels.")
            normalized_flat = np.zeros_like(flat_data, dtype=np.float32)
            normalized_flat[valid] = flat_data[valid] / np.median(flat_data[valid])
            corrected = np.zeros_like(reduced, dtype=np.float32)
            np.divide(reduced, normalized_flat, out=corrected, where=valid)
            reduced = corrected

        self.data = reduced
        logger.info("Image reduction complete")
        return self.data

    def register(self, reference_index=0):
        """Align loaded frames to one reference using phase correlation."""
        if not self.frames:
            raise RuntimeError("Load at least one PNG image before registration.")
        if not 0 <= reference_index < len(self.frames):
            raise IndexError("reference_index is outside the loaded frame list.")

        reference = self.frames[reference_index]
        registered = []
        for index, frame in enumerate(self.frames):
            if frame.shape != reference.shape:
                raise ValueError("All PNG frames must have identical dimensions.")
            if index == reference_index:
                registered.append(frame.copy())
                continue
            shift = _phase_correlation_shift(reference, frame)
            logger.info("Registering frame %d with shift %s", index, shift)
            registered.append(_shift_image(frame, shift))

        self.frames = registered
        self.raw_data = np.sum(registered, axis=0, dtype=np.float32)
        self.data = self.raw_data.copy()
        return self.data

    def _master_array(self, master, name):
        if isinstance(master, (str, Path)):
            array = Image.read_png(master)
        else:
            array = np.asarray(master, dtype=np.float32)
        if array.ndim != 2 or not array.size:
            raise ValueError(f"The {name} frame must be a non-empty 2D array.")
        return self._validated_shape(array, name)

    def _validated_shape(self, array, name):
        if array.shape != self.raw_data.shape:
            raise ValueError(
                f"The {name} frame has shape {array.shape}; "
                f"expected {self.raw_data.shape}."
            )
        return array


def _phase_correlation_shift(reference, moving):
    """Estimate the subpixel shift to apply to moving to match reference."""
    reference_fft = np.fft.fftn(reference)
    moving_fft = np.fft.fftn(moving)
    cross_power = reference_fft * moving_fft.conj()
    magnitude = np.abs(cross_power)
    cross_power = np.divide(
        cross_power,
        magnitude,
        out=np.zeros_like(cross_power),
        where=magnitude > np.finfo(np.float32).eps,
    )
    correlation = np.fft.ifftn(cross_power).real
    peak = np.array(np.unravel_index(np.argmax(correlation), correlation.shape))
    shifts = peak.astype(np.float64)

    for axis, axis_size in enumerate(reference.shape):
        if shifts[axis] > axis_size // 2:
            shifts[axis] -= axis_size

        before_index = peak.copy()
        after_index = peak.copy()
        before_index[axis] = (peak[axis] - 1) % axis_size
        after_index[axis] = (peak[axis] + 1) % axis_size
        before = correlation[tuple(before_index)]
        center = correlation[tuple(peak)]
        after = correlation[tuple(after_index)]
        denominator = before - 2 * center + after
        if denominator != 0:
            shifts[axis] += 0.5 * (before - after) / denominator

    return tuple(shifts)


def _shift_image(image, shift, block_rows=64):
    """Translate a 2D image with bilinear interpolation and zero fill."""
    height, width = image.shape
    source_x = np.arange(width, dtype=np.float32)[None, :] - shift[1]
    output = np.zeros_like(image, dtype=np.float32)
    for row_start in range(0, height, block_rows):
        row_end = min(row_start + block_rows, height)
        source_y = (
            np.arange(row_start, row_end, dtype=np.float32)[:, None] - shift[0]
        )
        output[row_start:row_end] = _bilinear_sample(image, source_x, source_y)
    return output


def _bilinear_sample(image, source_x, source_y):
    """Sample an image at broadcastable coordinates, filling outside with 0."""
    height, width = image.shape
    x0_float = np.floor(source_x)
    y0_float = np.floor(source_y)
    x0 = x0_float.astype(np.int32)
    y0 = y0_float.astype(np.int32)
    dx = source_x - x0_float
    dy = source_y - y0_float
    result = np.zeros(np.broadcast_shapes(source_x.shape, source_y.shape), dtype=np.float32)

    for y_offset, y_weight in ((0, 1 - dy), (1, dy)):
        sample_y = y0 + y_offset
        valid_y = (sample_y >= 0) & (sample_y < height)
        for x_offset, x_weight in ((0, 1 - dx), (1, dx)):
            sample_x = x0 + x_offset
            valid = valid_y & (sample_x >= 0) & (sample_x < width)
            clipped_y = np.clip(sample_y, 0, height - 1)
            clipped_x = np.clip(sample_x, 0, width - 1)
            result += (
                image[clipped_y, clipped_x]
                * y_weight
                * x_weight
                * valid
            )
    return result
