import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("inventory") / "test.db"
    os.environ["DB_PATH"] = str(db_path)
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    with TestClient(app_module.app) as test_client:
        yield test_client


def issue_first_label(client):
    response = client.post("/api/asset-labels", json={"quantity": 1})
    assert response.status_code == 201
    return response


def test_asset_details_persist_allow_partial_changes_and_clear(client):
    register_first_asset(client)
    path = "/api/assets/ASSET-00000001"
    values = {"serial_number": " SN-123 ", "manufacturer": "Dell", "model": "R750"}
    saved = client.patch(path + "/details", json=values)
    assert saved.status_code == 200
    assert saved.json()["serial_number"] == "SN-123"
    assert client.get(path).json()["model"] == "R750"
    assert client.patch(path + "/details", json={"model": "R760"}).status_code == 200
    assert client.get(path).json()["serial_number"] == "SN-123"
    assert client.patch(path + "/details", json={"serial_number": "  ", "manufacturer": None}).status_code == 200
    fetched = client.get(path).json()
    assert "serial_number" not in fetched
    assert "manufacturer" not in fetched
    assert fetched["model"] == "R760"
    assert client.patch(path + "/details", json={"model": "x" * 241}).status_code == 422
    with sys.modules["app"].get_db() as conn:
        events = conn.execute("SELECT * FROM asset_events WHERE action = 'DETAILS_CHANGE'").fetchall()
        assert len(events) == 3
    sys.modules["app"].init_db()
    assert client.get(path).json()["model"] == "R760"


