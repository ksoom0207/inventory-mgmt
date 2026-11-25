const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function main() {
  const source = fs.readFileSync(path.join(__dirname, "..", "dashboard.js"), "utf8");
  const line = source.split("\n").find((part) => part.startsWith('$("#site-add-form").addEventListener("submit",'));
  assert.ok(line, "Site 추가 제출 핸들러가 있어야 합니다.");
  const callbackSource = line.match(/^\$\("#site-add-form"\)\.addEventListener\("submit",(async e=>.*)\);$/)?.[1];
  assert.ok(callbackSource, "실제 제출 핸들러를 추출할 수 있어야 합니다.");

  const form = { resetCount: 0, reset() { this.resetCount += 1; } };
  const button = { disabled: false, textContent: "Site 추가" };
  const error = { hidden: true, textContent: "" };
  const nodes = {
    "#site-add-button": button,
    "#site-management-error": error,
    "#site-new-code": { value: "WAREHOUSE" },
    "#site-new-name": { value: "부품 창고" },
  };
  let dispatching = true;
  let created = 0;
  let refreshed = 0;
  let success = "";
  const handler = vm.runInNewContext(`(${callbackSource})`, {
    $: (selector) => nodes[selector],
    api: async () => { created += 1; return { code: "WAREHOUSE" }; },
    loadSites: async () => { refreshed += 1; },
    toast: (message) => { success = message; },
  });
  const event = {
    preventDefault() {},
    get currentTarget() { return dispatching ? form : null; },
  };
  const submitted = handler(event);
  dispatching = false; // Browser clears currentTarget once event dispatch finishes.
  await submitted;

  assert.equal(created, 1, "서버 저장은 한 번만 실행되어야 합니다.");
  assert.equal(form.resetCount, 1, "저장 성공 후 폼이 초기화되어야 합니다.");
  assert.equal(refreshed, 1, "저장 성공 후 Site 목록이 갱신되어야 합니다.");
  assert.equal(error.hidden, true, "저장 성공을 실패로 표시하면 안 됩니다.");
  assert.match(success, /Site를 추가했습니다/);
  assert.equal(button.disabled, false);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
