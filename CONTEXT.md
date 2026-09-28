# 인프라 재고 관리

IDC와 Office에 있는 인프라 부품을 개별 자산 단위로 식별하고, 현재 상태와 위치 및 사용 이력을 일관된 언어로 관리하는 업무 영역이다.

## Language

**자산 (Asset)**:
하나의 자산 ID와 QR 라벨로 개별 식별되는 물리적 부품 또는 장비.
_Avoid_: 품목, 재고 항목, Part

**자산 유형 (Asset Type)**:
자산을 분류하는 종류. 최초 유형은 SSD, HDD, MEMORY, NIC, HBA, RAID_CONTROLLER, GPU, PSU, SERVER, OTHER이다.
_Avoid_: 카테고리, 부품명, RAM, RAID_CONTROLLE

**자산 ID (Asset Identifier)**:
자산에 내부적으로 부여한 전역 고유 식별자. 일반 자산 ID, 서버 ID, 네트워크 장비 ID를 포함하며 제조사 Serial Number와는 별개다.
_Avoid_: Serial, 부품 ID

**일반 자산 ID (Asset ID)**:
서버와 네트워크 장비를 제외한 자산의 식별자. `ASSET-00000001`부터 독립적으로 순차 발급한다.
_Avoid_: 서버 ID, SVR

**서버 ID (Server ID)**:
SERVER 자산의 식별자. `SVR-00000001`부터 일반 자산 ID와 독립적으로 순차 발급한다.
_Avoid_: Server Asset ID, ASSET 서버

**네트워크 장비 ID (Network Equipment ID)**:
NETWORK 자산의 식별자. NET-00000001부터 다른 자산 ID와 독립적으로 순차 발급한다.

**미등록 라벨 (Unassigned Label)**:
자산 ID가 발급되었지만 아직 실제 자산에 연결되지 않은 QR 라벨.
_Avoid_: 미등록 자산

**등록 자산 (Registered Asset)**:
자산 유형과 Site가 확인되어 재고 원장에 포함된 자산.
_Avoid_: 등록 QR

**검증 자산 (Verified Asset)**:
Serial Number를 포함한 필수 상세정보가 실제 자산과 대조되어 확인된 등록 자산.
_Avoid_: 완성 자산

**Site**:
자산이 속한 최상위 장소 구분으로, 현재는 IDC 또는 Office 중 하나이다.
_Avoid_: 위치, Location

**상세 위치 (Detailed Location)**:
Site 아래에서 자산의 실제 보관 또는 장착 지점을 나타내는 계층적 장소. 등록 시에는 지정하지 않아도 된다.
_Avoid_: Site

**현재 위치 (Current Location)**:
자산이 지금 존재하는 Site와 상세 위치. 이동이 확정될 때 새 위치로 대체된다.
_Avoid_: 위치 이력

**위치 이력 (Location History)**:
자산이 거쳐 간 이전 위치와 이동 시점의 변경 기록. 현재 위치가 바뀌어도 삭제되지 않는다.
_Avoid_: 현재 위치

**이동 (Movement)**:
자산의 현재 위치를 다른 위치로 변경하고 이전 위치를 위치 이력에 남기는 작업.
_Avoid_: 위치 수정, 이전 위치 삭제

**사용처 (Assignment)**:
자산이 현재 장착되거나 사용되는 대상 장비와 슬롯의 연결 관계.
_Avoid_: 위치, 이동

**장착 (Installation)**:
자산을 SERVER 자산의 사용처와 선택적 슬롯에 연결하는 작업. 자산당 활성 사용처는 하나만 존재한다.
_Avoid_: 위치 수정, 서버 이동

**탈착 (Removal)**:
활성 사용처를 종료하고 자산의 새 현재 위치를 정하는 작업. 종료된 사용처와 이동 이력은 삭제하지 않는다.
_Avoid_: 사용처 삭제

**자산 상태 (Asset Status)**:
자산의 현재 운용 가능성과 처리 단계를 나타내는 분류. 사용 가능, 사용 중, 예약, 장애, RMA, 수리 중, 폐기, 분실, 확인 필요를 포함한다.
_Avoid_: 등록 상태

**장애 자산 (Faulty Asset)**:
자산 상태가 장애인 자산. 정상 재고와 구분해 별도로 집계하지만 재고 원장과 이력에서는 삭제하지 않는다.
_Avoid_: 고장항목, 폐기 자산

**등록 상태 (Registration Status)**:
QR 라벨과 자산 정보의 확정 수준. 미등록, 등록, 검증으로 구분한다.
_Avoid_: 자산 상태

**재고 원장 (Inventory Ledger)**:
등록된 개별 자산 전체의 현재 상태와 이력을 보존하는 기준 기록.
_Avoid_: 날짜별 수량, 재고 스냅샷

**전체 재고 현황 (Inventory Overview)**:
재고 원장을 자산 유형, Site, 자산 상태 등의 기준으로 집계해 보여주는 조회 결과.
_Avoid_: 재고 원장

**재고 조사 (Stocktake)**:
특정 위치의 기대 자산과 현장에서 실제 스캔한 자산을 대조하는 작업.
_Avoid_: 재고 등록, 수량 입력

**견적 품목 (Quote Item)**:
구매 가격을 비교하려는 부품 종류. 실제 재고의 개별 자산과는 별개다.
_Avoid_: 등록 자산, 구매처 견적

**기준 단가 (Reference Price)**:
견적 품목에 날짜별로 기록한 공급사 미지정 참고 가격.
_Avoid_: 구매처 견적, 확정 구매가

**구매처 견적 (Supplier Offer)**:
한 공급사가 특정 견적 품목·수량에 대해 제시한 가격, 납기, 유효기간 및 가격 기준의 기록.
_Avoid_: 기준 단가, 발주, 고객 제출 견적서
