# Seacargos - sea cargos aggregator web application.
# Copyright (C) 2022 Evgeny Deriglazov
# https://github.com/evgeny81d/seacargos/blob/main/LICENSE

import os
from flask import g, session, get_flashed_messages
from pymongo.mongo_client import MongoClient
from seacargos.db import db_conn
from seacargos.admin import size
from seacargos.admin import users_stats
from seacargos.admin import database_stats
from seacargos.admin import etl_log_stats
from seacargos.admin import active_user_names_from_db
from seacargos.admin import blocked_user_names_from_db

# Helper functions to run tests
def login(client, user, pwd, follow=True):
    """Simple login function."""
    return client.post(
        "/", data={"username": user, "password": pwd},
        follow_redirects=follow)

def logout(client, follow=True):
    """Simple logout function."""
    return client.get("/logout", follow_redirects=follow)

def test_admin_response(client, app):
    """Test admin panel for authenticated and not authenticated users."""
    with app.app_context():
        # Prepare test database (set all users active)
        db = db_conn()[g.db_name]
        db.users.update_many({}, {"$set": {"active": True}})
        
        # Not logged in user
        response = client.get("/admin")
        assert g.user == None
        assert response.status_code == 302
        assert response.headers["Location"] == "http://localhost/"

        # Logged in user
        user = app.config["ADMIN_NAME"]
        pwd = app.config["ADMIN_PASSWORD"]
        response = login(client, user, pwd, False)
        assert response.status_code == 302
        assert response.headers["Location"] == "http://localhost/admin"
        response = login(client, user, pwd)
        assert response.status_code == 200
        logout(client)
        
        # Wrong user role
        user = app.config["USER_NAME"]
        pwd = app.config["USER_PASSWORD"]
        login(client, user, pwd)
        response = client.get("/admin")
        assert response.status_code == 403
        assert b'You are not authorized to view this page.' in response.data
        logout(client)
        
def test_size():
    """Test size() function."""
    assert size(1023) == "1023 bytes"
    assert size(1024) == "1.0 Kb"
    assert size(1048500) == "1023.9 Kb"
    assert size(1048576) == "1.0 Mb"
    assert size(1024**3 - 100000) == "1023.9 Mb"
    assert size(1024**3) == "1.0 Gb"

def test_users_stats(app):
    """Test users() function."""
    with app.app_context():
        db = db_conn()[g.db_name]
        # Prepare database
        db.users.delete_one({"name": "test1"})
        db.users.delete_one({"name": "test2"})
        db.users.delete_one({"name": "test3"})

        # Test initial state
        assert users_stats(db) ==\
            {"admin": 1, "user": 1, "active": 2, "blocked": 0}
        # Test with extra users
        test_data = [
            {"name": "test1", "role": "user", "active": True},
            {"name": "test2", "role": "user", "active": True},
            {"name": "test3", "role": "admin", "active": False}
        ]
        db.users.insert_many(test_data)
        assert users_stats(db) ==\
            {"admin": 2, "user": 3, "active": 4, "blocked": 1}

        # Clean db after tests and check
        db.users.delete_one({"name": "test1"})
        db.users.delete_one({"name": "test2"})
        db.users.delete_one({"name": "test3"})
        assert db.users.count_documents({}) == 2

def test_database_stats(app):
    """Test database_stats() function."""
    with app.app_context():
        db = db_conn()[g.db_name]
        # Check db stats
        stats = database_stats(db)
        db_stats = db.command("dbstats")
        assert stats["storage_size"] == size(db_stats["storageSize"])
        assert stats["objects"] == db_stats["objects"]
        # Check collections stats
        collections = db.list_collection_names()
        check = []
        for coll in collections:
            data = {"name": coll}
            coll_stats = db.command("collstats", coll)
            data["storage_size"] = size(coll_stats["storageSize"])
            data["objects"] = coll_stats["count"]
            check.append(data)
        assert stats["collections"] == check

def test_etl_log_stats():
    """Test etl_log_stats() function."""
    # Check existing file
    stats = etl_log_stats()
    with open("etl.log", "r") as f:
        logs = len(f.readlines())
    logs_size = size(os.path.getsize("etl.log"))
    assert stats["size"] == logs_size
    assert stats["logs"] == logs

    # Delte file and check
    os.remove("etl.log")
    stats = etl_log_stats()
    with open("etl.log", "r") as f:
        logs = len(f.readlines())
    logs_size = size(os.path.getsize("etl.log"))
    assert stats["size"] == logs_size
    assert stats["logs"] == logs

def test_active_user_names_from_db(app):
    """Test active_user_names_from_db() function."""
    with app.app_context():
        db = db_conn()[g.db_name]
        active_users = active_user_names_from_db(db)
        cur = db.users.find({"active": True}, {"_id": 0, "name": 1})
        count = db.users.count_documents({"active": True})
        check = []
        for c in cur:
            check.append(c["name"])
        assert active_users == check
        assert count == len(check)

def test_blocked_user_names_from_db(app):
    """Test blocked_user_names_from_db() function."""
    with app.app_context():
        # Prepare test database data
        db = db_conn()[g.db_name]
        db.users.update_many({}, {"$set": {"active": True}})

        # Check current database condition
        blocked_users = blocked_user_names_from_db(db)
        cur = db.users.find({"active": False}, {"_id": 0, "name": 1})
        count = db.users.count_documents({"active": False})
        check = []
        for c in cur:
            check.append(c["name"])
        assert blocked_users == check
        assert count == len(check)

        # Block all users in database
        db.users.update_many({}, {"$set": {"active": False}})
        blocked_users = blocked_user_names_from_db(db)
        cur = db.users.find({"active": False}, {"_id": 0, "name": 1})
        count = db.users.count_documents({"active": False})
        check = []
        for c in cur:
            check.append(c["name"])
        assert blocked_users == check
        assert count == len(check)       

        # Restore test database data
        db.users.update_many({}, {"$set": {"active": True}})
        del db