def test_asset_details_require_registered_asset_and_operator(client, monkeypatch):
    issue_first_label(client)
    path = "/api/assets/ASSET-00000001/details"
    assert client.patch(path, json={"model": "R750"}).status_code == 404
    module = sys.modules["app"]
    monkeypatch.setattr(module, "AUTH_REQUIRED", True)
    monkeypatch.setattr(module, "ADMIN_EMAILS", set())
    monkeypatch.setattr(module, "OPERATOR_EMAILS", set())
    assert client.patch(path, json={"model": "R750"}).status_code == 401
    assert client.patch(path, json={"model": "R750"}, headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"}).status_code == 403


@pytest.mark.parametrize("asset_type,specifications", [
    ("SSD", {"capacity": {"value": 1.92, "unit": "TB"}, "interface": "SAS"}),
    ("HDD", {"capacity": {"value": 1200, "unit": "GB"}, "interface": "SATA"}),
    ("MEMORY", {"capacity": {"value": 32, "unit": "GB"}, "ddr": "DDR5", "memory_speed": {"value": 4800, "unit": "MT/s"}}),
    ("NIC", {"speed": {"value": 25, "unit": "Gbps"}, "ports": {"value": 2, "unit": "개"}}),
    ("PSU", {"power": {"value": 750, "unit": "W"}}),
    ("GPU", {"vram": {"value": 24, "unit": "GB"}}),
    ("HBA", {"interface": "FC", "speed": {"value": 32, "unit": "Gbps"}}),
    ("RAID_CONTROLLER", {"cache": {"value": 2, "unit": "GB"}}),
    ("OTHER", {"notes": "특수 부품 사양"}),
])
def test_asset_specifications_round_trip(client, asset_type, specifications):
    register_first_asset(client, asset_type=asset_type)
    path = "/api/assets/ASSET-00000001"
    assert client.patch(path + "/details", json={"specifications": specifications}).status_code == 200
    assert client.get(path).json()["specifications"] == specifications
    client.patch(path + "/details", json={"manufacturer": "Example"})
    sys.modules["app"].init_db()
    assert client.get(path).json()["specifications"] == specifications
    assert client.patch(path + "/details", json={"specifications": {}}).status_code == 200
    assert "specifications" not in client.get(path).json()


@pytest.mark.parametrize("specifications", [
    {"capacity": {"value": -1, "unit": "GB"}},
    {"capacity": {"value": 1, "unit": "Gbps"}},
    {"capacity": {"value": True, "unit": "GB"}},
    {"capacity": {"value": 0, "unit": "TB"}},
    {"ddr": "DDR4"}, {"interface": "invalid"}, {"capacity": "1TB"},
])
def test_invalid_specifications_are_not_saved(client, specifications):
    register_first_asset(client)
    path = "/api/assets/ASSET-00000001"
    assert client.patch(path + "/details", json={"specifications": specifications}).status_code == 422
    assert "specifications" not in client.get(path).json()


def test_mobile_navigation_and_specification_schema(client):
    assert 'href="/app"' in client.get("/mobile").text
    schema = client.get("/api/asset-specifications").json()
    assert schema["fields"]["capacity"]["units"] == ["GB", "TB"]
    assert schema["types"]["NETWORK"] == ["speed", "ports"]


@pytest.mark.parametrize("asset_type,specifications", [
    ("SSD", {"disk_size": "M.2 2280"}),
    ("HDD", {"disk_size": "3.5인치"}),
    ("MEMORY", {"memory_type": "RDIMM", "ddr": "DDR5"}),
    ("NIC", {"connector": "SFP28", "speed": {"value": 25, "unit": "Gbps"}}),
])
def test_part_number_and_hardware_types_persist(client, asset_type, specifications):
    register_first_asset(client, asset_type=asset_type)
    path = "/api/assets/ASSET-00000001"
    response = client.patch(path + "/details", json={"part_number": " PN-123 ", "specifications": specifications})
    assert response.status_code == 200
    assert response.json()["part_number"] == "PN-123"
    sys.modules["app"].init_db()
    saved = client.get(path).json()
    assert saved["part_number"] == "PN-123"
    assert saved["specifications"] == specifications
    client.patch(path + "/details", json={"model": "updated"})
    assert client.get(path).json()["part_number"] == "PN-123"
    client.patch(path + "/details", json={"part_number": " "})
    assert "part_number" not in client.get(path).json()
    assert client.get(path).json()["specifications"] == specifications
    assert client.patch(path + "/details", json={"part_number": "x" * 241}).status_code == 422


@pytest.mark.parametrize("asset_type,specifications", [
    ("SSD", {"memory_type": "RDIMM"}),
    ("MEMORY", {"memory_type": "invalid"}),
    ("NIC", {"connector": "invalid"}),
    ("HDD", {"disk_size": "invalid"}),
])
def test_hardware_types_reject_invalid_choices(client, asset_type, specifications):
    register_first_asset(client, asset_type=asset_type)
    assert client.patch("/api/assets/ASSET-00000001/details", json={"specifications": specifications}).status_code == 422


def test_equipment_label_sequences_and_registration(client):
    for endpoint, prefix, asset_type in (
        ("server", "SVR", "SERVER"), ("network", "NET", "NETWORK"),
        ("server", "SVR", "SERVER"), ("network", "NET", "NETWORK"),
    ):
        response = client.post(f"/api/{endpoint}-labels", json={"quantity": 2})
        assert response.status_code == 201
        codes = response.json()["asset_codes"]
        assert all(code.startswith(prefix + "-") for code in codes)
        for code in codes:
            wrong = client.post(f"/api/assets/{code}/register", json={"asset_type": "SSD", "site_type": "IDC"})
            assert wrong.status_code == 422
            registered = client.post(f"/api/assets/{code}/register", json={"site_type": "IDC"})
            assert registered.status_code == 201
            assert registered.json()["asset_type"] == asset_type
            assert client.get(f"/api/asset-labels/{code}/qr.svg").status_code == 200
    assert client.post("/api/network-labels", json={"quantity": 1}).json()["asset_codes"] == ["NET-00000005"]
    assert issue_first_label(client).json()["asset_codes"] == ["ASSET-00000001"]


def test_legacy_srv_label_stays_usable(client):
    module = sys.modules["app"]
    with module.get_db() as conn:
        conn.execute("INSERT INTO asset_labels VALUES ('SRV-00000001', -1, 'UNASSIGNED', '2026-09-27')")
        conn.execute("UPDATE server_id_sequence SET next_value = 2")
    assert client.post("/api/assets/SRV-00000001/register", json={"site_type": "IDC"}).status_code == 201
    assert issue_first_server_label(client).json()["asset_codes"] == ["SVR-00000002"]
    register_first_asset(client)
    assert client.post("/api/assets/ASSET-00000001/assignments", json={"target_asset_code": "SRV-00000001"}).status_code == 201


@pytest.mark.parametrize("issue_endpoint,prefix", [
    ("asset-labels", "ASSET"), ("server-labels", "SVR"), ("network-labels", "NET"),
])
def test_reprint_issued_labels_without_advancing_sequence(client, issue_endpoint, prefix):
    issued = client.post(f"/api/{issue_endpoint}", json={"quantity": 3}).json()["asset_codes"]
    response = client.get("/api/asset-labels/reprint", params={"start_code": issued[0], "quantity": 2})
    assert response.status_code == 200
    assert response.json() == {"asset_codes": issued[:2]}
    assert client.get(f"/api/asset-labels/{issued[0]}/qr.svg").status_code == 200
    assert client.post(f"/api/{issue_endpoint}", json={"quantity": 1}).json()["asset_codes"] == [f"{prefix}-00000004"]


def test_reprint_rejects_unissued_or_invalid_codes(client):
    issued = client.post("/api/asset-labels", json={"quantity": 2}).json()["asset_codes"]
    assert client.get("/api/asset-labels/reprint", params={"start_code": issued[1], "quantity": 2}).status_code == 404
    assert client.get("/api/asset-labels/reprint", params={"start_code": "ASSET-00000003", "quantity": 1}).status_code == 404
    assert client.get("/api/asset-labels/reprint", params={"start_code": "OTHER-00000001", "quantity": 1}).status_code == 422
    assert client.get("/api/asset-labels/reprint", params={"start_code": issued[0], "quantity": 501}).status_code == 422
    assert client.post("/api/asset-labels", json={"quantity": 1}).json()["asset_codes"] == ["ASSET-00000003"]


def issue_first_server_label(client):
    response = client.post("/api/server-labels", json={"quantity": 1})
    assert response.status_code == 201
    return response


def register_first_asset(client, asset_type="SSD", site_type="IDC"):
    issue_first_label(client)
    response = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": asset_type, "site_type": site_type},
    )
    assert response.status_code == 201
    return response


