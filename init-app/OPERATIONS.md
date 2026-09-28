# Inventory 운영 안내서

## 1. Cloudflare Access와 권한

Cloudflare Tunnel의 원본 서버는 외부에 직접 노출하지 않는다. Access가 전달하는 `Cf-Access-Authenticated-User-Email` 헤더를 앱이 사용하므로, 원본 서버에 직접 접속하면 헤더를 위조할 수 있다.

`.env`에 다음 값을 설정한다.

```dotenv
INVENTORY_AUTH_REQUIRED=true
INVENTORY_ADMIN_EMAILS=admin@example.com
INVENTORY_OPERATOR_EMAILS=operator1@example.com,operator2@example.com
INVENTORY_PUBLIC_BASE_URL=https://inventory.example.com
```

`INVENTORY_PUBLIC_BASE_URL`은 QR에 저장될 외부 HTTPS 주소다. 영영 환경에서는 반드시 설정해 프록시 내부 주소가 QR에 들어가지 않게 한다.

- 관리자: Asset ID 라벨 발급과 모든 자산 작업
- 작업자: 등록, 이동, 상태 변경, 장착·탈착
- 조회자: Access에 로그인한 나머지 사용자. API 조회만 가능

## 2. 백업

SQLite 온라인 백업 API를 사용하므로 서비스를 중단하지 않아도 된다.

```bash
mkdir -p backups
docker compose exec -T inventory python -c "import sqlite3; source=sqlite3.connect('/data/inventory.db'); target=sqlite3.connect('/data/inventory-backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp inventory:/data/inventory-backup.db "backups/inventory-$(date +%F-%H%M%S).db"
```

매일 1회 백업하고, 최소 30일분을 서버와 다른 저장소에 유지한다.

## 3. 복구

```bash
docker compose cp backups/inventory-YYYY-MM-DD-HHMMSS.db inventory:/data/restore.db
docker compose stop inventory
docker compose run --rm --no-deps --entrypoint python inventory -c "import sqlite3, shutil; db=sqlite3.connect('/data/restore.db'); result=db.execute('PRAGMA integrity_check').fetchone()[0]; db.close(); assert result == 'ok', result; shutil.copyfile('/data/restore.db', '/data/inventory.db')"
docker compose up -d inventory
curl --fail http://localhost:3004/health
```

복구 중에는 쓰기를 막기 위해 컨테이너를 중단한다. 무결성 검사가 실패하면 기존 DB를 덮어쓰지 않는다.

## 4. 모니터링

```bash
curl --fail http://localhost:3004/health
docker inspect --format '{{json .State.Health}}' idc-inventory
docker compose logs --since=30m inventory
```

`/health`는 앱과 SQLite 연결이 정상이면 `200` 응답을 보낸다. 1분 내 2회 연속 실패하면 운영자에게 알림하도록 외부 모니터에 등록한다.
