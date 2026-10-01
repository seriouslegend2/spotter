import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUTE_URL = "https://api.heigit.org/openrouteservice/v2/directions/driving-car/geojson"


class RoutingError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def get_driving_route(start, finish):
    api_key = os.environ.get("ORS_API_KEY")
    if not api_key:
        raise RoutingError("ORS_API_KEY is not configured.")

    body = json.dumps({"coordinates": [[start[1], start[0]], [finish[1], finish[0]]]}).encode()
    request = Request(
        ROUTE_URL,
        data=body,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code in (400, 404):
            raise RoutingError("No drivable route was found for these locations.", 422) from exc
        raise RoutingError("The routing service is unavailable.") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise RoutingError("The routing service is unavailable.") from exc

    try:
        feature = payload["features"][0]
        coordinates = feature["geometry"]["coordinates"]
        distance_m = feature["properties"]["summary"]["distance"]
        if len(coordinates) < 2 or distance_m <= 0:
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RoutingError("The routing service returned an invalid route.") from exc
    return coordinates, distance_m / 1609.344
