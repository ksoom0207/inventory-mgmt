(() => {
  const $ = (selector) => document.querySelector(selector);
  const money = (value) => `${Number(value).toLocaleString("ko-KR")}원`;
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  let offers = [];
  let opened = false;

  async function request(path, options = {}) {
    const response = await fetch(`/api${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `요청 실패 (${response.status})`);
    return body;
  }

  async function loadItems() {
    const items = await request("/quotes");
    const select = $("#offer-item");
    const selected = select.value;
    select.replaceChildren(new Option("품목 선택", ""));
    items.forEach((item) => select.add(new Option(
      `${item.name}${item.part_number ? ` · ${item.part_number}` : ""}`,
      item.id,
    )));
    if (items.some((item) => item.id === selected)) select.value = selected;
    select.disabled = items.length === 0;
  }

  function render() {
    const query = $("#quote-search").value.trim().toLocaleLowerCase();
    const visible = offers.filter((offer) => [offer.item_name, offer.part_number, offer.supplier,
      offer.supplier_ref].some((value) => String(value || "").toLocaleLowerCase().includes(query)));
    $("#offer-count").textContent = `${visible.length}개 견적`;
    $("#offer-empty").hidden = visible.length > 0;
    $("#offer-body").closest(".table-wrap").hidden = visible.length === 0;
    const statusLabels = { ACTIVE: "유효", EXPIRED: "만료", UPCOMING: "시작 전" };
    $("#offer-body").innerHTML = visible.map((offer) => `
      <tr>
        <td data-label="품목 · P/N"><strong>${escapeHtml(offer.item_name)}</strong>${offer.part_number ? `<small class="offer-reference">${escapeHtml(offer.part_number)}</small>` : ""}</td>
        <td data-label="공급사"><strong>${escapeHtml(offer.supplier)}</strong>${offer.supplier_ref ? `<small class="offer-reference">${escapeHtml(offer.supplier_ref)}</small>` : ""}</td>
        <td data-label="수량" class="number">${offer.quantity.toLocaleString("ko-KR")}</td>
        <td data-label="단가" class="number">${money(offer.unit_price)}</td>
        <td data-label="배송비" class="number">${money(offer.shipping_cost)}</td>
        <td data-label="비교 금액" class="number ${offer.lowest ? "offer-best" : ""}">${money(offer.total_price)}${offer.lowest ? " · 최저" : ""}</td>
        <td data-label="부가세">${offer.tax_basis === "INCLUDED" ? "포함" : "별도"}</td>
        <td data-label="견적일 · 유효기간">${escapeHtml(offer.quoted_on)}${offer.valid_until ? ` ~ ${escapeHtml(offer.valid_until)}` : " · 미정"}</td>
        <td data-label="납기">${offer.lead_days === null ? "미정" : `${offer.lead_days}일`}</td>
        <td data-label="상태"><span class="offer-state ${offer.status.toLowerCase()}">${statusLabels[offer.status]}</span></td>
      </tr>`).join("");
  }

  async function loadOffers() {
    const asOf = $("#quote-date").value;
    offers = await request(`/purchase-offers?${new URLSearchParams({ as_of: asOf })}`);
    render();
  }

  async function openComparison() {
    if (!opened) {
      opened = true;
      try {
        await Promise.all([loadItems(), loadOffers()]);
      } catch (error) {
        opened = false;
        $("#offer-form-error").textContent = `구매 견적을 불러오지 못했습니다: ${error.message}`;
        $("#offer-form-error").hidden = false;
      }
    }
  }

  document.addEventListener("quote-tab-selected", openComparison);
  document.addEventListener("quote-catalog-changed", () => {
    if (opened) loadItems().catch((error) => {
      $("#offer-form-error").textContent = `품목을 갱신하지 못했습니다: ${error.message}`;
      $("#offer-form-error").hidden = false;
    });
  });
  $("#quote-search").addEventListener("input", render);
  $("#quote-date").addEventListener("change", () => {
    if (opened) loadOffers().catch((error) => {
      $("#offer-form-error").textContent = `비교 기준일을 변경하지 못했습니다: ${error.message}`;
      $("#offer-form-error").hidden = false;
    });
  });

  $("#offer-date").value = new Date().toISOString().slice(0, 10);
  $("#purchase-offer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#offer-save");
    const error = $("#offer-form-error");
    error.hidden = true;
    const itemId = $("#offer-item").value;
    button.disabled = true;
    button.textContent = "기록 중…";
    try {
      await request("/purchase-offers", {
        method: "POST",
        body: JSON.stringify({
          item_id: itemId,
          supplier: $("#offer-supplier").value.trim(),
          supplier_ref: $("#offer-ref").value.trim() || null,
          quantity: Number($("#offer-quantity").value),
          unit_price: Number($("#offer-unit-price").value),
          shipping_cost: Number($("#offer-shipping").value),
          tax_basis: $("#offer-tax-basis").value,
          quoted_on: $("#offer-date").value,
          valid_until: $("#offer-valid-until").value || null,
          lead_days: $("#offer-lead-days").value === "" ? null : Number($("#offer-lead-days").value),
        }),
      });
      event.currentTarget.reset();
      $("#offer-item").value = itemId;
      $("#offer-date").value = new Date().toISOString().slice(0, 10);
      await loadOffers();
    } catch (caught) {
      error.textContent = `견적을 기록하지 못했습니다: ${caught.message}`;
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = "공급사 견적 기록";
    }
  });
})();
