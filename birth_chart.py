"""Vedic birth chart — reference admin data, optional jyotishyam, sun/moon fallback."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

ZODIAC_SIGNS_ORDER = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

PLANET_ABBR = {
    "Lagna": "Asc",
    "Sun": "Su",
    "Moon": "Mo",
    "Mars": "Ma",
    "Mercury": "Me",
    "Jupiter": "Ju",
    "Venus": "Ve",
    "Saturn": "Sa",
    "Rahu": "Ra",
    "Ketu": "Ke",
    "Uranus": "Ur",
    "Neptune": "Ne",
    "Pluto": "Pl",
}

DEFAULT_LAT = 28.6139
DEFAULT_LON = 77.2090
DEFAULT_TZ = timezone(timedelta(hours=5, minutes=30))

LIBRARY_INSTALL_MSG = (
    "Full Vedic chart requires `jyotishyam`. Install with: pip install jyotishyam"
)

# Rohit Mudgal (H_U_ADMIN) — DOB 30 Jul 1990, 07:05, Delhi (reference chart)
ADMIN_REFERENCE_ASCENDANT: dict[str, Any] = {
    "sign": "Leo",
    "degree": "02°07'08\"",
    "nakshatra": "Magha",
    "pada": 1,
    "retrograde": False,
}

ADMIN_REFERENCE_PLANETS: list[dict[str, Any]] = [
    {"name": "Sun", "sign": "Cancer", "degree": "12°56'22\"", "nakshatra": "Pushya", "pada": 3, "retrograde": False},
    {"name": "Moon", "sign": "Libra", "degree": "18°18'29\"", "nakshatra": "Swati", "pada": 4, "retrograde": False},
    {"name": "Mars", "sign": "Aries", "degree": "17°41'33\"", "nakshatra": "Bharani", "pada": 2, "retrograde": False},
    {"name": "Mercury", "sign": "Leo", "degree": "07°08'58\"", "nakshatra": "Magha", "pada": 3, "retrograde": False},
    {"name": "Jupiter", "sign": "Cancer", "degree": "02°03'20\"", "nakshatra": "Punarvasu", "pada": 4, "retrograde": True},
    {"name": "Venus", "sign": "Gemini", "degree": "18°14'34\"", "nakshatra": "Ardra", "pada": 4, "retrograde": False},
    {"name": "Saturn", "sign": "Sagittarius", "degree": "27°09'24\"", "nakshatra": "Uttarashada", "pada": 1, "retrograde": True},
    {"name": "Rahu", "sign": "Capricorn", "degree": "13°36'18\"", "nakshatra": "Shravana", "pada": 2, "retrograde": True},
    {"name": "Ketu", "sign": "Cancer", "degree": "13°36'18\"", "nakshatra": "Pushya", "pada": 4, "retrograde": True},
    {"name": "Uranus", "sign": "Sagittarius", "degree": "12°47'15\"", "nakshatra": "Moola", "pada": 4, "retrograde": True},
    {"name": "Neptune", "sign": "Sagittarius", "degree": "18°46'02\"", "nakshatra": "Purvashada", "pada": 2, "retrograde": True},
    {"name": "Pluto", "sign": "Libra", "degree": "21°13'06\"", "nakshatra": "Vishakha", "pada": 1, "retrograde": False},
]

ADMIN_RASI_HOUSES = [
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
]

ADMIN_CHANDRA_HOUSES = [
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
]


def _parse_birth_datetime(dob_iso: str, birth_time: str) -> datetime:
    d = date.fromisoformat(str(dob_iso).strip()[:10])
    raw = (birth_time or "12:00").strip()
    parts = raw.replace(".", ":").split(":")
    hour = int(parts[0]) if parts and parts[0].isdigit() else 12
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return datetime.combine(d, time(hour, minute), tzinfo=DEFAULT_TZ)


def _houses_from_lagna(lagna_sign: str) -> list[str]:
    try:
        start = ZODIAC_SIGNS_ORDER.index(lagna_sign)
    except ValueError:
        start = 0
    return [ZODIAC_SIGNS_ORDER[(start + i) % 12] for i in range(12)]


def _planets_for_house_grid(
    house_signs: list[str], planets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One cell per house (1–12) with sign label and planet abbreviations in that sign."""
    cells: list[dict[str, Any]] = []
    for idx, sign in enumerate(house_signs):
        labels: list[str] = []
        for p in planets:
            if str(p.get("sign") or "") == sign:
                ab = PLANET_ABBR.get(str(p.get("name") or ""), str(p.get("name", ""))[:2])
                if p.get("retrograde"):
                    ab += "℞"
                labels.append(ab)
        cells.append(
            {
                "house": idx + 1,
                "sign": sign,
                "planets": labels,
            }
        )
    return cells


