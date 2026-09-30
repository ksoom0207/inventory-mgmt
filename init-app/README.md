# IDC 부품 재고 현황 — 서버 저장형 (Docker)

재고 데이터를 **서버(SQLite)** 에 저장하고, 모든 사용자가 같은 데이터를 공유합니다.
FastAPI 하나가 재고 현황 앱(`index.html`)과 재고 API를 함께 서빙합니다.

## 파일 구성
- `index.html` — 재고 현황 웹 앱 (서버 API 연동)
- `dashboard.js`, `purchase-quotes.js` — 재고 화면과 공급사 견적 비교 화면
- `mobile.html`, `mobile.css`, `mobile.js` — 스마트폰용 QR 자산 등록 PWA
- `manifest.webmanifest`, `sw.js` — PWA 설치 정보와 앱 셸 캐시
- `app.py` — FastAPI 백엔드 (부품/재고 CRUD + SQLite)
- `requirements.txt` — 파이썬 의존성
- `Dockerfile` — 컨테이너 이미지 정의
- `docker-compose.yml` — 포트 매핑 + 데이터 볼륨

## 실행 방법

### docker compose (권장)
```bash
docker compose up -d --build
```
브라우저에서 http://localhost:3004 접속. 재고 웹 앱은 `/app`에서 열립니다.

- 전체 재고 화면: http://localhost:3004/app
- 모바일 등록 PWA: http://localhost:3004/mobile
- QR 딥링크 예시: http://localhost:3004/a/ASSET-00000001

중지:
```bash
docker compose down          # 컨테이너만 중지 (데이터 유지)
docker compose down -v       # 데이터 볼륨까지 삭제
```

### docker 명령만 사용
```bash
docker build -t idc-inventory .
docker run -d --name idc-inventory -p 8080:80 -v inventory-data:/data idc-inventory
```

포트 변경: `docker-compose.yml`의 `8080:80`에서 앞 숫자를 수정.

## 데이터 저장

전체 재고 화면은 SSD·HDD를 용량·인터페이스·폼팩터별로 묶습니다. 단위 통일, 사양 미입력 처리 및 다른 부품의 권장 기준은 [재고 집계 기준](../docs/inventory-grouping.md)을 참고하세요.
- SQLite 파일(`/data/inventory.db`)에 저장되며, `inventory-data` 볼륨으로 영속화됩니다.
- 컨테이너를 재시작하거나 이미지를 다시 빌드해도 데이터가 유지됩니다.
- 접속하는 모든 브라우저/사용자가 같은 재고 데이터를 봅니다.
- DB가 비어 있으면 시작 시 샘플 부품 6종이 자동으로 들어갑니다. 실제 사용 시 "부품 관리"에서 삭제 후 추가하세요.

## API (참고)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/parts` | 전체 부품 + 재고 기록 |
| POST | `/api/parts` | 부품 추가 |
| PATCH | `/api/parts/{id}` | 부품 정보(이름/카테고리/위치/안전재고) 수정 |
| DELETE | `/api/parts/{id}` | 부품 삭제 (재고 기록 함께 삭제) |
| PUT | `/api/parts/{id}/records` | 날짜별 재고 입력/갱신 (같은 날짜면 덮어씀) |

### 개별 자산 API

자산 상세의 `정보 수정`에서 Serial, 제조사, 모델을 입력·수정할 수 있습니다. 모두 선택값이며 비우고 저장하면 삭제됩니다. `PATCH /api/assets/{asset_code}/details`로 저장하고 자산 상세 API로 다시 조회합니다. 기존 DB에는 시작 시 필요한 컬럼이 자동 추가됩니다.

모바일 상단의 `전체 재고` 링크로 `/app`에 이동합니다. `정보 수정`에는 유형별 사양이 표시됩니다: SSD/HDD 용량(GB/TB)·인터페이스, 메모리 용량·DDR·MT/s, NIC/네트워크 장비 포트당 Gbps·포트 수, GPU 메모리(GB), PSU 출력(W), HBA 인터페이스·속도·포트 수, RAID 컨트롤러 인터페이스·캐시·포트 수. 서버 및 기타 부품을 포함한 모든 유형에 추가 사양 메모를 지원합니다. 용량은 입력한 숫자와 단위를 그대로 보존하며 자동 환산하지 않습니다.

사양은 상세 수정 API의 `specifications` 객체로 전달합니다. 예: `{"capacity":{"value":1.92,"unit":"TB"},"interface":"SAS"}`. 이 객체를 생략하면 기존 사양을 유지하고, `{}`로 전달하면 사양을 비웁니다. 허용 항목과 단위는 `GET /api/asset-specifications`에서 조회합니다.

