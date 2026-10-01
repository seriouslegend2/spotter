import json
import math
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path


MAX_RANGE_MILES = 500.0
MPG = 10.0
TANK_GALLONS = MAX_RANGE_MILES / MPG
CORRIDOR_MILES = 20.0
START_STATION_RADIUS_MILES = 5.0
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "stations.json"


class FuelPlanError(Exception):
    pass


@lru_cache(maxsize=1)
def load_stations():
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _distance_miles(lat1, lon1, lat2, lon2):
    mean_lat = math.radians((lat1 + lat2) / 2)
    return math.hypot((lat1 - lat2) * 69.0, (lon1 - lon2) * 69.172 * math.cos(mean_lat))


def _route_samples(coordinates):
    samples = []
    total = 0.0
    previous_lon, previous_lat = coordinates[0]
    samples.append((previous_lat, previous_lon, total))
    last_sample_mile = 0.0
    for lon, lat in coordinates[1:]:
        total += _distance_miles(previous_lat, previous_lon, lat, lon)
        if total - last_sample_mile >= 2.0:
            samples.append((lat, lon, total))
            last_sample_mile = total
        previous_lat, previous_lon = lat, lon
    if samples[-1][2] != total:
        samples.append((previous_lat, previous_lon, total))
    return samples, total


def stations_near_route(coordinates, route_miles, stations=None):
    samples, geometry_miles = _route_samples(coordinates)
    if geometry_miles <= 0:
        raise FuelPlanError("The route has no usable geometry.")

    # A small spatial grid avoids comparing every station with every route point.
    grid = {}
    for lat, lon, mile in samples:
        grid.setdefault((math.floor(lat * 5), math.floor(lon * 5)), []).append((lat, lon, mile))

    candidates = []
    for station in stations if stations is not None else load_stations():
        lat, lon = station["lat"], station["lon"]
        lat_cell, lon_cell = math.floor(lat * 5), math.floor(lon * 5)
        nearest = None
        for y in range(lat_cell - 3, lat_cell + 4):
            for x in range(lon_cell - 4, lon_cell + 5):
                for sample_lat, sample_lon, mile in grid.get((y, x), ()):
                    distance = _distance_miles(lat, lon, sample_lat, sample_lon)
                    if nearest is None or distance < nearest[0]:
                        nearest = (distance, mile)
        if nearest and nearest[0] <= CORRIDOR_MILES:
            candidates.append({**station, "route_mile": nearest[1] * route_miles / geometry_miles})
    return sorted(candidates, key=lambda item: item["route_mile"])


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _stop(station, route_mile, gallons, initial=False):
    price = Decimal(str(station["price_per_gallon_usd"]))
    cost = _money(price * Decimal(str(gallons)))
    return {
        "station_id": station["station_id"],
        "station_name": station["name"],
        "city": station["city"],
        "state": station["state"],
        "location": {"latitude": station["lat"], "longitude": station["lon"]},
        "route_mile": round(route_mile, 1),
        "initial_fill": initial,
        "price_per_gallon_usd": float(price),
        "gallons": gallons,
        "cost_usd": float(cost),
    }


def plan_fuel(candidates, route_miles, start=None, all_stations=None):
    initial_options = [
        station for station in candidates
        if station["route_mile"] <= 20.0
        and (
            start is None
            or _distance_miles(start[0], start[1], station["lat"], station["lon"])
            <= START_STATION_RADIUS_MILES
        )
    ]
    if initial_options:
        initial_station = min(initial_options, key=lambda item: float(item["price_per_gallon_usd"]))
        initial_stop = _stop(initial_station, 0.0, TANK_GALLONS, initial=True)
    elif start is not None:
        catalog = all_stations if all_stations is not None else load_stations()
        initial_station = min(
            catalog,
            key=lambda item: _distance_miles(start[0], start[1], item["lat"], item["lon"]),
            default=None,
        )
        if initial_station is None:
            raise FuelPlanError("No fuel prices are available for the starting tank.")
        initial_stop = _stop(initial_station, 0.0, TANK_GALLONS, initial=True)
        initial_stop.update({
            "station_id": None,
            "station_name": "Starting tank (estimated price)",
            "city": None,
            "state": None,
            "location": {"latitude": start[0], "longitude": start[1]},
            "price_source": {
                "station_id": initial_station["station_id"],
                "city": initial_station["city"],
                "state": initial_station["state"],
                "distance_miles": round(_distance_miles(start[0], start[1], initial_station["lat"], initial_station["lon"]), 1),
            },
        })
    else:
        raise FuelPlanError("No priced fuel station was found near the start.")
    stops = [initial_stop]

    fuel = TANK_GALLONS
    previous_mile = 0.0
    route_stations = [station for station in candidates if 0.1 < station["route_mile"] < route_miles]
    for index, station in enumerate(route_stations):
        mile = station["route_mile"]
        fuel -= (mile - previous_mile) / MPG
        if fuel < -0.0001:
            raise FuelPlanError("No fuel station is reachable within the 500-mile range.")
        previous_mile = mile

        cheaper_mile = next(
            (
                later["route_mile"] for later in route_stations[index + 1:]
                 if later["route_mile"] - mile <= MAX_RANGE_MILES
                 and float(later["price_per_gallon_usd"]) < float(station["price_per_gallon_usd"])),
            None,
        )
        target_distance = cheaper_mile - mile if cheaper_mile is not None else min(MAX_RANGE_MILES, route_miles - mile)
        target_gallons = target_distance / MPG
        buy = max(0.0, target_gallons - max(fuel, 0.0))
        if buy > 0.00005:
            gallons = math.ceil(buy * 10000) / 10000
            gallons = min(gallons, round(TANK_GALLONS - max(fuel, 0.0), 4))
            fuel += gallons
            stops.append(_stop(station, mile, gallons))

    fuel -= (route_miles - previous_mile) / MPG
    if fuel < -0.0001:
        raise FuelPlanError("No fuel station is reachable within the 500-mile range.")

    total_cost = sum(Decimal(str(stop["cost_usd"])) for stop in stops)
    return stops, float(_money(total_cost))
