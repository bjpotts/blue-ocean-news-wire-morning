#!/usr/bin/env python3
"""Fetch current local conditions for the run location into data/weather.json.

Location is taken from the machine timezone, not IP geolocation: the sandbox
egress IP resolves to a datacenter (Houston) rather than where the digest is
actually produced, so the timezone is the trustworthy signal.
"""
import json, os, urllib.request, datetime, zoneinfo

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "weather.json")

TZ = os.path.realpath("/etc/localtime").split("zoneinfo/")[-1]

PLACES = {
    "Australia/Sydney": {"name": "Sydney", "region": "NSW", "lat": -33.8688, "lon": 151.2093,
                         "url": "https://www.bom.gov.au/nsw/forecasts/sydney.shtml",
                         "url_label": "Bureau of Meteorology"},
}
place = PLACES.get(TZ)
if place is None:
    raise SystemExit("no place mapping for timezone %r - add one before running" % TZ)

WMO = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers",
    81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorms", 96: "Storms with hail", 99: "Storms with hail",
}
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

api = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
       "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
       "wind_speed_10m,wind_direction_10m,precipitation"
       "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
       "&timezone=%s&forecast_days=1") % (place["lat"], place["lon"], TZ.replace("/", "%2F"))

with urllib.request.urlopen(api, timeout=30) as r:
    d = json.load(r)

cur, day = d["current"], d["daily"]
obs = datetime.datetime.fromisoformat(cur["time"])
now = datetime.datetime.now(zoneinfo.ZoneInfo(TZ))

out = {
    "place": "%s, %s" % (place["name"], place["region"]),
    "timezone": TZ,
    "lat": place["lat"], "lon": place["lon"],
    "source_url": place["url"], "source_label": place["url_label"],
    "obs_url": api,
    "observed": obs.strftime("%-I:%M %p, %a %-d %B %Y"),
    "condition": WMO.get(cur["weather_code"], "Code %s" % cur["weather_code"]),
    "temp": "%.1f&deg;C" % cur["temperature_2m"],
    "feels": "%.1f&deg;C" % cur["apparent_temperature"],
    "humidity": "%d%%" % cur["relative_humidity_2m"],
    "wind": "%d km/h %s" % (round(cur["wind_speed_10m"]),
                            COMPASS[int((cur["wind_direction_10m"] % 360) / 22.5 + 0.5) % 16]),
    "high": "%.1f&deg;C" % day["temperature_2m_max"][0],
    "low": "%.1f&deg;C" % day["temperature_2m_min"][0],
    "rain_chance": "%d%%" % day["precipitation_probability_max"][0],
    "fetched": now.strftime("%-I:%M %p %Z, %-d %B %Y"),
}
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps(out, indent=1))
