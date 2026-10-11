import os
import struct
from io import BytesIO
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image, ImageCms

from src.services.media.posters import MAX_BYTES, PosterError, poster_url, store_poster

GPS_INFO_TAG = 34853
ORIENTATION_TAG = 274


def _encode(size: tuple[int, int], fmt: str, **save_kwargs: object) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def _wide_gamut_profile() -> bytes:
    """A small matrix/TRC RGB profile with Display P3 primaries (PIL cannot build one itself)."""

    def fixed(value: float) -> bytes:
        return struct.pack(">i", round(value * 65536))

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ \0\0\0\0" + fixed(x) + fixed(y) + fixed(z)

    name = b"Display P3 like\0"
    description = b"desc\0\0\0\0" + struct.pack(">I", len(name)) + name + bytes(4 + 4 + 2 + 1 + 67)
    gamma = b"curv\0\0\0\0" + struct.pack(">IH", 1, round(2.2 * 256))
    tags = {
        b"desc": description,
        b"wtpt": xyz(0.9642, 1.0, 0.8249),
        b"rXYZ": xyz(0.5151, 0.2412, -0.0011),
        b"gXYZ": xyz(0.2920, 0.6922, 0.0419),
        b"bXYZ": xyz(0.1571, 0.0666, 0.7841),
        b"rTRC": gamma,
        b"gTRC": gamma,
        b"bTRC": gamma,
        b"cprt": b"text\0\0\0\0test\0",
    }
    body = bytearray()
    table = bytearray()
    first_tag = 128 + 4 + 12 * len(tags)
    for signature, data in tags.items():
        data += bytes(-len(data) % 4)
        table += signature + struct.pack(">II", first_tag + len(body), len(data))
        body += data
    header = bytearray(128)
    struct.pack_into(">I", header, 8, 0x02400000)
    header[12:24] = b"mntrRGB XYZ "
    header[36:40] = b"acsp"
    header[68:80] = fixed(0.9642) + fixed(1.0) + fixed(0.8249)
    profile = header + struct.pack(">I", len(tags)) + table + body
    struct.pack_into(">I", profile, 0, len(profile))
    return bytes(profile)


def _master_pixel(media_root: Path, key: str, xy: tuple[int, int]) -> tuple[int, ...]:
    with Image.open(media_root / f"{key}-master.webp") as image:
        assert "icc_profile" not in image.info
        assert "exif" not in image.info
        pixel = image.getpixel(xy)
        assert isinstance(pixel, tuple)
        return pixel


def _variants(media_root: Path) -> list[Path]:
    return sorted((media_root / "posters").glob("*.webp"))


def test_stores_three_webp_variants(tmp_path: Path) -> None:
    stored = store_poster(_encode((1200, 1500), "JPEG"), tmp_path)

    assert stored.key.startswith("posters/")
    assert (stored.width, stored.height) == (1080, 1350)
    name = stored.key.removeprefix("posters/")
    assert [path.name for path in _variants(tmp_path)] == sorted(
        f"{name}-{suffix}.webp" for suffix in ("480", "1080", "master")
    )
    with Image.open(tmp_path / f"{stored.key}-1080.webp") as image:
        assert image.format == "WEBP"
        assert image.size == (1080, 1350)
    with Image.open(tmp_path / f"{stored.key}-480.webp") as image:
        assert image.width == 480


def test_converts_wide_gamut_photo_to_srgb(tmp_path: Path) -> None:
    data = _encode((1200, 1500), "JPEG", icc_profile=_wide_gamut_profile())

    stored = store_poster(data, tmp_path)

    red, green, blue = _master_pixel(tmp_path, stored.key, (600, 750))
    # (200, 80, 40) in wide-gamut RGB is a more saturated colour in sRGB.
    assert red > 210
    assert blue < 20
    assert green < 80


def test_photo_without_profile_is_treated_as_srgb(tmp_path: Path) -> None:
    stored = store_poster(_encode((1200, 1500), "JPEG"), tmp_path)

    pixel = _master_pixel(tmp_path, stored.key, (600, 750))
    assert all(abs(got - want) <= 6 for got, want in zip(pixel, (200, 80, 40), strict=True))


def test_srgb_profile_leaves_colours_alone(tmp_path: Path) -> None:
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    stored = store_poster(_encode((1200, 1500), "JPEG", icc_profile=srgb), tmp_path)

    pixel = _master_pixel(tmp_path, stored.key, (600, 750))
    assert all(abs(got - want) <= 6 for got, want in zip(pixel, (200, 80, 40), strict=True))


def test_unreadable_profile_is_ignored(tmp_path: Path) -> None:
    stored = store_poster(_encode((1200, 1500), "JPEG", icc_profile=b"not a profile"), tmp_path)

    pixel = _master_pixel(tmp_path, stored.key, (600, 750))
    assert all(abs(got - want) <= 6 for got, want in zip(pixel, (200, 80, 40), strict=True))


