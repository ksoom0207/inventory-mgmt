const API = "/api";
const ASSET_CODE_PATTERN = /^(?:ASSET|SVR|SRV|NET)-\d{8}$/;
const ASSET_TYPES = ["SSD", "HDD", "MEMORY", "NIC", "HBA", "RAID_CONTROLLER", "GPU", "PSU", "OTHER"];
const STATUS_LABELS = { AVAILABLE: "사용 가능", IN_USE: "사용 중", RESERVED: "예약", FAULTY: "장애", RMA: "RMA", REPAIR: "수리 중", DISPOSED: "폐기", LOST: "분실", UNKNOWN: "확인 필요" };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

let currentAsset = null;
let cameraStream = null;
let scanTimer = null;

const $ = (selector) => document.querySelector(selector);
const screens = [...document.querySelectorAll(".screen")];

function announce(message) {
  $("#app-status").textContent = message;
}

function showScreen(name, { focus = true } = {}) {
  stopScanner();
  screens.forEach((screen) => { screen.hidden = screen.id !== `screen-${name}`; });
  window.scrollTo({ top: 0, behavior: "auto" });
  if (focus) {
    requestAnimationFrame(() => $("#main").focus({ preventScroll: true }));
  }
}

function normalizeAssetCode(rawValue) {
  const value = String(rawValue || "").trim().toUpperCase();
  const pathMatch = value.match(/\/A\/((?:ASSET|SVR|SRV|NET)-\d{8})(?:[/?#]|$)/i);
  return pathMatch ? pathMatch[1].toUpperCase() : value;
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `요청 실패 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function lookupAsset(rawCode) {
  const code = normalizeAssetCode(rawCode);
  if (!ASSET_CODE_PATTERN.test(code)) {
    const error = $("#asset-code-error");
    error.textContent = "ASSET-, SVR- 또는 NET- 뒤에 숫자 8자리를 입력하세요.";
    $("#asset-code").setAttribute("aria-invalid", "true");
    $("#asset-code").focus();
    return;
  }

  $("#asset-code-error").textContent = "";
  $("#asset-code").removeAttribute("aria-invalid");
  showScreen("loading");
  try {
    const asset = await request(`/assets/${encodeURIComponent(code)}`);
    currentAsset = asset;
    if (asset.registration_status === "UNASSIGNED") showRegistration(asset);
    else showDetail(asset);
  } catch (error) {
    showError(error.status === 404
      ? `${code}는 Inventory 서버에서 발급되지 않은 자산 ID입니다.`
      : "서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.");
  }
}

function showRegistration(asset) {
  const isServer = /^(SVR|SRV|NET)-/.test(asset.asset_code);
  $("#register-code").textContent = asset.asset_code;
  $("#register-form").reset();
  $("#asset-type-fieldset").hidden = isServer;
  $("#server-registration-note").hidden = !isServer;
  $("#server-registration-note").textContent = asset.asset_code.startsWith("NET-") ? "NET 라벨은 NETWORK로 자동 등록됩니다." : "SVR 라벨은 SERVER로 자동 등록됩니다.";
  clearRegistrationErrors();
  showScreen("register");
  announce(`${asset.asset_code}, 미등록 라벨입니다.`);
}

let specificationSchema;
async function loadSpecificationSchema() {
  if (!specificationSchema) specificationSchema = await request("/asset-specifications");
  return specificationSchema;
}

function formatSpecifications(specifications, fields) {
  return Object.entries(specifications || {}).map(([key, value]) => {
    const label = fields?.[key]?.label || key;
    return `${label}: ${typeof value === "object" && value ? `${value.value} ${value.unit}` : value}`;
  }).join(" · ");
}

async function renderSpecifications(asset) {
  const element = $("#detail-specifications");
  element.textContent = "미입력";
  element.classList.add("muted");
  if (!Object.keys(asset.specifications || {}).length) return;
  let fields;
  try { fields = (await loadSpecificationSchema()).fields; } catch { /* Saved values remain readable offline. */ }
  if (currentAsset !== asset) return;
  element.textContent = formatSpecifications(asset.specifications, fields);
  element.classList.remove("muted");
}

function renderSpecificationForm(asset, schema) {
  const container = $("#edit-specifications");
  container.replaceChildren();
  for (const key of [...(schema.types[asset.asset_type] || []), "notes"]) {
    const field = schema.fields[key], saved = asset.specifications?.[key];
    const group = document.createElement("div");
    group.className = "form-field";
    const label = document.createElement("label");
    label.htmlFor = `spec-${key}`;
    label.textContent = field.label;
    const input = document.createElement(field.options ? "select" : field.text ? "textarea" : "input");
    input.id = `spec-${key}`;
    input.dataset.specKey = key;
    if (field.options) {
      input.add(new Option("미입력", ""));
      field.options.forEach(value => input.add(new Option(value, value)));
      input.value = saved || "";
    } else if (field.text) {
      input.maxLength = 1000;
      input.rows = 3;
      input.value = saved || "";
      input.placeholder = "예: ECC RDIMM, 포트 커넥터, CPU 사양";
    } else {
      input.type = "number";
      input.min = field.integer ? "1" : "0.000001";
      input.max = "1000000000";
      input.step = field.integer ? "1" : "any";
      input.inputMode = field.integer ? "numeric" : "decimal";
      input.value = saved?.value ?? "";
    }
    group.append(label, input);
    if (field.units) {
      const unitLabel = document.createElement("label");
      unitLabel.htmlFor = `spec-${key}-unit`;
      unitLabel.textContent = `${field.label} 단위`;
      const unit = document.createElement("select");
      unit.id = `spec-${key}-unit`;
      field.units.forEach(value => unit.add(new Option(value, value)));
      unit.value = saved?.unit || field.units[0];
      group.append(unitLabel, unit);
    }
    container.append(group);
  }
}

function readSpecificationForm() {
  const values = {};
  document.querySelectorAll("[data-spec-key]").forEach(input => {
    if (!input.value.trim()) return;
    const key = input.dataset.specKey, unit = document.getElementById(`spec-${key}-unit`);
    values[key] = unit ? { value: Number(input.value), unit: unit.value } : input.value.trim();
  });
  return values;
}

function showDetail(asset) {
  currentAsset = asset;
  renderSpecifications(asset);
  $("#detail-code").textContent = asset.asset_code;
  $("#detail-type").textContent = asset.asset_type;
  $("#detail-status").textContent = STATUS_LABELS[asset.status] || asset.status;
  $("#detail-site").textContent = asset.site_type;
  $("#detail-location").textContent = asset.detailed_location || "미지정";
  $("#detail-serial").textContent = asset.serial_number || "미입력";
  $("#detail-part-number").textContent = asset.part_number || "미입력";
  $("#detail-part-number").classList.toggle("muted", !asset.part_number);
  $("#detail-serial").classList.toggle("muted", !asset.serial_number);
  $("#detail-manufacturer-model").textContent = [asset.manufacturer, asset.model].filter(Boolean).join(" · ") || "미입력";
  $("#detail-manufacturer-model").classList.toggle("muted", !asset.manufacturer && !asset.model);
  const hasAssignment = Boolean(asset.assignment);
  $("#detail-assignment-row").hidden = !hasAssignment;
  $("#detail-assignment").textContent = hasAssignment ? `${asset.assignment.target_asset_code}${asset.assignment.slot ? ` / ${asset.assignment.slot}` : ""}` : "";
  $("#open-install").hidden = hasAssignment || asset.asset_type === "SERVER";
  $("#open-remove").hidden = !hasAssignment;
  showScreen("detail");
  announce(`${asset.asset_code} 자산 상세를 표시했습니다.`);
}

function showComplete(asset) {
  currentAsset = asset;
  $("#complete-summary").innerHTML = [
    ["자산 ID", asset.asset_code],
    ["자산 유형", asset.asset_type],
    ["현재 Site", asset.site_type],
    ["상태", STATUS_LABELS[asset.status] || asset.status],
  ].map(([term, value]) => `<div><dt>${term}</dt><dd>${value}</dd></div>`).join("");
  saveRecent(asset);
  showScreen("complete");
  announce(`${asset.asset_code} 등록이 완료되었습니다.`);
}

function showError(message) {
  $("#error-message").textContent = message;
  showScreen("error");
  announce(message);
}

function clearRegistrationErrors() {
  ["#asset-type-error", "#site-type-error", "#register-error"].forEach((id) => { $(id).textContent = ""; });
}

function renderAssetTypes() {
  $("#asset-type-options").innerHTML = ASSET_TYPES.map((type) => `
    <label class="choice-card">
      <input type="radio" name="asset_type" value="${type}">
      <span><strong>${type}</strong></span>
    </label>`).join("");
}

function getRecent() {
  try { return JSON.parse(localStorage.getItem("infrastock-recent") || "[]"); }
  catch { return []; }
}

function saveRecent(asset) {
  const recent = getRecent().filter((item) => item.asset_code !== asset.asset_code);
  recent.unshift({ ...asset, saved_at: new Date().toISOString() });
  localStorage.setItem("infrastock-recent", JSON.stringify(recent.slice(0, 5)));
  renderRecent();
}

function renderRecent() {
  const recent = getRecent();
  $("#clear-recent").hidden = recent.length === 0;
  $("#recent-list").innerHTML = recent.length
    ? recent.map((asset) => `
      <button class="recent-item" type="button" data-asset-code="${asset.asset_code}">
        <span><strong>${asset.asset_code}</strong><small>${asset.asset_type} · ${asset.site_type}</small></span>
        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>`).join("")
    : `<p class="empty-recent">아직 등록 작업이 없습니다.</p>`;
}

async function startScanner() {
  showScreen("scanner");
  $("#scanner-recovery").hidden = true;
  $("#scanner-status").textContent = "카메라를 준비하고 있습니다.";

  if (!("BarcodeDetector" in window)) {
    showScannerRecovery("이 브라우저는 앱 내부 QR 스캔을 지원하지 않습니다.");
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    showScannerRecovery("이 브라우저에서 카메라에 접근할 수 없습니다.");
    return;
  }

  try {
    const formats = await BarcodeDetector.getSupportedFormats();
    if (!formats.includes("qr_code")) {
      showScannerRecovery("이 브라우저는 QR 형식을 지원하지 않습니다.");
      return;
    }
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }, audio: false,
    });
    const video = $("#camera-preview");
    video.srcObject = cameraStream;
    await video.play();
    $("#camera-placeholder").hidden = true;
    $("#scanner-status").textContent = "QR 코드를 사각형 안에 맞춰주세요.";
    detectQr(new BarcodeDetector({ formats: ["qr_code"] }));
  } catch (error) {
    showScannerRecovery(error.name === "NotAllowedError"
      ? "카메라 권한이 거부되었습니다. 브라우저 설정에서 권한을 허용해주세요."
      : "카메라를 시작하지 못했습니다.");
  }
}

function detectQr(detector) {
  const video = $("#camera-preview");
  const scan = async () => {
    if (!cameraStream) return;
    try {
      const codes = await detector.detect(video);
      if (codes.length) {
        const code = normalizeAssetCode(codes[0].rawValue);
        if (ASSET_CODE_PATTERN.test(code)) {
          navigator.vibrate?.(80);
          stopScanner();
          lookupAsset(code);
          return;
        }
        $("#scanner-status").textContent = "Inventory 자산 ID가 아닌 QR입니다. 다른 QR을 스캔하세요.";
      }
    } catch { /* 다음 프레임에서 재시도 */ }
    scanTimer = window.setTimeout(scan, 300);
  };
  scan();
}

function showScannerRecovery(message) {
  $("#scanner-status").textContent = message;
  $("#scanner-recovery").hidden = false;
}

function stopScanner() {
  if (scanTimer) window.clearTimeout(scanTimer);
  scanTimer = null;
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  const video = $("#camera-preview");
  if (video) video.srcObject = null;
  const placeholder = $("#camera-placeholder");
  if (placeholder) placeholder.hidden = false;
}

function goHome() {
  history.replaceState({}, "", "/mobile");
  showScreen("home");
  renderRecent();
  requestAnimationFrame(() => $("#asset-code").focus());
}

function backToDetail() { showDetail(currentAsset); }

function openMove() {
  $("#move-form").reset();
  $("#move-current").textContent = `현재: ${currentAsset.site_type}${currentAsset.detailed_location ? ` / ${currentAsset.detailed_location}` : ""}`;
  $("#move-site-error").textContent = $("#move-error").textContent = "";
  showScreen("move");
}

function openStatus() {
  $("#status-form").reset();
  $("#new-status").value = currentAsset.status;
  $("#status-error").textContent = "";
  showScreen("status");
}

function openInstall() { $("#install-form").reset(); $("#install-error").textContent = ""; showScreen("install"); }
function openRemove() { $("#remove-form").reset(); $("#remove-site-error").textContent = $("#remove-error").textContent = ""; showScreen("remove"); }

async function openHistory() {
  showScreen("history");
  $("#history-list").innerHTML = '<p class="history-empty">이력을 불러오는 중입니다.</p>';
  try {
    const history = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/history`);
    $("#history-list").innerHTML = history.length ? history.map((item) => {
      const isLocation = ["MOVE", "INSTALL", "REMOVE"].includes(item.action);
      const title = { MOVE: "위치 이동", INSTALL: "서버 장착", REMOVE: "서버 탈착" }[item.action] || "상태 변경";
      const detail = isLocation
        ? `${item.from_site_type}${item.from_detailed_location ? ` / ${item.from_detailed_location}` : ""} → ${item.to_site_type}${item.to_detailed_location ? ` / ${item.to_detailed_location}` : ""}`
        : `${STATUS_LABELS[item.before_status] || item.before_status} → ${STATUS_LABELS[item.after_status] || item.after_status}`;
      return `<article class="history-item"><header><strong>${title}</strong><time datetime="${escapeHtml(item.created_at)}">${new Date(item.created_at).toLocaleString("ko-KR")}</time></header><p>${escapeHtml(detail)}</p><p>작업자: ${escapeHtml(item.actor)}</p>${item.memo ? `<p>메모: ${escapeHtml(item.memo)}</p>` : ""}</article>`;
    }).join("") : '<p class="history-empty">아직 이동 또는 상태 변경 이력이 없습니다.</p>';
  } catch (error) {
    $("#history-list").innerHTML = '<p class="history-empty">이력을 불러오지 못했습니다.</p>';
  }
}

$("#asset-lookup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  lookupAsset($("#asset-code").value);
});

