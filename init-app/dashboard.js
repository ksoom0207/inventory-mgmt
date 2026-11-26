const API="/api",$=s=>document.querySelector(s),today=()=>new Date().toISOString().slice(0,10);
const STATUS_LABELS={AVAILABLE:"사용 가능",IN_USE:"사용 중",RESERVED:"예약",FAULTY:"장애",RMA:"RMA",REPAIR:"수리 중",DISPOSED:"폐기",LOST:"분실",UNKNOWN:"확인 필요"};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let inventory={totals:{},items:[]},quoteParts=[],sites=[],prefixes=[],toastTimer;
async function api(path,opt={}){const r=await fetch(API+path,{...opt,headers:{"Content-Type":"application/json",...(opt.headers||{})}}),d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||`요청 실패 (${r.status})`);return d}
function toast(message){clearTimeout(toastTimer);$("#toast").textContent=message;$("#toast").hidden=false;toastTimer=setTimeout(()=>{$("#toast").hidden=true},4000)}
function sum(items,key){return items.reduce((n,x)=>n+Number(x[key]||0),0)}
function filtered(){const site=$("#stock-site").value,type=$("#stock-type").value;return inventory.items.filter(x=>(!site||x.site_type===site)&&(!type||x.asset_type===type))}
function siteLabel(code){const site=sites.find(x=>x.code===code);return site?`${site.code} · ${site.name}`:code}
async function loadPrefixes(){prefixes=await api("/asset-code-prefixes");const select=$("#label-code-prefix"),selected=select.value;select.innerHTML='<option value="">접두어 선택</option>'+prefixes.map(item=>`<option value="${esc(item.prefix)}">${esc(item.prefix)}</option>`).join("");if(prefixes.some(item=>item.prefix===selected))select.value=selected;else if($("#label-asset-type").value)select.value=$("#label-asset-type").value==="SERVER"?"SVR":$("#label-asset-type").value==="NETWORK"?"NET":"ASSET";$("#prefix-list").textContent=`등록된 접두어: ${prefixes.map(item=>item.prefix).join(" · ")}`}
async function loadSites(){sites=await api("/sites");const select=$("#stock-site"),selected=select.value;select.innerHTML='<option value="">전체 Site</option>'+sites.map(site=>`<option value="${esc(site.code)}">${esc(siteLabel(site.code))}</option>`).join("");if(sites.some(site=>site.code===selected))select.value=selected;const labelSite=$("#label-site"),labelSelected=labelSite.value;labelSite.innerHTML='<option value="">Site 선택</option>'+sites.map(site=>`<option value="${esc(site.code)}">${esc(siteLabel(site.code))}</option>`).join("");if(sites.some(site=>site.code===labelSelected))labelSite.value=labelSelected;$("#site-list").innerHTML=sites.map(site=>`<div class="site-entry"><span class="site-entry-label">${esc(siteLabel(site.code))}</span>${site.can_delete?`<button type="button" class="button danger" data-delete-site="${esc(site.code)}" aria-label="${esc(site.code)} Site 삭제">삭제</button>`:`<small>${site.code==="IDC"||site.code==="OFFICE"?"기본 Site":"사용 이력 있음 · 삭제 불가"}</small>`}</div>`).join("");renderInventory()}
function populateTypes(){const select=$("#stock-type"),selected=select.value,types=[...new Set(inventory.items.map(x=>x.asset_type))].sort();select.innerHTML='<option value="">전체 유형</option>'+types.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join("");if(types.includes(selected))select.value=selected}
function renderInventory(){const items=filtered(),metrics=[["등록 자산",sum(items,"registered"),""],["정상 재고",sum(items,"normal"),""],["사용 가능",sum(items,"available"),""],["장애 자산",sum(items,"faulty"),"fault"]];$("#stock-cards").innerHTML=metrics.map(([l,v,k])=>`<article class="metric ${k}"><span class="label">${l}</span><strong class="value">${v.toLocaleString("ko-KR")}</strong></article>`).join("");const faulty=sum(items,"faulty");$("#fault-notice").hidden=!faulty;$("#fault-title").textContent=`장애 자산 ${faulty.toLocaleString("ko-KR")}개가 별도로 분리되어 있습니다.`;$("#row-count").textContent=`${items.length}개 그룹`;const body=$("#stock-body");$("#stock-empty").hidden=!!items.length;body.closest(".table-wrap").hidden=!items.length;body.innerHTML=items.map(x=>`<tr><td data-label="자산 유형"><strong>${esc(x.asset_type)}</strong></td><td data-label="사양">${esc(x.specification_label||"—")}</td><td data-label="Site">${esc(siteLabel(x.site_type))}</td><td data-label="정상 재고" class="number">${x.normal}</td><td data-label="사용 가능" class="number">${x.available}</td><td data-label="사용 중" class="number">${x.in_use}</td><td data-label="장애" class="number ${x.faulty?"fault-number":""}">${x.faulty}</td><td data-label="폐기" class="number">${x.disposed}</td><td><button class="button secondary small" type="button" data-view-assets data-type="${esc(x.asset_type)}" data-site="${esc(x.site_type)}" data-group="${esc(x.group_key||"")}" data-specification="${esc(x.specification_label||"")}">자산 보기</button></td></tr>`).join("")}
async function loadInventory(){const b=$("#refresh-stock");b.disabled=true;try{inventory=await api("/inventory/summary?group_by=specification");populateTypes();renderInventory();$("#updated-at").textContent=`${new Date().toLocaleString("ko-KR")} 갱신`}catch(e){toast(`재고 현황을 불러오지 못했습니다: ${e.message}`)}finally{b.disabled=false}}
async function openAssets(type,site,groupKey="",specification=""){const dialog=$("#asset-dialog");$("#asset-dialog-title").textContent=[type,siteLabel(site),specification].filter(Boolean).join(" · ");$("#asset-list").innerHTML='<p class="empty-state">자산 목록을 불러오는 중입니다.</p>';dialog.showModal();try{const list=await api(`/assets?${new URLSearchParams({asset_type:type,site_type:site,...(groupKey?{group_key:groupKey}:{})})}`);$("#asset-list").innerHTML=list.length?list.map(x=>`<a class="asset-row" href="/a/${encodeURIComponent(x.asset_code)}"><span><strong>${esc(x.asset_code)}</strong><small>${esc(x.asset_type)} · ${esc(siteLabel(x.site_type))}</small></span><span class="status ${x.status.toLowerCase()}">${esc(STATUS_LABELS[x.status]||x.status)}</span></a>`).join(""):'<div class="empty-state"><h3>해당 자산이 없습니다</h3></div>'}catch(e){$("#asset-list").innerHTML=`<div class="empty-state"><h3>목록을 불러오지 못했습니다</h3><p>${esc(e.message)}</p></div>`}}
function asOf(prices,date){return prices.filter(x=>x.date<=date).sort((a,b)=>b.date.localeCompare(a.date))[0]||null}
function renderQuotes(){const q=$("#quote-search").value.trim().toLowerCase(),date=$("#quote-date").value||today(),rows=quoteParts.filter(x=>!q||x.name.toLowerCase().includes(q)||x.category.toLowerCase().includes(q)||(x.part_number||"").toLowerCase().includes(q)),body=$("#quote-body");$("#quote-empty").hidden=!!rows.length;body.closest(".table-wrap").hidden=!rows.length;body.innerHTML=rows.map(x=>{const p=asOf(x.prices,date);return`<tr><td data-label="부품명"><input aria-label="${esc(x.name)} 부품명" value="${esc(x.name)}" data-quote-name="${esc(x.id)}"></td><td data-label="카테고리">${esc(x.category)}</td><td data-label="P/N"><input aria-label="${esc(x.name)} P/N" value="${esc(x.part_number||"")}" data-quote-part-number="${esc(x.id)}"></td><td data-label="기준 단가" class="number"><input aria-label="${esc(x.name)} 기준 단가" inputmode="numeric" value="${p?p.price.toLocaleString("ko-KR"):""}" data-quote-price="${esc(x.id)}"></td><td><button class="button danger small" type="button" data-delete-quote="${esc(x.id)}">삭제</button></td></tr>`}).join("")}
async function loadQuotes(){try{quoteParts=await api("/quotes");renderQuotes();document.dispatchEvent(new Event("quote-catalog-changed"))}catch(e){toast(`견적을 불러오지 못했습니다: ${e.message}`)}}
function selectTab(name){document.querySelectorAll("[role=tab]").forEach(tab=>{const on=tab.dataset.tab===name;tab.classList.toggle("active",on);tab.setAttribute("aria-selected",String(on));$("#panel-"+tab.dataset.tab).hidden=!on});if(name==="label")loadPrintAssets();if(name==="sites")loadSites().catch(e=>toast(`Site 목록을 불러오지 못했습니다: ${e.message}`));if(name==="quote"){if(!quoteParts.length)loadQuotes();document.dispatchEvent(new Event("quote-tab-selected"))}}
$("[data-open-label]").addEventListener("click",()=>{selectTab("register");$("#label-asset-type").focus()});
$("#label-asset-type").addEventListener("change",()=>{const select=$("#label-code-prefix");if(!select.value)select.value=$("#label-asset-type").value==="SERVER"?"SVR":$("#label-asset-type").value==="NETWORK"?"NET":"ASSET"});
$("#prefix-new-code").addEventListener("input",e=>{const start=e.target.selectionStart,end=e.target.selectionEnd;e.target.value=e.target.value.toUpperCase();e.target.setSelectionRange(start,end)});
$("#prefix-add-form").addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget,code=$("#prefix-new-code").value.trim().toUpperCase(),button=$("#prefix-add-button"),error=$("#prefix-add-error");error.hidden=true;button.disabled=true;try{await api("/asset-code-prefixes",{method:"POST",body:JSON.stringify({prefix:code})});await loadPrefixes();$("#label-code-prefix").value=code;form.reset();toast(`${code} 접두어를 추가했습니다.`)}catch(err){error.textContent=`접두어를 추가하지 못했습니다: ${err.message}`;error.hidden=false}finally{button.disabled=false}});
function renderLabelSheets(codes,startPosition){
  const pages=[];
  let codeIndex=0;
  while(codeIndex<codes.length){
    const slots=Array(416).fill(null);
    const firstSlot=pages.length===0?(startPosition-1)*4:0;
    for(let slot=firstSlot;slot<slots.length&&codeIndex<codes.length;slot+=1)slots[slot]=codes[codeIndex++];
    pages.push(slots);
  }
  $("#label-preview").innerHTML=pages.map((slots,page)=>{
    const cells=Array.from({length:104},(_,cell)=>`<div class="label-cell">${slots.slice(cell*4,cell*4+4).map(code=>code?`<div class="qr-label"><img src="/api/asset-labels/${encodeURIComponent(code)}/qr.svg" alt="${esc(code)} QR"><span>${esc(code)}</span></div>`:'<div class="qr-label blank" aria-hidden="true"></div>').join("")}</div>`).join("");
    return `<section class="label-sheet" aria-label="QR 라벨 ${page+1}쪽">${cells}</section>`;
  }).join("");
}
async function waitForLabelImages(){const images=[...document.querySelectorAll("#label-preview img")];await Promise.all(images.map(image=>image.complete?Promise.resolve():new Promise(resolve=>{image.addEventListener("load",resolve,{once:true});image.addEventListener("error",resolve,{once:true})})));return images.every(image=>image.naturalWidth>0)}
async function showLabelPreview(codes,startPosition,labelName){renderLabelSheets(codes,startPosition);$("#label-result-actions").hidden=false;$("#print-labels").disabled=true;$("#label-status").textContent=`${codes.length}개 ${labelName}의 QR 이미지를 준비하는 중입니다.`;const sheet=$("#label-preview").firstElementChild;const ready=await waitForLabelImages();if(sheet!==$("#label-preview").firstElementChild)return;$("#print-labels").disabled=!ready;$("#label-status").textContent=ready?`${codes.length}개 ${labelName} 라벨이 준비됐습니다.`:"일부 QR 이미지를 불러오지 못했습니다. 새로고침 후 다시 시도하세요."}
document.querySelectorAll("[role=tab]").forEach(tab=>{tab.addEventListener("click",()=>selectTab(tab.dataset.tab));tab.addEventListener("keydown",e=>{const tabs=[...document.querySelectorAll("[role=tab]")],i=tabs.indexOf(tab);let next=null;if(e.key==="ArrowRight")next=tabs[(i+1)%tabs.length];if(e.key==="ArrowLeft")next=tabs[(i-1+tabs.length)%tabs.length];if(e.key==="Home")next=tabs[0];if(e.key==="End")next=tabs[tabs.length-1];if(next){e.preventDefault();next.focus();selectTab(next.dataset.tab)}})});$("#stock-site").addEventListener("change",renderInventory);$("#stock-type").addEventListener("change",renderInventory);$("#refresh-stock").addEventListener("click",()=>loadSites().catch(e=>toast(`Site 목록을 불러오지 못했습니다: ${e.message}`)).finally(loadInventory));$("#stock-body").addEventListener("click",e=>{const b=e.target.closest("[data-view-assets]");if(b)openAssets(b.dataset.type,b.dataset.site,b.dataset.group,b.dataset.specification)});$("[data-dialog-close]").addEventListener("click",()=>$("#asset-dialog").close());$("#asset-dialog").addEventListener("click",e=>{if(e.target===e.currentTarget)e.currentTarget.close()});$("#quote-search").addEventListener("input",renderQuotes);$("#quote-date").addEventListener("change",renderQuotes);
$("#quote-add-form").addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget,name=$("#quote-new-name").value.trim(),category=$("#quote-new-category").value.trim()||"기타",partNumber=$("#quote-new-part-number").value.trim(),rawPrice=$("#quote-new-price").value.trim(),price=Number(rawPrice),button=form.querySelector("button[type=submit]");if(!name||rawPrice!==""&&(!Number.isSafeInteger(price)||price<0)){toast("부품명과 0 이상의 정수 단가를 확인하세요.");return}button.disabled=true;try{const made=await api("/quotes",{method:"POST",body:JSON.stringify({name,category,part_number:partNumber||null})});if(rawPrice!=="")await api(`/quotes/${made.id}/prices`,{method:"PUT",body:JSON.stringify({date:$("#quote-date").value||today(),price})});form.reset();await loadQuotes();toast("견적 품목을 추가했습니다.")}catch(err){toast(`추가하지 못했습니다: ${err.message}`)}finally{button.disabled=false}});
$("#site-add-form").addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget,button=$("#site-add-button"),error=$("#site-management-error"),code=$("#site-new-code").value.trim().toUpperCase(),name=$("#site-new-name").value.trim();error.hidden=true;button.disabled=true;button.textContent="추가 중…";try{await api("/sites",{method:"POST",body:JSON.stringify({code,name})});form.reset();await loadSites();toast(`${name} Site를 추가했습니다.`)}catch(err){const messages={"admin role required":"관리자 권한이 필요합니다.","site code already exists":"이미 사용 중인 코드입니다. 다른 코드를 입력하세요.","site name already exists":"이미 사용 중인 이름입니다. 다른 이름을 입력하세요."};error.textContent=`Site를 추가하지 못했습니다: ${messages[err.message]||err.message}`;error.hidden=false}finally{button.disabled=false;button.textContent="Site 추가"}});
$("#site-list").addEventListener("click",async e=>{const button=e.target.closest("[data-delete-site]");if(!button)return;const code=button.dataset.deleteSite,site=sites.find(item=>item.code===code);if(!site||!confirm(`${site.name} (${code}) Site를 삭제할까요? 삭제한 코드는 다시 추가할 수 있습니다.`))return;const error=$("#site-management-error");error.hidden=true;button.disabled=true;button.textContent="삭제 중…";try{await api(`/sites/${encodeURIComponent(code)}`,{method:"DELETE"});await loadSites();toast(`${site.name} Site를 삭제했습니다.`)}catch(err){const messages={"admin role required":"관리자 권한이 필요합니다.","site has asset or movement history and cannot be deleted":"자산 또는 이력에서 사용된 Site입니다. 삭제할 수 없습니다.","default sites cannot be deleted":"기본 Site는 삭제할 수 없습니다."};error.textContent=`Site를 삭제하지 못했습니다: ${messages[err.message]||err.message}`;error.hidden=false;button.disabled=false;button.textContent="삭제"}});
$("#site-new-code").addEventListener("input",e=>{const start=e.target.selectionStart,end=e.target.selectionEnd;e.target.value=e.target.value.toUpperCase();e.target.setSelectionRange(start,end)});
$("#quote-body").addEventListener("change",async e=>{const nameId=e.target.dataset.quoteName,partNumberId=e.target.dataset.quotePartNumber,priceId=e.target.dataset.quotePrice;try{if(nameId)await api(`/quotes/${nameId}`,{method:"PATCH",body:JSON.stringify({name:e.target.value.trim()})});if(partNumberId)await api(`/quotes/${partNumberId}`,{method:"PATCH",body:JSON.stringify({part_number:e.target.value.trim()})});if(priceId){const raw=e.target.value.replace(/,/g,"").trim(),price=Number(raw);if(raw===""||!Number.isSafeInteger(price)||price<0)throw Error("기준 단가는 0 이상의 정수로 입력하세요.");await api(`/quotes/${priceId}/prices`,{method:"PUT",body:JSON.stringify({date:$("#quote-date").value||today(),price})})}await loadQuotes();toast("견적 품목을 저장했습니다.")}catch(err){toast(`저장하지 못했습니다: ${err.message}`)}});
$("#quote-body").addEventListener("click",async e=>{const id=e.target.dataset.deleteQuote;if(!id||!confirm("이 견적 항목과 단가 기록을 삭제할까요?"))return;try{await api(`/quotes/${id}`,{method:"DELETE"});await loadQuotes();toast("견적 항목을 삭제했습니다.")}catch(err){toast(`삭제하지 못했습니다: ${err.message}`)}});
let batchSpecSchema;
let specFormVersion = 0;
async function showBatchSpecs() {
  const version = ++specFormVersion;
  const type = $("#label-asset-type").value;
  const fields = $("#batch-spec-fields");
  fields.replaceChildren();
  $("#batch-specs").hidden = !type;
  if (!type) return;
  fields.textContent = "사양을 불러오는 중…";
  try {
    batchSpecSchema ??= await api("/asset-specifications");
    if (version === specFormVersion) {
      renderSpecificationForm(fields, {asset_type: type}, batchSpecSchema);
    }
  } catch {
    if (version !== specFormVersion) return;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "사양 다시 불러오기";
    retry.addEventListener("click", showBatchSpecs);
    fields.replaceChildren(retry);
  }
}
$("#label-asset-type").addEventListener("change", showBatchSpecs);
$("#label-issue-form").addEventListener("submit", async event => {
  event.preventDefault();
  const quantity = Number($("#label-quantity").value);
  const serial = $("#label-serial").value.trim();
  if (quantity > 1 && serial) {
    toast("여러 대 등록 시 Serial Number를 비우세요.");
    $("#label-serial").focus();
    return;
  }
  const button = $("#issue-labels");
  button.disabled = true;
  const result = $("#registration-result");
  result.textContent = "등록 중…";
  try {
    const created = await api("/assets", {method:"POST", body:JSON.stringify({
      asset_type: $("#label-asset-type").value, site_type: $("#label-site").value,
      specifications: readSpecificationForm(),
      code_prefix: $("#label-code-prefix").value, quantity, serial_number: serial || null,
      manufacturer: $("#label-manufacturer").value.trim() || null,
      model: $("#label-model").value.trim() || null, part_number: $("#label-part-number").value.trim() || null
    })});
    result.textContent = created.quantity + "건 등록 완료 · " + created.asset_codes[0]
      + (created.quantity > 1 ? " ~ " + created.asset_codes.at(-1) : "");
    $("#label-serial").value = "";
    await loadInventory();
  } catch (error) { result.textContent = "등록 실패 · " + error.message; }
  finally { button.disabled = false; }
});