def issue_and_register(client, quantity, registrations):
    issued = client.post("/api/asset-labels", json={"quantity": quantity})
    assert issued.status_code == 201
    for asset_code, asset_type, site_type in registrations:
        response = client.post(
            f"/api/assets/{asset_code}/register",
            json={"asset_type": asset_type, "site_type": site_type},
        )
        assert response.status_code == 201


def test_inventory_server_issues_first_unassigned_label(client):
    issued = issue_first_label(client)

    assert issued.status_code == 201
    assert issued.json() == {
        "asset_codes": ["ASSET-00000001"],
        "registration_status": "UNASSIGNED",
    }

    retrieved = client.get("/api/assets/ASSET-00000001")

    assert retrieved.status_code == 200
    assert retrieved.json() == {
        "asset_code": "ASSET-00000001",
        "registration_status": "UNASSIGNED",
    }


def test_operator_registers_an_unassigned_label(client):
    issue_first_label(client)
    registered = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "SSD", "site_type": "IDC"},
    )

    assert registered.status_code == 201
    assert registered.json() == {
        "asset_code": "ASSET-00000001",
        "registration_status": "REGISTERED",
        "asset_type": "SSD",
        "status": "AVAILABLE",
        "site_type": "IDC",
    }

    retrieved = client.get("/api/assets/ASSET-00000001")

    assert retrieved.status_code == 200
    assert retrieved.json() == registered.json()


def test_retrying_the_same_registration_is_idempotent(client):
    issue_first_label(client)
    created = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "SSD", "site_type": "IDC"},
    )
    assert created.status_code == 201

    retried = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "SSD", "site_type": "IDC"},
    )

    assert retried.status_code == 200
    assert retried.json() == {
        "asset_code": "ASSET-00000001",
        "registration_status": "REGISTERED",
        "asset_type": "SSD",
        "status": "AVAILABLE",
        "site_type": "IDC",
    }


