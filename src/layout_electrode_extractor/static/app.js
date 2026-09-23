"use strict";

let state = null;
let tab = "electrodes";
let selected = null;
let layer = "ALL";
let drawVersion = 0;
const imageCache = new Map();
const tintCache = new Map();
const $ = (id) => document.getElementById(id);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function status(message, error = false) {
  $("status").textContent = message;
  $("status").className = error ? "error" : "ok";
}

function asset(path) {
  return "/api/asset/" + encodeURIComponent(path);
}

function loadImage(path) {
  if (!imageCache.has(path)) {
    imageCache.set(path, new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Could not load " + path));
      img.src = asset(path);
    }));
  }
  return imageCache.get(path);
}

async function tinted(path, color) {
  const key = path + "|" + color;
  if (!tintCache.has(key)) {
    tintCache.set(key, loadImage(path).then((img) => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const rgb = [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16));
      for (let i = 0; i < pixels.data.length; i += 4) {
        const maskValue = pixels.data[i];
        pixels.data[i] = rgb[0];
        pixels.data[i + 1] = rgb[1];
        pixels.data[i + 2] = rgb[2];
        pixels.data[i + 3] = maskValue;
      }
      ctx.putImageData(pixels, 0, 0);
      return canvas;
    }));
  }
  return tintCache.get(key);
}

async function draw() {
  if (!state) return;
  const version = ++drawVersion;
  const meta = state.metadata;
  const canvas = $("layout");
  const [height, width] = meta.output_shape_px;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#070b13";
  ctx.fillRect(0, 0, width, height);
  const visible = meta.layers.filter((item) => layer === "ALL" || item.id === layer);
  const colors = ["#75baff", "#ffbd70", "#70deaa", "#da99f7", "#e9e275", "#ff8d9d"];
  for (let index = 0; index < visible.length; index++) {
    const item = visible[index];
    const mask = await tinted(item.cut_path, colors[index % colors.length]);
    if (version !== drawVersion) return;
    const unitWidth = width / 2;
    const unitHeight = height / 2;
    ctx.globalAlpha = layer === "ALL" ? 0.33 : 0.54;
    for (let ty = 0; ty < 2; ty++) {
      for (let tx = 0; tx < 2; tx++) {
        ctx.drawImage(mask, tx * unitWidth, ty * unitHeight);
      }
    }
  }
  if (selected?.kind === "electrodes") {
    const item = meta.electrodes.find((entry) => entry.id === selected.id);
    if (item) {
      for (const [layerId, info] of Object.entries(item.layers)) {
        if (layer !== "ALL" && layer !== layerId) continue;
        const mask = await tinted(info.path, "#fff18a");
        if (version !== drawVersion) return;
        ctx.globalAlpha = 0.9;
        ctx.drawImage(mask, 0, 0);
      }
    }
  }
  if (selected?.kind === "tr") {
    const item = meta.tr.find((entry) => entry.id === selected.id);
    if (item) {
      const mask = await tinted(item.path, "#ff55d8");
      if (version !== drawVersion) return;
      ctx.globalAlpha = 0.95;
      ctx.drawImage(mask, 0, 0);
    }
  }
  ctx.globalAlpha = 1;
  ctx.strokeStyle = "#ffffff70";
  ctx.lineWidth = Math.max(1, width / 1200);
  ctx.beginPath();
  ctx.moveTo(width / 2, 0);
  ctx.lineTo(width / 2, height);
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();
}

function objectName(kind, id) {
  return state.annotations[kind][id]?.name || "";
}

function updateSummary() {
  const meta = state.metadata;
  const unnamedE = meta.electrodes.filter((item) => !objectName("electrodes", item.id)).length;
  const unnamedT = meta.tr.filter((item) => !objectName("tr", item.id)).length;
  $("summary").textContent = `${meta.output_shape_px[1]}×${meta.output_shape_px[0]} px · ${meta.pixel_size_um} µm/px · ${unnamedE} unnamed electrodes · ${unnamedT} unnamed TRs`;
}

function renderList() {
  const list = $("object-list");
  list.replaceChildren();
  $("electrode-tab").classList.toggle("active", tab === "electrodes");
  $("tr-tab").classList.toggle("active", tab === "tr");
  const search = $("search").value.trim().toLocaleLowerCase();
  const items = state.metadata[tab];
  for (const item of items) {
    const name = objectName(tab, item.id);
    if ($("unnamed").checked && name) continue;
    if (search && !(item.id + " " + name).toLocaleLowerCase().includes(search)) continue;
    const button = node("button", `${item.id}  ${name || "(unnamed)"}`);
    button.classList.toggle("active", selected?.kind === tab && selected.id === item.id);
    button.onclick = () => {
      selected = {kind: tab, id: item.id};
      renderList();
      renderEditor();
      draw().catch((error) => status(error.message, true));
    };
    list.append(button);
  }
}

function field(container, labelText, value, onInput) {
  const label = node("label", labelText);
  const input = node("input");
  input.value = value;
  input.addEventListener("input", () => onInput(input.value));
  label.append(input);
  container.append(label);
  return input;
}

function renderSuggestions() {
  const panel = $("suggestions");
  panel.replaceChildren();
  panel.append(node("strong", "Suggestions require confirmation"));
  if (!selected) return;
  const info = state.suggestions[selected.kind]?.[selected.id];
  if (!info) {
    panel.append(node("p", "No anchored circuit evidence yet.", "muted"));
    return;
  }
  if (selected.kind === "tr") {
    panel.append(node("p", `${info.status}: ${info.device_candidates.join(", ") || "none"}`));
  } else {
    panel.append(node("p", `${info.status}: ${info.net_candidates.join(", ") || "none"}`));
  }
  if (state.suggestions.conflicts.includes(selected.id)) {
    panel.append(node("p", "Conflicting net anchors need correction.", "error"));
  }
}

