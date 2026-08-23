"""Dependency-free PNG composition for the Sentinel-2 dNBR pilot."""

from __future__ import annotations

import json
import hashlib
import struct
import zlib
from dataclasses import dataclass
from typing import Any, Mapping


NBR_VIS_MIN = -1.0
NBR_VIS_MAX = 1.0
# Fixed descriptive display range; symmetric so the neutral midpoint is dNBR=0.
DNBR_VIS_MIN = -1.0
DNBR_VIS_MAX = 1.0
VISUALIZATION_PALETTE = ("313695", "74add1", "ffffbf", "f46d43", "a50026")
PANEL_THUMB_DIMENSION = 480
PANEL_WIDTH = 1600
PANEL_HEIGHT = 1120

PANEL_KEYS = ("rgb_pre", "rgb_post", "nbr_pre", "nbr_post", "dnbr", "mask")
PANEL_LABELS = {
    "rgb_pre": "RGB PRE",
    "rgb_post": "RGB POST",
    "nbr_pre": "NBR PRE",
    "nbr_post": "NBR POST",
    "dnbr": "dNBR",
    "mask": "COMMON VALID MASK",
}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_INVALID_PIXEL = (148, 163, 184)
_BORDER = (71, 85, 105)
_TEXT = (15, 23, 42)
_MUTED_TEXT = (51, 65, 85)


@dataclass
class RGBImage:
    width: int
    height: int
    pixels: bytearray

    @classmethod
    def solid(cls, width: int, height: int, color: tuple[int, int, int]) -> "RGBImage":
        return cls(width, height, bytearray(bytes(color) * (width * height)))

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.pixels[offset : offset + 3] = bytes(color)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * 3
        return tuple(self.pixels[offset : offset + 3])  # type: ignore[return-value]

    def paste(self, source: "RGBImage", left: int, top: int) -> None:
        for y in range(source.height):
            target_y = top + y
            if not 0 <= target_y < self.height:
                continue
            source_start = y * source.width * 3
            source_end = source_start + source.width * 3
            target_left = max(left, 0)
            target_right = min(left + source.width, self.width)
            if target_left >= target_right:
                continue
            source_offset = source_start + (target_left - left) * 3
            target_offset = (target_y * self.width + target_left) * 3
            length = (target_right - target_left) * 3
            self.pixels[target_offset : target_offset + length] = source.pixels[
                source_offset : source_offset + length
            ]


@dataclass(frozen=True)
class PNGDetails:
    """Decoded RGB pixels plus auditable source encoding statistics."""

    image: RGBImage
    mode: str
    width: int
    height: int
    raw_channels: int
    raw_array_shape: tuple[int, ...]
    array_shape: tuple[int, int, int]
    dtype: str
    channel_min_max: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    channel_unique_counts: tuple[int, int, int]
    unique_pixel_count: int
    exact_green_fraction: float
    alpha_present: bool
    alpha_min: int | None
    alpha_max: int | None
    alpha_unique_count: int | None
    source_sha256: str
    pixel_sha256: str