def test_registered_label_cannot_be_registered_with_different_values(client):
    issue_first_label(client)
    created = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "SSD", "site_type": "IDC"},
    )
    assert created.status_code == 201

    conflicting = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "HDD", "site_type": "OFFICE"},
    )

    assert conflicting.status_code == 409
    assert conflicting.json() == {
        "detail": "asset label is already registered differently"
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_type": "RAM", "site_type": "IDC"},
        {"asset_type": "SSD", "site_type": "WAREHOUSE"},
    ],
)
def test_registration_rejects_unknown_reference_values(client, payload):
    rejected = client.post(
        "/api/assets/ASSET-00000001/register",
        json=payload,
    )

    assert rejected.status_code == 422


def test_registration_rejects_an_unissued_asset_id(client):
    missing = client.post(
        "/api/assets/ASSET-99999999/register",
        json={"asset_type": "SSD", "site_type": "IDC"},
    )

    assert missing.status_code == 404
    assert missing.json() == {"detail": "asset label not found"}


def test_inventory_server_issues_a_contiguous_label_batch(client):
    issued = client.post("/api/asset-labels", json={"quantity": 2})

    assert issued.status_code == 201
    assert issued.json() == {
        "asset_codes": ["ASSET-00000001", "ASSET-00000002"],
        "registration_status": "UNASSIGNED",
    }


def test_server_labels_use_an_independent_srv_sequence_and_register_as_server(client):
    issue_first_label(client)
    issued = client.post("/api/server-labels", json={"quantity": 2})

    assert issued.status_code == 201
    assert issued.json() == {
        "asset_codes": ["SVR-00000001", "SVR-00000002"],
        "registration_status": "UNASSIGNED",
    }
    next_asset = client.post("/api/asset-labels", json={"quantity": 1})
    assert next_asset.json()["asset_codes"] == ["ASSET-00000002"]

    registered = client.post(
        "/api/assets/SVR-00000001/register",
        json={"site_type": "IDC"},
    )
    assert registered.status_code == 201
    assert registered.json() == {
        "asset_code": "SVR-00000001",
        "registration_status": "REGISTERED",
        "asset_type": "SERVER",
        "status": "AVAILABLE",
        "site_type": "IDC",
    }


def test_general_asset_label_rejects_server_registration(client):
    issue_first_label(client)

    response = client.post(
        "/api/assets/ASSET-00000001/register",
        json={"asset_type": "SERVER", "site_type": "IDC"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "SERVER must use an SVR label"}


def test_issued_label_has_a_printable_qr_svg(client):
    issue_first_label(client)

    response = client.get("/api/asset-labels/ASSET-00000001/qr.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-qr-content"].endswith("/a/ASSET-00000001")
    assert b"<svg" in response.content


@pytest.mark.parametrize(
    "path, content_type",
    [
        ("/app", "text/html"),
        ("/mobile", "text/html"),
        ("/a/ASSET-00000001", "text/html"),
        ("/a/SVR-00000001", "text/html"),
        ("/mobile.css", "text/css"),
        ("/mobile.js", "application/javascript"),
        ("/dashboard.css", "text/css"),
        ("/dashboard.js", "application/javascript"),
        ("/manifest.webmanifest", "application/manifest+json"),
        ("/sw.js", "application/javascript"),
        ("/icon-192.svg", "image/svg+xml"),
        ("/icon-512.svg", "image/svg+xml"),
    ],
)
def test_mobile_pwa_files_are_served(client, path, content_type):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)


def test_inventory_overview_aggregates_registered_assets(client):
    register_first_asset(client, asset_type="SSD", site_type="IDC")

    response = client.get("/api/inventory/summary")

    assert response.status_code == 200
    assert response.json() == {
        "totals": {
            "registered": 1,
            "normal": 1,
            "available": 1,
            "in_use": 0,
            "faulty": 0,
            "disposed": 0,
        },
        "items": [
            {
                "asset_type": "SSD",
                "site_type": "IDC",
                "registered": 1,
                "normal": 1,
                "available": 1,
                "in_use": 0,
                "faulty": 0,
                "disposed": 0,
                "other": 0,
            }
        ],
    }


