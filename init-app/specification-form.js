function renderSpecificationForm(container, asset, schema) {
  container.replaceChildren();
  for (const key of [...(schema.types[asset.asset_type] || []), "notes"]) {
    const field = schema.fields[key], saved = asset.specifications?.[key];
    const group = document.createElement("div");
    group.className = "form-field field";
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