class QuicklookValidationError(ValueError):
    """Raised when quicklook source artifacts cannot support a trustworthy panel."""

    def __init__(self, message: str, *, stats: Mapping[str, Any] | None = None) -> None:
        self.stats = dict(stats or {})
        super().__init__(message)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_png(image: RGBImage, metadata: Mapping[str, Any] | None = None) -> bytes:
    """Encode an RGB image as a self-contained PNG with optional text metadata."""

    scanlines = bytearray()
    row_width = image.width * 3
    for row in range(image.height):
        scanlines.append(0)
        start = row * row_width
        scanlines.extend(image.pixels[start : start + row_width])
    chunks = [
        _chunk(b"IHDR", struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0)),
        _chunk(b"IDAT", zlib.compress(bytes(scanlines), level=6)),
    ]
    if metadata:
        safe_metadata = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        chunks.append(_chunk(b"tEXt", b"fuegopa\0" + safe_metadata.encode("latin-1")))
    chunks.append(_chunk(b"IEND", b""))
    return _PNG_SIGNATURE + b"".join(chunks)


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distance_left = abs(estimate - left)
    distance_above = abs(estimate - above)
    distance_upper_left = abs(estimate - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _unfilter_rows(raw: bytes, width: int, height: int, bytes_per_pixel: int) -> list[bytes]:
    row_width = width * bytes_per_pixel
    rows: list[bytes] = []
    previous = bytearray(row_width)
    offset = 0
    for _ in range(height):
        if offset >= len(raw):
            raise ValueError("PNG truncado: falta una fila")
        filter_type = raw[offset]
        offset += 1
        encoded = raw[offset : offset + row_width]
        offset += row_width
        if len(encoded) != row_width:
            raise ValueError("PNG truncado: fila incompleta")
        row = bytearray(encoded)
        for index in range(row_width):
            left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + above) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + _paeth(left, above, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Filtro PNG no soportado: {filter_type}")
        rows.append(bytes(row))
        previous = row
    return rows


def _parse_png(payload: bytes) -> tuple[int, int, int, int, list[bytes], list[tuple[int, int, int]], list[int], bytes | None, int | None, tuple[int, ...]]:
    if not payload.startswith(_PNG_SIGNATURE):
        raise ValueError("El thumbnail no es un PNG")
    offset = len(_PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    palette: list[tuple[int, int, int]] = []
    transparency: list[int] = []
    transparent_gray: int | None = None
    transparent_rgb: tuple[int, int, int] | None = None
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("PNG truncado: encabezado de chunk")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(payload):
            raise ValueError("PNG truncado: payload de chunk")
        chunk_payload = payload[start:end]
        offset = end + 4
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk_payload
            )
        elif kind == b"IDAT":
            compressed.extend(chunk_payload)
        elif kind == b"PLTE":
            palette = [
                tuple(chunk_payload[index : index + 3])  # type: ignore[misc]
                for index in range(0, len(chunk_payload), 3)
            ]
        elif kind == b"tRNS":
            if color_type == 3:
                transparency = list(chunk_payload)
            elif color_type == 0 and len(chunk_payload) >= 2:
                transparent_gray = struct.unpack(">H", chunk_payload[:2])[0] & 0xFF
            elif color_type == 2 and len(chunk_payload) >= 6:
                transparent_rgb = tuple(
                    struct.unpack(">H", chunk_payload[index : index + 2])[0] & 0xFF
                    for index in range(0, 6, 2)
                )  # type: ignore[assignment]
        elif kind == b"IEND":
            break
    if width is None or height is None or bit_depth != 8 or interlace != 0:
        raise ValueError("PNG incompatible: se requiere 8-bit sin interlace")
    if color_type not in {0, 2, 3, 4, 6}:
        raise ValueError(f"Tipo de color PNG no soportado: {color_type}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    rows = _unfilter_rows(zlib.decompress(bytes(compressed)), width, height, channels)
    mode = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}[color_type]
    raw_shape = (height, width, channels) if color_type not in {0, 3} else (height, width)
    return width, height, color_type, channels, rows, palette, transparency, bytes(compressed), transparent_gray, raw_shape


def _blend_over_neutral(color: tuple[int, int, int], alpha: int) -> tuple[int, int, int]:
    if alpha <= 0:
        return _INVALID_PIXEL
    if alpha >= 255:
        return color
    return tuple(
        (component * alpha + background * (255 - alpha) + 127) // 255
        for component, background in zip(color, _INVALID_PIXEL)
    )  # type: ignore[return-value]


def decode_png_details(payload: bytes) -> PNGDetails:
    """Decode PNGs to RGB while retaining source mode and alpha diagnostics.

    Palette and RGBA inputs are explicitly converted to RGB. Alpha is only
    used to composite transparent pixels over the neutral invalid-pixel color;
    it is never exposed as a scientific band.
    """

    source_sha256 = hashlib.sha256(payload).hexdigest()
    parsed = _parse_png(payload)
    width, height, color_type, channels, rows, palette, transparency, _compressed, transparent_gray, raw_shape = parsed
    _transparent_rgb = None
    if color_type == 2:
        # Re-read the tRNS value only when present; the parser keeps the raw
        # chunk semantics separate from the RGB pixel array.
        offset = len(_PNG_SIGNATURE)
        while offset < len(payload):
            length = struct.unpack(">I", payload[offset : offset + 4])[0]
            kind = payload[offset + 4 : offset + 8]
            chunk_payload = payload[offset + 8 : offset + 8 + length]
            offset += 12 + length
            if kind == b"tRNS" and len(chunk_payload) >= 6:
                _transparent_rgb = tuple(
                    struct.unpack(">H", chunk_payload[index : index + 2])[0] & 0xFF
                    for index in range(0, 6, 2)
                )  # type: ignore[assignment]
                break
    mode = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}[color_type]
    has_alpha = color_type in {4, 6} or bool(transparency) or transparent_gray is not None or _transparent_rgb is not None
    alpha_values: list[int] = []
    image = RGBImage.solid(width, height, _INVALID_PIXEL)
    for y, row in enumerate(rows):
        for x in range(width):
            index = x * channels
            alpha = 255
            if color_type == 0:
                value = row[index]
                color = (value, value, value)
                if transparent_gray is not None and value == transparent_gray:
                    alpha = 0
            elif color_type == 2:
                color = tuple(row[index : index + 3])  # type: ignore[assignment]
                if _transparent_rgb is not None and color == _transparent_rgb:
                    alpha = 0
            elif color_type == 3:
                palette_index = row[index]
                if palette_index >= len(palette):
                    raise ValueError("PNG inválido: índice de paleta fuera de rango")
                color = palette[palette_index]
                alpha = transparency[palette_index] if palette_index < len(transparency) else 255
            elif color_type == 4:
                value = row[index]
                color = (value, value, value)
                alpha = row[index + 1]
            else:
                color = tuple(row[index : index + 3])  # type: ignore[assignment]
                alpha = row[index + 3]
            if has_alpha:
                alpha_values.append(alpha)
            image.set_pixel(x, y, _blend_over_neutral(color, alpha))
    pixels = [image.get_pixel(x, y) for y in range(height) for x in range(width)]
    channel_min_max = tuple(
        (min(pixel[channel] for pixel in pixels), max(pixel[channel] for pixel in pixels))
        for channel in range(3)
    )  # type: ignore[assignment]
    channel_unique_counts = tuple(
        len({pixel[channel] for pixel in pixels}) for channel in range(3)
    )  # type: ignore[assignment]
    pixel_bytes = bytes(image.pixels)
    return PNGDetails(
        image=image,
        mode=mode,
        width=width,
        height=height,
        raw_channels=channels,
        raw_array_shape=raw_shape,
        array_shape=(height, width, 3),
        dtype="uint8",
        channel_min_max=channel_min_max,
        channel_unique_counts=channel_unique_counts,
        unique_pixel_count=len(set(pixels)),
        exact_green_fraction=sum(pixel == (0, 255, 0) for pixel in pixels) / len(pixels),
        alpha_present=has_alpha,
        alpha_min=min(alpha_values) if alpha_values else None,
        alpha_max=max(alpha_values) if alpha_values else None,
        alpha_unique_count=len(set(alpha_values)) if alpha_values else None,
        source_sha256=source_sha256,
        pixel_sha256=hashlib.sha256(pixel_bytes).hexdigest(),
    )


