from src.lesson2.geo import haversine_km, nearest_plant
from src.lesson2.models import Coordinates, PowerPlant


def test_haversine_zero_distance():
    point = Coordinates(lat=52.0, lon=21.0)
    assert haversine_km(point, point) == 0.0


def test_nearest_plant_selects_closest():
    points = [Coordinates(lat=52.0, lon=21.0)]
    plants = [
        PowerPlant(code="PWR_A", lat=50.0, lon=19.0),
        PowerPlant(code="PWR_B", lat=52.1, lon=21.1),
    ]
    plant, distance = nearest_plant(points, plants)
    assert plant.code == "PWR_B"
    assert distance >= 0

