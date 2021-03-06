# Seacargos - sea cargos aggregator web application.
# Copyright (C) 2022 Evgeny Deriglazov
# https://github.com/evgeny81d/seacargos/blob/main/LICENSE

import time
import requests
from pymongo.mongo_client import MongoClient
from pymongo import ASCENDING
from seacargos.etl.oneline import container_request_payload
from seacargos.etl.oneline import extract_schedule_data
from seacargos.etl.oneline import extract_container_data
from seacargos.etl.oneline import schedule_request_payload
from seacargos.etl.oneline import extract_data
from seacargos.etl.oneline import transform_data
from seacargos.etl.oneline import load_data
from seacargos.etl.oneline import etl_one

URL = "https://ecomm.one-line.com/ecom/CUP_HOM_3301GS.do"

# Helper functions to run tests
def login(client, user, pwd, follow=True):
    """Simple login function."""
    return client.post(
        "/", data={"username": user, "password": pwd},
        follow_redirects=follow)

def test_container_request_payload():
    """Test container_request_payload() function."""
    # Prepare test data
    check = {
            '_search': 'false', 'nd': str(time.time_ns())[:-6],
            'rows': '10000', 'page': '1', 'sidx': '',
            'sord': 'asc', 'f_cmd': '121', 'search_type': 'A',
            'search_name': None, 'cust_cd': '',
        }

    # Booking number condition
    check["search_name"] = "booking"
    result = container_request_payload({"bkgNo": "booking"})
    assert result == check
    
    # Container number condition
    check["search_name"] = "container"
    result = container_request_payload({"cntrNo": "container"})
    assert result == check
    
    # Empty condition
    check["search_name"] = None
    result = container_request_payload({"empty": ""})
    assert result == check

def test_extract_container_data():
    """Test extract_container_data() function."""
    # Prepare payload with booking number
    payload = {
            '_search': 'false', 'nd': str(time.time_ns())[:-6],
            'rows': '10000', 'page': '1', 'sidx': '',
            'sord': 'asc', 'f_cmd': '121', 'search_type': 'A',
            'search_name': "OSAB76633400", 'cust_cd': '',
        }
    
    # Check condition with booking number
    r = requests.get(URL, params=payload)
    check = r.json().get("list", None)
    if check and isinstance(check, list):
        check[0].pop("hashColumns", None)
    data = extract_container_data(payload)
    assert data == check[0]

    # Check condition with container number
    payload["search_name"] = "KKTU6079875"
    r = requests.get(URL, params=payload)
    check = r.json().get("list", None)
    if check and isinstance(check, list):
        check[0].pop("hashColumns", None)
    data = extract_container_data(payload)
    assert data == check[0]

    # Check condition for wrong number
    payload["search_name"] = "--test--"
    data = extract_container_data(payload)
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [extract_container_data()]"\
        + " [No details data for --test--]" in check[-1]

def test_schedule_request_payload():
    """Test schedule_request_payload() function."""
    # Prepare test data
    check = {
            '_search': 'false', 'f_cmd': '125', 'cntr_no': "KKTU6079875",
            'bkg_no': '', 'cop_no': None
        }
    cntr_data = {"cntrNo": "KKTU6079875", "copNo": None}
    # Run test
    payload = schedule_request_payload(cntr_data)
    assert payload == check

def test_extract_schedule_data():
    """Test extract_schedule_data() function."""
    # Prepare payload
    # Run this if explicit declaration fails
    #query = {"cntrNo": "KKTU6079875"}
    #cntr_payload = container_request_payload(query)
    #cntr_data = extract_container_data(cntr_payload)
    #schedule_payload = schedule_request_payload(cntr_data)
    #assert schedule_payload == 1
    schedule_payload = {
        "_search": "false", "bkg_no": "", "cntr_no": "KKTU6079875",
        "cop_no": "COSA1C20995300", "f_cmd": "125"
        }
    
    # Check condition for container and cop number
    data = extract_schedule_data(schedule_payload)
    r = requests.get(URL, params=schedule_payload)
    check_data = r.json()
    if "list" in check_data:
        check = check_data["list"]
        check[0].pop("hashColumns", None)
    assert data == check

    # Check condition for wrong number (log record)
    schedule_payload["cntr_no"] = "--test--"
    schedule_payload["cop_no"] = None
    data = extract_schedule_data(schedule_payload)
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [extract_schedule_data()]"\
        +" [No schedule data for container --test--]" in check[-1]

def test_extract_data():
    """Test extract_data() function."""
    # If schedule data condition - not covered inside extract_data()
    # Use bkgNo to extract data and check
    data = extract_data({"bkgNo": "OSAB76633400"})
    assert data["query"] == {"bkgNo": "OSAB76633400"}
    assert "container_data" in data
    assert "schedule_data" in data

    # Empty query condition
    data = extract_data({"empty": ""})
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [extract_data()]"\
        +" [No container data for {'empty': ''}]" in check[-1]

