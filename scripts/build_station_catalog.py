"""Build the bundled, city-level station catalog from the supplied CSV and GeoNames."""

import csv
import io
import json
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "fuel-prices-for-be-assessment.csv"
DESTINATION = ROOT / "routes" / "data" / "stations.json"
GEONAMES_URL = "https://download.geonames.org/export/zip/US.zip"
US_STATES = set("AL AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


def normalize(value):
    return "".join(char for char in unicodedata.normalize("NFKD", value.casefold()) if char.isalnum())


def city_coordinates():
    with urllib.request.urlopen(GEONAMES_URL, timeout=30) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    coords = defaultdict(list)
    with archive.open("US.txt") as data:
        for line in io.TextIOWrapper(data, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            coords[(normalize(parts[2]), parts[4])].append((float(parts[9]), float(parts[10])))
    return {
        key: (round(sum(point[0] for point in points) / len(points), 5),
              round(sum(point[1] for point in points) / len(points), 5))
        for key, points in coords.items()
    }


def main():
    positions = city_coordinates()
    cheapest_by_city = {}
    unmatched = set()
    with SOURCE.open(newline="", encoding="utf-8-sig") as data:
        for row in csv.DictReader(data):
            if row["State"] not in US_STATES:
                continue
            city = row["City"].strip()
            state = row["State"].strip()
            key = (normalize(city), state)
            if key not in positions:
                unmatched.add((city, state))
                continue
            price = float(row["Retail Price"])
            if price <= 0:
                continue
            old = cheapest_by_city.get(key)
            if old is None or price < old["price_per_gallon_usd"]:
                lat, lon = positions[key]
                cheapest_by_city[key] = {
                    "station_id": row["OPIS Truckstop ID"].strip(),
                    "name": row["Truckstop Name"].strip(),
                    "city": city,
                    "state": state,
                    "lat": lat,
                    "lon": lon,
                    "price_per_gallon_usd": price,
                }
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    stations = sorted(cheapest_by_city.values(), key=lambda item: (item["state"], item["city"]))
    DESTINATION.write_text(json.dumps(stations, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(stations)} US city-level stations to {DESTINATION}")
    print(f"Unmatched city/state pairs: {len(unmatched)}")
    for city, state in sorted(unmatched):
        print(f"  {city}, {state}")


if __name__ == "__main__":
    main()
