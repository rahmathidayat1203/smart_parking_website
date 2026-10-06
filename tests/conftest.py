"""
Pytest configuration and shared fixtures for Smart Parking Monitoring System.
Includes a flexible in-memory MockSupabaseClient that simulates Supabase PostgREST queries.
"""

import copy
from datetime import datetime, timezone, timedelta
import pytest


class MockAPIResponse:
    """Simulates PostgrestAPIResponse returned by Supabase client execute()."""
    def __init__(self, data):
        self.data = data


class MockQueryBuilder:
    """Simulates Supabase table query builder with method chaining."""

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self._action = "select"  # select, insert, update, delete, upsert
        self._columns = "*"
        self._filters = []  # list of (column, op, value)
        self._order_by = None
        self._desc = False
        self._limit_count = None
        self._is_single = False
        self._payload = None

    def select(self, columns="*"):
        self._action = "select"
        self._columns = columns
        return self

    def insert(self, data):
        self._action = "insert"
        self._payload = data
        return self

    def update(self, data):
        self._action = "update"
        self._payload = data
        return self

    def delete(self):
        self._action = "delete"
        return self

    def upsert(self, data, on_conflict=None):
        self._action = "upsert"
        self._payload = data
        self._on_conflict = on_conflict
        return self

    def eq(self, column, value):
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column, value):
        self._filters.append((column, "neq", value))
        return self

    def order(self, column, desc=False):
        self._order_by = column
        self._desc = desc
        return self

    def limit(self, count):
        self._limit_count = count
        return self

    def single(self):
        self._is_single = True
        return self

    def _matches_filters(self, row):
        for col, op, val in self._filters:
            row_val = row.get(col)
            if op == "eq":
                if row_val != val:
                    return False
            elif op == "neq":
                if row_val == val:
                    return False
        return True

    def execute(self):
        table = self.client.get_table(self.table_name)

        if self._action == "select":
            matched = [copy.deepcopy(row) for row in table if self._matches_filters(row)]
            if self._order_by:
                matched.sort(
                    key=lambda r: (r.get(self._order_by) is not None, r.get(self._order_by)),
                    reverse=self._desc
                )
            if self._limit_count is not None:
                matched = matched[:self._limit_count]
            if self._is_single:
                result = matched[0] if matched else None
                return MockAPIResponse(result)
            return MockAPIResponse(matched)

        elif self._action == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for item in items:
                row = copy.deepcopy(item)
                if "id" not in row:
                    row["id"] = self.client.next_id(self.table_name)
                if "created_at" not in row and self.table_name in ["parking_members", "rfid_scans", "sensor_data", "audit_forensic_logs"]:
                    row["created_at"] = datetime.now(timezone.utc).isoformat()
                if "updated_at" not in row and self.table_name == "parking_slots":
                    row["updated_at"] = datetime.now(timezone.utc).isoformat()
                table.append(row)
                inserted.append(row)
            return MockAPIResponse(inserted)

        elif self._action == "update":
            updated = []
            for row in table:
                if self._matches_filters(row):
                    row.update(self._payload)
                    if "updated_at" not in self._payload and self.table_name == "parking_slots":
                        row["updated_at"] = datetime.now(timezone.utc).isoformat()
                    updated.append(copy.deepcopy(row))
            return MockAPIResponse(updated)

        elif self._action == "delete":
            deleted = []
            remaining = []
            for row in table:
                if self._matches_filters(row):
                    deleted.append(copy.deepcopy(row))
                else:
                    remaining.append(row)
            self.client.set_table(self.table_name, remaining)
            return MockAPIResponse(deleted)

        elif self._action == "upsert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            results = []
            for item in items:
                pk_val = item.get("slot_code") or item.get("device_id") or item.get("rfid_uid") or item.get("id")
                pk_field = (
                    "slot_code" if "slot_code" in item else
                    "device_id" if "device_id" in item else
                    "rfid_uid" if "rfid_uid" in item else "id"
                )
                existing = next((r for r in table if r.get(pk_field) == pk_val), None)
                if existing:
                    existing.update(item)
                    results.append(copy.deepcopy(existing))
                else:
                    row = copy.deepcopy(item)
                    if "id" not in row:
                        row["id"] = self.client.next_id(self.table_name)
                    table.append(row)
                    results.append(copy.deepcopy(row))
            return MockAPIResponse(results)

        return MockAPIResponse([])