def _transparent_left_half(mode: str) -> bytes:
    size = (1000, 1250)
    buffer = BytesIO()
    if mode == "RGBA":
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        image.paste(Image.new("RGBA", (500, 1250), (200, 80, 40, 255)), (500, 0))
        image.save(buffer, "PNG")
    elif mode == "LA":
        image = Image.new("LA", size, (0, 0))
        image.paste(Image.new("LA", (500, 1250), (90, 255)), (500, 0))
        image.save(buffer, "PNG")
    else:
        image = Image.new("P", size, 0)
        image.putpalette([0, 0, 0, 200, 80, 40])
        image.paste(1, (500, 0, 1000, 1250))
        image.save(buffer, "PNG", transparency=0)
    return buffer.getvalue()


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_transparency_is_flattened_onto_white(tmp_path: Path, mode: str) -> None:
    stored = store_poster(_transparent_left_half(mode), tmp_path)

    assert min(_master_pixel(tmp_path, stored.key, (100, 600))) >= 250
    assert max(_master_pixel(tmp_path, stored.key, (900, 600))) < 230


def test_decode_failure_keeps_its_cause(tmp_path: Path) -> None:
    with pytest.raises(PosterError) as error:
        store_poster(_encode((1200, 1500), "JPEG")[:200], tmp_path)

    assert error.value.__cause__ is not None


def test_poster_url() -> None:
    assert poster_url("posters/abc") == "/media/posters/abc-1080.webp"


def test_strips_exif_gps(tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[GPS_INFO_TAG] = {1: "N", 2: (55.0, 45.0, 0.0)}
    exif[0x010F] = "Camera Maker"
    stored = store_poster(_encode((1200, 1500), "JPEG", exif=exif), tmp_path)

    for suffix in ("480", "1080", "master"):
        with Image.open(tmp_path / f"{stored.key}-{suffix}.webp") as image:
            assert len(image.getexif()) == 0
            assert "exif" not in image.info


def test_applies_orientation(tmp_path: Path) -> None:
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = 6
    stored = store_poster(_encode((1500, 1200), "JPEG", exif=exif), tmp_path)

    with Image.open(tmp_path / f"{stored.key}-master.webp") as image:
        assert image.height > image.width
        assert image.size == (1200, 1500)


def test_heic_accepted(tmp_path: Path) -> None:
    pillow_heif.register_heif_opener()
    stored = store_poster(_encode((1000, 1250), "HEIF"), tmp_path)

    assert stored.width == 1000
    assert (tmp_path / f"{stored.key}-1080.webp").exists()


def test_rejects_small(tmp_path: Path) -> None:
    with pytest.raises(PosterError) as error:
        store_poster(_encode((700, 900), "JPEG"), tmp_path)

    assert error.value.status == 422
    assert error.value.message == "Фото маловато — нужно хотя бы 800×1000"
    assert _variants(tmp_path) == []


def test_rejects_non_image(tmp_path: Path) -> None:
    with pytest.raises(PosterError) as pdf:
        store_poster(b"%PDF-1.7 not a photo", tmp_path)
    assert pdf.value.status == 415
    assert pdf.value.message == "Это не фото — подойдут JPEG, PNG, WebP или HEIC"

    with pytest.raises(PosterError) as truncated:
        store_poster(_encode((1200, 1500), "JPEG")[:200], tmp_path)
    assert truncated.value.status == 415


def test_rejects_pixel_bomb(tmp_path: Path) -> None:
    with pytest.raises(PosterError) as error:
        store_poster(_encode((8000, 6000), "PNG"), tmp_path)

    assert error.value.status == 422
    assert error.value.message == "Фото слишком большое по пикселям"


def test_rejects_oversize_bytes(tmp_path: Path) -> None:
    with pytest.raises(PosterError) as error:
        store_poster(b"\xff\xd8\xff" + bytes(MAX_BYTES), tmp_path)

    assert error.value.status == 413
    assert error.value.message == "Фото больше 15 МБ"


def test_same_photo_same_key(tmp_path: Path) -> None:
    data = _encode((1200, 1500), "JPEG")

    first = store_poster(data, tmp_path)
    second = store_poster(data, tmp_path)

    assert first == second
    assert len(_variants(tmp_path)) == 3
    assert [path.name for path in (tmp_path / "posters").iterdir() if path.suffix != ".webp"] == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_stored_files_readable_by_file_server(tmp_path: Path) -> None:
    store_poster(_encode((1200, 1500), "JPEG"), tmp_path)

    for path in _variants(tmp_path):
        assert path.stat().st_mode & 0o044 == 0o044