def _build_payload(
    *,
    ascendant: dict[str, Any],
    planets: list[dict[str, Any]],
    rasi_houses: list[str],
    chandra_houses: list[str],
    library_missing: bool = False,
    mock: bool = False,
    message: str | None = None,
    source: str = "reference",
) -> dict[str, Any]:
    table_rows: list[dict[str, Any]] = [
        {
            "name": "Lagna (Asc)",
            "sign": ascendant["sign"],
            "degree": ascendant.get("degree", "—"),
            "nakshatra": ascendant.get("nakshatra", "—"),
            "pada": ascendant.get("pada"),
            "retrograde": bool(ascendant.get("retrograde")),
        }
    ]
    table_rows.extend(planets)

    moon_sign = next((p["sign"] for p in planets if p.get("name") == "Moon"), chandra_houses[0])
    sun_sign = next((p["sign"] for p in planets if p.get("name") == "Sun"), rasi_houses[0])

    return {
        "available": True,
        "library_missing": library_missing,
        "mock": mock,
        "source": source,
        "message": message or "",
        "ascendant": ascendant,
        "planets": planets,
        "rasi_houses": rasi_houses,
        "chandra_houses": chandra_houses,
        "table_rows": table_rows,
        "moon_sign": moon_sign,
        "sun_sign": sun_sign,
        "rasi_grid": _planets_for_house_grid(rasi_houses, planets),
        "chandra_grid": _planets_for_house_grid(chandra_houses, planets),
    }


def admin_reference_chart() -> dict[str, Any]:
    return _build_payload(
        ascendant=dict(ADMIN_REFERENCE_ASCENDANT),
        planets=[dict(p) for p in ADMIN_REFERENCE_PLANETS],
        rasi_houses=list(ADMIN_RASI_HOUSES),
        chandra_houses=list(ADMIN_CHANDRA_HOUSES),
        library_missing=False,
        mock=False,
        source="admin_reference",
    )


def _is_admin_reference_user(
    private_id: str,
    date_of_birth: str,
    birth_time: str,
    *,
    is_admin: bool = False,
) -> bool:
    pid = (private_id or "").strip().upper()
    if pid == "HU-014918240" or pid == "H_U_ADMIN":
        return True
    if is_admin and str(date_of_birth or "").startswith("1990-07-30"):
        bt = (birth_time or "").strip()
        if bt.startswith("07:05") or bt.startswith("7:05"):
            return True
    return False


def _simple_fallback(
    *,
    sun_sign: str,
    moon_sign: str,
    library_missing: bool,
    message: str,
) -> dict[str, Any]:
    asc_sign = sun_sign or "Leo"
    moon = moon_sign or asc_sign
    rasi = _houses_from_lagna(asc_sign)
    chandra = _houses_from_lagna(moon)
    planets = [
        {"name": "Sun", "sign": sun_sign or asc_sign, "degree": "—", "nakshatra": "—", "pada": None, "retrograde": False},
        {"name": "Moon", "sign": moon, "degree": "—", "nakshatra": "—", "pada": None, "retrograde": False},
    ]
    asc = {
        "sign": asc_sign,
        "degree": "— (estimated)",
        "nakshatra": "—",
        "pada": None,
        "retrograde": False,
    }
    return _build_payload(
        ascendant=asc,
        planets=planets,
        rasi_houses=rasi,
        chandra_houses=chandra,
        library_missing=library_missing,
        mock=True,
        message=message,
        source="fallback",
    )


def _planet_from_jyotish_row(name: str, row: Any) -> dict[str, Any] | None:
    """Best-effort mapping from assorted jyotishyam return shapes."""
    if isinstance(row, dict):
        sign = row.get("sign") or row.get("rasi") or row.get("sign_name")
        degree = row.get("degree") or row.get("longitude") or row.get("pos")
        nak = row.get("nakshatra") or row.get("nakshatra_name") or "—"
        pada = row.get("pada") or row.get("nakshatra_pada")
        retro = row.get("retrograde") or row.get("is_retrograde") or False
        if sign:
            return {
                "name": name,
                "sign": str(sign),
                "degree": str(degree or "—"),
                "nakshatra": str(nak),
                "pada": pada,
                "retrograde": bool(retro),
            }
    return None


