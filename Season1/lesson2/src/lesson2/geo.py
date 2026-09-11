from math import asin, cos, radians, sin, sqrt

from .models import Coordinates, PowerPlant

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: Coordinates, b: Coordinates) -> float:
    lat1 = radians(a.lat)
    lon1 = radians(a.lon)
    lat2 = radians(b.lat)
    lon2 = radians(b.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))


def nearest_plant(points: list[Coordinates], plants: list[PowerPlant]) -> tuple[PowerPlant, float]:
    if not points:
        raise ValueError("No person locations provided")
    if not plants:
        raise ValueError("No power plants provided")

    best_plant = plants[0]
    best_distance = float("inf")

    for point in points:
        for plant in plants:
            plant_coord = Coordinates(lat=plant.lat, lon=plant.lon)
            distance = haversine_km(point, plant_coord)
            if distance < best_distance:
                best_distance = distance
                best_plant = plant

    return best_plant, best_distance

