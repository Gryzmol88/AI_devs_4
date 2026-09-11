import unicodedata
from math import asin, cos, radians, sin


def normalize_text(value: str) -> str:
    """
    Upraszcza tekst do porownan: male litery, bez diakrytykow i bez spacji skrajnych.
    """
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Liczy odleglosc miedzy dwoma punktami geograficznymi w kilometrach.
    """
    earth_radius_km = 6371.0
    r_lat1 = radians(lat1)
    r_lon1 = radians(lon1)
    r_lat2 = radians(lat2)
    r_lon2 = radians(lon2)
    d_lat = r_lat2 - r_lat1
    d_lon = r_lon2 - r_lon1
    value = sin(d_lat / 2) ** 2 + cos(r_lat1) * cos(r_lat2) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(value**0.5)