def _compute_with_jyotishyam(
    *,
    date_of_birth: str,
    birth_time: str,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Try jyotishyam / jyotishyamitra APIs; raise if nothing usable."""
    import importlib

    errors: list[str] = []
    for mod_name in ("jyotishyam", "jyotishyamitra"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            errors.append(f"{mod_name} not installed")
            continue

        dt = _parse_birth_datetime(date_of_birth, birth_time)

        if hasattr(mod, "calculate_birth_chart"):
            raw = mod.calculate_birth_chart(
                dt.year,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute,
                latitude,
                longitude,
            )
        elif hasattr(mod, "get_chart"):
            raw = mod.get_chart(dt, latitude, longitude)
        elif hasattr(mod, "compute_chart"):
            raw = mod.compute_chart(
                date_of_birth,
                birth_time,
                latitude,
                longitude,
            )
        else:
            errors.append(f"{mod_name} has no known chart function")
            continue

        if isinstance(raw, dict):
            asc_raw = raw.get("ascendant") or raw.get("lagna") or raw.get("Ascendant")
            asc_sign = "Leo"
            asc_degree = "—"
            asc_nak = "—"
            asc_pada = None
            if isinstance(asc_raw, dict):
                asc_sign = str(asc_raw.get("sign") or asc_sign)
                asc_degree = str(asc_raw.get("degree") or asc_degree)
                asc_nak = str(asc_raw.get("nakshatra") or asc_nak)
                asc_pada = asc_raw.get("pada")
            elif isinstance(asc_raw, str):
                asc_sign = asc_raw

            ascendant = {
                "sign": asc_sign,
                "degree": asc_degree,
                "nakshatra": asc_nak,
                "pada": asc_pada,
                "retrograde": False,
            }

            planets: list[dict[str, Any]] = []
            plist = raw.get("planets") or raw.get("grahas") or []
            if isinstance(plist, dict):
                for pname, prow in plist.items():
                    p = _planet_from_jyotish_row(str(pname), prow)
                    if p:
                        planets.append(p)
            elif isinstance(plist, list):
                for prow in plist:
                    if isinstance(prow, dict):
                        pname = str(prow.get("name") or prow.get("planet") or "")
                        p = _planet_from_jyotish_row(pname, prow)
                        if p:
                            planets.append(p)

            if not planets:
                raise ValueError(f"{mod_name} returned no planets")

            rasi = _houses_from_lagna(asc_sign)
            moon_sign = next((p["sign"] for p in planets if p["name"] == "Moon"), asc_sign)
            chandra = _houses_from_lagna(moon_sign)
            return _build_payload(
                ascendant=ascendant,
                planets=planets,
                rasi_houses=rasi,
                chandra_houses=chandra,
                library_missing=False,
                mock=False,
                source=mod_name,
            )

    raise ImportError("; ".join(errors) or "jyotishyam not available")


def compute_birth_chart(
    *,
    date_of_birth: str,
    birth_time: str,
    sun_sign: str = "",
    moon_sign: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    private_id: str = "",
    is_admin: bool = False,
) -> dict[str, Any]:
    """Always returns JSON-serializable chart data."""
    lat = float(latitude if latitude is not None else DEFAULT_LAT)
    lon = float(longitude if longitude is not None else DEFAULT_LON)
    sun = str(sun_sign or "").strip()
    moon = str(moon_sign or "").strip()

    if _is_admin_reference_user(private_id, date_of_birth, birth_time, is_admin=is_admin):
        return admin_reference_chart()

    try:
        return _compute_with_jyotishyam(
            date_of_birth=date_of_birth,
            birth_time=birth_time,
            latitude=lat,
            longitude=lon,
        )
    except ImportError:
        return _simple_fallback(
            sun_sign=sun,
            moon_sign=moon,
            library_missing=True,
            message=LIBRARY_INSTALL_MSG,
        )
    except Exception as exc:
        return _simple_fallback(
            sun_sign=sun,
            moon_sign=moon,
            library_missing=True,
            message=f"{LIBRARY_INSTALL_MSG} (calculation failed: {exc})",
        )