def test_transform_data():
    """Test transform_data() function."""
    # Inner function to_date_obj() not covered
    # No data condition
    data = transform_data(False)
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [transform_data()] [No raw data]" in check[-1]

    # Prepare query
    query = {
        "bkgNo": "OSAB76633400", "user": None,
        "line": "ONE", "refId": "1", "requestedETA": "-"
        }

    # Check container info keys
    raw = extract_data(query)
    data = transform_data(raw)
    cntr_info_keys = [
        "cntrNo", "cntrType", "copNo", "bkgNo", "blNo", "user", "refId",
        "trackStart", "regularUpdate", "recordUpdate", "trackEnd",
        "outboundTerminal", "departureDate", "inboundTerminal", "arrivalDate",
        "vesselName", "location", "schedule", "initSchedule", "line",
        "requestedETA"]
    assert set(cntr_info_keys) == set(data)

    # Check schedule keys
    schedule_keys =[
        "no", "event", "placeName", "yardName", "eventDate", "status", 
        "vesselName", "imo"]
    for i in data["schedule"]:
        assert set(schedule_keys) == set(i)
    for i in data["initSchedule"]:
        assert set(schedule_keys) == set(i)

    # Missing container keys condition
    missing_keys = extract_data(query)
    missing_keys["container_data"].pop("cntrNo", None)
    data = transform_data(missing_keys)
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [transform_data()]"\
        + f" [Keys do not match in container data {query}]" in check[-1]

    # Missing schedule keys condition
    missing_keys = extract_data(query)
    missing_keys["schedule_data"][0].pop("statusNm", None)
    data = transform_data(missing_keys)
    assert data == False
    # Verify log record
    with open("etl.log", "r") as f:
        check = f.read().split("\n")
    assert "[oneline.py] [transform_data()]"\
        + f" [Keys do not match in schedule data {query}]" in check[-1]

def test_load_data(app):
    """Test load_data() function."""
    with app.app_context():
        # cursor.acknowledged == False not covered
        # Prepare variables and database
        uri = app.config["DB_FRONTEND_URI"]
        db_name = app.config["DB_NAME"]
        conn = MongoClient(uri)
        db = conn[db_name]
        db.tracking.delete_many({})

        # Test empty data and log recording
        result = load_data(False, conn, db)
        assert result == {"etl_message": "No data to load yet."}
        # Verify log record
        with open("etl.log", "r") as f:
            check = f.read().split("\n")
        assert "[oneline.py] [load_data()] [No data to load]" in check[-1]
        
        # Write record to db
        query = {
            "bkgNo": "OSAB76633400", "user": None,
            "line": "ONE", "refId": "1", "requestedETA": "-"
        }
        raw = extract_data(query)
        data = transform_data(raw)
        assert db.tracking.count_documents({}) == 0
        result = load_data(data, conn, db)
        assert result == {"etl_message": "New record successfully added"}
        assert db.tracking.count_documents({}) == 1
        # Keep record in database for next test ->
        
        # Base Exception condition check
        db.tracking.create_index(
            [("bkgNo", ASCENDING)], name="test", unique=True
        )
        result = load_data(data, conn, db)
        assert result == {"etl_message": "Unexpected error"}
        # Verify log record
        with open("etl.log", "r") as f:
            check = f.read().split("\n")
        assert "[oneline.py] [load_data()]" in check[-1]
        assert "E11000 duplicate key error collection:" in check[-1]
        db.tracking.drop_index("test")
        db.tracking.delete_many({})

        # Connection failure condition check
        #bad_conn = MongoClient(uri.replace("27017", "27016"))
        #result = load_data(data, bad_conn, db)
        #assert result == {"etl_message": "Database connection failure"}
        # Verify log record
        #with open("etl.log", "r") as f:
        #    check = f.read().split("\n")
        #assert "[oneline.py] [load_data()]"\
        #    + f" [Connection failure for {query['bkgNo']}]" in check[-1]
        
        # Clean database and close db connection
        db.tracking.delete_many({})
        del db
        conn.close()

def test_etl_one(app):
    """Test etl_one() function."""
    with app.app_context():
        # Prepare variables and database
        uri = app.config["DB_FRONTEND_URI"]
        db_name = app.config["DB_NAME"]
        conn = MongoClient(uri)
        db = conn[db_name]
        db.tracking.delete_many({})
        query = {
            "bkgNo": "OSAB76633400", "user": None,
            "line": "ONE", "refId": "1", "requestedETA": "-"
        }
        result = etl_one(query, conn, db)
        assert result == {"etl_message": "New record successfully added"}

        # Clean database and close db connection
        db.tracking.delete_many({})
        del db
        conn.close()