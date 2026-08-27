#!/usr/bin/env python3
"""Solar position for any location.

    python3 -m lib.solar 39.7392 -104.9903 America/Denver

Everything works in apparent solar time, so noon is always the sun's meridian
crossing. Converting to clock time is a separate, cosmetic step: add the equation
of time and the longitude offset from the time zone meridian, plus an hour when
daylight saving is in force.

Angles are degrees. Azimuth is a true bearing: 0 north, 90 east, 180 south.

The time zone comes from an IANA name rather than from longitude, because
longitude gets it wrong. Austin sits at -97.74, which is west of the -97.5
midpoint between the Central and Mountain meridians, so a longitude rule would
put it an hour off. `zoneinfo` also handles daylight saving for the actual date
instead of assuming the current US rule held in every year.
"""
import datetime
import math
import sys

try:
    from zoneinfo import ZoneInfo
except ImportError:                                    # pragma: no cover
    ZoneInfo = None

DOY = {"Mar 20": 79, "Jun 21": 172, "Sep 22": 265, "Dec 21": 355}
MONTH_DOY = {
    "Jan": 17, "Feb": 47, "Mar": 75, "Apr": 105, "May": 135, "Jun": 162,
    "Jul": 198, "Aug": 228, "Sep": 258, "Oct": 288, "Nov": 318, "Dec": 344,
}
MONTHS = list(MONTH_DOY)


# ------------------------------------------------------------------ astronomy

def declination(doy):
    """Solar declination, Cooper's approximation. Good to about 0.3 degrees."""
    return 23.44 * math.sin(math.radians(360.0 * (284 + doy) / 365.0))


def equation_of_time(doy):
    """Minutes that apparent solar time leads mean solar time."""
    b = math.radians(360.0 * (doy - 81) / 364.0)
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def position(doy, solar_hour, lat):
    """Altitude and true azimuth for a day of year and apparent solar hour."""
    dec = math.radians(declination(doy))
    la = math.radians(lat)
    H = math.radians(15.0 * (solar_hour - 12.0))
    sin_alt = math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(H)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    az = math.degrees(math.atan2(
        math.sin(H),
        math.cos(H) * math.sin(la) - math.tan(dec) * math.cos(la)))
    return alt, (az + 180.0) % 360.0


def day_length(doy, lat):
    """Sunrise and sunset in apparent solar hours."""
    dec = math.radians(declination(doy))
    la = math.radians(lat)
    c = -math.tan(la) * math.tan(dec)
    if c <= -1.0:
        return 0.0, 24.0
    if c >= 1.0:
        return 12.0, 12.0
    h = math.degrees(math.acos(c)) / 15.0
    return 12.0 - h, 12.0 + h


def profile_angle(alt, az, wall_azimuth):
    """Sun altitude projected into the vertical plane normal to a wall.

    This is the angle to compare against obstruction heights when the obstruction
    runs parallel to the wall, as a house wall and a fence line usually do.
    Returns None when the sun is behind the wall.
    """
    d = math.radians(((az - wall_azimuth + 180.0) % 360.0) - 180.0)
    if abs(math.degrees(d)) >= 90.0 or alt <= 0:
        return None
    return math.degrees(math.atan(math.tan(math.radians(alt)) / math.cos(d)))


def fmt_clock(hour):
    hour %= 24.0
    h = int(hour)
    m = int(round((hour - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    suffix = "am" if h < 12 else "pm"
    hh = h % 12 or 12
    return f"{hh}:{m:02d} {suffix}"


def guess_timezone(lon):
    """Crude fallback when no IANA zone is recorded. Says so, loudly."""
    return f"Etc/GMT{-int(round(lon / 15.0)):+d}"


# ------------------------------------------------------------------- the site

class SolarSite:
    """Solar geometry bound to one location.

    lat, lon    degrees, west negative
    tz          IANA name, e.g. 'America/New_York'. Falls back to a longitude
                guess, which is wrong for places like Austin.
    year        the year whose daylight-saving rules apply
    """

    def __init__(self, lat, lon, tz=None, year=None):
        self.lat = float(lat)
        self.lon = float(lon)
        self.tz_name = tz or guess_timezone(lon)
        self.tz_guessed = tz is None
        self.year = year or datetime.date.today().year
        self._cache = {}

    @classmethod
    def from_site(cls, site, year=None):
        a = site.get("address", {})
        return cls(a["lat"], a["lon"], a.get("timezone"), year)

    # -------------------------------------------------------------- offsets
    def _zone(self, doy):
        """Standard UTC offset and daylight-saving hours on this day."""
        if doy in self._cache:
            return self._cache[doy]
        std, dst = -5.0, 0.0
        if ZoneInfo is not None:
            try:
                base = datetime.datetime(self.year, 1, 1, 12) + \
                    datetime.timedelta(days=int(doy) - 1)
                aware = base.replace(tzinfo=ZoneInfo(self.tz_name))
                total = aware.utcoffset().total_seconds() / 3600.0
                dst = aware.dst().total_seconds() / 3600.0
                std = total - dst
            except Exception:
                std, dst = -round(-self.lon / 15.0), 0.0
        self._cache[doy] = (std, dst)
        return std, dst

    def tz_meridian(self, doy):
        return 15.0 * self._zone(doy)[0]

    def clock_offset(self, doy):
        """Hours to add to an apparent solar hour to get local clock time."""
        std, dst = self._zone(doy)
        minutes = (self.lon - 15.0 * std) * 4.0 - equation_of_time(doy)
        return minutes / 60.0 + dst

    # ---------------------------------------------------------------- calls
    def position(self, doy, solar_hour):
        return position(doy, solar_hour, self.lat)

    def day_length(self, doy):
        return day_length(doy, self.lat)

    def solar_to_clock(self, doy, solar_hour):
        return solar_hour + self.clock_offset(doy)

    def clock_to_solar(self, doy, clock_hour):
        return clock_hour - self.clock_offset(doy)

    def solar_noon_clock(self, doy):
        return self.solar_to_clock(doy, 12.0)

    def noon_altitude(self, doy):
        return self.position(doy, 12.0)[0]

    def summary(self):
        rows = []
        for name, doy in DOY.items():
            rise, set_ = self.day_length(doy)
            rows.append({
                "date": name,
                "noon_altitude": round(self.noon_altitude(doy), 1),
                "sunrise_clock": fmt_clock(self.solar_to_clock(doy, rise)),
                "sunset_clock": fmt_clock(self.solar_to_clock(doy, set_)),
                "solar_noon_clock": fmt_clock(self.solar_noon_clock(doy)),
                "day_length_hours": round(set_ - rise, 2),
            })
        return rows


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    tz = sys.argv[3] if len(sys.argv) > 3 else None
    s = SolarSite(lat, lon, tz)
    print(f"{lat:.5f}, {lon:.5f}   {s.tz_name}"
          f"{'  (guessed from longitude, may be an hour off)' if s.tz_guessed else ''}")
    print(f"{'date':9s} {'noon alt':>9s} {'sunrise':>9s} {'sunset':>9s} "
          f"{'solar noon':>11s} {'day':>6s}")
    for r in s.summary():
        print(f"{r['date']:9s} {r['noon_altitude']:8.1f}deg {r['sunrise_clock']:>9s} "
              f"{r['sunset_clock']:>9s} {r['solar_noon_clock']:>11s} "
              f"{r['day_length_hours']:5.1f}h")


if __name__ == "__main__":
    main()
