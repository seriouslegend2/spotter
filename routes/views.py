import hashlib
import json
import math

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from routes.fuel import FuelPlanError, plan_fuel, stations_near_route
from routes.routing import RoutingError, get_driving_route


def _coordinates(value):
    if not isinstance(value, dict) or set(value) != {"latitude", "longitude"}:
        raise ValueError("start and finish must each contain latitude and longitude.")
    lat, lon = value["latitude"], value["longitude"]
    if isinstance(lat, bool) or isinstance(lon, bool):
        raise ValueError("Coordinates must be numbers.")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError("Coordinates must be numbers.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not (24 <= lat <= 50 and -125 <= lon <= -66):
        raise ValueError("Coordinates must be within the contiguous USA bounds.")
    return round(lat, 5), round(lon, 5)


@csrf_exempt
def route_view(request):
    if request.method != "POST":
        response = JsonResponse({"error": "Use POST for this endpoint."}, status=405)
        response["Allow"] = "POST"
        return response
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict):
            raise ValueError("The request body must be a JSON object.")
        start = _coordinates(body.get("start"))
        finish = _coordinates(body.get("finish"))
        if start == finish:
            raise ValueError("Start and finish must differ.")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "The request body must be valid JSON."}, status=400)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    key = "route:" + hashlib.sha256(repr((start, finish)).encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return JsonResponse(cached)

    try:
        geometry, route_miles = get_driving_route(start, finish)
        candidates = stations_near_route(geometry, route_miles)
        stops, total_cost = plan_fuel(candidates, route_miles, start=start)
    except RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    except FuelPlanError as exc:
        return JsonResponse({"error": str(exc)}, status=422)

    result = {
        "route": {"type": "LineString", "coordinates": geometry},
        "route_miles": round(route_miles, 1),
        "fuel_stops": stops,
        "total_fuel_cost_usd": total_cost,
        "assumptions": {"tank_capacity_gallons": 50, "range_miles": 500, "miles_per_gallon": 10,
                        "station_locations": "Approximate city coordinates from GeoNames"},
    }
    cache.set(key, result, timeout=3600)
    return JsonResponse(result)
