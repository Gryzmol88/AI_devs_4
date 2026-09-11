"""Opcjonalny lokalny OCR dla załączników obrazkowych."""

from __future__ import annotations

from pathlib import Path


class ImageOcrUnavailable(RuntimeError):
    """Wyjątek sygnalizujący brak dostępnego backendu OCR."""


def extract_text_from_image(image_path: Path) -> str:
    """Próbuje odczytać tekst z obrazu lokalnie.

    Args:
        image_path: Ścieżka do pliku obrazu.

    Returns:
        Odczytany tekst OCR (może być pusty).

    Raises:
        ImageOcrUnavailable: Gdy OCR nie jest dostępny lokalnie.
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang="pol+eng")
        return str(text).strip()
    except Exception as error:
        raise ImageOcrUnavailable(
            "Brak lokalnego OCR (zainstaluj pytesseract + pillow + silnik Tesseract)."
        ) from error