def decode_png(payload: bytes) -> RGBImage:
    """Decode an RGB/RGBA/palette/gray PNG as explicit RGB pixels."""

    return decode_png_details(payload).image


def png_details_to_dict(details: PNGDetails, *, filename: str = "") -> dict[str, Any]:
    """Return JSON-safe diagnostics for one source PNG."""

    return {
        "filename": filename,
        "mode": details.mode,
        "width": details.width,
        "height": details.height,
        "array_shape": list(details.array_shape),
        "raw_array_shape": list(details.raw_array_shape),
        "dtype": details.dtype,
        "channel_min_max": [list(pair) for pair in details.channel_min_max],
        "channel_unique_counts": list(details.channel_unique_counts),
        "unique_pixel_count": details.unique_pixel_count,
        "exact_00FF00_percent": details.exact_green_fraction * 100,
        "alpha_present": details.alpha_present,
        "alpha_range": None
        if details.alpha_min is None
        else [details.alpha_min, details.alpha_max],
        "alpha_unique_count": details.alpha_unique_count,
        "source_sha256": details.source_sha256,
        "pixel_sha256": details.pixel_sha256,
    }


def _normalized_pixel_sha256(details: PNGDetails) -> str:
    """Fingerprint a source after common-size nearest-neighbour normalization."""

    normalized = _resize_nearest(details.image, 32, 32)
    return hashlib.sha256(bytes(normalized.pixels)).hexdigest()