def test_ssd_specification_groups_and_drill_down(client):
    base = {"capacity": {"value": 1.92, "unit": "TB"}, "interface": "SAS", "disk_size": "2.5인치"}
    equivalent = {**base, "capacity": {"value": 1920, "unit": "GB"}}
    cases = [
        ("SSD", "IDC", "AVAILABLE", base),
        ("SSD", "IDC", "IN_USE", equivalent),
        ("SSD", "IDC", "FAULTY", {**base, "interface": "SATA"}),
        ("SSD", "IDC", "DISPOSED", {**base, "disk_size": "U.2"}),
        ("SSD", "OFFICE", "AVAILABLE", base),
        ("SSD", "IDC", "AVAILABLE", {}),
        ("SSD", "IDC", "RESERVED", {"capacity": {"value": 960, "unit": "GB"}}),
        ("SSD", "IDC", "AVAILABLE", {**base, "disk_size": "기타"}),
        ("HDD", "IDC", "AVAILABLE", base),
        ("HDD", "IDC", "AVAILABLE", equivalent),
    ]
    codes = client.post("/api/asset-labels", json={"quantity": len(cases)}).json()["asset_codes"]
    for code, (kind, site, status, specs) in zip(codes, cases):
        assert client.post(f"/api/assets/{code}/register", json={"asset_type": kind, "site_type": site}).status_code == 201
        assert client.patch(f"/api/assets/{code}/details", json={"specifications": specs}).status_code == 200
        assert client.patch(f"/api/assets/{code}", json={"status": status}).status_code == 200

    grouped = client.get("/api/inventory/summary", params={"group_by": "specification"}).json()
    assert grouped["totals"] == client.get("/api/inventory/summary").json()["totals"]
    assert len(grouped["items"]) == 6
    merged = next(item for item in grouped["items"] if item["asset_type"] == "SSD" and item.get("specification_label") == "1.92 TB · SAS · 2.5인치" and item["site_type"] == "IDC")
    assert (merged["registered"], merged["available"], merged["in_use"]) == (2, 1, 1)
    missing = next(item for item in grouped["items"] if item.get("group_key") == "ssd:incomplete")
    assert (missing["registered"], missing["available"], missing["other"]) == (3, 2, 1)
    seen = []
    for item in grouped["items"]:
        params = {"asset_type": item["asset_type"], "site_type": item["site_type"]}
        if "group_key" in item:
            params["group_key"] = item["group_key"]
        assets = client.get("/api/assets", params=params).json()
        assert len(assets) == item["registered"]
        seen.extend(asset["asset_code"] for asset in assets)
    assert sorted(seen) == sorted(codes)
    only_available = client.get("/api/assets", params={"asset_type": "SSD", "site_type": "IDC", "group_key": merged["group_key"], "status": "AVAILABLE"}).json()
    assert [asset["asset_code"] for asset in only_available] == [codes[0]]

    # Editing a missing specification moves the asset into the matching group.
    client.patch(f"/api/assets/{codes[5]}/details", json={"specifications": base})
    updated = client.get("/api/assets", params={"asset_type": "SSD", "site_type": "IDC", "group_key": merged["group_key"]}).json()
    assert {asset["asset_code"] for asset in updated} == {codes[0], codes[1], codes[5]}


def test_empty_specification_summary_and_invalid_mode(client):
    result = client.get("/api/inventory/summary?group_by=specification")
    assert result.status_code == 200
    assert result.json()["items"] == []
    assert result.json()["totals"]["registered"] == 0
    assert client.get("/api/inventory/summary?group_by=size").status_code == 422


