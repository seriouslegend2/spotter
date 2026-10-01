# Fuel Route API

A small Django API for the Backend Django Engineer assessment. It returns a driving route, cost-effective fuel stops, and fuel purchased for a 500-mile-range vehicle that gets 10 mpg.

## Run locally

Use Python 3.12 or newer. Create a free [openrouteservice API key](https://account.heigit.org/), copy `.env.example` to `.env`, then paste the key after `ORS_API_KEY=`. Django loads `.env` automatically.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py runserver
```

The station catalog is already bundled. If the CSV changes, rebuild it with `python scripts/build_station_catalog.py`; that command downloads [GeoNames US postal data](https://download.geonames.org/export/zip/) once. Normal API requests do not call GeoNames.

## Request

`POST http://127.0.0.1:8000/api/route/` with JSON:

```json
{
  "start": {"latitude": 39.0997, "longitude": -94.5786},
  "finish": {"latitude": 38.6270, "longitude": -90.1994}
}
```

Use Postman or:

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start":{"latitude":39.0997,"longitude":-94.5786},"finish":{"latitude":38.6270,"longitude":-90.1994}}'
```

The response contains:

```json
{
  "route": {"type": "LineString", "coordinates": [[-94.5786, 39.0997], [-90.1994, 38.627]]},
  "route_miles": 250.0,
  "fuel_stops": [
    {
      "station_id": "example-id",
      "station_name": "Example Station",
      "city": "Kansas City",
      "state": "MO",
      "location": {"latitude": 39.1, "longitude": -94.58},
      "route_mile": 0.0,
      "initial_fill": true,
      "price_per_gallon_usd": 3.0,
      "gallons": 50.0,
      "cost_usd": 150.0
    }
  ],
  "total_fuel_cost_usd": 150.0,
  "assumptions": {
    "tank_capacity_gallons": 50,
    "range_miles": 500,
    "miles_per_gallon": 10,
    "station_locations": "Approximate city coordinates from GeoNames"
  }
}
```

That response is illustrative; real route geometry, prices, and costs come from the routing service and supplied CSV. `route.coordinates` follows GeoJSON's `[longitude, latitude]` order and can be plotted with markers from `fuel_stops`.

## How stops are chosen

The API calls openrouteservice Directions once for a new start/finish pair, then uses the local station catalog. It keeps stations whose **city coordinates** are within 20 miles of the route. For each city it keeps the cheapest supplied station. Starting with a purchased 50-gallon tank near the origin, it buys enough at each later station to reach a cheaper station within range; if none exists, it fills as needed for the remaining journey. A listed station is used for the starting fill only when its city coordinate is within 5 miles of the origin. Otherwise, the starting fill is shown at the origin and its price is estimated from the nearest listed station, identified in `price_source`. It returns HTTP 422 when no reachable chain of later stops exists.

Costs include the full starting tank, even if some fuel remains at the destination. Each stop's cost is rounded to cents, and the total is the sum of those displayed costs. Results are cached in memory for one hour; a cache hit makes no routing request.

The supplied CSV has prices and city/state names but no exact station coordinates. Fuel stop markers and route-mile positions are therefore estimates based on city locations, and detour distance is not included in the cost or 500-mile calculation. The endpoint accepts coordinates within the contiguous US bounding box. A successful request needs a drivable route from openrouteservice, which has a [6,000 km driving request limit](https://openrouteservice.org/restrictions/).

## Tests

```bash
python manage.py test
python manage.py check
```

The tests mock the routing service; they need no API key. A live call requires `ORS_API_KEY`.

## Submission checklist

1. Show a short and a multi-stop request in Postman, plus the route coordinates and fuel costs.
2. Record a Loom walkthrough of the API and code in under five minutes.
3. Share the GitHub repository and Loom link within three days of receiving the exercise.

Station coordinates: [GeoNames](https://www.geonames.org/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Fuel prices: assessment CSV supplied with the exercise.
