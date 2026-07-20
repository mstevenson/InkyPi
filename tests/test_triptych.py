from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.plugins.triptych.triptych import Triptych, find_images


COLORS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def make_content_folder(tmp_path, colors=COLORS):
    content_folder = tmp_path / "content"
    content_folder.mkdir()

    for index, color in enumerate(colors, start=1):
        folder = content_folder / f"category-{index}"
        folder.mkdir()
        Image.new("RGB", (40, 40), color).save(folder / "image.png")

    return {
        "content_folder": str(content_folder),
        "three_image_chance": "100",
        "image_padding": "0",
    }


def make_device_config(resolution=(10, 6), orientation="horizontal"):
    config = MagicMock()
    config.get_resolution.return_value = resolution
    config.get_config.return_value = orientation
    return config


def make_plugin():
    return Triptych({"id": "triptych"})


def test_three_image_layout_uses_one_source_per_panel(tmp_path):
    image = make_plugin().generate_image(
        make_content_folder(tmp_path),
        make_device_config(),
    )

    assert image.size == (10, 6)
    panel_colors = [
        image.getpixel((0, 2)),
        image.getpixel((4, 2)),
        image.getpixel((9, 2)),
    ]
    assert all(color in COLORS for color in panel_colors)


def test_single_image_layout_fits_within_the_display(tmp_path):
    settings = make_content_folder(tmp_path)
    settings["three_image_chance"] = "0"

    image = make_plugin().generate_image(settings, make_device_config())

    assert image.size == (10, 6)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((5, 3)) in COLORS


def test_single_image_is_contained_with_configurable_padding(tmp_path):
    settings = make_content_folder(tmp_path, colors=COLORS[:1])
    settings.update({
        "three_image_chance": "0",
        "image_padding": "1",
        "background_color": "#ffffff",
    })

    image = make_plugin().generate_image(settings, make_device_config())

    assert image.size == (10, 6)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((2, 2)) == (255, 255, 255)
    assert image.getpixel((3, 2)) == COLORS[0]
    assert image.getpixel((6, 3)) == COLORS[0]
    assert image.getpixel((7, 3)) == (255, 255, 255)


def test_default_image_padding_is_40_pixels():
    assert make_plugin()._get_image_padding({}) == 40


def test_three_image_gutters_match_outer_padding(tmp_path):
    settings = make_content_folder(tmp_path)
    settings["image_padding"] = "40"

    image = make_plugin().generate_image(
        settings,
        make_device_config(resolution=(280, 120)),
    )

    background = (255, 255, 255)
    center_y = 60
    assert all(image.getpixel((x, center_y)) == background for x in range(0, 40))
    assert all(image.getpixel((x, center_y)) != background for x in range(40, 80))
    assert all(image.getpixel((x, center_y)) == background for x in range(80, 120))
    assert all(image.getpixel((x, center_y)) != background for x in range(120, 160))
    assert all(image.getpixel((x, center_y)) == background for x in range(160, 200))
    assert all(image.getpixel((x, center_y)) != background for x in range(200, 240))
    assert all(image.getpixel((x, center_y)) == background for x in range(240, 280))


def test_vertical_orientation_reverses_generation_dimensions(tmp_path):
    image = make_plugin().generate_image(
        make_content_folder(tmp_path),
        make_device_config(resolution=(10, 6), orientation="vertical"),
    )

    assert image.size == (6, 10)


@pytest.mark.parametrize("chance", ["not-a-number", "-1", "101"])
def test_invalid_probability_is_rejected(tmp_path, chance):
    settings = make_content_folder(tmp_path)
    settings["three_image_chance"] = chance

    with pytest.raises(RuntimeError, match="Three-image chance"):
        make_plugin().generate_image(settings, make_device_config())


@pytest.mark.parametrize("padding", ["not-a-number", "1.5", "-1"])
def test_invalid_padding_is_rejected(tmp_path, padding):
    settings = make_content_folder(tmp_path)
    settings["image_padding"] = padding

    with pytest.raises(RuntimeError, match="Image padding"):
        make_plugin().generate_image(settings, make_device_config())


