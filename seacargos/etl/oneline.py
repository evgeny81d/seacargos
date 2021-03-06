# Seacargos - sea cargos aggregator web application.
# Copyright (C) 2022 Evgeny Deriglazov
# https://github.com/evgeny81d/seacargos/blob/main/LICENSE

import requests
import time
from datetime import datetime
from pymongo.errors import ConnectionFailure

URL = "https://ecomm.one-line.com/ecom/CUP_HOM_3301GS.do"

def log(message):
    """Log function to log errors."""
    timestamp = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
    with open("etl.log", "a") as f:
        f.write("\n" + timestamp + " " + message)

# Helper function for main extract_data() function
def container_request_payload(query):
    """Prepare payload for container details request."""
    payload = {
            '_search': 'false', 'nd': str(time.time_ns())[:-6],
            'rows': '10000', 'page': '1', 'sidx': '',
            'sord': 'asc', 'f_cmd': '121', 'search_type': 'A',
            'search_name': None, 'cust_cd': '',
        }
    if "bkgNo" in query:
        payload["search_name"] = query["bkgNo"]
    elif "cntrNo" in query:
        payload["search_name"] = query["cntrNo"]
    return payload

# Helper function for main extract_data() function
def extract_container_data(payload):
    """Extract container details from web site."""
    r = requests.get(URL, params=payload)
    data = r.json()
    # Extract container details data
    if "list" in data:
        container_details = data["list"][0]
        container_details.pop("hashColumns", None)
        return container_details
    else:
        log("[oneline.py] [extract_container_data()]"\
            + f" [No details data for {payload['search_name']}]")
        return False

# Helper function for main extract_data() function
def schedule_request_payload(container_data):
    """Prepare payload for schedule details request."""
    payload = {
            '_search': 'false', 'f_cmd': '125',
            'cntr_no': container_data["cntrNo"],
            'bkg_no': '', 'cop_no': container_data["copNo"]
        }
    return payload

# Helper function for main extract_data() function
def extract_schedule_data(payload):
    """Extract schedule details."""
    r = requests.get(URL, params=payload)
    data = r.json()
    # Extract container schedule data
    if "list" in data:
        schedule_details = data["list"]
        schedule_details[0].pop("hashColumns", None)
        return schedule_details
    else:
        log("[oneline.py] [extract_schedule_data()]"\
            + f" [No schedule data for container {payload['cntr_no']}]")
        return False

# Main extract_data() function
def extract_data(query):
    """Extract container and schedule details. Return one document."""
    container_payload = container_request_payload(query)
    container_data = extract_container_data(container_payload)
    if container_data:
        schedule_payload = schedule_request_payload(container_data)
        schedule_data = extract_schedule_data(schedule_payload)
        if schedule_data:
            return {"container_data": container_data,
                    "schedule_data": schedule_data,
                    "query": query}
        else:
            log("[oneline.py] [extract_data()]"\
                + f" [No schedule data for {query}]")
            return False
    else:
        log("[oneline.py] [extract_data()]"\
            + f" [No container data for {query}]")
        return False

# Main transform_data() function
def transform_data(data):
    """Transform raw data to be ready for database load."""
    if not data:
        log("[oneline.py] [transform_data()]"\
            + f" [No raw data]")
        return False
    
    def to_date_obj(string):
        """Transform string date to datetime object."""
        f_str = "%Y-%m-%d %H:%M"
        return datetime.strptime(string, f_str)
    
    # Check contnainer keys and extract container info
    cntr_keys = ["cntrNo", "cntrTpszNm", "copNo", "blNo"]
    if set(cntr_keys).issubset(set(data["container_data"])):
        # Prepare requested ETA field
        if len(data["query"]["requestedETA"]) > 1:
            data["query"]["requestedETA"] =\
                datetime.strptime(
                data["query"]["requestedETA"], "%Y-%m-%d"
                )
        # Prepare timestamp
        timestamp = datetime.now().replace(microsecond=0)
        result = {
            "cntrNo": data["container_data"]["cntrNo"],
            "cntrType": data["container_data"]["cntrTpszNm"],
            "copNo": data["container_data"]["copNo"],
            "bkgNo": data["container_data"]["bkgNo"],
            "blNo": data["container_data"]["blNo"],
            "user": data["query"]["user"], "line": data["query"]["line"],
            "refId": data["query"]["refId"],
            "requestedETA": data["query"]["requestedETA"],
            "trackStart": timestamp,
            "regularUpdate": timestamp,
            "recordUpdate": timestamp,
            "trackEnd": None, "outboundTerminal": "", "departureDate": "",
            "inboundTerminal": "", "arrivalDate": "", "vesselName": None,
            "location": None, "schedule": None,
        }
    else:
        log("[oneline.py] [transform_data()]"\
            + f" [Keys do not match in container data {data['query']}]")
        return False
    # Check schedule keys and extract schedule data
    schedule_keys = ["no", "statusNm", "placeNm", "yardNm", "eventDt",
                     "actTpCd", "actTpCd", "vslEngNm", "lloydNo"]
    if set(schedule_keys).issubset(set(data["schedule_data"][0])):
        schedule = []
        for i in data["schedule_data"]:
            # Add schedule item point
            schedule.append({
            "no": int(i["no"]), "event": i["statusNm"],
            "placeName": i["placeNm"], "yardName": i["yardNm"],
            "eventDate": to_date_obj(i["eventDt"]), "status": i["actTpCd"],
            "vesselName": i["vslEngNm"], "imo": i["lloydNo"]
            })
            # Find & save outbound/inbound terminals & departure/arrival dates
            if i["statusNm"].find("Departure from Port of Loading") > -1:
                result["outboundTerminal"] = i["placeNm"]\
                + "|" + i["yardNm"]
                result["departureDate"] = to_date_obj(i["eventDt"])
            if i["statusNm"].find("Arrival at Port of Discharging") > -1:
                result["inboundTerminal"] = i["placeNm"]\
                + "|" + i["yardNm"]
                result["arrivalDate"] = to_date_obj(i["eventDt"])
        result["schedule"] = schedule
        result["initSchedule"] = schedule
   
    else:
        log("[oneline.py] [transform_data()]"\
            + f" [Keys do not match in schedule data {data['query']}]")
        return False
    return result

# Main load_data() function
def load_data(data, conn, db):
    """Loads data into shipments and tracking collections."""
    if not data:
        log("[oneline.py] [load_data()] [No data to load]")
        return {"etl_message": "No data to load yet."}
    try:
        conn.admin.command("ping")
        cursor = db.tracking.insert_one(data)
        if cursor.acknowledged == False:
            log("[oneline.py] [load_data()] "\
                + f"[{data['bkgNo']} not loaded to tracking]")
            return {"etl_message": "Write operation failure"}
        else:
            return {"etl_message": "New record successfully added"}
    except ConnectionFailure:
        log("[oneline.py] [transform_data()] "\
            + f"[Connection failure for {data['bkgNo']}]")
        return {"etl_message": "Database connection failure"}
    except BaseException as err:
        log("[oneline.py] [load_data()] "\
            + f"[{err} for {data['bkgNo']}]")
        return {"etl_message": "Unexpected error"}

# Main ETL function
def etl_one(query, conn, db):
    """Main data pipeline flow."""
    raw_data = extract_data(query)
    transformed_data = transform_data(raw_data)
    result = load_data(transformed_data, conn, db)
    return result