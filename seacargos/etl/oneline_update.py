#!/usr/bin/env python3

import requests
import json
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.json_util import dumps

URL = "https://ecomm.one-line.com/ecom/CUP_HOM_3301GS.do"

def log(message):
    """Log function to log errors."""
    timestamp = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
    with open("etl.log", "a") as f:
        f.write(timestamp + " " + message + "\n")

def records_to_update(conn, db, user=None):
    """Prepare records which require update."""
    # Check function args
    if user:
        query = {"trackEnd": None, "user": user}
        project = {"user": 1, "bkgNo": 1, "copNo": 1, "_id": 0}
    else:  
        now = datetime.now().replace(microsecond=0)
        query = {
            "trackEnd": None,
            "schedule": {"$elemMatch": {"status": "E", "eventDate": {"$lte": now}}}
        }
        project = {"bkgNo": 1, "copNo": 1, "_id": 0}
    # Run query
    try:
        conn.admin.command("ping")
        cur = db.tracking.find(query, project)
        records = json.loads(dumps(cur))
        if len(records) > 0:
            return records
        else:
            # Write log
            return False
    except ConnectionFailure:
        log("[oneline_update.py] [records_to_update()] "\
            + f"[DB Connection failure]")
        return False
    except BaseException as err:
        log("[oneline_update.py] [records_to_update()] "\
            + f"[{err.details}]")
        return False

def extract_schedule_details(records):
    """Extract schedule details for update."""
    # Check input
    if not records:
        return False
    # Extract data
    for rec in records:
        # Create payload
        payload = {
            '_search': 'false', 'f_cmd': '125', 'cntr_no': "",
            'bkg_no': rec["bkgNo"], 'cop_no': rec["copNo"]
        }
        # Run request and fetch json data
        r = requests.get(URL, params=payload)
        data = r.json()
        # Get schedule, clean and add to record
        if "list" in data:
            schedule_details = data["list"]
            if "hashColumns" in schedule_details[0]:
                del schedule_details[0]["hashColumns"]
            rec["schedule"] = schedule_details
        else:
            log("[oneline_update.py] [extract_schedule_details()]"\
                + f" [No schedule for {rec['bkgNo']}]")
            rec["schedule"] = None
    return records

def transform(records):
    """Transforms raw data."""
    # Check input
    if not records:
        return False
    # Check schedule keys and extract schedule data
    schedule_keys = ["no", "statusNm", "placeNm", "yardNm",
                     "eventDt", "actTpCd", "actTpCd", "vslEngNm",
                     "lloydNo"]
    for rec in records:
        if set(schedule_keys).issubset(set(rec["schedule"][0])):
            schedule = [{
                "no": int(i["no"]),
                "event": i["statusNm"],
                "placeName": i["placeNm"],
                "yardName": i["yardNm"],
                "eventDate": datetime.strptime(i["eventDt"], "%Y-%m-%d %H:%M"),
                "status": i["actTpCd"],
                "vesselName": i["vslEngNm"],
                "imo": i["lloydNo"],
            } for i in rec["schedule"]]
            rec["schedule"] = schedule
        else:
            log("[oneline_update.py] [transform()] "\
                + f"[Keys do not match in schedule data {rec['bkgNo']}]")
            rec["schedule"] = None
    return records

def update(conn, db, records):
    """Update records in database."""
    # Check function args
    if not records:
        return False
    try:
        conn.admin.command("ping")
        query = {"bkgNo": None, "trackEnd": None}
        for rec in records:
            if rec["schedule"]:
                query["bkgNo"] = rec["bkgNo"]
                if "user" in rec:
                    query["user"] = rec["user"]
                cur_tracking = db.tracking.update_one(
                    query,
                    {"$set": {"schedule": rec["schedule"]}}
                )
                if cur_tracking.acknowledged == False:
                    log("[oneline_update.py] [update()] "\
                    + f"[{rec['bkgNo']} not updated for {rec.get('user', None)}]")
            else:
                log("[oneline_update.py] [update()] "\
                + f"[Not updated {rec['bkgNo']}]")
    except ConnectionFailure:
        log(f"[oneline_update.py] [update()] [Connection failure]")
    except BaseException as err:
        log(f"[oneline_update.py] [update()] [{err}]")

def arrived(conn, db, user=None):
    """Find containers which arrived to destination."""
    # Check function args
    if user:
        query = {"trackEnd": None, "user": user}
    else:
        query = {"trackEnd": None}
    # Query database
    try:
        conn.admin.command("ping")
        cur = db.tracking.aggregate([
            {"$match": query},
            {"$addFields": {"last": {"$last": "$schedule"}}},
            {"$match": {"last.status": "A" }},
            {"$project": {"bkgNo": 1, "_id": 0}}
        ])
        records = json.loads(dumps(cur))
        if len(records) > 0:
            return records
        else:
            return False
    except ConnectionFailure:
        log("[oneline_update.py] [arrived()] "\
            + f"[DB Connection failure]")
        return False
    except BaseException as err:
        log("[oneline_update.py] [arrived()] "\
            + f"[{err.details}]")
        return False
    
def track_end(conn, db, records):
    """Set trackEnd field in database to current date and time."""
    # Check function args
    if not records:
        return False
    # Run update
    try:
        conn.admin.command("ping")
        query = {"bkgNo": None, "trackEnd": None}
        for rec in records:
            query["bkgNo"] = rec["bkgNo"]
            cur = db.tracking.update_one(
                query,
                {"$set": {"trackEnd": datetime.now().replace(microsecond=0)}},
            )
            if cur.acknowledged == False:
                log("[oneline_update.py] [track_end()] "\
                    + f"[{rec['bkgNo']} not closed for {rec.get('user', None)}]")
    except ConnectionFailure:
        log("[oneline_update.py] [track_end()] "\
            + f"[DB Connection failure]")
        return False
    except BaseException as err:
        log("[oneline_update.py] [track_end()] "\
            + f"[{err.details}]")
        return False

# ETL Pipelines
def regular_update(conn, db):
    """Update records which require update for all users."""
    records = records_to_update(conn, db)
    raw_data = extract_schedule_details(records)
    transformed_data = transform(raw_data)
    update(conn, db, transformed_data)
    arrived_records = arrived(conn, db)
    track_end(conn, db, arrived_records)

def user_update(conn, db, user):
    """Update all records for single user."""
    records = records_to_update(conn, db, user)
    raw_data = extract_schedule_details(records)
    transformed_data = transform(raw_data)
    update(conn, db, transformed_data)
    arrived_records = arrived(conn, db, user)
    track_end(conn, db, arrived_records)

if __name__ == "__main__":
    pass