$("#register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearRegistrationErrors();
  const form = new FormData(event.currentTarget);
  const isServer = /^(SVR|SRV|NET)-/.test(currentAsset.asset_code);
  const assetType = isServer ? (currentAsset.asset_code.startsWith("NET-") ? "NETWORK" : "SERVER") : form.get("asset_type");
  const siteType = form.get("site_type");
  if (!assetType) $("#asset-type-error").textContent = "자산 유형을 선택하세요.";
  if (!siteType) $("#site-type-error").textContent = "현재 Site를 선택하세요.";
  if (!assetType || !siteType) return;

  const submit = $("#register-submit");
  submit.disabled = true;
  submit.textContent = "등록 중…";
  try {
    const asset = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/register`, {
      method: "POST",
      body: JSON.stringify(isServer ? { site_type: siteType } : { asset_type: assetType, site_type: siteType }),
    });
    showComplete(asset);
  } catch (error) {
    $("#register-error").textContent = error.status === 409
      ? "이미 다른 정보로 등록된 자산 ID입니다. 자산 상세를 다시 확인하세요."
      : "등록하지 못했습니다. 네트워크를 확인하고 다시 시도하세요.";
  } finally {
    submit.disabled = false;
    submit.textContent = "자산 등록";
  }
});

document.querySelectorAll("[data-go-home]").forEach((button) => button.addEventListener("click", goHome));
$("#start-scan").addEventListener("click", startScanner);
$("#scan-next").addEventListener("click", startScanner);
$("#detail-scan-next").addEventListener("click", startScanner);
$("#retry-camera").addEventListener("click", startScanner);
$("#error-retry").addEventListener("click", goHome);
$("#view-complete-asset").addEventListener("click", () => showDetail(currentAsset));
$("#open-move").addEventListener("click", openMove);
$("#open-details").addEventListener("click", async () => {
  const asset = currentAsset;
  $("#edit-details-code").textContent = currentAsset.asset_code;
  $("#edit-serial").value = currentAsset.serial_number || "";
  $("#edit-manufacturer").value = currentAsset.manufacturer || "";
  $("#edit-model").value = currentAsset.model || "";
  $("#edit-part-number").value = currentAsset.part_number || "";
  $("#edit-details-error").textContent = "";
  $("#edit-specifications").textContent = "사양 입력 항목을 불러오는 중…";
  $("#edit-details-submit").disabled = true;
  showScreen("edit-details");
  try {
    const schema = await loadSpecificationSchema();
    if (currentAsset !== asset) return;
    renderSpecificationForm(asset, schema);
    $("#edit-details-submit").disabled = false;
  } catch {
    $("#edit-specifications").textContent = "";
    $("#edit-details-error").textContent = "사양 항목을 불러오지 못했습니다. 뒤로 돌아가 정보 수정을 다시 열어주세요.";
  }
});
$("#edit-details-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#edit-details-submit");
  button.disabled = true;
  button.textContent = "저장 중…";
  $("#edit-details-error").textContent = "";
  try {
    const details = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/details`, {
      method: "PATCH",
      body: JSON.stringify({ serial_number: $("#edit-serial").value.trim(), manufacturer: $("#edit-manufacturer").value.trim(), model: $("#edit-model").value.trim(), part_number: $("#edit-part-number").value.trim(), specifications: readSpecificationForm() }),
    });
    showDetail({ ...currentAsset, ...details });
    announce("자산 정보를 저장했습니다.");
  } catch (error) {
    $("#edit-details-error").textContent = error.status === 403 ? "정보를 수정할 권한이 없습니다." : "저장하지 못했습니다. 입력값과 연결 상태를 확인하고 다시 시도하세요.";
  } finally {
    button.disabled = false;
    button.textContent = "저장";
  }
});
$("#open-status").addEventListener("click", openStatus);
$("#open-history").addEventListener("click", openHistory);
$("#open-install").addEventListener("click", openInstall);
$("#open-remove").addEventListener("click", openRemove);
document.querySelectorAll("[data-back-detail]").forEach((button) => button.addEventListener("click", backToDetail));
$("#clear-recent").addEventListener("click", () => { localStorage.removeItem("infrastock-recent"); renderRecent(); });
$("#recent-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-asset-code]");
  if (button) lookupAsset(button.dataset.assetCode);
});
document.addEventListener("visibilitychange", () => { if (document.hidden) stopScanner(); });

