"""Kivy presentation and orchestration for the QuickSpec SA100 app."""

import logging
import math
import os
import shutil
from pathlib import Path

from kivy.app import App
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.stencilview import StencilView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.widget import Widget
from kivy.utils import platform

from image_processing import Image
from spectra_processing import Spectra

logger = logging.getLogger(__name__)
ANDROID_PICKER_REQUEST = 7412


class ImageViewport(StencilView):
    """Image surface supporting pan, pinch zoom and accurate selection taps."""

    def __init__(self, on_image_tap, **kwargs):
        super().__init__(**kwargs)
        self.on_image_tap = on_image_tap
        self.selecting = False
        self.image_widget = None
        self._touch_positions = {}
        self._tap_candidates = {}
        self._fit_size = (0, 0)
        self.zoom = 1.0
        self.max_zoom = 16.0
        self.markers = []
        self.bind(pos=self._redraw_markers, size=self._redraw_markers)

    @property
    def scale(self):
        return self.zoom

    def layout_image(self):
        if self.image_widget is None:
            return
        width, height = self.image_widget.texture_size
        if not width or not height or not self.width or not self.height:
            return
        factor = min(self.width / width, self.height / height)
        self._fit_size = (width * factor, height * factor)
        self.zoom = 1.0
        self.image_widget.size = self._fit_size
        self.image_widget.pos = (
            self.x + (self.width - self.image_widget.width) / 2,
            self.y + (self.height - self.image_widget.height) / 2,
        )
        self._redraw_markers()
        if hasattr(self, "placeholder"):
            self.placeholder.pos = self.pos
            self.placeholder.size = self.size

    def reset_zoom(self):
        self.layout_image()

    def zoom_by(self, factor, center=None):
        if self.image_widget is None or not self.image_widget.texture:
            return
        new_zoom = min(self.max_zoom, max(1.0, self.zoom * factor))
        actual_factor = new_zoom / self.zoom
        if actual_factor == 1:
            return
        if center is None:
            center = self.center

        image = self.image_widget
        center_x, center_y = center
        image.pos = (
            center_x - (center_x - image.x) * actual_factor,
            center_y - (center_y - image.y) * actual_factor,
        )
        image.size = (
            self._fit_size[0] * new_zoom,
            self._fit_size[1] * new_zoom,
        )
        self.zoom = new_zoom
        self._redraw_markers()

    def add_marker(self, point, color):
        self.markers.append((point, color))
        self._redraw_markers()

    def clear_markers(self):
        self.markers.clear()
        self._redraw_markers()

    def marker_center(self, point):
        image = self.image_widget
        if image is None:
            return None
        width, height = image.texture_size
        if not width or not height:
            return None
        pixel_x, pixel_y = point
        return (
            image.x + pixel_x / width * image.width,
            image.top - pixel_y / height * image.height,
        )

    def _redraw_markers(self, *_args):
        image = self.image_widget
        if image is None:
            return
        canvas = image.canvas.after
        canvas.clear()
        if not image.texture:
            return
        marker_size = dp(7)
        with canvas:
            for point, color in self.markers:
                center = self.marker_center(point)
                if center is None:
                    continue
                x, y = center
                cross_points = (
                    (x - marker_size, y, x + marker_size, y),
                    (x, y - marker_size, x, y + marker_size),
                )
                Color(0, 0, 0, 0.9)
                for points in cross_points:
                    Line(points=points, width=dp(4))
                Color(*color)
                for points in cross_points:
                    Line(points=points, width=dp(2))

    def image_point_from_window(self, x, y):
        image = self.image_widget
        if image is None or not image.width or not image.height:
            return None

        local_x, local_y = x, y
        if not (
            image.x <= local_x <= image.right
            and image.y <= local_y <= image.top
        ):
            return None

        image_width, image_height = image.texture_size
        if not image_width or not image_height:
            return None
        pixel_x = (local_x - image.x) / image.width * image_width
        pixel_y = (1 - (local_y - image.y) / image.height) * image_height
        return pixel_x, pixel_y

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            local_pos = touch.pos
            if self._touch_positions:
                self._tap_candidates.clear()
            self._touch_positions[touch.uid] = local_pos
            if self.selecting and len(self._touch_positions) == 1:
                if self._point_from_local(*local_pos) is not None:
                    self._tap_candidates[touch.uid] = touch.pos
            touch.grab(self)
            return True
        return False

    def _point_from_local(self, x, y):
        image = self.image_widget
        if image is None or not image.width or not image.height:
            return None
        if not (image.x <= x <= image.right and image.y <= y <= image.top):
            return None
        width, height = image.texture_size
        return (
            (x - image.x) / image.width * width,
            (1 - (y - image.y) / image.height) * height,
        )

    def on_touch_move(self, touch):
        if touch.grab_current is not self or touch.uid not in self._touch_positions:
            return False
        current = touch.pos
        previous = self._touch_positions[touch.uid]
        if len(self._touch_positions) >= 2:
            other_uid = next(uid for uid in self._touch_positions if uid != touch.uid)
            other = self._touch_positions[other_uid]
            old_dx, old_dy = previous[0] - other[0], previous[1] - other[1]
            new_dx, new_dy = current[0] - other[0], current[1] - other[1]
            old_distance = math.hypot(old_dx, old_dy)
            new_distance = math.hypot(new_dx, new_dy)
            if old_distance:
                center = (
                    (current[0] + other[0]) / 2,
                    (current[1] + other[1]) / 2,
                )
                self.zoom_by(new_distance / old_distance, center)
            self._touch_positions[other_uid] = other
        else:
            dx, dy = current[0] - previous[0], current[1] - previous[1]
            candidate = self._tap_candidates.get(touch.uid)
            if candidate is not None and math.hypot(
                touch.x - candidate[0], touch.y - candidate[1]
            ) > dp(10):
                self._tap_candidates.pop(touch.uid, None)
            if self.image_widget is not None:
                self.image_widget.pos = (
                    self.image_widget.x + dx,
                    self.image_widget.y + dy,
                )
        self._touch_positions[touch.uid] = current
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        start = self._tap_candidates.pop(touch.uid, None)
        if start is not None and self.selecting:
            dx = touch.x - start[0]
            dy = touch.y - start[1]
            if math.hypot(dx, dy) <= dp(10):
                point = self.image_point_from_window(*touch.pos)
                if point is not None:
                    self.on_image_tap(point)
        touch.ungrab(self)
        self._touch_positions.pop(touch.uid, None)
        if len(self._touch_positions) < 2:
            self._tap_candidates.clear()
        return True


