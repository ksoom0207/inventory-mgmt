# 인프라 부품 재고·자산 추적 시스템 기획서

## 1. 프로젝트 목적

HDD, SSD, RAM, NIC, HBA, GPU, PSU 등 인프라 부품에 대해 다음 정보를 관리한다.

- 어떤 부품이 있는가
- 몇 개 있는가
- IDC 또는 Office 중 어디에 있는가
- 세부 위치가 어디인가
- 현재 어느 서버나 장비에서 사용되고 있는가
- 과거 어디에서 사용되었는가
- 장애, RMA, 폐기 등 현재 상태가 무엇인가

핵심 목표는 **현장에서는 빠르게 등록하고, 필요한 상세정보는 이후에 보완할 수 있는 자산관리 시스템**을 만드는 것이다.

---

# 2. 핵심 운영 원칙

시스템의 운영 원칙은 다음과 같다.

```text
1. QR 라벨을 미리 발급한다.
2. 부품에 QR을 붙인다.
3. 휴대폰으로 QR을 스캔한다.
4. 최소 정보만 입력하여 등록한다.
5. 상세 정보는 나중에 추가한다.
6. 이후 이동, 장착, 탈착, 장애 등의 이력을 계속 기록한다.
```

즉 자산 등록 단계에서 많은 정보를 강제로 입력하지 않는다.

현장에서 가장 중요한 것은 **자산을 시스템에 빠르게 등록하는 것**이다.

---

# 3. 관리 대상

초기 관리 대상은 다음과 같다.

```text
HDD
SSD
RAM
NIC
HBA / RAID Controller
GPU
PSU
```

향후 다음 항목으로 확장할 수 있다.

```text
Server
Switch
SFP / QSFP
Cable
Appliance
기타 장비 및 부품
```

---

# 4. Asset ID

모든 자산은 고유 Asset ID를 가진다.

형식:

```text
ASSET-000001
ASSET-000002
ASSET-000003
...
```

자산 종류에 따라 번호 체계를 나누지 않는다.

예를 들어 다음과 같이 사용하지 않는다.

```text
DISK-000001
RAM-000001
GPU-000001
```

대신 모든 자산을 하나의 번호 체계로 관리한다.

```text
ASSET-000001
```

실제 자산 종류는 DB에서 관리한다.

장점:

- QR을 미리 대량 출력할 수 있음
- 어떤 부품에 붙일지 사전에 정할 필요 없음
- 새로운 자산 종류가 추가되어도 QR 체계를 변경할 필요 없음

---

# 5. QR 라벨 운영

## 5.1 QR 선발급

QR 라벨은 자산 등록 전에 미리 출력할 수 있다.

예:

```text
ASSET-000101
ASSET-000102
ASSET-000103
...
ASSET-000200
```

100장 또는 500장 단위로 미리 출력해 둘 수 있다.

---

## 5.2 QR 내용

QR에는 상세 자산정보를 넣지 않는다.

다음과 같은 URL만 저장한다.

```text
https://inventory.example.com/a/ASSET-000042
```

또는 내부적으로 Asset ID만 사용할 수도 있다.

```text
ASSET-000042
```

권장 방식은 URL 방식이다.

휴대폰 기본 카메라로 바로 접근할 수 있기 때문이다.

---

## 5.3 QR 라벨 예시

```text
┌─────────────────────┐
│                     │
│      QR CODE        │
│                     │
│   ASSET-000042      │
│                     │
└─────────────────────┘
```

QR 아래에는 사람이 직접 읽을 수 있도록 Asset ID도 출력한다.

---

# 6. QR 상태

QR Asset ID는 다음 상태를 가진다.

### UNASSIGNED

QR만 발급된 상태.

```text
ASSET-000042

상태:
미등록
```

아직 어떤 부품에도 연결되지 않은 QR이다.

---

### REGISTERED

최소 정보가 등록된 상태.

예:

```text
ASSET-000042

Type
SSD

Site
IDC
```

정상적인 자산으로 관리된다.

---

### VERIFIED

상세정보까지 확인된 상태.

예:

```text
ASSET-000042

SSD
Samsung PM9A3
3.84TB

Serial
S6XXXXXX

Site
IDC

Location
IDC-A / Rack-03 / Server-12 / Bay-04
```

---

# 7. 자산 등록 UX