모든 자산에 P/N(제조사 부품번호, `part_number`)을 입력할 수 있습니다. SSD/HDD는 디스크 크기·폼팩터(`disk_size`), 메모리는 RDIMM/LRDIMM/UDIMM 등의 종류(`memory_type`), NIC는 RJ45/SFP28 등의 커넥터(`connector`)를 사양에서 선택합니다. 모르면 미입력으로 두고, 목록에 없는 규격은 `기타`와 추가 사양 메모를 사용하세요.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/asset-labels` | Inventory 서버에서 QR용 Asset ID 일괄 발급 |
| POST | `/api/server-labels` | Inventory 서버에서 QR용 Server ID 일괄 발급 |
| POST | `/api/network-labels` | 네트워크 장비용 NET ID 일괄 발급 |
| GET | `/api/assets/{asset_code}` | 미등록 라벨 또는 등록 자산 조회 |
| POST | `/api/assets/{asset_code}/register` | 자산 유형과 Site로 최초 등록 |
| GET | `/api/assets` | 유형·Site·상태별 개별 자산 목록 |
| GET | `/api/inventory/summary` | 자산 유형·Site별 전체 재고 집계 |
| PATCH | `/api/assets/{asset_code}` | 자산 상태 변경 |
| POST | `/api/assets/{asset_code}/movements` | 현재 위치 이동 |
| GET | `/api/assets/{asset_code}/history` | 이동·장착·탈착·상태 이력 |
| POST | `/api/assets/{asset_code}/assignments` | SERVER 자산에 장착 |
| POST | `/api/assets/{asset_code}/assignments/remove` | SERVER 자산에서 탈착 |

일반 자산 ID는 `ASSET-00000001`, 서버 ID는 `SVR-00000001`부터 각각 독립적으로 발급됩니다. SVR 라벨은 등록 시 `SERVER` 유형으로 자동 지정됩니다. 허용 Site는 `IDC`, `OFFICE`입니다.

### 모바일 QR 스캔 참고

- 카메라는 HTTPS 또는 `localhost` 같은 보안 컨텍스트에서만 사용할 수 있습니다.
- 앱 내부 스캔은 브라우저의 `BarcodeDetector` QR 지원 여부에 따라 활성화됩니다.
- 미지원 브라우저에서는 휴대폰 기본 카메라로 QR 딥링크를 열거나 Asset ID를 직접 입력할 수 있습니다.

### A4 QR 라벨 출력

- 전체 재고 화면의 `QR 라벨` 탭에서 `일반 자산(ASSET)`, `서버(SVR)`, `네트워크 장비(NET)`를 선택해 발급·인쇄합니다.
- NET ID는 `NET-00000001`부터 독립 발급하며 등록 시 `NETWORK` 유형을 자동 지정합니다. 기존 SRV 라벨도 계속 조회·등록·장착할 수 있습니다.
- 폼텍 QR-3111의 20×20mm, 8열×13행, 104칸을 유지하고 각 칸에 10×10mm 라벨 4개를 2×2로 배치합니다. A4 한 장에 최대 416개이며 초과분은 다음 장으로 넘어갑니다.
- 각 칸 안에서는 왼쪽 위 → 오른쪽 위 → 왼쪽 아래 → 오른쪽 아래 순서로 서로 다른 ID를 넣습니다. QR은 8×8mm이고 아래에 ID를 표시합니다. 10mm 단위 재단은 직접 해야 합니다.
- 일부를 사용한 용지는 `첫 장 시작 칸`으로 빈칸을 건너뜁니다.
- `첫 장 시작 칸`은 20×20mm 칸 기준(1~104)으로, 해당 칸의 왼쪽 위부터 출력합니다. 용지 위치만 정하고 ID 순번에는 영향을 주지 않습니다. `ID 발급 및 라벨 생성`을 누를 때마다 새 번호가 발급됩니다.
- 이전 번호를 다시 인쇄하려면 `기존 라벨 재출력`에서 시작 ID·수량·첫 장 시작 칸을 지정하세요. 이미 발급된 연속 번호만 인쇄하며 새 ID를 발급하지 않습니다. `GET /api/asset-labels/reprint?start_code=ASSET-00000001&quantity=1`로 확인합니다.
- 브라우저 인쇄 설정에서 A4, 배율 100%, 여백 없음, 머리글·바닥글 표시 안 함을 선택합니다.

### 전체 재고와 견적 데이터

- 전체 재고 화면은 개별 `assets` 원장만 집계하며 수량 직접 입력 기능을 제공하지 않습니다.
- 기존 `parts`와 `records` 데이터는 계속 보관하지만 전체 재고 화면에서는 조회하지 않습니다.
- 견적은 별도 `quote_items`와 `quote_prices`로 최초 1회 복사되며 이후 재고 데이터와 독립적으로 관리됩니다.
- `구매 견적 비교` 탭의 기존 날짜별 단가는 공급사 미지정 기준 단가로 유지합니다. 공급사별 구매 견적은 별도 기록으로 저장하며, 품목 P/N, 공급사, 수량, 원화 단가, 배송비, 부가세 포함·별도 기준, 견적일, 유효기간, 납기를 입력합니다.
- 비교 금액은 `수량 × 단가 + 배송비`입니다. 유효한 견적 중 같은 품목·수량·부가세 기준끼리만 최저 금액을 표시합니다. 부가세 환산은 하지 않으며, 유효기간이 지난 견적과 견적일이 아직 오지 않은 견적은 최저 금액 판단에서 제외합니다.
- 견적 품목과 기준 단가, 공급사 견적은 각각 `GET /api/quotes`, `GET /api/purchase-offers?as_of=YYYY-MM-DD`에서 조회합니다. 공급사 견적은 `POST /api/purchase-offers`로 추가합니다. 기존 품목·단가 자료를 공급사 견적으로 자동 변환하지 않습니다.

## 테스트

```bash
python3 -m venv .venv
.venv/bin/pip install -r init-app/requirements-dev.txt
cd init-app
../.venv/bin/pytest -q
```

## 운영 참고

- Cloudflare Access 인증, 권한, 백업·복구, 모니터링 절차는 [OPERATIONS.md](OPERATIONS.md)를 따릅니다.