def test_hdd_groups_split_specifications_and_missing_values(client):
    base = {"capacity": {"value": 4, "unit": "TB"}, "interface": "SATA", "disk_size": "3.5인치"}
    specifications = [base, {**base, "capacity": {"value": 4000, "unit": "GB"}},
                      {**base, "interface": "SAS"}, {**base, "disk_size": "2.5인치"}, {}]
    codes = client.post("/api/asset-labels", json={"quantity": 5}).json()["asset_codes"]
    for code, specs in zip(codes, specifications):
        client.post(f"/api/assets/{code}/register", json={"asset_type": "HDD", "site_type": "IDC"})
        assert client.patch(f"/api/assets/{code}/details", json={"specifications": specs}).status_code == 200
    result = client.get("/api/inventory/summary?group_by=specification").json()
    assert len(result["items"]) == 4
    merged = next(item for item in result["items"] if item["specification_label"] == "4 TB · SATA · 3.5인치")
    assert merged["registered"] == 2
    listed = client.get("/api/assets", params={"asset_type": "HDD", "site_type": "IDC", "group_key": merged["group_key"]}).json()
    assert {row["asset_code"] for row in listed} == set(codes[:2])
    missing = client.get("/api/assets", params={"group_key": "hdd:incomplete"}).json()
    assert [row["asset_code"] for row in missing] == [codes[-1]]
    assert result["totals"] == client.get("/api/inventory/summary").json()["totals"]


def test_inventory_user_filters_the_individual_asset_list(client):
    register_first_asset(client, asset_type="SSD", site_type="IDC")

    response = client.get(
        "/api/assets",
        params={"asset_type": "SSD", "site_type": "IDC", "status": "AVAILABLE"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "asset_code": "ASSET-00000001",
            "registration_status": "REGISTERED",
            "asset_type": "SSD",
            "status": "AVAILABLE",
            "site_type": "IDC",
            "detailed_location": None,
        }
    ]


def test_moving_an_asset_updates_current_location_and_preserves_history(client):
    register_first_asset(client, asset_type="SSD", site_type="IDC")

    moved = client.post(
        "/api/assets/ASSET-00000001/movements",
        headers={"Cf-Access-Authenticated-User-Email": "operator@example.com"},
        json={
            "site_type": "OFFICE",
            "detailed_location": "본사 / 5F / 창고",
            "memo": "현장 예비품 이동",
        },
    )

    assert moved.status_code == 201
    assert moved.json() == {
        "asset_code": "ASSET-00000001",
        "site_type": "OFFICE",
        "detailed_location": "본사 / 5F / 창고",
    }

    current = client.get("/api/assets/ASSET-00000001")
    assert current.json()["site_type"] == "OFFICE"
    assert current.json()["detailed_location"] == "본사 / 5F / 창고"

    history = client.get("/api/assets/ASSET-00000001/history")
    assert history.status_code == 200
    assert history.json()[0] | {"created_at": "ignored"} == {
        "action": "MOVE",
        "from_site_type": "IDC",
        "from_detailed_location": None,
        "to_site_type": "OFFICE",
        "to_detailed_location": "본사 / 5F / 창고",
        "actor": "operator@example.com",
        "memo": "현장 예비품 이동",
        "created_at": "ignored",
    }


def test_faulty_status_is_separated_from_normal_inventory_and_recorded(client):
    register_first_asset(client, asset_type="SSD", site_type="IDC")

    changed = client.patch(
        "/api/assets/ASSET-00000001",
        headers={"Cf-Access-Authenticated-User-Email": "operator@example.com"},
        json={"status": "FAULTY", "memo": "SMART 오류"},
    )

    assert changed.status_code == 200
    assert changed.json() == {
        "asset_code": "ASSET-00000001",
        "status": "FAULTY",
    }

    summary = client.get("/api/inventory/summary").json()
    assert summary["totals"]["normal"] == 0
    assert summary["totals"]["faulty"] == 1

    history = client.get("/api/assets/ASSET-00000001/history").json()
    status_event = next(item for item in history if item["action"] == "STATUS_CHANGE")
    assert status_event | {"created_at": "ignored"} == {
        "action": "STATUS_CHANGE",
        "before_status": "AVAILABLE",
        "after_status": "FAULTY",
        "actor": "operator@example.com",
        "memo": "SMART 오류",
        "created_at": "ignored",
    }


