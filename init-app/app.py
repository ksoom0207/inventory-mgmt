"""IDC 부품 재고 현황 - 백엔드 (FastAPI + SQLite)

정적 페이지(index.html)와 재고 API를 함께 서빙한다.
데이터는 SQLite 파일에 저장되며, Docker 볼륨으로 영속화한다.
"""
from __future__ import annotations

import os
import io
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import segno

DB_PATH = os.environ.get("DB_PATH", "/data/inventory.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_REQUIRED = os.environ.get("INVENTORY_AUTH_REQUIRED", "false").lower() in {
    "1", "true", "yes", "on",
}


def configured_emails(name: str) -> set[str]:
    return {
        email.strip().lower()
        for email in os.environ.get(name, "").split(",")
        if email.strip()
    }


ADMIN_EMAILS = configured_emails("INVENTORY_ADMIN_EMAILS")
OPERATOR_EMAILS = configured_emails("INVENTORY_OPERATOR_EMAILS")
PUBLIC_BASE_URL = os.environ.get("INVENTORY_PUBLIC_BASE_URL", "").rstrip("/")

app = FastAPI(title="IDC 부품 재고 API")

# Shared by API validation and the mobile specification form. Values retain their units.
SPEC_FIELDS = {
    "capacity": {"label": "용량", "units": ["GB", "TB"]},
    "interface": {"label": "인터페이스", "options": ["SAS", "SATA", "NVMe", "PCIe", "FC"]},
    "ddr": {"label": "메모리 규격", "options": ["DDR", "DDR2", "DDR3", "DDR4", "DDR5"]},
    "memory_type": {"label": "메모리 종류", "options": ["RDIMM", "LRDIMM", "UDIMM", "SODIMM", "기타"]},
    "disk_size": {"label": "디스크 크기 / 폼팩터", "options": ["2.5인치", "3.5인치", "M.2 2230", "M.2 2242", "M.2 2260", "M.2 2280", "M.2 22110", "U.2", "U.3", "E1.S", "E1.L", "E3.S", "기타"]},
    "connector": {"label": "NIC 커넥터", "options": ["RJ45", "SFP", "SFP+", "SFP28", "SFP56", "QSFP+", "QSFP28", "QSFP56", "QSFP-DD", "OSFP", "기타"]},
    "memory_speed": {"label": "메모리 속도", "units": ["MT/s"]},
    "speed": {"label": "포트당 속도", "units": ["Gbps"]},
    "ports": {"label": "포트 수", "units": ["개"], "integer": True},
    "vram": {"label": "GPU 메모리", "units": ["GB"]},
    "power": {"label": "정격 출력", "units": ["W"]},
    "cache": {"label": "캐시 용량", "units": ["MB", "GB"]},
    "notes": {"label": "추가 사양", "text": True},
}
SPEC_TYPES = {
    "SSD": ["capacity", "interface", "disk_size"], "HDD": ["capacity", "interface", "disk_size"],
    "MEMORY": ["capacity", "ddr", "memory_type", "memory_speed"],
    "NIC": ["speed", "ports", "connector"], "NETWORK": ["speed", "ports"],
    "GPU": ["vram"], "PSU": ["power"],
    "HBA": ["interface", "speed", "ports"],
    "RAID_CONTROLLER": ["interface", "cache", "ports"],
    "SERVER": [], "OTHER": [],
}


@app.middleware("http")
async def require_cloudflare_access(request: Request, call_next):
    if AUTH_REQUIRED and request.url.path.startswith("/api/"):
        email = request.headers.get("Cf-Access-Authenticated-User-Email")
        if not email:
            return JSONResponse(status_code=401, content={"detail": "login required"})
    return await call_next(request)


def access_actor(
    cf_access_user: Optional[str] = Header(
        default=None,
        alias="Cf-Access-Authenticated-User-Email",
    ),
) -> str:
    return cf_access_user.strip().lower() if cf_access_user else "local-operator"


def require_operator(actor: str = Depends(access_actor)) -> str:
    if AUTH_REQUIRED and actor not in ADMIN_EMAILS | OPERATOR_EMAILS:
        raise HTTPException(403, "operator role required")
    return actor


