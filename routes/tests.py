import json
from io import BytesIO
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from routes.fuel import FuelPlanError, plan_fuel, stations_near_route
from routes.routing import RoutingError, get_driving_route


def station(mile, price, station_id="1"):
    return {
        "station_id": station_id,
        "name": f"Station {station_id}",
        "city": "Test City",
        "state": "KS",
        "lat": 39.0,
        "lon": -98.0,
        "price_per_gallon_usd": price,
        "route_mile": mile,
    }


class FuelPlanTests(SimpleTestCase):
    def test_short_trip_only_needs_initial_fill(self):
        stops, total = plan_fuel([station(0, 3.0)], 100)
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["gallons"], 50)
        self.assertEqual(total, 150.0)

    def test_multiple_stops_choose_cheaper_fuel_ahead(self):
        candidates = [station(0, 3.0, "start"), station(400, 4.0, "a"),
                      station(600, 2.0, "b"), station(900, 5.0, "c")]
        stops, total = plan_fuel(candidates, 1100)
        self.assertEqual([stop["station_id"] for stop in stops], ["start", "a", "b"])
        self.assertEqual([stop["gallons"] for stop in stops], [50, 10, 50])
        self.assertEqual(total, 290.0)

    def test_unreachable_fuel_gap(self):
        with self.assertRaises(FuelPlanError):
            plan_fuel([station(0, 3.0), station(600, 2.0)], 1000)

    def test_starting_price_uses_explicit_proxy_when_no_nearby_station(self):
        source = {key: value for key, value in station(200, 4.0).items() if key != "route_mile"}
        stops, total = plan_fuel([], 100, start=(39.0, -98.0), all_stations=[source])
        self.assertEqual(stops[0]["station_id"], None)
        self.assertEqual(stops[0]["price_source"]["station_id"], "1")
        self.assertEqual(total, 200.0)

    def test_route_filter_keeps_nearby_station(self):
        geometry = [[-98.0, 39.0], [-97.0, 39.0]]
        catalog = [{key: value for key, value in station(0, 3.0).items() if key != "route_mile"}]
        nearby = stations_near_route(geometry, 60.0, catalog)
        self.assertEqual(len(nearby), 1)
        self.assertAlmostEqual(nearby[0]["route_mile"], 0)


class RouteApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.body = {"start": {"latitude": 39.0, "longitude": -98.0},
                     "finish": {"latitude": 39.0, "longitude": -97.0}}

    @patch("routes.views.stations_near_route")
    @patch("routes.views.get_driving_route")
    def test_success_and_cache(self, route_mock, stations_mock):
        route_mock.return_value = ([[-98.0, 39.0], [-97.0, 39.0]], 60.0)
        stations_mock.return_value = [station(0, 3.0)]
        first = self.client.post("/api/route/", self.body, content_type="application/json")
        second = self.client.post("/api/route/", self.body, content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["total_fuel_cost_usd"], 150.0)
        self.assertEqual(first.json(), second.json())
        route_mock.assert_called_once()

    def test_invalid_coordinates(self):
        self.body["start"]["latitude"] = 90
        response = self.client.post("/api/route/", self.body, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch("routes.views.get_driving_route", side_effect=RoutingError("The routing service is unavailable."))
    def test_routing_failure(self, _route_mock):
        response = self.client.post("/api/route/", self.body, content_type="application/json")
        self.assertEqual(response.status_code, 503)

    @patch("routes.views.stations_near_route", return_value=[station(0, 3.0), station(600, 2.0)])
    @patch("routes.views.get_driving_route", return_value=([[-98.0, 39.0], [-97.0, 39.0]], 1000.0))
    def test_unreachable_route(self, _route_mock, _stations_mock):
        response = self.client.post("/api/route/", self.body, content_type="application/json")
        self.assertEqual(response.status_code, 422)


class RoutingClientTests(SimpleTestCase):
    @patch.dict("os.environ", {"ORS_API_KEY": "test-key"})
    @patch("routes.routing.urlopen")
    def test_one_request_uses_geojson_and_longitude_latitude_order(self, urlopen_mock):
        payload = {"features": [{"geometry": {"coordinates": [[-98.0, 39.0], [-97.0, 39.0]]},
                                 "properties": {"summary": {"distance": 160934.4}}}]}
        urlopen_mock.return_value.__enter__.return_value = BytesIO(json.dumps(payload).encode())
        geometry, miles = get_driving_route((39.0, -98.0), (39.0, -97.0))
        self.assertEqual(geometry[0], [-98.0, 39.0])
        self.assertAlmostEqual(miles, 100.0)
        urlopen_mock.assert_called_once()
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(json.loads(request.data)["coordinates"], [[-98.0, 39.0], [-97.0, 39.0]])