def test_padding_too_large_for_panel_is_rejected(tmp_path):
    settings = make_content_folder(tmp_path)
    settings["image_padding"] = "2"

    with pytest.raises(RuntimeError, match="padding is too large"):
        make_plugin().generate_image(settings, make_device_config())


def test_empty_subfolder_is_ignored(tmp_path):
    settings = make_content_folder(tmp_path)
    empty_folder = tmp_path / "content" / "empty"
    empty_folder.mkdir()

    image = make_plugin().generate_image(settings, make_device_config())

    assert image.size == (10, 6)
    assert image.getpixel((0, 2)) in COLORS
    assert image.getpixel((4, 2)) in COLORS
    assert image.getpixel((9, 2)) in COLORS


def test_content_folder_without_images_is_rejected(tmp_path):
    content_folder = tmp_path / "content"
    content_folder.mkdir()
    (content_folder / "empty").mkdir()
    settings = {
        "content_folder": str(content_folder),
        "three_image_chance": "100",
        "image_padding": "0",
    }

    with pytest.raises(RuntimeError, match="no supported images"):
        make_plugin().generate_image(settings, make_device_config())


def test_fewer_than_three_images_can_still_fill_three_slots(tmp_path):
    settings = make_content_folder(tmp_path, colors=COLORS[:2])

    image = make_plugin().generate_image(settings, make_device_config())

    assert image.size == (10, 6)
    assert image.getpixel((0, 2)) in COLORS[:2]
    assert image.getpixel((4, 2)) in COLORS[:2]
    assert image.getpixel((9, 2)) in COLORS[:2]


def test_three_image_layout_selects_a_folder_for_each_slot(tmp_path, monkeypatch):
    content_folder = tmp_path / "content"
    small_folder = content_folder / "small"
    large_folder = content_folder / "large"
    small_folder.mkdir(parents=True)
    large_folder.mkdir()
    Image.new("RGB", (40, 40), COLORS[0]).save(small_folder / "only.png")
    for index, color in enumerate(COLORS):
        Image.new("RGB", (40, 40), color).save(large_folder / f"{index}.png")

    folder_choices = []

    def choose(items):
        if items and isinstance(items[0], tuple):
            folder_choices.append([name for name, _ in items])
            return items[0]
        return items[0]

    monkeypatch.setattr("src.plugins.triptych.triptych.random.choice", choose)

    settings = {
        "content_folder": str(content_folder),
        "three_image_chance": "100",
        "image_padding": "0",
    }
    image = make_plugin().generate_image(settings, make_device_config())

    assert folder_choices == [["large", "small"]] * 3
    panel_colors = [
        image.getpixel((0, 2)),
        image.getpixel((4, 2)),
        image.getpixel((9, 2)),
    ]
    assert panel_colors[0] in COLORS
    assert panel_colors == [panel_colors[0]] * 3


def test_images_in_content_folder_root_are_available(tmp_path):
    content_folder = tmp_path / "content"
    content_folder.mkdir()
    for index, color in enumerate(COLORS):
        Image.new("RGB", (40, 40), color).save(content_folder / f"{index}.png")

    settings = {
        "content_folder": str(content_folder),
        "three_image_chance": "100",
        "image_padding": "0",
    }
    image = make_plugin().generate_image(settings, make_device_config())

    assert image.size == (10, 6)
    assert all(color in COLORS for color in [
        image.getpixel((0, 2)),
        image.getpixel((4, 2)),
        image.getpixel((9, 2)),
    ])


def test_find_images_skips_hidden_content(tmp_path):
    visible = tmp_path / "visible.jpg"
    Image.new("RGB", (2, 2)).save(visible)
    Image.new("RGB", (2, 2)).save(tmp_path / ".hidden.jpg")
    hidden_folder = tmp_path / ".hidden"
    hidden_folder.mkdir()
    Image.new("RGB", (2, 2)).save(hidden_folder / "nested.jpg")

    assert find_images(tmp_path) == [str(visible)]


def test_find_images_supports_tif_files(tmp_path):
    tif_image = tmp_path / "image.tif"
    Image.new("RGB", (2, 2)).save(tif_image)

    assert find_images(tmp_path) == [str(tif_image)]