def require_admin(actor: str = Depends(access_actor)) -> str:
    if AUTH_REQUIRED and actor not in ADMIN_EMAILS:
        raise HTTPException(403, "admin role required")
    return actor


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS parts (
                id       TEXT PRIMARY KEY,
                name     TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '기타',
                idc      TEXT NOT NULL DEFAULT '미지정',
                safety   INTEGER NOT NULL DEFAULT 0,
                price    INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS records (
                part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                date    TEXT NOT NULL,
                qty     INTEGER NOT NULL,
                PRIMARY KEY (part_id, date)
            );
            CREATE TABLE IF NOT EXISTS prices (
                part_id TEXT NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                date    TEXT NOT NULL,
                price   INTEGER NOT NULL,
                PRIMARY KEY (part_id, date)
            );
            CREATE TABLE IF NOT EXISTS asset_id_sequence (
                singleton  INTEGER PRIMARY KEY CHECK (singleton = 1),
                next_value INTEGER NOT NULL CHECK (next_value > 0)
            );
            CREATE TABLE IF NOT EXISTS server_id_sequence (
                singleton  INTEGER PRIMARY KEY CHECK (singleton = 1),
                next_value INTEGER NOT NULL CHECK (next_value > 0)
            );
            CREATE TABLE IF NOT EXISTS network_id_sequence (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                next_value INTEGER NOT NULL CHECK (next_value > 0)
            );
            CREATE TABLE IF NOT EXISTS asset_labels (
                asset_code          TEXT PRIMARY KEY,
                sequence_number     INTEGER NOT NULL UNIQUE,
                registration_status TEXT NOT NULL DEFAULT 'UNASSIGNED'
                    CHECK (registration_status IN ('UNASSIGNED', 'REGISTERED', 'VERIFIED')),
                created_at          TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                asset_code TEXT PRIMARY KEY REFERENCES asset_labels(asset_code),
                asset_type TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'AVAILABLE',
                site_type  TEXT NOT NULL,
                detailed_location TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS asset_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_code  TEXT NOT NULL REFERENCES assets(asset_code),
                action      TEXT NOT NULL,
                before_data TEXT,
                after_data  TEXT NOT NULL,
                actor       TEXT,
                memo        TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS asset_events_no_update
            BEFORE UPDATE ON asset_events
            BEGIN SELECT RAISE(ABORT, 'asset event history is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS asset_events_no_delete
            BEFORE DELETE ON asset_events
            BEGIN SELECT RAISE(ABORT, 'asset event history is immutable'); END;
            CREATE TABLE IF NOT EXISTS asset_movements (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_code             TEXT NOT NULL REFERENCES assets(asset_code),
                action                 TEXT NOT NULL DEFAULT 'MOVE',
                from_site_type         TEXT NOT NULL,
                from_detailed_location TEXT,
                to_site_type           TEXT NOT NULL,
                to_detailed_location   TEXT,
                actor                  TEXT NOT NULL,
                memo                   TEXT,
                created_at             TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS asset_movements_no_update
            BEFORE UPDATE ON asset_movements
            BEGIN SELECT RAISE(ABORT, 'asset movement history is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS asset_movements_no_delete
            BEFORE DELETE ON asset_movements
            BEGIN SELECT RAISE(ABORT, 'asset movement history is immutable'); END;
            CREATE TABLE IF NOT EXISTS assignments (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_code        TEXT NOT NULL REFERENCES assets(asset_code),
                target_asset_code TEXT NOT NULL REFERENCES assets(asset_code),
                slot              TEXT,
                installed_at      TEXT NOT NULL,
                removed_at        TEXT,
                installed_by      TEXT NOT NULL,
                removed_by        TEXT,
                removal_reason    TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS assignments_one_active_per_asset
            ON assignments(asset_code) WHERE removed_at IS NULL;
            CREATE TRIGGER IF NOT EXISTS assignments_no_delete
            BEFORE DELETE ON assignments
            BEGIN SELECT RAISE(ABORT, 'assignment history is immutable'); END;
            CREATE TABLE IF NOT EXISTS quote_items (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                category   TEXT NOT NULL DEFAULT '기타',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quote_prices (
                item_id TEXT NOT NULL REFERENCES quote_items(id) ON DELETE CASCADE,
                date    TEXT NOT NULL,
                price   INTEGER NOT NULL CHECK (price >= 0),
                PRIMARY KEY (item_id, date)
            );
            CREATE TABLE IF NOT EXISTS app_migrations (
                name       TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO asset_id_sequence (singleton, next_value)
            VALUES (1, 1);
            INSERT OR IGNORE INTO server_id_sequence (singleton, next_value)
            VALUES (1, 1);
            INSERT OR IGNORE INTO network_id_sequence (singleton, next_value)
            VALUES (1, 1);
            """
        )
        # 마이그레이션: 기존 DB에 price 컬럼이 없으면 추가
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(parts)").fetchall()]
        if "price" not in cols:
            conn.execute("ALTER TABLE parts ADD COLUMN price INTEGER NOT NULL DEFAULT 0")
        asset_cols = [
            row["name"] for row in conn.execute("PRAGMA table_info(assets)").fetchall()
        ]
        if "detailed_location" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN detailed_location TEXT")
        for column in ("serial_number", "manufacturer", "model", "part_number"):
            if column not in asset_cols:
                conn.execute(f"ALTER TABLE assets ADD COLUMN {column} TEXT")
        if "specifications" not in asset_cols:
            conn.execute("ALTER TABLE assets ADD COLUMN specifications TEXT NOT NULL DEFAULT '{}'")
        event_cols = [
            row["name"] for row in conn.execute("PRAGMA table_info(asset_events)").fetchall()
        ]
        if "memo" not in event_cols:
            conn.execute("ALTER TABLE asset_events ADD COLUMN memo TEXT")
        # 마이그레이션: 기존 단일 단가(price>0)를 날짜별 단가 테이블로 이관
        rows = conn.execute(
            """SELECT id, price FROM parts
               WHERE price > 0 AND id NOT IN (SELECT DISTINCT part_id FROM prices)"""
        ).fetchall()
        today = date.today().isoformat()
        for r in rows:
            conn.execute(
                "INSERT OR IGNORE INTO prices (part_id, date, price) VALUES (?,?,?)",
                (r["id"], today, r["price"]),
            )
        # 비어 있으면 시드 데이터 삽입
        n = conn.execute("SELECT COUNT(*) AS c FROM parts").fetchone()["c"]
        if n == 0:
            seed(conn)
        quote_migration = conn.execute(
            "SELECT 1 FROM app_migrations WHERE name = 'separate_quote_catalog'"
        ).fetchone()
        if quote_migration is None:
            migrated_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT OR IGNORE INTO quote_items (id, name, category, created_at)
                   SELECT id, name, category, ? FROM parts""",
                (migrated_at,),
            )
            conn.execute(
                """INSERT OR IGNORE INTO quote_prices (item_id, date, price)
                   SELECT part_id, date, price FROM prices"""
            )
            conn.execute(
                """INSERT INTO app_migrations (name, applied_at)
                   VALUES ('separate_quote_catalog', ?)""",
                (migrated_at,),
            )


def seed(conn):
    def dm(days):
        return (date.today() - timedelta(days=days)).isoformat()

    # (id, name, category, idc, safety, 재고기록[(date,qty)], 단가기록[(date,price)])
    parts = [
        ("p1", "SFP+ 10G 모듈", "네트워크", "가산 IDC A-12랙", 20,
         [(dm(30), 60), (dm(14), 42), (dm(3), 15)],
         [(dm(30), 45000), (dm(5), 47000)]),
        ("p2", "DDR4 32GB RDIMM", "서버", "가산 IDC A-12랙", 30,
         [(dm(30), 120), (dm(10), 80), (dm(2), 55)],
         [(dm(30), 180000), (dm(7), 172000)]),
        ("p3", "2.5\" SSD 1.92TB", "스토리지", "평촌 IDC B-03랙", 15,
         [(dm(25), 40), (dm(7), 22), (dm(1), 8)],
         [(dm(25), 320000)]),
        ("p4", "전원 케이블 C13-C14", "전원", "평촌 IDC B-03랙", 50,
         [(dm(20), 200), (dm(5), 140)],
         [(dm(20), 3500)]),
        ("p5", "RJ45 패치코드 1m", "네트워크", "가산 IDC A-12랙", 100,
         [(dm(18), 300), (dm(4), 260)],
         [(dm(18), 1200), (dm(3), 1350)]),
        ("p6", "서버 팬 모듈", "서버", "평촌 IDC B-03랙", 12,
         [(dm(12), 18), (dm(2), 6)],
         [(dm(12), 85000)]),
    ]
    for pid, name, cat, idc, safety, recs, prices in parts:
        conn.execute(
            "INSERT INTO parts (id, name, category, idc, safety, price) VALUES (?,?,?,?,?,0)",
            (pid, name, cat, idc, safety),
        )
        for d, q in recs:
            conn.execute(
                "INSERT INTO records (part_id, date, qty) VALUES (?,?,?)",
                (pid, d, q),
            )
        for d, pr in prices:
            conn.execute(
                "INSERT INTO prices (part_id, date, price) VALUES (?,?,?)",
                (pid, d, pr),
            )


# ---------- 스키마 ----------
class PartIn(BaseModel):
    name: str
    category: str = "기타"
    idc: str = "미지정"
    safety: int = Field(default=0, ge=0)
    price: int = Field(default=0, ge=0)


class PartPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    idc: Optional[str] = None
    safety: Optional[int] = Field(default=None, ge=0)
    price: Optional[int] = Field(default=None, ge=0)


class RecordIn(BaseModel):
    date: str  # YYYY-MM-DD
    qty: int = Field(ge=0)


class PriceIn(BaseModel):
    date: str  # YYYY-MM-DD
    price: int = Field(ge=0)


class AssetLabelIssueIn(BaseModel):
    quantity: int = Field(default=1, ge=1, le=500)


class AssetRegistrationIn(BaseModel):
    asset_type: Optional[Literal[
        "SSD", "HDD", "MEMORY", "NIC", "HBA", "RAID_CONTROLLER",
        "GPU", "PSU", "SERVER", "NETWORK", "OTHER",
    ]] = None
    site_type: Literal["IDC", "OFFICE"]


class QuoteItemIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = "기타"


class QuoteItemPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    category: Optional[str] = Field(default=None, min_length=1)


class AssetMovementIn(BaseModel):
    site_type: Literal["IDC", "OFFICE"]
    detailed_location: Optional[str] = Field(default=None, max_length=240)
    memo: Optional[str] = Field(default=None, max_length=500)


class AssetStatusPatch(BaseModel):
    status: Literal[
        "AVAILABLE", "IN_USE", "RESERVED", "FAULTY", "RMA", "REPAIR",
        "DISPOSED", "LOST", "UNKNOWN",
    ]
    memo: Optional[str] = Field(default=None, max_length=500)


class AssetDetailsPatch(BaseModel):
    part_number: Optional[str] = Field(default=None, max_length=240)
    serial_number: Optional[str] = Field(default=None, max_length=240)
    manufacturer: Optional[str] = Field(default=None, max_length=240)
    model: Optional[str] = Field(default=None, max_length=240)
    specifications: Optional[dict] = None


class AssignmentIn(BaseModel):
    target_asset_code: str = Field(pattern=r"^(?:SVR|SRV)-\d{8}$")
    slot: Optional[str] = Field(default=None, max_length=120)


class AssignmentRemovalIn(BaseModel):
    site_type: Literal["IDC", "OFFICE"]
    detailed_location: Optional[str] = Field(default=None, max_length=240)
    reason: Optional[str] = Field(default=None, max_length=500)


# ---------- API ----------
def storage_inventory_group(asset_type: str, specifications: str):
    """One canonical key shared by summary rows and their asset drill-down."""
    specs = json.loads(specifications or "{}")
    capacity = specs.get("capacity") or {}
    interface = specs.get("interface")
    form_factor = specs.get("disk_size")
    try:
        value = Decimal(str(capacity.get("value")))
        unit = capacity.get("unit")
        complete = (
            value.is_finite() and value > 0 and unit in ("GB", "TB")
            and interface in SPEC_FIELDS["interface"]["options"]
            and form_factor in SPEC_FIELDS["disk_size"]["options"]
            and form_factor != "기타"
        )
    except (InvalidOperation, AttributeError):
        complete = False
    if not complete:
        return {"group_key": f"{asset_type.lower()}:incomplete", "specification_label": "사양 미입력"}
    gb = value * (1000 if unit == "TB" else 1)
    canonical = format(gb.normalize(), "f")
    display_value, display_unit = (gb / 1000, "TB") if gb >= 1000 else (gb, "GB")
    return {
        "group_key": json.dumps([asset_type, canonical, interface, form_factor], ensure_ascii=False, separators=(",", ":")),
        "specification_label": f"{format(display_value.normalize(), 'f')} {display_unit} · {interface} · {form_factor}",
    }


@app.get("/api/inventory/summary")
def inventory_summary(group_by: Literal["type", "specification"] = "type"):
    if group_by == "specification":
        with get_db() as conn:
            rows = conn.execute(
                "SELECT asset_type, site_type, status, specifications FROM assets ORDER BY asset_type, site_type, asset_code"
            ).fetchall()
        groups = {}
        for row in rows:
            spec = storage_inventory_group(row["asset_type"], row["specifications"]) if row["asset_type"] in ("SSD", "HDD") else {}
            key = (row["asset_type"], row["site_type"], spec.get("group_key"))
            if key not in groups:
                groups[key] = {
                    "asset_type": row["asset_type"], "site_type": row["site_type"], **spec,
                    **dict.fromkeys(("registered", "normal", "available", "in_use", "faulty", "disposed", "other"), 0),
                }
            item = groups[key]
            item["registered"] += 1
            item["normal"] += row["status"] not in ("FAULTY", "DISPOSED")
            bucket = {"AVAILABLE": "available", "IN_USE": "in_use", "FAULTY": "faulty", "DISPOSED": "disposed"}.get(row["status"], "other")
            item[bucket] += 1
        items = sorted(groups.values(), key=lambda item: (item["asset_type"], item["site_type"], item.get("group_key", "")))
        totals = {key: sum(item[key] for item in items) for key in ("registered", "normal", "available", "in_use", "faulty", "disposed")}
        return {"totals": totals, "items": items}
    with get_db() as conn:
        rows = conn.execute(
            """SELECT asset_type, site_type,
                      COUNT(*) AS registered,
                      SUM(CASE WHEN status NOT IN ('FAULTY', 'DISPOSED') THEN 1 ELSE 0 END) AS normal,
                      SUM(CASE WHEN status = 'AVAILABLE' THEN 1 ELSE 0 END) AS available,
                      SUM(CASE WHEN status = 'IN_USE' THEN 1 ELSE 0 END) AS in_use,
                      SUM(CASE WHEN status = 'FAULTY' THEN 1 ELSE 0 END) AS faulty,
                      SUM(CASE WHEN status = 'DISPOSED' THEN 1 ELSE 0 END) AS disposed,
                      SUM(CASE WHEN status NOT IN ('AVAILABLE', 'IN_USE', 'FAULTY', 'DISPOSED') THEN 1 ELSE 0 END) AS other
               FROM assets
               GROUP BY asset_type, site_type
               ORDER BY asset_type, site_type"""
        ).fetchall()

    items = [dict(row) for row in rows]
    totals = {
        key: sum(item[key] for item in items)
        for key in ("registered", "normal", "available", "in_use", "faulty", "disposed")
    }
    return {"totals": totals, "items": items}


@app.get("/api/quotes")
def list_quotes():
    with get_db() as conn:
        items = conn.execute("SELECT * FROM quote_items ORDER BY name").fetchall()
        prices = conn.execute("SELECT * FROM quote_prices ORDER BY date").fetchall()
    prices_by_item = {}
    for price in prices:
        prices_by_item.setdefault(price["item_id"], []).append(
            {"date": price["date"], "price": price["price"]}
        )
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "prices": prices_by_item.get(item["id"], []),
        }
        for item in items
    ]


@app.post("/api/quotes", status_code=201)
def create_quote_item(item: QuoteItemIn, _actor: str = Depends(require_admin)):
    item_id = "q" + str(int(time.time() * 1000))
    with get_db() as conn:
        conn.execute(
            """INSERT INTO quote_items (id, name, category, created_at)
               VALUES (?, ?, ?, ?)""",
            (item_id, item.name, item.category, datetime.now(timezone.utc).isoformat()),
        )
    return {"id": item_id}


@app.patch("/api/quotes/{item_id}")
def update_quote_item(
    item_id: str,
    patch: QuoteItemPatch,
    _actor: str = Depends(require_admin),
):
    fields = {key: value for key, value in patch.model_dump().items() if value is not None}
    if not fields:
        return {"ok": True}
    sets = ", ".join(f"{key} = ?" for key in fields)
    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE quote_items SET {sets} WHERE id = ?",
            (*fields.values(), item_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "quote item not found")
    return {"ok": True}


@app.delete("/api/quotes/{item_id}")
def delete_quote_item(item_id: str, _actor: str = Depends(require_admin)):
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM quote_items WHERE id = ?", (item_id,))
        if cursor.rowcount == 0:
            raise HTTPException(404, "quote item not found")
    return {"ok": True}


@app.put("/api/quotes/{item_id}/prices")
def upsert_quote_price(
    item_id: str,
    price: PriceIn,
    _actor: str = Depends(require_admin),
):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM quote_items WHERE id = ?", (item_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(404, "quote item not found")
        conn.execute(
            """INSERT INTO quote_prices (item_id, date, price) VALUES (?, ?, ?)
               ON CONFLICT(item_id, date) DO UPDATE SET price = excluded.price""",
            (item_id, price.date, price.price),
        )
    return {"ok": True}


@app.post("/api/asset-labels", status_code=201)
def issue_asset_labels(
    request: AssetLabelIssueIn,
    _actor: str = Depends(require_admin),
):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        first = conn.execute(
            "SELECT next_value FROM asset_id_sequence WHERE singleton = 1"
        ).fetchone()["next_value"]
        conn.execute(
            "UPDATE asset_id_sequence SET next_value = ? WHERE singleton = 1",
            (first + request.quantity,),
        )
        created_at = datetime.now(timezone.utc).isoformat()
        asset_codes = []
        for sequence_number in range(first, first + request.quantity):
            asset_code = f"ASSET-{sequence_number:08d}"
            conn.execute(
                """INSERT INTO asset_labels
                   (asset_code, sequence_number, registration_status, created_at)
                   VALUES (?, ?, 'UNASSIGNED', ?)""",
                (asset_code, sequence_number, created_at),
            )
            asset_codes.append(asset_code)
    return {
        "asset_codes": asset_codes,
        "registration_status": "UNASSIGNED",
    }


@app.post("/api/server-labels", status_code=201)
def issue_server_labels(
    request: AssetLabelIssueIn,
    _actor: str = Depends(require_admin),
):
    return issue_equipment_labels(request, "server_id_sequence", "SVR")


@app.post("/api/network-labels", status_code=201)
def issue_network_labels(
    request: AssetLabelIssueIn,
    _actor: str = Depends(require_admin),
):
    return issue_equipment_labels(request, "network_id_sequence", "NET")


def issue_equipment_labels(request: AssetLabelIssueIn, sequence_table: str, prefix: str):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        first = conn.execute(
            f"SELECT next_value FROM {sequence_table} WHERE singleton = 1"
        ).fetchone()["next_value"]
        conn.execute(
            f"UPDATE {sequence_table} SET next_value = ? WHERE singleton = 1",
            (first + request.quantity,),
        )
        created_at = datetime.now(timezone.utc).isoformat()
        asset_codes = []
        internal_sequence = conn.execute(
            "SELECT MIN(COALESCE(MIN(sequence_number), 0), 0) FROM asset_labels"
        ).fetchone()[0]
        for sequence_number in range(first, first + request.quantity):
            asset_code = f"{prefix}-{sequence_number:08d}"
            internal_sequence -= 1
            conn.execute(
                """INSERT INTO asset_labels
                   (asset_code, sequence_number, registration_status, created_at)
                   VALUES (?, ?, 'UNASSIGNED', ?)""",
                (asset_code, internal_sequence, created_at),
            )
            asset_codes.append(asset_code)
    return {
        "asset_codes": asset_codes,
        "registration_status": "UNASSIGNED",
    }


@app.get("/api/asset-labels/{asset_code}/qr.svg")
def asset_label_qr(asset_code: str, request: Request):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM asset_labels WHERE asset_code = ?",
            (asset_code,),
        ).fetchone()
    if exists is None:
        raise HTTPException(404, "asset label not found")

    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    content = f"{base_url}/a/{asset_code}"
    qr = segno.make_qr(content, error="M")
    output = io.BytesIO()
    qr.save(output, kind="svg", scale=4, border=4, dark="#0f172a", light="#ffffff")
    return Response(
        content=output.getvalue(),
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-QR-Content": content,
        },
    )


@app.get("/api/assets")
def list_assets(
    asset_type: Optional[str] = None,
    site_type: Optional[str] = None,
    status: Optional[str] = None,
    group_key: Optional[str] = None,
):
    conditions = []
    values = []
    for column, value in (
        ("a.asset_type", asset_type),
        ("a.site_type", site_type),
        ("a.status", status),
    ):
        if value:
            conditions.append(f"{column} = ?")
            values.append(value)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT a.asset_code, l.registration_status,
                       a.asset_type, a.status, a.site_type, a.detailed_location, a.specifications
                FROM assets AS a
                JOIN asset_labels AS l ON l.asset_code = a.asset_code
                {where_clause}
                ORDER BY a.asset_code""",
            values,
        ).fetchall()
    result = []
    for row in rows:
        if group_key is not None and (
            row["asset_type"] not in ("SSD", "HDD") or storage_inventory_group(row["asset_type"], row["specifications"])["group_key"] != group_key
        ):
            continue
        item = dict(row)
        item.pop("specifications")
        result.append(item)
    return result


@app.get("/api/asset-specifications")
def asset_specification_schema():
    return {"fields": SPEC_FIELDS, "types": SPEC_TYPES}


@app.get("/api/assets/{asset_code}")
def get_asset(asset_code: str):
    with get_db() as conn:
        asset = conn.execute(
            """SELECT l.asset_code, l.registration_status,
                      a.asset_type, a.status, a.site_type, a.detailed_location,
                      a.serial_number, a.manufacturer, a.model, a.part_number, a.specifications
               FROM asset_labels AS l
               LEFT JOIN assets AS a ON a.asset_code = l.asset_code
               WHERE l.asset_code = ?""",
            (asset_code,),
        ).fetchone()
        assignment = conn.execute(
            """SELECT target_asset_code, slot FROM assignments
               WHERE asset_code = ? AND removed_at IS NULL""",
            (asset_code,),
        ).fetchone()
    if asset is None:
        raise HTTPException(404, "asset label not found")
    result = {key: asset[key] for key in asset.keys() if asset[key] is not None}
    specifications = json.loads(result.pop("specifications", "{}"))
    if specifications:
        result["specifications"] = specifications
    if assignment is not None:
        result["assignment"] = dict(assignment)
    return result


@app.patch("/api/assets/{asset_code}/details")
def update_asset_details(
    asset_code: str,
    patch: AssetDetailsPatch,
    actor: str = Depends(require_operator),
):
    raw_changes = patch.model_dump(exclude_unset=True)
    specifications = raw_changes.pop("specifications", None)
    changes = {
        key: value.strip() or None if value is not None else None
        for key, value in raw_changes.items()
    }
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT serial_number, manufacturer, model, part_number, specifications, asset_type FROM assets WHERE asset_code = ?",
            (asset_code,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "registered asset not found")
        before = dict(row)
        asset_type = before.pop("asset_type")
        before["specifications"] = json.loads(before["specifications"])
        if "specifications" in patch.model_fields_set:
            validated = {}
            for key, value in (specifications or {}).items():
                if key not in SPEC_TYPES[asset_type] + ["notes"]:
                    raise HTTPException(422, "해당 자산 유형에 맞지 않는 사양입니다.")
                field = SPEC_FIELDS[key]
                if field.get("text"):
                    if not isinstance(value, str) or len(value) > 1000:
                        raise HTTPException(422, "추가 사양은 1000자 이내로 입력하세요.")
                    if value.strip():
                        validated[key] = value.strip()
                elif "options" in field:
                    if value not in field["options"]:
                        raise HTTPException(422, "지원하지 않는 사양 종류입니다.")
                    validated[key] = value
                else:
                    if not isinstance(value, dict) or set(value) != {"value", "unit"}:
                        raise HTTPException(422, "사양의 숫자와 단위를 함께 입력하세요.")
                    number = value["value"]
                    if type(number) not in (int, float) or not 0 < number <= 1000000000 or value["unit"] not in field["units"]:
                        raise HTTPException(422, "사양은 올바른 단위와 0보다 큰 숫자로 입력하세요.")
                    if field.get("integer") and int(number) != number:
                        raise HTTPException(422, "포트 수는 정수로 입력하세요.")
                    validated[key] = value
            changes["specifications"] = validated
        after = {**before, **changes}
        if before != after:
            changed_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE assets SET serial_number = ?, manufacturer = ?, model = ?, part_number = ?, specifications = ?, updated_at = ? WHERE asset_code = ?",
                (after["serial_number"], after["manufacturer"], after["model"], after["part_number"], json.dumps(after["specifications"]), changed_at, asset_code),
            )
            conn.execute(
                """INSERT INTO asset_events
                   (asset_code, action, before_data, after_data, actor, created_at)
                   VALUES (?, 'DETAILS_CHANGE', ?, ?, ?, ?)""",
                (asset_code, json.dumps(before), json.dumps(after), actor, changed_at),
            )
    return {"asset_code": asset_code, **after}


@app.patch("/api/assets/{asset_code}")
def change_asset_status(
    asset_code: str,
    patch: AssetStatusPatch,
    actor: str = Depends(require_operator),
):
    memo = patch.memo.strip() if patch.memo else None
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        asset = conn.execute(
            "SELECT status FROM assets WHERE asset_code = ?", (asset_code,)
        ).fetchone()
        if asset is None:
            raise HTTPException(404, "registered asset not found")
        if asset["status"] == patch.status:
            return {"asset_code": asset_code, "status": patch.status}
        changed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE assets SET status = ?, updated_at = ? WHERE asset_code = ?",
            (patch.status, changed_at, asset_code),
        )
        conn.execute(
            """INSERT INTO asset_events
               (asset_code, action, before_data, after_data, actor, memo, created_at)
               VALUES (?, 'STATUS_CHANGE', ?, ?, ?, ?, ?)""",
            (
                asset_code,
                json.dumps({"status": asset["status"]}),
                json.dumps({"status": patch.status}),
                actor,
                memo,
                changed_at,
            ),
        )
    return {"asset_code": asset_code, "status": patch.status}


@app.post("/api/assets/{asset_code}/assignments", status_code=201)
def install_asset(
    asset_code: str,
    assignment: AssignmentIn,
    actor: str = Depends(require_operator),
):
    if asset_code == assignment.target_asset_code:
        raise HTTPException(422, "asset cannot be assigned to itself")
    slot = assignment.slot.strip() if assignment.slot else None
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        component = conn.execute(
            """SELECT site_type, detailed_location, status FROM assets
               WHERE asset_code = ?""",
            (asset_code,),
        ).fetchone()
        target = conn.execute(
            """SELECT asset_type, site_type, detailed_location FROM assets
               WHERE asset_code = ?""",
            (assignment.target_asset_code,),
        ).fetchone()
        if component is None:
            raise HTTPException(404, "component asset not found")
        if target is None or target["asset_type"] != "SERVER":
            raise HTTPException(422, "assignment target must be a registered SERVER")
        active = conn.execute(
            """SELECT 1 FROM assignments
               WHERE asset_code = ? AND removed_at IS NULL""",
            (asset_code,),
        ).fetchone()
        if active is not None:
            raise HTTPException(409, "asset already has an active assignment")
        installed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO assignments
               (asset_code, target_asset_code, slot, installed_at, installed_by)
               VALUES (?, ?, ?, ?, ?)""",
            (asset_code, assignment.target_asset_code, slot, installed_at, actor),
        )
        conn.execute(
            """INSERT INTO asset_movements
               (asset_code, action, from_site_type, from_detailed_location,
                to_site_type, to_detailed_location, actor, memo, created_at)
               VALUES (?, 'INSTALL', ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset_code,
                component["site_type"],
                component["detailed_location"],
                target["site_type"],
                target["detailed_location"],
                actor,
                f"{assignment.target_asset_code}{' / ' + slot if slot else ''}",
                installed_at,
            ),
        )
        conn.execute(
            """UPDATE assets SET status = 'IN_USE', site_type = ?,
                      detailed_location = ?, updated_at = ? WHERE asset_code = ?""",
            (target["site_type"], target["detailed_location"], installed_at, asset_code),
        )
    return {
        "asset_code": asset_code,
        "status": "IN_USE",
        "assignment": {
            "target_asset_code": assignment.target_asset_code,
            "slot": slot,
        },
    }


@app.post("/api/assets/{asset_code}/assignments/remove")
def remove_asset_assignment(
    asset_code: str,
    removal: AssignmentRemovalIn,
    actor: str = Depends(require_operator),
):
    location = removal.detailed_location.strip() if removal.detailed_location else None
    reason = removal.reason.strip() if removal.reason else None
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        asset = conn.execute(
            "SELECT site_type, detailed_location FROM assets WHERE asset_code = ?",
            (asset_code,),
        ).fetchone()
        active = conn.execute(
            """SELECT id, target_asset_code, slot FROM assignments
               WHERE asset_code = ? AND removed_at IS NULL""",
            (asset_code,),
        ).fetchone()
        if asset is None:
            raise HTTPException(404, "component asset not found")
        if active is None:
            raise HTTPException(409, "asset has no active assignment")
        removed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE assignments SET removed_at = ?, removed_by = ?, removal_reason = ?
               WHERE id = ?""",
            (removed_at, actor, reason, active["id"]),
        )
        conn.execute(
            """INSERT INTO asset_movements
               (asset_code, action, from_site_type, from_detailed_location,
                to_site_type, to_detailed_location, actor, memo, created_at)
               VALUES (?, 'REMOVE', ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset_code,
                asset["site_type"],
                asset["detailed_location"],
                removal.site_type,
                location,
                actor,
                reason,
                removed_at,
            ),
        )
        conn.execute(
            """UPDATE assets SET status = 'AVAILABLE', site_type = ?,
                      detailed_location = ?, updated_at = ? WHERE asset_code = ?""",
            (removal.site_type, location, removed_at, asset_code),
        )
    return {
        "asset_code": asset_code,
        "status": "AVAILABLE",
        "site_type": removal.site_type,
        "detailed_location": location,
    }


@app.post("/api/assets/{asset_code}/movements", status_code=201)
def move_asset(
    asset_code: str,
    movement: AssetMovementIn,
    actor: str = Depends(require_operator),
):
    detailed_location = movement.detailed_location.strip() if movement.detailed_location else None
    memo = movement.memo.strip() if movement.memo else None
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            """SELECT site_type, detailed_location FROM assets
               WHERE asset_code = ?""",
            (asset_code,),
        ).fetchone()
        if current is None:
            raise HTTPException(404, "registered asset not found")
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO asset_movements
               (asset_code, action, from_site_type, from_detailed_location,
                to_site_type, to_detailed_location, actor, memo, created_at)
               VALUES (?, 'MOVE', ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset_code,
                current["site_type"],
                current["detailed_location"],
                movement.site_type,
                detailed_location,
                actor,
                memo,
                created_at,
            ),
        )
        conn.execute(
            """UPDATE assets
               SET site_type = ?, detailed_location = ?, updated_at = ?
               WHERE asset_code = ?""",
            (movement.site_type, detailed_location, created_at, asset_code),
        )
    return {
        "asset_code": asset_code,
        "site_type": movement.site_type,
        "detailed_location": detailed_location,
    }


@app.get("/api/assets/{asset_code}/history")
def asset_history(asset_code: str):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM assets WHERE asset_code = ?", (asset_code,)
        ).fetchone()
        if exists is None:
            raise HTTPException(404, "registered asset not found")
        movement_rows = conn.execute(
            """SELECT action, from_site_type, from_detailed_location,
                      to_site_type, to_detailed_location, actor, memo, created_at
               FROM asset_movements WHERE asset_code = ?
               ORDER BY created_at DESC, id DESC""",
            (asset_code,),
        ).fetchall()
        status_rows = conn.execute(
            """SELECT action, before_data, after_data, actor, memo, created_at
               FROM asset_events
               WHERE asset_code = ? AND action = 'STATUS_CHANGE'
               ORDER BY created_at DESC, id DESC""",
            (asset_code,),
        ).fetchall()
    history = [dict(row) for row in movement_rows]
    for row in status_rows:
        before = json.loads(row["before_data"])
        after = json.loads(row["after_data"])
        history.append(
            {
                "action": row["action"],
                "before_status": before["status"],
                "after_status": after["status"],
                "actor": row["actor"],
                "memo": row["memo"],
                "created_at": row["created_at"],
            }
        )
    history.sort(key=lambda item: item["created_at"], reverse=True)
    return history


@app.post("/api/assets/{asset_code}/register", status_code=201)
def register_asset(
    asset_code: str,
    registration: AssetRegistrationIn,
    response: Response,
    actor: str = Depends(require_operator),
):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        label = conn.execute(
            """SELECT registration_status FROM asset_labels
               WHERE asset_code = ?""",
            (asset_code,),
        ).fetchone()
        if label is None:
            raise HTTPException(404, "asset label not found")
        if asset_code.startswith(("SVR-", "SRV-", "NET-")):
            asset_type = "NETWORK" if asset_code.startswith("NET-") else "SERVER"
            if registration.asset_type not in (None, asset_type):
                raise HTTPException(422, f"{asset_code.split('-')[0]} labels always register as {asset_type}")
        elif asset_code.startswith("ASSET-"):
            if registration.asset_type is None:
                raise HTTPException(422, "asset_type is required for ASSET labels")
            if (
                registration.asset_type in ("SERVER", "NETWORK")
                and label["registration_status"] == "UNASSIGNED"
            ):
                prefix = "SVR" if registration.asset_type == "SERVER" else "NET"
                raise HTTPException(422, f"{registration.asset_type} must use an {prefix} label")
            asset_type = registration.asset_type
        else:
            raise HTTPException(422, "unsupported asset code")
        if label["registration_status"] != "UNASSIGNED":
            existing = conn.execute(
                """SELECT asset_type, status, site_type FROM assets
                   WHERE asset_code = ?""",
                (asset_code,),
            ).fetchone()
            if (
                existing is not None
                and existing["asset_type"] == asset_type
                and existing["site_type"] == registration.site_type
            ):
                response.status_code = 200
                return {
                    "asset_code": asset_code,
                    "registration_status": label["registration_status"],
                    "asset_type": existing["asset_type"],
                    "status": existing["status"],
                    "site_type": existing["site_type"],
                }
            raise HTTPException(409, "asset label is already registered differently")

        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO assets
               (asset_code, asset_type, status, site_type, created_at, updated_at)
               VALUES (?, ?, 'AVAILABLE', ?, ?, ?)""",
            (
                asset_code,
                asset_type,
                registration.site_type,
                created_at,
                created_at,
            ),
        )
        conn.execute(
            """UPDATE asset_labels SET registration_status = 'REGISTERED'
               WHERE asset_code = ?""",
            (asset_code,),
        )
        conn.execute(
            """INSERT INTO asset_events
               (asset_code, action, before_data, after_data, actor, created_at)
               VALUES (?, 'REGISTER', NULL, ?, ?, ?)""",
            (
                asset_code,
                json.dumps(
                    {
                        "asset_type": asset_type,
                        "status": "AVAILABLE",
                        "site_type": registration.site_type,
                    },
                    ensure_ascii=False,
                ),
                actor,
                created_at,
            ),
        )
    return {
        "asset_code": asset_code,
        "registration_status": "REGISTERED",
        "asset_type": asset_type,
        "status": "AVAILABLE",
        "site_type": registration.site_type,
    }


@app.get("/api/parts")
def list_parts():
    with get_db() as conn:
        parts = conn.execute("SELECT * FROM parts ORDER BY name").fetchall()
        recs = conn.execute("SELECT * FROM records ORDER BY date").fetchall()
        prcs = conn.execute("SELECT * FROM prices ORDER BY date").fetchall()
    recs_by: dict[str, list] = {}
    for r in recs:
        recs_by.setdefault(r["part_id"], []).append({"date": r["date"], "qty": r["qty"]})
    price_by: dict[str, list] = {}
    for r in prcs:
        price_by.setdefault(r["part_id"], []).append({"date": r["date"], "price": r["price"]})
    return [
        {
            "id": p["id"], "name": p["name"], "category": p["category"],
            "idc": p["idc"], "safety": p["safety"],
            "records": recs_by.get(p["id"], []),
            "prices": price_by.get(p["id"], []),
        }
        for p in parts
    ]


@app.post("/api/parts", status_code=201)
def create_part(p: PartIn, _actor: str = Depends(require_admin)):
    pid = "p" + str(int(time.time() * 1000))
    with get_db() as conn:
        conn.execute(
            "INSERT INTO parts (id, name, category, idc, safety, price) VALUES (?,?,?,?,?,?)",
            (pid, p.name, p.category, p.idc, p.safety, p.price),
        )
    return {"id": pid}


@app.patch("/api/parts/{pid}")
def update_part(
    pid: str,
    patch: PartPatch,
    _actor: str = Depends(require_admin),
):
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not fields:
        return {"ok": True}
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE parts SET {sets} WHERE id = ?", (*fields.values(), pid)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "part not found")
    return {"ok": True}


@app.delete("/api/parts/{pid}")
def delete_part(pid: str, _actor: str = Depends(require_admin)):
    with get_db() as conn:
        conn.execute("DELETE FROM parts WHERE id = ?", (pid,))
    return {"ok": True}


@app.put("/api/parts/{pid}/records")
def upsert_record(
    pid: str,
    rec: RecordIn,
    _actor: str = Depends(require_admin),
):
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM parts WHERE id = ?", (pid,)).fetchone()
        if not exists:
            raise HTTPException(404, "part not found")
        conn.execute(
            """INSERT INTO records (part_id, date, qty) VALUES (?,?,?)
               ON CONFLICT(part_id, date) DO UPDATE SET qty = excluded.qty""",
            (pid, rec.date, rec.qty),
        )
    return {"ok": True}


@app.put("/api/parts/{pid}/prices")
def upsert_price(
    pid: str,
    pr: PriceIn,
    _actor: str = Depends(require_admin),
):
    """견적 날짜별 단가 입력/갱신 (같은 날짜면 덮어씀)."""
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM parts WHERE id = ?", (pid,)).fetchone()
        if not exists:
            raise HTTPException(404, "part not found")
        conn.execute(
            """INSERT INTO prices (part_id, date, price) VALUES (?,?,?)
               ON CONFLICT(part_id, date) DO UPDATE SET price = excluded.price""",
            (pid, pr.date, pr.price),
        )
    return {"ok": True}


# ---------- 정적 페이지 ----------
@app.get("/health")
def health():
    with get_db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ready"}


@app.get("/")
def landing():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/app")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/mobile")
def mobile():
    return FileResponse(os.path.join(BASE_DIR, "mobile.html"), headers={"Cache-Control": "no-cache"})


@app.get("/a/{asset_code}")
def asset_deep_link(asset_code: str):
    return FileResponse(os.path.join(BASE_DIR, "mobile.html"), headers={"Cache-Control": "no-cache"})


@app.get("/mobile.css")
def mobile_styles():
    return FileResponse(os.path.join(BASE_DIR, "mobile.css"), media_type="text/css")


@app.get("/dashboard.css")
def dashboard_styles():
    return FileResponse(os.path.join(BASE_DIR, "dashboard.css"), media_type="text/css")


@app.get("/dashboard.js")
def dashboard_script():
    return FileResponse(
        os.path.join(BASE_DIR, "dashboard.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/mobile.js")
def mobile_script():
    return FileResponse(
        os.path.join(BASE_DIR, "mobile.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest")
def web_manifest():
    return FileResponse(
        os.path.join(BASE_DIR, "manifest.webmanifest"),
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        os.path.join(BASE_DIR, "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/icon-192.svg")
def icon_192():
    return FileResponse(os.path.join(BASE_DIR, "icon-192.svg"), media_type="image/svg+xml")


@app.get("/icon-512.svg")
def icon_512():
    return FileResponse(os.path.join(BASE_DIR, "icon-512.svg"), media_type="image/svg+xml")


init_db()