class SpectrumPlot(Widget):
    """Minimal spectrum plot drawn with Kivy canvas instructions."""

    x_axis_label = "Longueur d’onde (Å)"
    y_axis_label = "Flux"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.x_values = []
        self.y_values = []
        self.x_tick_labels = []
        self.y_tick_labels = []
        self.bind(pos=self._redraw, size=self._redraw)

    def set_data(self, x_values, y_values):
        self.x_values = list(x_values)
        self.y_values = list(y_values)
        self._redraw()

    def clear(self):
        self.x_values = []
        self.y_values = []
        self._redraw()

    @staticmethod
    def _format_tick(value, step):
        if value and (abs(value) >= 1e6 or abs(value) < 1e-3):
            return f"{value:.1e}"
        if step == 0:
            return f"{value:g}"
        decimals = max(0, min(6, -math.floor(math.log10(abs(step))) + 1))
        formatted = f"{value:.{decimals}f}"
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        return formatted

    @staticmethod
    def _expanded_range(minimum, maximum):
        if minimum != maximum:
            return minimum, maximum
        padding = max(abs(minimum) * 0.05, 0.5)
        return minimum - padding, maximum + padding

    @staticmethod
    def _draw_text(text, center, font_size, color):
        label = CoreLabel(
            text=text,
            font_size=font_size,
            color=color,
        )
        label.refresh()
        texture = label.texture
        Rectangle(
            texture=texture,
            pos=(
                center[0] - texture.width / 2,
                center[1] - texture.height / 2,
            ),
            size=texture.size,
        )

    def _redraw(self, *_args):
        self.canvas.clear()
        left = self.x + 58
        bottom = self.y + 42
        right = self.right - 12
        top = self.top - 28
        plot_width = max(right - left, 1)
        plot_height = max(top - bottom, 1)

        has_data = (
            len(self.x_values) >= 2
            and len(self.x_values) == len(self.y_values)
        )
        if has_data:
            x_min, x_max = self._expanded_range(
                min(self.x_values),
                max(self.x_values),
            )
            y_min, y_max = self._expanded_range(
                min(self.y_values),
                max(self.y_values),
            )
        else:
            x_min, x_max, y_min, y_max = 0, 1, 0, 1
        x_step = (x_max - x_min) / 5
        y_step = (y_max - y_min) / 4
        x_ticks = [
            x_min + index * x_step
            for index in range(6)
        ]
        y_ticks = [
            y_min + index * y_step
            for index in range(5)
        ]

        self.x_tick_labels = [
            self._format_tick(value, x_step) for value in x_ticks
        ] if has_data else []
        self.y_tick_labels = [
            self._format_tick(value, y_step) for value in y_ticks
        ] if has_data else []

        with self.canvas:
            Color(0.08, 0.10, 0.13, 1)
            Rectangle(pos=self.pos, size=self.size)

            Color(0.25, 0.30, 0.36, 1)
            for y in (
                bottom + (value - y_min) / (y_max - y_min) * plot_height
                for value in y_ticks
            ):
                Line(points=(left, y, right, y), width=0.7)
            for value in x_ticks:
                x = left + (value - x_min) / (x_max - x_min) * plot_width
                Line(points=(x, bottom, x, top), width=0.7)
            Color(0.72, 0.77, 0.83, 1)
            Line(points=(left, bottom, left, top, right, top), width=1.0)
            Line(points=(left, bottom, right, bottom), width=1.0)

            if has_data:
                points = []
                for x_value, y_value in zip(self.x_values, self.y_values):
                    x = left + (x_value - x_min) / (x_max - x_min) * plot_width
                    y = bottom + (y_value - y_min) / (y_max - y_min) * plot_height
                    points.extend((x, y))
                Color(0.30, 0.78, 1.0, 1)
                Line(points=points, width=1.5)

            if has_data:
                tick_color = (0.72, 0.77, 0.83, 1)
                axis_color = (0.82, 0.86, 0.9, 1)
                tick_font_size = dp(10)
                for index, text in enumerate(self.x_tick_labels):
                    x = left + index * plot_width / (len(x_ticks) - 1)
                    self._draw_text(
                        text,
                        (x, self.y + 26),
                        tick_font_size,
                        tick_color,
                    )
                for value, text in zip(y_ticks, self.y_tick_labels):
                    y = bottom + (value - y_min) / (y_max - y_min) * plot_height
                    self._draw_text(
                        text,
                        (self.x + 31, y),
                        tick_font_size,
                        tick_color,
                    )
                self._draw_text(
                    self.x_axis_label,
                    (left + plot_width / 2, self.y + 8),
                    dp(11),
                    axis_color,
                )
                self._draw_text(
                    self.y_axis_label,
                    (self.x + 29, top + 13),
                    dp(11),
                    axis_color,
                )


