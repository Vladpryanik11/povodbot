import hashlib
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pillow_heif
from PIL import Image, ImageCms, ImageOps

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000
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
    return store_image(data, media_root, "posters")


def store_image(
    data: bytes, media_root: Path, folder: str, min_size: tuple[int, int] | None = None
) -> StoredPoster:
    """WebP master and 480/1080 variants under MEDIA_ROOT/<folder>/, named by content hash."""
    if len(data) > MAX_BYTES:
        raise PosterError(413, "Фото больше 15 МБ")
    if not _has_image_signature(data):
        raise PosterError(415, NOT_A_PHOTO)
    master = _decode(data, min_size)
    master_bytes = _encode_webp(master)
    name = hashlib.sha256(master_bytes).hexdigest()
    sizes = {width: _fit_width(master.size, width) for width in VARIANT_WIDTHS}
    directory = media_root / folder
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
    return StoredPoster(key=f"{folder}/{name}", width=width, height=height)


def _has_image_signature(data: bytes) -> bool:
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        or (data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS)
    )


def _decode(data: bytes, min_size: tuple[int, int] | None) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise PosterError(422, "Фото слишком большое по пикселям")
            icc_profile = source.info.get("icc_profile")
            image = _to_srgb(ImageOps.exif_transpose(source), icc_profile)
    except PosterError:
        raise
    except Image.DecompressionBombError as exc:
        raise PosterError(422, "Фото слишком большое по пикселям") from exc
    except Exception as exc:
        raise PosterError(415, NOT_A_PHOTO) from exc
    if min_size and (image.width < min_size[0] or image.height < min_size[1]):
        raise PosterError(422, f"Фото маловато — нужно хотя бы {min_size[0]}×{min_size[1]}")
    image.thumbnail(MASTER_BOX, Image.Resampling.LANCZOS)
    return image


def _to_srgb(image: Image.Image, icc_profile: bytes | None) -> Image.Image:
    """An RGB copy in sRGB: transparency goes onto white, a non-sRGB profile is applied.

    A photo without a profile, or with one that cannot be read, is taken as sRGB already.
    """
    if image.has_transparency_data:
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, (255, 255, 255))
        image.paste(rgba, mask=rgba)
    if icc_profile:
        try:
            profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            if "srgb" not in ImageCms.getProfileDescription(profile).lower():
                if image.mode not in ("RGB", "L", "CMYK"):
                    image = image.convert("RGB")
                converted = ImageCms.profileToProfile(
                    image, profile, ImageCms.createProfile("sRGB"), outputMode="RGB"
                )
                if converted is not None:  # None only for in-place conversion
                    return converted
        except (OSError, ImageCms.PyCMSError):
            pass
    return image.convert("RGB")


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