let printAssets = [];
const selectedCodes = new Set();
let printListRequest = 0;
function filteredPrintAssets() {
  const query = $("#print-search").value.trim().toLowerCase();
  return printAssets.filter(asset => [asset.asset_code, asset.asset_type, siteLabel(asset.site_type)]
    .some(value => value.toLowerCase().includes(query)));
}
function updatePrintSelection() {
  $("#label-preview").replaceChildren();
  $("#label-result-actions").hidden = true;
  $("#print-labels").disabled = true;
  $("#preview-selected").disabled = !selectedCodes.size;
  $("#preview-selected").textContent = "선택 " + selectedCodes.size + "건 미리보기";
}
function renderPrintList() {
  const visible = filteredPrintAssets();
  $("#print-assets").innerHTML = visible.map(asset =>
    `<label><input type="checkbox" value="${esc(asset.asset_code)}" ${selectedCodes.has(asset.asset_code) ? "checked" : ""}> <strong>${esc(asset.asset_code)}</strong> · ${esc(asset.asset_type)} · ${esc(siteLabel(asset.site_type))}</label>`
  ).join("") || "해당하는 등록 자산이 없습니다.";
}
async function loadPrintAssets() {
  const request = ++printListRequest;
  printAssets = [];
  updatePrintSelection();
  $("#preview-selected").disabled = true;
  $("#print-assets").textContent = "등록 자산을 조회하는 중…";
  try {
    const assets = await api("/assets");
    if (request !== printListRequest) return;
    printAssets = assets;
    const available = new Set(assets.map(asset => asset.asset_code));
    for (const code of selectedCodes) if (!available.has(code)) selectedCodes.delete(code);
    updatePrintSelection();
    renderPrintList();
  } catch (error) {
    if (request === printListRequest) {
      selectedCodes.clear();
      updatePrintSelection();
      $("#print-assets").textContent = "자산 조회 실패 · " + error.message;
    }
  }
}
$("#print-assets").addEventListener("change", event => {
  const input = event.target;
  if (input.checked) selectedCodes.add(input.value);
  else selectedCodes.delete(input.value);
  updatePrintSelection();
});
$("#print-search").addEventListener("input", renderPrintList);
$("#select-visible").addEventListener("click", () => {
  filteredPrintAssets().forEach(asset => selectedCodes.add(asset.asset_code));
  updatePrintSelection();
  renderPrintList();
});
$("#clear-selection").addEventListener("click", () => {
  selectedCodes.clear();
  updatePrintSelection();
  renderPrintList();
});
$("#label-start-position").addEventListener("input", updatePrintSelection);
$("#print-selection").addEventListener("submit", async event => {
  event.preventDefault();
  const codes = printAssets.map(asset => asset.asset_code).filter(code => selectedCodes.has(code));
  if (codes.length) await showLabelPreview(codes, Number($("#label-start-position").value), "자산");
});
$("#print-labels").addEventListener("click",()=>window.print());
$("#quote-date").value=today();loadSites().catch(e=>toast(`Site 목록을 불러오지 못했습니다: ${e.message}`)).finally(loadInventory);loadPrefixes().catch(e=>toast(`자산 코드 목록을 불러오지 못했습니다: ${e.message}`));