def test_component_can_be_installed_in_and_removed_from_a_server(client):
    register_first_asset(client, asset_type="SSD", site_type="IDC")
    issue_first_server_label(client)
    server = client.post(
        "/api/assets/SVR-00000001/register",
        json={"site_type": "IDC"},
    )
    assert server.status_code == 201

    installed = client.post(
        "/api/assets/ASSET-00000001/assignments",
        json={"target_asset_code": "SVR-00000001", "slot": "Bay-04"},
    )
    assert installed.status_code == 201
    assert installed.json()["status"] == "IN_USE"
    assert installed.json()["assignment"] == {
        "target_asset_code": "SVR-00000001",
        "slot": "Bay-04",
    }

    removed = client.post(
        "/api/assets/ASSET-00000001/assignments/remove",
        json={"site_type": "OFFICE", "detailed_location": "본사 / 창고"},
    )
    assert removed.status_code == 200
    assert removed.json() == {
        "asset_code": "ASSET-00000001",
        "status": "AVAILABLE",
        "site_type": "OFFICE",
        "detailed_location": "본사 / 창고",
    }

    asset = client.get("/api/assets/ASSET-00000001").json()
    assert "assignment" not in asset
    assert asset["status"] == "AVAILABLE"


def test_cloudflare_access_requires_login_and_operator_role(tmp_path, monkeypatch):
    db_path = tmp_path / "secured.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.delenv("INVENTORY_AUTH_REQUIRED", raising=False)
    sys.modules.pop("app", None)
    setup_module = importlib.import_module("app")
    with TestClient(setup_module.app) as setup_client:
        register_first_asset(setup_client)

    monkeypatch.setenv("INVENTORY_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INVENTORY_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("INVENTORY_OPERATOR_EMAILS", "operator@example.com")
    sys.modules.pop("app", None)
    secured_module = importlib.import_module("app")
    with TestClient(secured_module.app) as secured_client:
        assert secured_client.get("/api/inventory/summary").status_code == 401
        assert secured_client.get(
            "/api/inventory/summary",
            headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"},
        ).status_code == 200

        forbidden = secured_client.post(
            "/api/assets/ASSET-00000001/movements",
            headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"},
            json={"site_type": "OFFICE"},
        )
        assert forbidden.status_code == 403
        assert secured_client.post(
            "/api/asset-labels",
            headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"},
            json={"quantity": 1},
        ).status_code == 403
        assert secured_client.post(
            "/api/server-labels",
            headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"},
            json={"quantity": 1},
        ).status_code == 403
        assert secured_client.post(
            "/api/quotes",
            headers={"Cf-Access-Authenticated-User-Email": "viewer@example.com"},
            json={"name": "견적 품목"},
        ).status_code == 403

        allowed = secured_client.post(
            "/api/assets/ASSET-00000001/movements",
            headers={"Cf-Access-Authenticated-User-Email": "operator@example.com"},
            json={"site_type": "OFFICE"},
        )
        assert allowed.status_code == 201


def test_health_check_reports_database_ready(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}


def test_purchase_offer_comparison_preserves_reference_prices(client):
    created = client.post("/api/quotes", json={"name": "SSD 1.92TB", "category": "SSD", "part_number": " PN-001 "})
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert client.put(f"/api/quotes/{item_id}/prices", json={"date": "2026-09-01", "price": 150000}).status_code == 200
    offers = [
        {"supplier": "공급사 A", "unit_price": 120000, "shipping_cost": 10000, "tax_basis": "EXCLUDED", "valid_until": "2026-10-31"},
        {"supplier": "공급사 B", "unit_price": 123000, "shipping_cost": 0, "tax_basis": "EXCLUDED", "valid_until": "2026-10-31"},
        {"supplier": "공급사 C", "unit_price": 100000, "shipping_cost": 0, "tax_basis": "EXCLUDED", "valid_until": "2026-09-10"},
        {"supplier": "공급사 D", "unit_price": 110000, "shipping_cost": 0, "tax_basis": "INCLUDED", "valid_until": "2026-10-31"},
    ]
    for offer in offers:
        response = client.post("/api/purchase-offers", json={
            "item_id": item_id, "quantity": 2, "quoted_on": "2026-09-01", "lead_days": 5,
            **offer,
        })
        assert response.status_code == 201
    items = client.get("/api/quotes").json()
    item = next(item for item in items if item["id"] == item_id)
    assert item["part_number"] == "PN-001"
    assert item["prices"] == [{"date": "2026-09-01", "price": 150000}]
    compared = {offer["supplier"]: offer for offer in client.get("/api/purchase-offers", params={"as_of": "2026-09-28"}).json()}
    assert compared["공급사 A"]["total_price"] == 250000
    assert compared["공급사 B"]["total_price"] == 246000
    assert compared["공급사 B"]["lowest"] is True
    assert compared["공급사 A"]["lowest"] is False
    assert compared["공급사 C"]["status"] == "EXPIRED"
    assert compared["공급사 C"]["lowest"] is False
    assert compared["공급사 D"]["lowest"] is True  # VAT basis differs.
    assert client.get("/api/purchase-offers", params={"as_of": "2026-08-31"}).json()[0]["status"] == "UPCOMING"
    assert client.delete(f"/api/quotes/{item_id}").status_code == 409
    sys.modules["app"].init_db()
    assert len(client.get("/api/purchase-offers").json()) == 4


def test_purchase_offer_rejects_invalid_dates_and_amounts(client):
    item_id = client.post("/api/quotes", json={"name": "NIC"}).json()["id"]
    valid = {"item_id": item_id, "supplier": "Vendor", "quantity": 2, "unit_price": 0,
             "tax_basis": "EXCLUDED", "quoted_on": "2026-09-28"}
    assert client.post("/api/purchase-offers", json=valid).status_code == 201
    invalid = [
        {"quantity": 0}, {"unit_price": -1}, {"shipping_cost": -1},
        {"tax_basis": "UNKNOWN"}, {"supplier": "   "},
        {"valid_until": "2026-09-27"}, {"lead_days": -1},
    ]
    for changed in invalid:
        assert client.post("/api/purchase-offers", json={**valid, **changed}).status_code == 422
    assert client.post("/api/purchase-offers", json={**valid, "item_id": "missing"}).status_code == 404
    assert client.get("/api/purchase-offers", params={"as_of": "not-a-date"}).status_code == 422


def test_existing_quote_catalog_migrates_without_losing_prices(client, tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_path) as conn:
        conn.execute("CREATE TABLE quote_items (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE quote_prices (item_id TEXT NOT NULL, date TEXT NOT NULL, price INTEGER NOT NULL, PRIMARY KEY (item_id, date))")
        conn.execute("INSERT INTO quote_items VALUES ('old-1', '기존 SSD', '스토리지', '2026-01-01')")
        conn.execute("INSERT INTO quote_prices VALUES ('old-1', '2026-01-01', 42000)")
    module = sys.modules["app"]
    monkeypatch.setattr(module, "DB_PATH", str(legacy_path))
    module.init_db()
    item = next(item for item in client.get("/api/quotes").json() if item["id"] == "old-1")
    assert item["part_number"] is None
    assert item["prices"] == [{"date": "2026-01-01", "price": 42000}]
    response = client.post("/api/purchase-offers", json={
        "item_id": "old-1", "supplier": "구매처", "quantity": 1, "unit_price": 40000,
        "tax_basis": "EXCLUDED", "quoted_on": "2026-09-28",
    })
    assert response.status_code == 201


def test_purchase_offer_creation_requires_admin(client, monkeypatch):
    module = sys.modules["app"]
    monkeypatch.setattr(module, "AUTH_REQUIRED", True)
    monkeypatch.setattr(module, "ADMIN_EMAILS", {"admin@example.com"})
    monkeypatch.setattr(module, "OPERATOR_EMAILS", {"operator@example.com"})
    payload = {"item_id": "missing", "supplier": "구매처", "quantity": 1,
               "unit_price": 40000, "tax_basis": "EXCLUDED", "quoted_on": "2026-09-28"}
    assert client.post("/api/purchase-offers", json=payload).status_code == 401
    assert client.post("/api/purchase-offers", json=payload,
                       headers={"Cf-Access-Authenticated-User-Email": "operator@example.com"}).status_code == 403