function renderEditor() {
  const editor = $("editor");
  editor.replaceChildren();
  if (!selected) {
    editor.append(node("p", "Select an item to name it."));
    $("selection-title").textContent = "Select an electrode or TR";
    renderSuggestions();
    return;
  }
  const {kind, id} = selected;
  const item = state.metadata[kind].find((row) => row.id === id);
  $("selection-title").textContent = `${id} · ${objectName(kind, id) || "unnamed"}`;
  editor.append(node("h2", kind === "tr" ? `TR ${id}` : `Electrode ${id}`));
  const row = state.annotations[kind][id] ||= kind === "tr"
    ? {name: "", device_id: ""} : {name: "", net: ""};
  field(editor, "Display name", row.name, (value) => {
    row.name = value;
    updateSummary();
  });
  if (kind === "electrodes") {
    field(editor, "Confirmed circuit net ID (optional)", row.net, (value) => {row.net = value;});
    editor.append(node("p", "Layers: " + Object.keys(item.layers).join(", "), "muted"));
  } else {
    editor.append(node("p", `Source: ${item.source_pair.gat} × ${item.source_pair.channel}`, "muted"));
    const label = node("label", "Circuit device anchor");
    const select = node("select");
    const empty = node("option", "Unassigned");
    empty.value = "";
    select.append(empty);
    for (const device of state.circuit?.devices || []) {
      const option = node("option", device.id);
      option.value = device.id;
      select.append(option);
    }
    select.value = row.device_id;
    select.onchange = () => {
      row.device_id = select.value;
      const device = state.circuit?.devices.find((candidate) => candidate.id === row.device_id);
      if (device) {
        const links = state.annotations.terminal_links[id] ||= {};
        if (!("B" in device.terminals)) delete links.B;
        for (const terminal of Object.keys(device.terminals)) {
          const link = links[terminal] ||= {net: "", electrodes: []};
          if (!link.net) link.net = device.terminals[terminal];
        }
      }
      renderEditor();
    };
    label.append(select);
    editor.append(label);
    editor.append(node("p", "Map each terminal to a circuit net and one or more extracted electrodes. Gate segments may share one net after TR cutting.", "muted"));
    const links = state.annotations.terminal_links[id] ||= {};
    const device = state.circuit?.devices.find((candidate) => candidate.id === row.device_id);
    const terminalNames = ["G", "S", "D", "B"].filter((terminal) =>
      terminal !== "B" || (device ? "B" in device.terminals : "B" in links));
    for (const terminal of terminalNames) {
      const link = links[terminal] ||= {net: "", electrodes: []};
      const box = node("div", undefined, "terminal-row");
      box.append(node("strong", terminal));
      field(box, "Net ID", link.net, (value) => {link.net = value;});
      const idInput = field(box, "Electrode IDs (comma separated)", link.electrodes.join(", "), (value) => {
        link.electrodes = value.split(/[\s,]+/).filter(Boolean);
      });
      idInput.placeholder = "E00001, E00002";
      const adjacent = item.terminal_adjacency
        .filter((entry) => entry.electrode_id && (terminal === "G"
          ? entry.layer === item.source_pair.gat
          : entry.layer === item.source_pair.channel))
        .map((entry) => entry.electrode_id);
      box.append(node("p", "Nearby: " + ([...new Set(adjacent)].join(", ") || "none"), "muted"));
      editor.append(box);
    }
    if (!device && !("B" in links)) {
      const addBody = node("button", "Add explicit body terminal");
      addBody.type = "button";
      addBody.onclick = () => {
        links.B = {net: "", electrodes: []};
        renderEditor();
      };
      editor.append(addBody);
    }
  }
  renderSuggestions();
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Review-Token": state.csrf},
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}

async function save() {
  const result = await post("/api/save", {annotations: state.annotations, revision: state.revision});
  state.revision = result.revision;
  state.suggestions = result.suggestions;
  renderList();
  renderEditor();
  status("Annotations saved.");
}

async function start() {
  const response = await fetch("/api/state");
  if (!response.ok) throw new Error("Could not load review state");
  state = await response.json();
  const layerSelect = $("layer");
  const all = node("option", "All layers");
  all.value = "ALL";
  layerSelect.append(all);
  for (const item of state.metadata.layers) {
    const option = node("option", `${item.id} (${item.role})`);
    option.value = item.id;
    layerSelect.append(option);
  }
  layerSelect.onchange = () => {layer = layerSelect.value; draw().catch((error) => status(error.message, true));};
  $("electrode-tab").onclick = () => {
    tab = "electrodes";
    selected = null;
    renderList();
    renderEditor();
    draw().catch((error) => status(error.message, true));
  };
  $("tr-tab").onclick = () => {
    tab = "tr";
    selected = null;
    renderList();
    renderEditor();
    draw().catch((error) => status(error.message, true));
  };
  $("search").oninput = renderList;
  $("unnamed").onchange = renderList;
  $("save").onclick = () => save().catch((error) => status(error.message, true));
  $("export").onclick = async () => {
    try {
      await save();
      const result = await post("/api/export", {});
      status("Exported to " + result.output);
    } catch (error) {
      status(error.message, true);
    }
  };
  if (state.schematic_available) {
    const img = node("img");
    img.src = "/api/schematic";
    img.alt = "Imported schematic reference";
    $("schematic-wrap").replaceChildren(img);
  }
  updateSummary();
  renderList();
  renderEditor();
  await draw();
}

start().catch((error) => status(error.message, true));
