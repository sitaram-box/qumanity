#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


XML_PATH = Path("SITAXML.xml")
DB_PATH = Path("indiaq.db")

# These IDs are derived from XML values, with the "global" root implied.
GLOBAL_ROOT = "IND"


def attr(elem: ET.Element, *names: str) -> str:
    for name in names:
        v = elem.get(name)
        if v is not None:
            return v.strip()
    return ""


def main() -> None:
    if not XML_PATH.is_file():
        raise FileNotFoundError(f"XML file not found: {XML_PATH.resolve()}")

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        cur.executescript(
            """
            CREATE TABLE zone (
                id   TEXT PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE state (
                id   TEXT PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE district (
                id   TEXT PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE tehsil (
                id   TEXT PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE village (
                id   TEXT PRIMARY KEY,
                name TEXT
            );
            """
        )

        zone_count = 0
        state_count = 0
        district_count = 0
        tehsil_count = 0
        village_count = 0

        seen_country_tag = False
        inside_india = False
        current_zone_id = ""
        current_state_code = ""

        context = ET.iterparse(XML_PATH, events=("start", "end"))

        for event, elem in context:
            tag = elem.tag

            if event == "start":
                if tag == "Global_Country":
                    seen_country_tag = True
                    country_name = attr(elem, "name", "Name")
                    inside_india = country_name == "India"
                    continue

                if tag == "Public_Zone" and (inside_india or not seen_country_tag):
                    zone_id = attr(elem, "id", "ID")
                    zone_name = attr(elem, "name", "Name")
                    if zone_id:
                        current_zone_id = zone_id
                        # XML uses 'IND/CS' (global/zone). We want shorter dot-form: 'IND.CS'.
                        zone_id_short = zone_id.replace("/", ".")
                        cur.execute(
                            "INSERT INTO zone (id, name) VALUES (?, ?)",
                            (zone_id_short, zone_name),
                        )
                        zone_count += 1
                    continue

                if tag == "Public_State" and current_zone_id and (inside_india or not seen_country_tag):
                    state_code = attr(elem, "id", "ID")
                    state_name = attr(elem, "name", "Name")
                    if state_code:
                        current_state_code = state_code
                        # XML state ids already include the zone prefix (e.g. 'CS.DL').
                        # Avoid repeating it by using only the global root + '/' + state_code.
                        state_id = f"{GLOBAL_ROOT}/{state_code}"
                        cur.execute("INSERT INTO state (id, name) VALUES (?, ?)", (state_id, state_name))
                        state_count += 1
                    continue

                if tag == "Public_District" and current_state_code and (inside_india or not seen_country_tag):
                    district_code = attr(elem, "id", "ID")
                    district_name = attr(elem, "name", "Name")
                    if district_code:
                        # current_state_code = 'CS.DL'  -> zone_part='CS', state_part='DL'
                        # district_code      = 'CS.DL.1'-> strip leading 'CS.DL.' -> district_local='1'
                        # target id          = 'IND/CS/DL.1'
                        zone_part, state_part = current_state_code.split(".", 1)
                        prefix = current_state_code + "."          # 'CS.DL.'
                        if district_code.startswith(prefix):
                            district_local = district_code[len(prefix):]  # '1'
                        else:
                            district_local = district_code
                        district_id = f"{GLOBAL_ROOT}/{zone_part}/{state_part}.{district_local}"
                        cur.execute(
                            "INSERT INTO district (id, name) VALUES (?, ?)",
                            (district_id, district_name),
                        )
                        district_count += 1
                    continue

                if tag == "Public_Tehsil" and current_state_code and (inside_india or not seen_country_tag):
                    tehsil_code = attr(elem, "id", "ID")  # e.g. CS.DL.1.1
                    tehsil_name = attr(elem, "name", "Name")
                    if tehsil_code:
                        # current_state_code = CS.DL -> zone_part=CS, state_part=DL
                        # tehsil_code      = CS.DL.1.1 -> strip 'CS.DL.' -> local='1.1'
                        zone_part, state_part = current_state_code.split(".", 1)
                        prefix = current_state_code + "."
                        if tehsil_code.startswith(prefix):
                            tehsil_local = tehsil_code[len(prefix):]  # '1.1'
                        else:
                            tehsil_local = tehsil_code

                        tehsil_id = f"{GLOBAL_ROOT}/{zone_part}/{state_part}.{tehsil_local}"
                        cur.execute(
                            "INSERT OR IGNORE INTO tehsil (id, name) VALUES (?, ?)",
                            (tehsil_id, tehsil_name),
                        )
                        if cur.rowcount == 1:
                            tehsil_count += 1
                    continue

                if tag == "Public_Village" and current_state_code and (inside_india or not seen_country_tag):
                    village_code = attr(elem, "id", "ID")  # e.g. CS.DL.1.1.1
                    village_name = attr(elem, "name", "Name")
                    if village_code:
                        # current_state_code = CS.DL -> zone_part=CS, state_part=DL
                        # village_code      = CS.DL.1.1.1 -> strip 'CS.DL.' -> local='1.1.1'
                        zone_part, state_part = current_state_code.split(".", 1)
                        prefix = current_state_code + "."
                        if village_code.startswith(prefix):
                            village_local = village_code[len(prefix):]  # '1.1.1'
                        else:
                            village_local = village_code

                        village_id = f"{GLOBAL_ROOT}/{zone_part}/{state_part}.{village_local}"
                        cur.execute(
                            "INSERT OR IGNORE INTO village (id, name) VALUES (?, ?)",
                            (village_id, village_name),
                        )
                        if cur.rowcount == 1:
                            village_count += 1
                    continue

            else:  # event == "end"
                if tag == "Public_Zone":
                    current_zone_id = ""
                elif tag == "Public_State":
                    current_state_code = ""
                elif tag == "Global_Country" and seen_country_tag:
                    inside_india = False
                elem.clear()

        conn.commit()

        print(f"{zone_count} zones inserted.")
        print(f"{state_count} states inserted.")
        print(f"{district_count} districts inserted.")
        print(f"{tehsil_count} tehsils inserted.")
        print(f"{village_count} villages inserted.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