$("#move-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const siteType = form.get("site_type");
  if (!siteType) { $("#move-site-error").textContent = "새 Site를 선택하세요."; return; }
  const button = $("#move-submit"); button.disabled = true; button.textContent = "이동 중…";
  try {
    await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/movements`, { method: "POST", body: JSON.stringify({ site_type: siteType, detailed_location: $("#move-location").value.trim() || null, memo: $("#move-memo").value.trim() || null }) });
    currentAsset = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}`); showDetail(currentAsset); announce("현재 위치를 변경하고 이전 위치를 이력에 저장했습니다.");
  } catch { $("#move-error").textContent = "이동을 저장하지 못했습니다. 다시 시도하세요."; }
  finally { button.disabled = false; button.textContent = "이동 완료"; }
});

$("#status-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = $("#status-submit"); button.disabled = true; button.textContent = "변경 중…";
  try {
    await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}`, { method: "PATCH", body: JSON.stringify({ status: $("#new-status").value, memo: $("#status-memo").value.trim() || null }) });
    currentAsset = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}`); showDetail(currentAsset); announce("자산 상태를 변경했습니다.");
  } catch { $("#status-error").textContent = "상태를 변경하지 못했습니다. 다시 시도하세요."; }
  finally { button.disabled = false; button.textContent = "상태 변경"; }
});