def validate_thumbnail_sources(
    thumbnails: Mapping[str, bytes],
    *,
    filenames: Mapping[str, str] | None = None,
) -> tuple[dict[str, PNGDetails], dict[str, dict[str, Any]]]:
    """Validate six semantic source images before any panel is written."""

    missing = [key for key in PANEL_KEYS if key not in thumbnails]
    if missing:
        raise QuicklookValidationError(f"Faltan thumbnails para el panel: {', '.join(missing)}")
    filenames = filenames or {}
    details = {
        key: decode_png_details(thumbnails[key])
        for key in PANEL_KEYS
    }
    stats = {
        key: png_details_to_dict(details[key], filename=filenames.get(key, ""))
        for key in PANEL_KEYS
    }
    normalized_hashes = {key: _normalized_pixel_sha256(value) for key, value in details.items()}
    for key, value in normalized_hashes.items():
        stats[key]["normalized_pixel_sha256"] = value

    def fail(message: str) -> None:
        raise QuicklookValidationError(message, stats=stats)

    for key in ("rgb_pre", "rgb_post"):
        item = details[key]
        if item.unique_pixel_count <= 1 or max(channel_max - channel_min for channel_min, channel_max in item.channel_min_max) <= 1:
            fail(f"{key} es una superficie uniforme o casi uniforme; se conserva su auditoría antes del rechazo")
        if item.exact_green_fraction > 0.95:
            fail(f"{key} contiene más de 95% de píxeles exactamente #00FF00")

    for key in ("nbr_pre", "nbr_post", "dnbr"):
        item = details[key]
        if item.exact_green_fraction > 0.95:
            fail(f"{key} parece un marcador RGB #00FF00, no un raster científico")
        if normalized_hashes[key] in {normalized_hashes["rgb_pre"], normalized_hashes["rgb_post"]}:
            fail(f"{key} comparte el array normalizado de una imagen RGB")

    if len(set(normalized_hashes.values())) == 1:
        fail("Los seis paneles tienen el mismo array normalizado")
    if normalized_hashes["mask"] in {
        normalized_hashes["rgb_pre"],
        normalized_hashes["rgb_post"],
        normalized_hashes["nbr_pre"],
        normalized_hashes["nbr_post"],
        normalized_hashes["dnbr"],
    }:
        fail("La máscara se está reutilizando como otra capa del panel")
    return details, stats


def _resize_nearest(image: RGBImage, width: int, height: int) -> RGBImage:
    resized = RGBImage.solid(width, height, (255, 255, 255))
    for y in range(height):
        source_y = min(image.height - 1, int(y * image.height / height))
        for x in range(width):
            source_x = min(image.width - 1, int(x * image.width / width))
            resized.set_pixel(x, y, image.get_pixel(source_x, source_y))
    return resized