class ImagePanel(BoxLayout):
    """Image display, file-open control and three-click SA100 selection."""

    def __init__(self, on_open, on_point, on_select, **kwargs):
        super().__init__(orientation="vertical", spacing=5, padding=8, **kwargs)
        self.on_open = on_open
        self.on_point = on_point
        self.on_select = on_select
        self.selecting = False
        self.image_shape = None

        header = BoxLayout(size_hint_y=None, height=42, spacing=6)
        header.add_widget(Label(text="Image", font_size="19sp"))
        open_button = Button(text="Ouvrir PNG", size_hint_x=None, width=120)
        open_button.bind(on_release=lambda *_: self.on_open())
        header.add_widget(open_button)
        select_button = Button(text="Sélection SA100", size_hint_x=None, width=145)
        select_button.bind(on_release=lambda *_: self.on_select())
        self.select_button = select_button
        header.add_widget(select_button)
        self.add_widget(header)

        zoom_controls = BoxLayout(size_hint_y=None, height=40, spacing=6)
        zoom_out = Button(text="−", size_hint_x=None, width=52)
        zoom_out.bind(on_release=lambda *_: self.zoom_by(0.75))
        zoom_controls.add_widget(zoom_out)
        zoom_in = Button(text="+", size_hint_x=None, width=52)
        zoom_in.bind(on_release=lambda *_: self.zoom_by(1.5))
        self.zoom_in_button = zoom_in
        zoom_controls.add_widget(zoom_in)
        fit_button = Button(text="Ajuster", size_hint_x=None, width=90)
        fit_button.bind(on_release=lambda *_: self.fit_image())
        zoom_controls.add_widget(fit_button)
        zoom_controls.add_widget(Label(
            text="Pince pour zoomer · glisse pour déplacer",
            font_size="12sp",
            halign="left",
        ))
        self.add_widget(zoom_controls)

        self.status = Label(
            text="Ouvre un PNG, puis sélectionne l’ordre zéro, le spectre et le ciel.",
            size_hint_y=None,
            height=28,
            font_size="12sp",
        )
        self.add_widget(self.status)

        self.preview = ImageViewport(
            on_image_tap=self._on_image_tap,
            size_hint=(1, 1),
        )
        self.image_widget = KivyImage(
            fit_mode="contain",
            size_hint=(None, None),
            opacity=0,
        )
        self.preview.image_widget = self.image_widget
        self.image_widget.bind(
            pos=self.preview._redraw_markers,
            size=self.preview._redraw_markers,
        )
        self.preview.add_widget(self.image_widget)
        self.placeholder = Label(
            text="Image PNG",
            color=(0.72, 0.77, 0.83, 1),
            size_hint=(1, 1),
        )
        self.preview.add_widget(self.placeholder)
        self.preview.bind(
            pos=self._layout_image,
            size=self._layout_image,
        )
        self.add_widget(self.preview)

    def _layout_image(self, *_args):
        self.placeholder.pos = self.preview.pos
        self.placeholder.size = self.preview.size
        if self.image_widget.texture:
            self.preview.layout_image()

    def display_png(self, path, shape):
        texture = CoreImage(str(path)).texture
        self.image_widget.texture = texture
        self.image_widget.opacity = 1
        self.image_shape = shape
        self.placeholder.opacity = 0
        self.selecting = False
        self.preview.selecting = False
        self.preview.clear_markers()
        self.preview.layout_image()
        self.status.text = f"{Path(path).name} — {shape[1]} × {shape[0]} px"

    def fit_image(self):
        self.preview.reset_zoom()

    def zoom_by(self, factor):
        self.preview.zoom_by(factor)

    def begin_selection(self):
        if self.image_shape is None:
            self.status.text = "Charge d’abord une image PNG."
            return
        self.selecting = True
        self.preview.selecting = True
        self.preview.clear_markers()
        self.status.text = "Clique l’ordre zéro (1/3)."

    def finish_selection(self):
        self.selecting = False
        self.preview.selecting = False

    def _on_image_tap(self, point):
        if self.selecting:
            marker_colors = (
                (1, 0.1, 0.1, 1),
                (0.1, 1, 0.2, 1),
                (0.2, 0.45, 1, 1),
            )
            marker_index = len(self.preview.markers)
            if marker_index < len(marker_colors):
                self.preview.add_marker(point, marker_colors[marker_index])
            self.on_point(point)