자산 등록은 최대한 단순하게 구성한다.

새로운 SSD가 입고된 경우:

```text
SSD 입고
   ↓
QR 스티커 부착
   ↓
휴대폰 카메라로 QR 스캔
   ↓
Cloudflare Access 인증
   ↓
미등록 자산 화면
   ↓
최소 정보 입력
   ↓
등록 완료
```

---

# 8. 최초 등록 화면

QR을 처음 스캔하면 다음 화면을 표시한다.

```text
┌────────────────────────┐
│ ASSET-000042           │
│                        │
│ 미등록 자산입니다.     │
│                        │
│ 자산 종류 *            │
│ [ SSD             ▼ ] │
│                        │
│ 위치 *                 │
│ [ IDC ] [ Office ]     │
│                        │
│       [ 등록 ]         │
└────────────────────────┘
```

최초 등록 필수값은 최대한 줄인다.

---

# 9. 최초 등록 필수 정보

필수:

```text
Asset ID
Asset Type
Site Type
```

Asset ID는 QR을 통해 자동 입력된다.

따라서 사용자가 실제로 입력하는 것은 사실상 두 가지다.

```text
자산 종류

+

IDC / Office
```

예:

```text
ASSET-000042

자산 종류
SSD

위치
IDC

[등록]
```

이것으로 등록이 완료된다.

---

# 10. 선택 입력 정보

다음 정보는 최초 등록 시 입력하지 않아도 된다.

```text
Manufacturer
Model
Serial Number
Capacity

Detailed Location

IDC 이름
Room
Rack
Server
Slot / Bay

Office
Floor
Room
Shelf

구매일
보증기간
구매처
메모
사진
```

필요한 경우 등록 직후 또는 나중에 수정한다.

---

# 11. 등록 완료 화면

최소 등록이 끝나면 바로 자산 상세 화면으로 이동한다.

```text
ASSET-000042

SSD

상태
AVAILABLE

Site
IDC

상세 위치
미지정

제조사
미입력

Model
미입력

Serial
미입력

Capacity
미입력

[정보 추가]

[이동]

[사용처 등록]
```

---

# 12. 정보 완성도

상세정보가 얼마나 등록되어 있는지 표시할 수 있다.

예:

```text
ASSET-000042

정보 완성도
40%
```

미입력 항목:

```text
Serial
Model
Capacity
상세 위치
```

이를 통해 현장에서는 빠르게 등록하고, 이후 담당자가 상세정보를 정리할 수 있다.

---

# 13. 위치 관리 원칙

모든 자산은 다음 중 하나를 반드시 선택한다.

```text
IDC

또는

Office
```

즉 `Site Type`은 필수이다.

---

# 14. IDC 위치

IDC를 선택한 경우 하위 위치는 전부 선택사항이다.

예:

```text
Site
IDC                 필수

IDC
IDC-A               선택

Room
Server Room 1       선택

Rack
Rack-03             선택

Server
Server-12           선택

Slot
Bay-04              선택
```

따라서 다음 상태도 정상적으로 허용된다.

```text
ASSET-000042

Site
IDC

Detailed Location
미지정
```

---

# 15. Office 위치

Office 역시 하위 위치는 선택사항이다.

```text
Site
Office              필수

Office
본사                 선택

Floor
5F                   선택

Room
창고                 선택

Shelf
Shelf-A              선택
```

예:

```text
ASSET-000105

Site
Office

Detailed Location
본사 / 5F / 창고 / Shelf-A
```

---

# 16. 위치 입력 방식

Asset을 등록하거나 이동할 때 가장 먼저 Site를 선택한다.

```text
현재 위치 *

[ IDC ]

[ Office ]
```

IDC 선택:

```text
IDC            [선택]
Room           [선택]
Rack           [선택]
Server         [선택]
Slot / Bay     [선택]
```

Office 선택:

```text
Office         [선택]
Floor          [선택]
Room           [선택]
Shelf          [선택]
```

세부 항목은 입력하지 않아도 저장할 수 있다.

---

# 17. 자산 상태

각 자산은 다음 상태를 가진다.

```text
AVAILABLE
사용 가능

IN_USE
사용 중

RESERVED
사용 예정

FAULTY
장애

RMA
RMA 진행 중

REPAIR
수리 중

DISPOSED
폐기

LOST
분실

UNKNOWN
상태 확인 필요
```