def _fill_rect(image: RGBImage, left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    for y in range(max(0, top), min(image.height, top + height)):
        start = (y * image.width + max(0, left)) * 3
        end = (y * image.width + min(image.width, left + width)) * 3
        if end > start:
            image.pixels[start:end] = bytes(color) * ((end - start) // 3)


def _stroke_rect(image: RGBImage, left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    for x in range(left, left + width):
        image.set_pixel(x, top, color)
        image.set_pixel(x, top + height - 1, color)
    for y in range(top, top + height):
        image.set_pixel(left, y, color)
        image.set_pixel(left + width - 1, y, color)


_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
}


def draw_text(image: RGBImage, text: str, left: int, top: int, *, scale: int = 1, color: tuple[int, int, int] = _TEXT) -> None:
    cursor = left
    for character in text.upper():
        glyph = _FONT.get(character, _FONT["?"])
        if character == " ":
            cursor += 4 * scale
            continue
        for row, pattern in enumerate(glyph):
            for column, bit in enumerate(pattern):
                if bit == "1":
                    _fill_rect(image, cursor + column * scale, top + row * scale, scale, scale, color)
        cursor += 6 * scale


def _hex_color(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _palette_color(position: float) -> tuple[int, int, int]:
    position = min(1.0, max(0.0, position))
    scaled = position * (len(VISUALIZATION_PALETTE) - 1)
    lower = min(len(VISUALIZATION_PALETTE) - 2, int(scaled))
    fraction = scaled - lower
    first = _hex_color(VISUALIZATION_PALETTE[lower])
    second = _hex_color(VISUALIZATION_PALETTE[lower + 1])
    return tuple(round(first[index] + (second[index] - first[index]) * fraction) for index in range(3))  # type: ignore[return-value]


def _draw_colorbar(image: RGBImage, left: int, top: int, height: int, minimum: float, maximum: float, label: str) -> None:
    width = 18
    for y in range(height):
        _fill_rect(image, left, top + y, width, 1, _palette_color(1 - y / max(1, height - 1)))
    _stroke_rect(image, left, top, width, height, _BORDER)
    draw_text(image, label, left - 4, top - 16, scale=1, color=_MUTED_TEXT)
    draw_text(image, f"{maximum:g}", left + width + 5, top - 2, scale=1, color=_MUTED_TEXT)
    draw_text(image, "0", left + width + 5, top + height // 2 - 4, scale=1, color=_MUTED_TEXT)
    draw_text(image, f"{minimum:g}", left + width + 5, top + height - 8, scale=1, color=_MUTED_TEXT)


def compose_panel_png(
    thumbnails: Mapping[str, bytes],
    metadata: Mapping[str, Any],
) -> bytes:
    """Compose six embedded thumbnails into one portable, labeled PNG panel."""

    details, _stats = validate_thumbnail_sources(thumbnails)
    canvas = RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, (248, 250, 252))
    event_id = str(metadata.get("event_id", ""))
    analysis_mode = str(metadata.get("analysis_mode", ""))
    cloud_threshold = str(metadata.get("cloud_threshold", ""))
    overlap = str(metadata.get("valid_overlap_fraction", "n/a"))
    pre_date = str(metadata.get("pre_timestamp_utc", ""))
    post_date = str(metadata.get("post_timestamp_utc", ""))
    draw_text(canvas, event_id, 24, 18, scale=2)
    draw_text(
        canvas,
        f"MODE {analysis_mode}  CS+ {cloud_threshold}  OVERLAP {overlap}  CRS EPSG:32617  SCALE 20M",
        24,
        42,
        color=_MUTED_TEXT,
    )
    draw_text(
        canvas,
        f"PRE {pre_date}  POST {post_date}  AOI B0500  FIRMS/AOI OVERLAY  INVALID PIXELS ARE GRAY/MAGENTA",
        24,
        58,
        color=_MUTED_TEXT,
    )
    tile_width, tile_height = 505, 490
    left_margin, top_margin = 24, 100
    image_width, image_height = 455, 410
    for index, key in enumerate(PANEL_KEYS):
        column, row = index % 3, index // 3
        left = left_margin + column * tile_width
        top = top_margin + row * tile_height
        _fill_rect(canvas, left, top, tile_width - 20, tile_height - 18, (255, 255, 255))
        _stroke_rect(canvas, left, top, tile_width - 20, tile_height - 18, _BORDER)
        draw_text(canvas, PANEL_LABELS[key], left + 12, top + 10, scale=1, color=_TEXT)
        thumbnail = _resize_nearest(details[key].image, image_width, image_height)
        canvas.paste(thumbnail, left + 12, top + 32)
        if key in {"nbr_pre", "nbr_post"}:
            _draw_colorbar(canvas, left + image_width - 2, top + 48, image_height - 22, NBR_VIS_MIN, NBR_VIS_MAX, "NBR")
        elif key == "dnbr":
            _draw_colorbar(canvas, left + image_width - 2, top + 48, image_height - 22, DNBR_VIS_MIN, DNBR_VIS_MAX, "dNBR")
        elif key == "mask":
            _fill_rect(canvas, left + 12, top + image_height + 40, 16, 12, _INVALID_PIXEL)
            draw_text(canvas, "INVALID", left + 34, top + image_height + 40, color=_MUTED_TEXT)
            _fill_rect(canvas, left + 112, top + image_height + 40, 16, 12, (15, 118, 110))
            draw_text(canvas, "VALID", left + 134, top + image_height + 40, color=_MUTED_TEXT)
    return encode_png(canvas, metadata)


def panel_filename(event_id: str, analysis_mode: str, cloud_threshold: float) -> str:
    safe_event = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_id)
    threshold = f"{int(round(cloud_threshold * 100)):03d}"
    return f"{safe_event}_{analysis_mode}_cs{threshold}_panel.png"


def quicklook_path_for_mode(path: str, analysis_mode: str) -> str:
    return path if analysis_mode == "selected_pair" else ""
