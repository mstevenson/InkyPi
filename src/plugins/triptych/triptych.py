import logging
import os
import random

from PIL import Image, ImageColor, ImageOps

from plugins.base_plugin.base_plugin import BasePlugin


logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (
    ".avif",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".heif",
    ".heic",
)


def find_images(folder_path):
    """Return supported images in a folder and its non-hidden subfolders."""
    images = []

    for root, directories, files in os.walk(folder_path):
        directories[:] = [
            directory for directory in directories if not directory.startswith(".")
        ]

        for filename in files:
            if (
                not filename.startswith(".")
                and filename.lower().endswith(IMAGE_EXTENSIONS)
            ):
                images.append(os.path.join(root, filename))

    return images


class Triptych(BasePlugin):
    """Display images selected from a content folder."""

    def _load_image_folders(self, settings):
        configured_path = settings.get("content_folder", "")
        if not str(configured_path).strip():
            raise RuntimeError("Content folder is required.")

        content_folder = os.path.abspath(
            os.path.expanduser(str(configured_path).strip())
        )
        if not os.path.isdir(content_folder):
            raise RuntimeError(f"Content folder does not exist: {content_folder}")

        image_folders = []

        root_images = [
            entry.path
            for entry in sorted(os.scandir(content_folder), key=lambda item: item.name)
            if entry.is_file()
            and not entry.name.startswith(".")
            and entry.name.lower().endswith(IMAGE_EXTENSIONS)
        ]
        if root_images:
            image_folders.append((os.path.basename(content_folder), root_images))

        for entry in sorted(os.scandir(content_folder), key=lambda item: item.name):
            if entry.name.startswith(".") or not entry.is_dir():
                continue

            image_paths = find_images(entry.path)
            if image_paths:
                image_folders.append((entry.name, image_paths))

        if not image_folders:
            raise RuntimeError("The content folder has no supported images.")

        return image_folders

    @staticmethod
    def _get_dimensions(device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        return dimensions

    @staticmethod
    def _get_three_image_chance(settings):
        try:
            chance = float(settings.get("three_image_chance", 75))
        except (TypeError, ValueError):
            raise RuntimeError(
                "Three-image chance must be a number from 0 to 100."
            )

        if not 0 <= chance <= 100:
            raise RuntimeError(
                "Three-image chance must be between 0 and 100."
            )

        return chance

    @staticmethod
    def _get_image_padding(settings):
        try:
            padding = int(settings.get("image_padding", 40))
        except (TypeError, ValueError):
            raise RuntimeError("Image padding must be a whole number.")

        if padding < 0:
            raise RuntimeError("Image padding cannot be negative.")

        return padding

    @staticmethod
    def _get_background_color(settings):
        configured_color = settings.get("background_color", "#ffffff")
        try:
            return ImageColor.getrgb(configured_color)
        except (TypeError, ValueError):
            raise RuntimeError("Background color is invalid.")

    def _render_image(self, image_path, dimensions, padding, background_color):
        inner_width = dimensions[0] - (padding * 2)
        inner_height = dimensions[1] - (padding * 2)
        if inner_width <= 0 or inner_height <= 0:
            raise RuntimeError(
                "Image padding is too large for the display or panel dimensions."
            )

        # Load without crop-to-fill resizing, then contain the image so its aspect
        # ratio is preserved and no source content is cut off.
        image = self.image_loader.from_file(image_path, dimensions, resize=False)
        if image is None:
            raise RuntimeError(
                f"Failed to load image: {os.path.basename(image_path)}"
            )

        image = ImageOps.contain(
            image,
            (inner_width, inner_height),
            method=Image.Resampling.LANCZOS,
        )
        panel = Image.new("RGB", dimensions, background_color)
        position = (
            padding + ((inner_width - image.width) // 2),
            padding + ((inner_height - image.height) // 2),
        )

        if image.mode in ("RGBA", "LA"):
            panel.paste(image, position, image.getchannel("A"))
        else:
            if image.mode != "RGB":
                image = image.convert("RGB")
            panel.paste(image, position)

        return panel

    def _generate_single_image(
        self, image_folders, dimensions, padding, background_color
    ):
        folder_name, image_paths = random.choice(image_folders)
        selected_path = random.choice(image_paths)
        logger.info("Selected single image from '%s': %s", folder_name, selected_path)
        return self._render_image(
            selected_path, dimensions, padding, background_color
        )

    def _generate_three_images(
        self, image_folders, dimensions, padding, background_color
    ):
        width, height = dimensions
        content_width = width - (padding * 4)
        content_height = height - (padding * 2)
        if content_width < 3 or content_height <= 0:
            raise RuntimeError(
                "Image padding is too large for the display or panel dimensions."
            )

        composite = Image.new("RGB", dimensions, background_color)
        selections = []
        for _ in range(3):
            folder_name, image_paths = random.choice(image_folders)
            selections.append((folder_name, random.choice(image_paths)))
        logger.info("Selected composite images: %s", selections)

        # Allocate the available content width between the panels. Each panel is
        # separated by one full padding-width gutter, matching the outer margins.
        boundaries = [index * content_width // 3 for index in range(4)]

        for index, (_, image_path) in enumerate(selections):
            panel_width = boundaries[index + 1] - boundaries[index]
            left = padding + boundaries[index] + (index * padding)
            panel = self._render_image(
                image_path,
                (panel_width, content_height),
                0,
                background_color,
            )
            composite.paste(panel, (left, padding))

        return composite

    def generate_image(self, settings, device_config):
        logger.info("=== Triptych Plugin: Starting image generation ===")

        image_folders = self._load_image_folders(settings)
        dimensions = self._get_dimensions(device_config)
        three_image_chance = self._get_three_image_chance(settings)
        padding = self._get_image_padding(settings)
        background_color = self._get_background_color(settings)

        show_three_images = random.random() * 100 < three_image_chance

        if show_three_images:
            logger.info(
                "Using three-image layout (configured chance: %.1f%%)",
                three_image_chance,
            )
            return self._generate_three_images(
                image_folders, dimensions, padding, background_color
            )

        logger.info(
            "Using single-image layout (configured chance: %.1f%%)",
            100 - three_image_chance,
        )
        return self._generate_single_image(
            image_folders, dimensions, padding, background_color
        )