신규 등록 기본 상태는:

```text
AVAILABLE
```

로 한다.

따라서 등록할 때 사용자가 상태까지 선택할 필요는 없다.

---

# 18. 부품 상세 정보

상세정보는 등록 이후 필요할 때 추가한다.

예:

```text
ASSET-000042

Type
SSD

Manufacturer
Samsung

Model
PM9A3

Capacity
3.84TB

Serial
S6XXXXXX

Interface
NVMe

Status
AVAILABLE

Site
IDC
```

---

# 19. Manufacturer Serial Number

내부 자산번호와 제조사 Serial은 별도로 관리한다.

```text
Asset ID
ASSET-000042

Manufacturer Serial
S6XXXXXX
```

Asset ID는 내부 관리용 식별자이고,

Serial Number는 실제 제조사 제품 식별자이다.

---

# 20. 재고 현황

대시보드에서는 전체 현황을 확인한다.

예:

```text
전체 자산
1,284

IDC
947

Office
337
```

그리고 부품 종류별로 조회한다.

```text
IDC

SSD
132

HDD
211

RAM
284

NIC
47

GPU
31
```

---

# 21. 사용 가능 재고 조회

실제 현장에서 중요한 것은 전체 수량보다 사용 가능한 재고다.

예:

```text
SSD / 3.84TB

전체
32

사용 중
19

사용 가능
10

장애
2

RMA
1
```

---

# 22. 검색 기능

다음 항목으로 검색할 수 있다.

```text
Asset ID

Serial Number

Asset Type

Manufacturer

Model

Capacity

Site

Rack

Server

Status
```

예:

```text
검색

PM9A3
```

결과:

```text
Samsung PM9A3

전체 32

IDC
27

Office
5

AVAILABLE
10

IN_USE
19

FAULTY
2

RMA
1
```

---

# 23. 자산 이동

QR을 스캔한 후 이동 버튼을 누른다.

```text
ASSET-000042

현재 위치

IDC
Rack-03

[이동]
```

새 위치:

```text
Site *

[ IDC ]

[ Office ]
```

세부 위치는 선택사항이다.

---

# 24. 이동 예시

기존:

```text
IDC
Rack-03
```

이동 후:

```text
Office
```

이 경우 세부 위치를 모르더라도 정상적으로 처리한다.

이력:

```text
2026-09-26 15:30

ASSET-000042

MOVE

FROM
IDC / Rack-03

TO
Office
```

---

# 25. 서버 장착

부품이 서버에 사용되는 경우 사용처를 연결한다.

예:

```text
ASSET-000042

SSD

[사용처 등록]
```

사용처:

```text
Server
SERVER-00032

Slot
Bay-04
```

결과:

```text
ASSET-000042

Status
IN_USE

Site
IDC

Used By
SERVER-00032

Slot
Bay-04
```

---

# 26. 탈착

서버에서 부품을 제거할 경우:

```text
ASSET-000042

[탈착]
```

다음 위치를 선택한다.

```text
IDC

또는

Office
```

필요하면 상세 위치도 지정한다.

탈착 이유:

```text
교체
장애
정기점검
재배치
기타
```

---

# 27. 자산 이력

자산의 모든 변경사항은 기록한다.

예:

```text
ASSET-000042

2026-09-01
등록

SSD
IDC

↓

2026-09-03
상세정보 추가

Samsung PM9A3
3.84TB

↓

2026-09-10
서버 장착

SERVER-00032
Bay-04

↓

2026-12-02
장애 발생

↓

2026-12-02
탈착

↓

2026-12-03
Office 이동

↓

2026-12-05
RMA 처리
```

---

# 28. Audit Log

모든 작업에는 다음 내용을 기록한다.

```text
누가

언제

어떤 자산을

무엇을 변경했고

기존 값이 무엇이고

변경된 값이 무엇인지
```

예:

```text
User
sumin

Asset
ASSET-000042

Action
MOVE

Before
IDC

After
Office

Timestamp
2026-09-26 15:30
```

Audit Log는 일반 사용자가 수정하거나 삭제할 수 없도록 한다.

---

# 29. 일괄 등록

동일한 제품이 여러 개 들어오는 경우 일괄 등록 기능을 제공한다.

예:

```text
20개 SSD 입고
```

공통 정보:

```text
Asset Type
SSD

Manufacturer
Samsung

Model
PM9A3

Capacity
3.84TB

Site
IDC
```

그다음 QR을 연속 스캔한다.

```text
ASSET-000101
ASSET-000102
ASSET-000103
...
ASSET-000120
```

공통 정보를 한꺼번에 적용한다.

Serial은 각 자산별로 나중에 입력하거나 스캔한다.

---

# 30. 대량 QR 발급

관리자는 QR 번호를 대량 생성할 수 있다.

예:

```text
시작 번호
ASSET-000100

수량
100
```

생성:

```text
ASSET-000100
~
ASSET-000199
```

이후 PDF 또는 라벨 프린터 형식으로 출력한다.

---

# 31. 재고 조사

재고 조사 시 먼저 장소를 선택한다.

```text
재고 조사

[ IDC ]

[ Office ]
```

필요하면 세부 위치도 선택한다.

예:

```text
IDC
IDC-A
Rack-03
```

이후 QR을 연속 스캔한다.

```text
ASSET-000010

ASSET-000021

ASSET-000042

ASSET-000105
```

결과:

```text
예상 자산
42개

확인
40개

미확인
2개

예상 위치와 다른 자산
1개
```

---

# 32. 세부 위치 미지정 관리

세부 위치가 없는 자산만 따로 조회할 수 있다.

예:

```text
IDC
상세 위치 미지정
17개

Office
상세 위치 미지정
8개
```

필터:

```text
[ 세부 위치 미지정만 보기 ]
```

이를 통해 나중에 위치를 정리할 수 있다.

---

# 33. 접근 구조

시스템은 인터넷에 직접 노출하지 않는다.

구조:

```text
휴대폰 / PC
     │
     │ HTTPS
     ▼
Cloudflare Zero Trust
     │
     ├─ Access
     │
     └─ Authentication
     │
     ▼
Cloudflare Tunnel
     │
     ▼
Inventory Application
     │
     ▼
FastAPI
     │
     ▼
PostgreSQL
```

내부 서버에는 인터넷 인바운드 포트를 열지 않는다.

---

# 34. 사용자 인증

Cloudflare Access를 통해 허가된 사용자만 접속할 수 있도록 한다.

예:

```text
inventory.example.com
```

접근:

```text
허가된 회사 사용자
    ↓
Cloudflare Access 인증
    ↓
Inventory
```

Google Workspace 또는 Microsoft Entra ID와 연동할 수 있도록 한다.

---

# 35. 애플리케이션 권한

Cloudflare Access는 시스템 접근 여부를 결정한다.

애플리케이션에서는 실제 작업 권한을 별도로 관리한다.

### Admin

```text
자산 관리

QR 대량 발급

위치 관리

사용자 권한 관리

삭제 / 폐기

전체 Audit Log
```

### Operator

```text
자산 등록

상세정보 수정

이동

장착

탈착

장애 처리

재고 조사
```

### Viewer

```text
자산 조회

재고 조회

위치 조회

이력 조회
```

---

# 36. 시스템 구성

```text
        Smartphone
            │
        QR Camera
            │
            ▼
     Web / PWA Frontend
            │
            ▼
   Cloudflare Access
            │
            ▼
   Cloudflare Tunnel
            │
            ▼
          FastAPI
            │
            ▼
       PostgreSQL
```

초기에는 별도의 Android/iOS 앱보다 PWA 형태를 우선한다.

장점:

```text
앱 설치 부담 감소

Android / iPhone 모두 사용

휴대폰 카메라 활용

웹 배포만으로 업데이트 가능

QR URL을 바로 열 수 있음
```

---

# 37. DB 기본 구조

## assets

```text
id

asset_code

asset_type

status

site_type

location_id

manufacturer

model

serial_number

capacity

parent_asset_id

registration_status

created_at

updated_at
```

필수 필드:

```text
asset_code NOT NULL

asset_type NOT NULL

site_type NOT NULL
```

나머지는 NULL을 허용한다.

---

# 38. registration_status

```text
UNASSIGNED

REGISTERED

VERIFIED
```

예:

```text
ASSET-000042

registration_status
REGISTERED
```

---

# 39. locations

```text
id

site_type

name

location_type

parent_location_id
```