class SpectrumPanel(BoxLayout):
    """Lower panel containing the extracted 1D spectrum."""

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=4, padding=8, **kwargs)
        header = BoxLayout(size_hint_y=None, height=38, spacing=8)
        header.add_widget(Label(text="Spectre SA100", font_size="19sp"))
        clear_button = Button(text="Effacer", size_hint_x=None, width=90)
        clear_button.bind(on_release=lambda *_: self.clear())
        header.add_widget(clear_button)
        self.add_widget(header)

        self.plot = SpectrumPlot()
        self.add_widget(self.plot)
        self.status = Label(
            text="Sélectionne trois points sur l’image pour extraire le spectre.",
            size_hint_y=None,
            height=26,
            font_size="12sp",
        )
        self.add_widget(self.status)

    def show_result(self, result):
        self.plot.set_data(result.wavelengths, result.flux)
        self.status.text = (
            f"{len(result.flux)} points — "
            f"{result.dispersion_angstrom_per_pixel:.2f} Å/px"
        )

    def clear(self):
        self.plot.clear()
        self.status.text = "Sélectionne trois points sur l’image pour extraire le spectre."


class QuickSpecGUI(App):
    """Main GUI class; owns and coordinates the two processing classes."""

    title = "QuickSpec SA100"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.image_processor = Image()
        self.spectra_processor = Spectra()
        self._selection_points = []
        self.image_panel = None
        self.spectrum_panel = None
        self._location_file = None
        self._last_picker_location = None

    def build(self):
        self._location_file = Path(self.user_data_dir) / "last-image-location.txt"
        self._last_picker_location = self._read_picker_location()
        root = TabbedPanel(
            do_default_tab=False,
            tab_pos="top_left",
            tab_height="48dp",
            padding=0,
        )
        self.image_panel = ImagePanel(
            on_open=self.open_png_picker,
            on_point=self._on_image_point,
            on_select=self._begin_sa100_selection,
        )
        self.spectrum_panel = SpectrumPanel()

        self.image_tab = TabbedPanelItem(text="Image")
        self.image_tab.add_widget(self.image_panel)
        self.spectrum_tab = TabbedPanelItem(text="Spectre")
        self.spectrum_tab.add_widget(self.spectrum_panel)
        root.add_widget(self.image_tab)
        root.add_widget(self.spectrum_tab)
        root.default_tab = self.image_tab
        self.tabs = root
        return root

    def open_png_picker(self):
        if platform == "android":
            self._open_android_picker()
        else:
            self._open_desktop_picker()

    def _open_desktop_picker(self):
        start_path = self._last_picker_location
        if not start_path or not Path(start_path).is_dir():
            pictures = Path.home() / "Pictures"
            start_path = str(pictures if pictures.is_dir() else Path.cwd())
        chooser = FileChooserIconView(
            path=start_path,
            filters=["*.png", "*.PNG"],
            multiselect=False,
        )
        content = BoxLayout(orientation="vertical", spacing=8, padding=8)
        content.add_widget(chooser)
        buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)
        popup = Popup(
            title="Choisir une image PNG",
            content=content,
            size_hint=(0.92, 0.9),
        )
        cancel = Button(text="Annuler")
        open_button = Button(text="Ouvrir")
        cancel.bind(on_release=popup.dismiss)

        def open_selected(_button):
            if chooser.selection:
                self._load_png(chooser.selection[0])
                popup.dismiss()
            else:
                self.image_panel.status.text = "Sélectionne d’abord un fichier PNG."

        open_button.bind(on_release=open_selected)
        buttons.add_widget(cancel)
        buttons.add_widget(open_button)
        content.add_widget(buttons)
        popup.open()

    def _open_android_picker(self):
        try:
            from android import activity
            from jnius import autoclass

            intent_class = autoclass("android.content.Intent")
            python_activity = autoclass("org.kivy.android.PythonActivity")
            intent = intent_class(intent_class.ACTION_OPEN_DOCUMENT)
            intent.setType("image/png")
            intent.addCategory(intent_class.CATEGORY_OPENABLE)
            grant_flags = (
                intent_class.FLAG_GRANT_READ_URI_PERMISSION
                | intent_class.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            )
            intent.setFlags(grant_flags)
            if self._last_picker_location:
                build_version = autoclass("android.os.Build$VERSION")
                if build_version.SDK_INT >= 26:
                    uri_class = autoclass("android.net.Uri")
                    initial_uri = uri_class.parse(self._last_picker_location)
                    intent.putExtra(
                        "android.provider.extra.INITIAL_URI",
                        initial_uri,
                    )
            activity.bind(on_activity_result=self._on_android_activity_result)
            python_activity.mActivity.startActivityForResult(
                intent, ANDROID_PICKER_REQUEST
            )
        except Exception as exc:
            logger.exception("Unable to open Android image picker")
            self.image_panel.status.text = f"Impossible d’ouvrir le sélecteur : {exc}"

    def _on_android_activity_result(self, request_code, result_code, intent):
        if request_code != ANDROID_PICKER_REQUEST or result_code != -1:
            return
        try:
            from jnius import autoclass

            python_activity = autoclass("org.kivy.android.PythonActivity")
            uri = intent.getData()
            picker_location = str(uri)
            try:
                flag = autoclass("android.content.Intent").FLAG_GRANT_READ_URI_PERMISSION
                python_activity.mActivity.getContentResolver().takePersistableUriPermission(
                    uri, flag
                )
            except Exception:
                logger.info("Android document provider did not persist URI permission")
            descriptor = python_activity.mActivity.getContentResolver().openFileDescriptor(
                uri, "r"
            )
            if descriptor is None:
                raise OSError("Android did not provide access to the selected file.")
            file_descriptor = descriptor.detachFd()
            cached_png = Path(self.user_data_dir) / "selected.png"
            with os.fdopen(file_descriptor, "rb") as source:
                with cached_png.open("wb") as target:
                    shutil.copyfileobj(source, target)
            self._load_png(str(cached_png), picker_location=picker_location)
        except Exception as exc:
            logger.exception("Unable to read selected Android image")
            self.image_panel.status.text = f"Impossible de lire ce PNG : {exc}"

    def _load_png(self, path, picker_location=None):
        try:
            data = self.image_processor.load([path])
            self.image_panel.display_png(path, data.shape)
            self.spectrum_panel.clear()
            self._selection_points = []
            if picker_location is None:
                picker_location = str(Path(path).parent)
            self._save_picker_location(picker_location)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.exception("Unable to load PNG image")
            self.image_panel.status.text = f"Chargement impossible : {exc}"

    def _read_picker_location(self):
        try:
            return self._location_file.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None
        except OSError:
            logger.exception("Unable to read the last image location")
            return None

    def _save_picker_location(self, location):
        self._last_picker_location = str(location)
        try:
            self._location_file.write_text(
                self._last_picker_location,
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Unable to save the last image location")

    def _begin_sa100_selection(self):
        self._selection_points = []
        self.image_panel.begin_selection()
        self.spectrum_panel.clear()

    def _on_image_point(self, point):
        self._selection_points.append(point)
        point_names = ("ordre zéro", "point de dispersion", "fond de ciel")
        point_index = len(self._selection_points)
        if point_index < 3:
            self.image_panel.status.text = (
                f"{point_names[point_index - 1]} sélectionné — "
                f"clique {point_names[point_index]} ({point_index + 1}/3)."
            )
            return

        self.image_panel.finish_selection()
        try:
            result = self.spectra_processor.process(
                self.image_processor.data,
                order_zero=self._selection_points[0],
                dispersion_point=self._selection_points[1],
                sky_point=self._selection_points[2],
            )
            self.spectrum_panel.show_result(result)
            self.tabs.switch_to(self.spectrum_tab)
            self.image_panel.status.text = (
                f"Extraction SA100 terminée — angle "
                f"{result.angle_degrees:.2f}°."
            )
        except (ValueError, RuntimeError) as exc:
            logger.exception("SA100 extraction failed")
            self.image_panel.status.text = f"Extraction impossible : {exc}"

    def on_stop(self):
        if platform == "android":
            try:
                from android import activity

                activity.unbind(on_activity_result=self._on_android_activity_result)
            except Exception:
                logger.exception("Unable to unbind Android activity result handler")
