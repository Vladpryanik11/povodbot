import hashlib
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000
MIN_SIZE = (800, 1000)
MASTER_BOX = (2000, 2000)
VARIANT_WIDTHS = (480, 1080)
WEBP_QUALITY = 82

NOT_A_PHOTO = "Это не фото — подойдут JPEG, PNG, WebP или HEIC"
HEIC_BRANDS = frozenset({b"heic", b"heix", b"heif", b"mif1", b"msf1", b"hevc"})

pillow_heif.register_heif_opener()


class PosterError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class StoredPoster:
    key: str
    width: int
    height: int


def poster_url(key: str) -> str:
    return f"/media/{key}-1080.webp"


def store_poster(data: bytes, media_root: Path) -> StoredPoster:
    if len(data) > MAX_BYTES:
        raise PosterError(413, "Фото больше 15 МБ")
    if not _has_image_signature(data):
        raise PosterError(415, NOT_A_PHOTO)
    master = _decode(data)
    master_bytes = _encode_webp(master)
    name = hashlib.sha256(master_bytes).hexdigest()
    sizes = {width: _fit_width(master.size, width) for width in VARIANT_WIDTHS}
    directory = media_root / "posters"
    master_path = directory / f"{name}-master.webp"
    if not master_path.exists():
        directory.mkdir(parents=True, exist_ok=True)
        for width, size in sizes.items():
            variant = (
                master if size == master.size else master.resize(size, Image.Resampling.LANCZOS)
            )
            _write_atomic(directory / f"{name}-{width}.webp", _encode_webp(variant))
        _write_atomic(master_path, master_bytes)
    width, height = sizes[1080]
    return StoredPoster(key=f"posters/{name}", width=width, height=height)


def _has_image_signature(data: bytes) -> bool:
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        or (data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS)
    )


def _decode(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise PosterError(422, "Фото слишком большое по пикселям")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except PosterError:
        raise
    except Image.DecompressionBombError:
        raise PosterError(422, "Фото слишком большое по пикселям") from None
    except Exception:
        raise PosterError(415, NOT_A_PHOTO) from None
    if image.width < MIN_SIZE[0] or image.height < MIN_SIZE[1]:
        raise PosterError(422, "Фото маловато — нужно хотя бы 800×1000")
    image.thumbnail(MASTER_BOX, Image.Resampling.LANCZOS)
    return image


def _encode_webp(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def _fit_width(size: tuple[int, int], target: int) -> tuple[int, int]:
    width, height = size
    if width <= target:
        return size
    return target, round(height * target / width)


def _write_atomic(path: Path, content: bytes) -> None:
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
