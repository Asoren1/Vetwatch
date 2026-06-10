// ============================================================
// VetWatch frontend
// ============================================================

const state = {
  selectedState: "",
  county: "",
  days: 30,
  isLoading: false,
  lastAlerts: [],
};

const els = {
  pills: document.getElementById("state-pills"),
  countyInput: document.getElementById("county-input"),
  daysInput: document.getElementById("days-input"),
  daysLabel: document.getElementById("days-label"),
  runButton: document.getElementById("run-button"),
  results: document.getElementById("results"),
  listCounter: document.getElementById("list-counter"),
  statusSources: document.getElementById("status-sources"),
  statusMapped: document.getElementById("status-mapped"),
  statusTime: document.getElementById("status-time"),
};

// ---------- map setup ----------

// Initial view centered on the SW US
const map = L.map("map", { zoomControl: true, attributionControl: true })
  .setView([34.5, -108.0], 5);

// Plain neutral tile layer — easier on the eyes than the default OSM colors
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: '© OpenStreetMap contributors',
  opacity: 0.75,
}).addTo(map);

const markerGroup = L.layerGroup().addTo(map);

// State bounds for auto-zoom (kept in sync with backend's STATE_BOUNDS)
const STATE_BOUNDS = {
  AZ: [[31.33, -114.82], [37.00, -109.05]],
  CA: [[32.53, -124.41], [42.01, -114.13]],
  NM: [[31.33, -109.05], [37.00, -103.00]],
  NV: [[35.00, -120.01], [42.00, -114.04]],
  TX: [[25.84, -106.65], [36.50, -93.51]],
};

// ---------- event wiring ----------

els.pills.addEventListener("click", (e) => {
  const button = e.target.closest("button.pill");
  if (!button) return;
  state.selectedState = button.dataset.state;
  for (const b of els.pills.querySelectorAll(".pill")) {
    b.setAttribute("aria-pressed", b === button ? "true" : "false");
  }
});

els.countyInput.addEventListener("input", (e) => { state.county = e.target.value.trim(); });
els.daysInput.addEventListener("change", (e) => {
  state.days = parseInt(e.target.value, 10);
  els.daysLabel.textContent = state.days;
});
els.runButton.addEventListener("click", () => runScan());
els.countyInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runScan(); });
els.pills.querySelector('[data-state=""]').setAttribute("aria-pressed", "true");

// ---------- scan ----------

async function runScan() {
  if (state.isLoading) return;
  state.isLoading = true;
  els.runButton.disabled = true;
  els.runButton.textContent = "scanning";
  els.results.innerHTML = `<div class="scanning">scanning sources</div>`;
  markerGroup.clearLayers();

  const params = new URLSearchParams();
  if (state.selectedState) params.set("state", state.selectedState);
  if (state.county) params.set("county", state.county);
  params.set("days", state.days);

  try {
    const resp = await fetch(`/api/alerts?${params}`);
    if (!resp.ok) throw new Error(`server returned ${resp.status}`);
    const data = await resp.json();
    state.lastAlerts = data.alerts || [];
    renderResults(data);
    renderMarkers(data.alerts || []);
    renderStatus(data);
    fitMapToSelection();
  } catch (err) {
    els.results.innerHTML = `
      <div class="empty-state">
        <p class="empty-headline">scan failed</p>
        <p class="empty-sub">${escapeHtml(err.message)}</p>
      </div>`;
  } finally {
    state.isLoading = false;
    els.runButton.disabled = false;
    els.runButton.textContent = "scan";
  }
}

function fitMapToSelection() {
  if (state.selectedState && STATE_BOUNDS[state.selectedState]) {
    map.fitBounds(STATE_BOUNDS[state.selectedState], { padding: [20, 20] });
  } else {
    map.setView([34.5, -108.0], 5);
  }
}

// ---------- render ----------

