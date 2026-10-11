import os
from io import BytesIO
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image

from src.services.media.posters import MAX_BYTES, PosterError, poster_url, store_poster

GPS_INFO_TAG = 34853
ORIENTATION_TAG = 274


def _encode(size: tuple[int, int], fmt: str, **save_kwargs: object) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


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