location_type 예:

```text
IDC

ROOM

RACK

SERVER

SLOT

OFFICE

FLOOR

SHELF
```

---

# 40. asset_movements

```text
id

asset_id

action

from_site_type

from_location_id

to_site_type

to_location_id

user_id

memo

created_at
```

---

# 41. assignments

자산의 실제 사용처를 관리한다.

```text
id

asset_id

target_asset_id

slot

installed_at

removed_at

installed_by

removed_by
```

예:

```text
ASSET-000042

↓

SERVER-00032

↓

Bay-04
```

---

# 42. audit_logs

```text
id

user_id

asset_id

action

before_data

after_data

timestamp
```

---

# 43. 대시보드

메인 화면에서는 복잡한 정보보다 운영에 필요한 수치를 먼저 보여준다.

```text
전체 자산
1,284

IDC
947

Office
337
```

추가:

```text
사용 가능
324

사용 중
876

장애
43

RMA
12
```

관리 필요 항목:

```text
상세정보 미완성

세부 위치 미지정

Serial 미등록

장애 자산

RMA 진행 중
```

---

# 44. 모바일 홈 화면

모바일에서는 복잡한 메뉴보다 작업 중심으로 구성한다.

```text
┌─────────────────────┐
│ Inventory           │
│                     │
│   [ QR 스캔 ]       │
│                     │
│   [ 자산 검색 ]     │
│                     │
│   [ 재고 현황 ]     │
│                     │
│   [ 재고 조사 ]     │
│                     │
│   [ 최근 작업 ]     │
└─────────────────────┘
```

가장 큰 버튼은 `QR 스캔`으로 한다.

---

# 45. QR 스캔 후 동작

## 미등록 QR

```text
QR Scan

↓

ASSET-000042

↓

미등록

↓

자산 종류 선택

↓

IDC / Office 선택

↓

등록
```

---

## 등록된 QR

```text
QR Scan

↓

ASSET-000042

↓

자산 상세정보

↓

조회
이동
장착
탈착
정보수정
```

---

# 46. MVP 범위

초기 버전에서는 다음 기능에 집중한다.

```text
Cloudflare Access 인증

QR 대량 생성

QR 출력

QR 스캔

간편 자산 등록

자산 상세정보 수정

IDC / Office 위치 관리

재고 조회

자산 검색

이동

장착

탈착

상태 변경

자산 이력

Audit Log
```

---

# 47. Phase 2

운영 이후 필요에 따라 추가한다.

```text
Excel Import / Export

제품 일괄 등록

Serial Barcode 스캔

사진 첨부

RMA 관리

구매 정보

보증기간

재고 부족 알림

정기 재고 조사
```

---

# 48. Phase 3

서버 정보를 자동으로 수집할 수 있다.

예:

```text
smartctl

nvme list

lsblk

lspci

dmidecode
```

Agent가 다음 정보를 발견한다.

```text
Server-12

Samsung PM9A3

Serial
S6XXXXXX
```

Inventory의 Serial과 비교한다.

```text
S6XXXXXX

↓

ASSET-000042

↓

현재 서버
Server-12
```

수동으로 등록한 정보와 실제 서버 상태가 일치하는지 검증할 수 있다.

---

# 49. 최종 사용 흐름

가장 일반적인 현장 작업은 다음 정도로 끝나야 한다.

```text
새 SSD 발견

↓

미리 출력한 QR 부착

↓

QR 스캔

↓

SSD 선택

↓

IDC 선택

↓

등록
```

이후 필요할 때:

```text
QR 스캔

↓

Serial 입력

↓

Model 입력

↓

Capacity 입력

↓

Rack / Server 위치 입력
```

즉 **자산 등록과 자산 정보 정리를 별개의 작업으로 분리한다.**

---

# 50. 최종 운영 원칙

시스템의 가장 중요한 원칙은 다음과 같다.

**“등록은 빠르게, 정보는 점진적으로, 이동과 사용 이력은 반드시 기록한다.”**

최소 등록 정보는:

```text
Asset ID
Asset Type
IDC / Office
```

뿐이다.

이를 통해 현장에서 등록 절차 때문에 재고관리 자체를 포기하게 되는 상황을 방지하고, 이후 필요한 수준까지 자산 정보를 점진적으로 완성할 수 있도록 한다.