function renderResults(data) {
  if (!data.alerts || data.alerts.length === 0) {
    const scope = state.selectedState || "any state";
    els.results.innerHTML = `
      <div class="empty-state">
        <p class="empty-headline">no alerts</p>
        <p class="empty-sub">
          no relevant items in the last ${state.days} days for ${scope}.
          this means connected sources returned nothing the AI flagged as
          vet-actionable — not necessarily that nothing is happening.
        </p>
      </div>`;
    els.listCounter.textContent = "0";
    return;
  }
  els.listCounter.textContent = data.alerts.length;
  els.results.innerHTML = data.alerts.map(renderAlert).join("");

  // Wire up alert ↔ map sync
  for (const el of els.results.querySelectorAll(".alert")) {
    el.addEventListener("click", (e) => {
      // Don't intercept clicks on the title link itself
      if (e.target.tagName === "A") return;
      const id = el.dataset.id;
      const alert = state.lastAlerts.find(a => a.id === id);
      if (alert && alert.latitude != null) {
        map.flyTo([alert.latitude, alert.longitude], 7, { duration: 0.6 });
      }
    });
  }
}

function renderAlert(a) {
  const date = new Date(a.published);
  const dateStr = date.toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "2-digit",
  });

  const sourceType = a.source_type || "federal";
  const tagClass = sourceType.replace(/[^a-z-]/g, "");

  const summary = a.clinical_summary
    ? `<p class="alert-summary">${escapeHtml(a.clinical_summary)}</p>`
    : `<p class="alert-summary muted">no summary — see source for details</p>`;

  const chips = [];
  if (a.category && a.category !== "other") {
    chips.push(`<span class="chip category-${a.category}">${escapeHtml(a.category)}</span>`);
  }
  if (a.county) {
    chips.push(`<span class="chip county">${escapeHtml(a.county)} co.</span>`);
  } else if (a.state) {
    chips.push(`<span class="chip">${escapeHtml(a.state)}</span>`);
  }
  for (const sp of (a.species || []).slice(0, 3)) {
    chips.push(`<span class="chip">${escapeHtml(sp)}</span>`);
  }

  return `
    <article class="alert" data-id="${escapeAttr(a.id)}">
      <div class="alert-meta">
        <span class="alert-date">${dateStr}</span>
        <span><span class="alert-source-tag ${tagClass}"></span>${escapeHtml(a.source)}</span>
      </div>
      <h3 class="alert-title">
        <a href="${escapeAttr(a.url)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(a.title)}
        </a>
      </h3>
      ${summary}
      <div class="alert-tags">${chips.join("")}</div>
    </article>`;
}

function renderMarkers(alerts) {
  const mapped = alerts.filter(a => a.latitude != null && a.longitude != null);

  for (const a of mapped) {
    const cat = a.category || "other";
    const stateFallback = a.geo_resolution === "state";
    const iconHtml = `<div class="vw-marker category-${cat} ${stateFallback ? "state-fallback" : ""}"></div>`;
    const icon = L.divIcon({
      html: iconHtml,
      className: "",
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });

    const marker = L.marker([a.latitude, a.longitude], { icon }).addTo(markerGroup);
    const popupHtml = `
      <div class="popup-title">${escapeHtml(a.title)}</div>
      <div class="popup-meta">${escapeHtml(a.source)} · ${formatDate(a.published)}${a.county ? " · " + escapeHtml(a.county) + " Co." : ""}</div>
      ${a.clinical_summary ? `<div>${escapeHtml(a.clinical_summary)}</div>` : ""}
      <div style="margin-top:6px"><a href="${escapeAttr(a.url)}" target="_blank" rel="noopener noreferrer">view source →</a></div>
    `;
    marker.bindPopup(popupHtml, { maxWidth: 320 });

    // Click marker → scroll its alert into view in the list
    marker.on("click", () => {
      const el = els.results.querySelector(`.alert[data-id="${a.id}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        el.classList.add("highlighted");
        setTimeout(() => el.classList.remove("highlighted"), 1500);
      }
    });
  }
}

function renderStatus(data) {
  const ok = (data.adapter_status || []).filter(s => s.status === "ok").length;
  const total = (data.adapter_status || []).length;
  els.statusSources.innerHTML = `<span class="ok">${ok}</span>/${total} responded`;

  const mapped = (data.alerts || []).filter(a => a.latitude != null).length;
  const totalAlerts = (data.alerts || []).length;
  els.statusMapped.textContent = `${mapped}/${totalAlerts} on map`;

  els.statusTime.textContent = new Date().toLocaleTimeString();
}

// ---------- utilities ----------

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "2-digit",
  });
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(s) { return escapeHtml(s); }