$("#install-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = $("#install-submit"); button.disabled = true; button.textContent = "장착 중…";
  try {
    await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/assignments`, { method: "POST", body: JSON.stringify({ target_asset_code: $("#target-server").value.trim().toUpperCase(), slot: $("#target-slot").value.trim() || null }) });
    currentAsset = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}`); showDetail(currentAsset); announce("서버 장착을 완료했습니다.");
  } catch (error) { $("#install-error").textContent = error.status === 422 ? "등록된 SVR 번호를 확인하세요." : "장착하지 못했습니다. 다시 시도하세요."; }
  finally { button.disabled = false; button.textContent = "장착 완료"; }
});

$("#remove-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const form = new FormData(event.currentTarget), siteType = form.get("site_type");
  if (!siteType) { $("#remove-site-error").textContent = "탈착 후 Site를 선택하세요."; return; }
  const button = $("#remove-submit"); button.disabled = true; button.textContent = "탈착 중…";
  try {
    await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}/assignments/remove`, { method: "POST", body: JSON.stringify({ site_type: siteType, detailed_location: $("#remove-location").value.trim() || null, reason: $("#remove-reason").value.trim() || null }) });
    currentAsset = await request(`/assets/${encodeURIComponent(currentAsset.asset_code)}`); showDetail(currentAsset); announce("서버 탈착을 완료하고 새 위치를 저장했습니다.");
  } catch { $("#remove-error").textContent = "탈착하지 못했습니다. 다시 시도하세요."; }
  finally { button.disabled = false; button.textContent = "탈착 완료"; }
});

renderAssetTypes();
renderRecent();

const deepLinkMatch = location.pathname.match(/^\/a\/((?:ASSET|SVR|SRV|NET)-\d{8})\/?$/i);
if (deepLinkMatch) lookupAsset(deepLinkMatch[1]);
else showScreen("home", { focus: false });

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