class MockSupabaseClient:
    """In-memory Supabase client simulation for unit tests."""

    def __init__(self):
        self._id_counters = {}
        now = datetime.now(timezone.utc)
        self.tables = {
            "parking_members": [
                {
                    "id": 1,
                    "rfid_uid": "A3F21C12",
                    "member_name": "Rahmat Hidayat",
                    "license_plate": "BG 1234 RH",
                    "vehicle_type": "car",
                    "status": "active",
                    "inside_parking": False,
                    "created_at": (now - timedelta(days=2)).isoformat(),
                },
                {
                    "id": 2,
                    "rfid_uid": "B4E22D33",
                    "member_name": "Budi Santoso",
                    "license_plate": "B 5678 CD",
                    "vehicle_type": "car",
                    "status": "active",
                    "inside_parking": False,
                    "created_at": (now - timedelta(days=1)).isoformat(),
                },
                {
                    "id": 3,
                    "rfid_uid": "C5F33E44",
                    "member_name": "Siti Aminah",
                    "license_plate": "D 9012 EF",
                    "vehicle_type": "motorcycle",
                    "status": "inactive",
                    "inside_parking": False,
                    "created_at": (now - timedelta(hours=12)).isoformat(),
                },
            ],
            "parking_slots": [
                {
                    "id": 1,
                    "slot_code": "P01",
                    "status": "available",
                    "sensor_value": 450,
                    "device_id": "PARKING-01",
                    "updated_at": now.isoformat(),
                },
                {
                    "id": 2,
                    "slot_code": "P02",
                    "status": "occupied",
                    "sensor_value": 2150,
                    "device_id": "PARKING-01",
                    "updated_at": now.isoformat(),
                },
                {
                    "id": 3,
                    "slot_code": "P03",
                    "status": "available",
                    "sensor_value": 420,
                    "device_id": "PARKING-01",
                    "updated_at": now.isoformat(),
                },
                {
                    "id": 4,
                    "slot_code": "P04",
                    "status": "available",
                    "sensor_value": 510,
                    "device_id": "PARKING-01",
                    "updated_at": now.isoformat(),
                },
            ],
            "rfid_scans": [
                {
                    "id": 1,
                    "uid": "A3F21C12",
                    "device_id": "GATE-01",
                    "created_at": (now - timedelta(minutes=10)).isoformat(),
                },
                {
                    "id": 2,
                    "uid": "B4E22D33",
                    "device_id": "GATE-01",
                    "created_at": (now - timedelta(minutes=5)).isoformat(),
                },
                {
                    "id": 3,
                    "uid": "D6A44B55",
                    "device_id": "GATE-01",
                    "created_at": (now - timedelta(minutes=1)).isoformat(),
                },
            ],
            "iot_devices": [
                {
                    "id": 1,
                    "device_id": "GATE-01",
                    "device_name": "ESP32-S3 Gate Controller",
                    "status": "online",
                    "last_seen": now.isoformat(),
                },
                {
                    "id": 2,
                    "device_id": "PARKING-01",
                    "device_name": "ESP32-S3 Parking Node",
                    "status": "online",
                    "last_seen": now.isoformat(),
                },
            ],
            "sensor_data": [
                {
                    "id": 1,
                    "device_id": "GATE-01",
                    "sensor_type": "ultrasonic",
                    "sensor_value": 18.5,
                    "created_at": (now - timedelta(seconds=30)).isoformat(),
                },
                {
                    "id": 2,
                    "device_id": "PARKING-01",
                    "sensor_type": "ir",
                    "sensor_value": 450.0,
                    "created_at": (now - timedelta(seconds=25)).isoformat(),
                },
                {
                    "id": 3,
                    "device_id": "PARKING-01",
                    "sensor_type": "ir",
                    "sensor_value": 2150.0,
                    "created_at": (now - timedelta(seconds=20)).isoformat(),
                },
                {
                    "id": 4,
                    "device_id": "PARKING-01",
                    "sensor_type": "ir",
                    "sensor_value": 420.0,
                    "created_at": (now - timedelta(seconds=15)).isoformat(),
                },
                {
                    "id": 5,
                    "device_id": "PARKING-01",
                    "sensor_type": "ir",
                    "sensor_value": 510.0,
                    "created_at": (now - timedelta(seconds=10)).isoformat(),
                },
            ],
            "app_users": [
                {
                    "id": 1,
                    "username": "admin",
                    "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
                    "role": "admin",
                    "full_name": "Administrator Smart Parking",
                    "device_id": None,
                    "created_at": now.isoformat(),
                },
                {
                    "id": 2,
                    "username": "siswa1",
                    "password_hash": "ca82d8a67832679fdc39c9156f087e31236b833ee7371eb3d6e081aeb90016c9",
                    "role": "student",
                    "full_name": "Ahmad Zaki",
                    "device_id": "DEV-SISWA-01",
                    "created_at": now.isoformat(),
                },
            ],
            "audit_forensic_logs": [],
        }

    def table(self, table_name: str) -> MockQueryBuilder:
        return MockQueryBuilder(self, table_name)

    def get_table(self, table_name: str) -> list:
        if table_name not in self.tables:
            self.tables[table_name] = []
        return self.tables[table_name]

    def set_table(self, table_name: str, rows: list):
        self.tables[table_name] = rows

    def next_id(self, table_name: str) -> int:
        table = self.get_table(table_name)
        existing_ids = [r.get("id", 0) for r in table if isinstance(r.get("id"), int)]
        max_id = max(existing_ids) if existing_ids else 0
        return max_id + 1


@pytest.fixture
def mock_supabase():
    """Provides a fresh isolated MockSupabaseClient instance."""
    return MockSupabaseClient()


@pytest.fixture
def sample_slots():
    """Provides 4 realistic sample parking slot records."""
    return [
        {"id": 1, "slot_code": "P01", "status": "available", "sensor_value": 450, "device_id": "PARKING-01"},
        {"id": 2, "slot_code": "P02", "status": "occupied", "sensor_value": 2150, "device_id": "PARKING-01"},
        {"id": 3, "slot_code": "P03", "status": "available", "sensor_value": 420, "device_id": "PARKING-01"},
        {"id": 4, "slot_code": "P04", "status": "available", "sensor_value": 510, "device_id": "PARKING-01"},
    ]


@pytest.fixture
def sample_member():
    """Provides a realistic active member dictionary."""
    return {
        "rfid_uid": "A3F21C12",
        "member_name": "Rahmat Hidayat",
        "license_plate": "BG 1234 RH",
        "vehicle_type": "car",
        "status": "active"
    }


@pytest.fixture
def sample_scan():
    """Provides a realistic RFID scan record."""
    return {
        "id": 10,
        "uid": "E9B87A65",
        "device_id": "GATE-01",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
