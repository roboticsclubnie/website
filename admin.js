/**
 * ROBOTICS CLUB NIE — admin.js
 * Host Admin Portal logic: Passcode verification, live SQL roster fetch,
 * candidate verification by unique code & USN, automated SMTP email configuration,
 * client-side search & filtering, real-time Excel download, and passcode management.
 */

const AUTH_TOKEN_KEY = "rc_host_token";
const STORAGE_KEY = "nie_robotics_recruitment_registrations";
const GOOGLE_SHEET_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxJmWqZ3WW4iuL4ag-AFd0ishWiKJlYMpZdqZz3cIHSSGEqgdn5OqcE_lxjK38hNg2s/exec";
let allRegistrations = [];

// Local modification tracking map (prevent in-flight poll overwrite race conditions)
const recentlyModified = new Map(); // usn.toUpperCase() -> { is_verified: 0|1, timestamp: number }
let liveSyncIntervalId = null;
let isLiveSyncInProgress = false;

/**
 * Automatically determine the correct backend API base URL.
 * When served via server.py (port 8080), returns relative "" (e.g. "/api/...").
 * When opened via VS Code Live Server (port 5500), Vite (port 5173), or file://,
 * automatically routes requests to "http://localhost:8080" where the Python backend runs.
 */
function getApiBaseUrl() {
  const origin = window.location.origin;
  if (!origin || origin === "null" || window.location.protocol === "file:") {
    return "http://localhost:8080";
  }
  const port = window.location.port;
  if (port && port !== "8080") {
    return "http://localhost:8080";
  }
  return "";
}

/**
 * Robust JSON fetch helper that safely parses responses and provides
 * clear, actionable error messages instead of SyntaxError on empty bodies.
 */
async function safeFetchJson(endpoint, options = {}) {
  const base = getApiBaseUrl();
  const url = endpoint.startsWith("http") ? endpoint : `${base}${endpoint}`;

  let res;
  try {
    res = await fetch(url, options);
  } catch (netErr) {
    throw new Error(
      `Cannot connect to backend server at ${url}. Please ensure 'python server.py' is running in your terminal.`
    );
  }

  const rawText = await res.text();
  let data = {};

  try {
    data = rawText ? JSON.parse(rawText) : {};
  } catch (parseErr) {
    if (!res.ok) {
      if (res.status === 405) {
        throw new Error(
          `Status 405 (Method Not Allowed): You are accessing this on a static host (e.g. GitHub Pages) which cannot run Python scripts. To use the admin backend, open http://localhost:8080/admin.html with 'python server.py' running locally.`
        );
      }
      throw new Error(`Server returned status ${res.status}. Is 'python server.py' running at http://localhost:8080?`);
    }
    throw new Error(`Invalid response received from ${endpoint}.`);
  }

  // Handle session expiration
  if (res.status === 401) {
    const errorMsg = data.message || "Unauthorized session. Please unlock the portal with your passcode.";
    // Don't auto-redirect on login attempt failure
    if (!endpoint.includes("/login")) {
      sessionStorage.removeItem(AUTH_TOKEN_KEY);
      hideDashboard();
      showGateError("Session expired or unauthorized. Please re-enter your passcode.");
    }
    return { ok: false, status: 401, data: { status: "error", message: errorMsg } };
  }

  return { ok: res.ok, status: res.status, data };
}

document.addEventListener("DOMContentLoaded", () => {
  initAuth();
  initDashboardControls();
});

/**
 * Initialize Passcode Authentication & Session Recovery
 */
function initAuth() {
  const passcodeForm = document.getElementById("passcodeForm");
  const passcodeInput = document.getElementById("passcodeInput");
  const toggleVisBtn = document.getElementById("togglePasscodeVis");
  const logoutBtn = document.getElementById("logoutBtn");
  const gateErrorMsg = document.getElementById("gateErrorMsg");

  // Toggle eye visibility
  if (toggleVisBtn && passcodeInput) {
    toggleVisBtn.addEventListener("click", () => {
      if (passcodeInput.type === "password") {
        passcodeInput.type = "text";
        toggleVisBtn.textContent = "🙈";
      } else {
        passcodeInput.type = "password";
        toggleVisBtn.textContent = "👁️";
      }
    });
  }

  // Handle Passcode Form Submit
  if (passcodeForm) {
    passcodeForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const code = passcodeInput.value.trim();
      if (!code) return;

      gateErrorMsg.style.display = "none";
      const unlockBtn = document.getElementById("unlockBtn");
      unlockBtn.disabled = true;
      unlockBtn.innerHTML = `<span>Verifying...</span>`;

      try {
        const { ok, data } = await safeFetchJson("/api/admin/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ passcode: code })
        });

        if (ok && data.status === "success") {
          sessionStorage.setItem(AUTH_TOKEN_KEY, data.token);
          passcodeInput.value = "";
          showDashboard();
        } else {
          showGateError(data.message || "Incorrect passcode. Access denied.");
        }
      } catch (err) {
        console.warn("Backend login API unreachable, checking local verification:", err);
        if (code === "roboticsnie2026") {
          sessionStorage.setItem(AUTH_TOKEN_KEY, "roboticsnie2026");
          showDashboard();
        } else {
          showGateError(err.message || "Incorrect Host Passcode. Please try again.");
        }
      } finally {
        unlockBtn.disabled = false;
        unlockBtn.innerHTML = `<span>Unlock Dashboard</span> <span aria-hidden="true">&rarr;</span>`;
      }
    });
  }

  // Logout
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      sessionStorage.removeItem(AUTH_TOKEN_KEY);
      allRegistrations = [];
      hideDashboard();
    });
  }

  // Auto-login if session token exists
  const existingToken = sessionStorage.getItem(AUTH_TOKEN_KEY);
  if (existingToken) {
    showDashboard();
  }
}

function showGateError(msg) {
  const gateErrorMsg = document.getElementById("gateErrorMsg");
  if (gateErrorMsg) {
    gateErrorMsg.textContent = msg;
    gateErrorMsg.style.display = "block";
  }
}

function showDashboard() {
  document.getElementById("passcodeGate").style.display = "none";
  document.getElementById("adminDashboard").style.display = "block";
  document.getElementById("logoutBtn").style.display = "inline-flex";
  fetchRegistrations();
  startLiveSync();
}

function hideDashboard() {
  stopLiveSync();
  document.getElementById("adminDashboard").style.display = "none";
  document.getElementById("passcodeGate").style.display = "flex";
  document.getElementById("logoutBtn").style.display = "none";
  const passcodeInput = document.getElementById("passcodeInput");
  if (passcodeInput) passcodeInput.focus();
}

/**
 * Update cloud connection status badge in header
 */
function updateCloudBadge(isConnected, message) {
  const badge = document.getElementById("cloudStatusBadge");
  const text = document.getElementById("cloudStatusText");
  const liveBadge = document.getElementById("cloudSyncLiveBadge");
  if (badge) {
    badge.className = `header-badge cloud-badge ${isConnected ? 'connected' : 'notice'}`;
  }
  if (text) {
    text.textContent = message;
  }
  if (liveBadge) {
    liveBadge.className = isConnected ? "badge bg-success" : "badge bg-warning text-dark";
    liveBadge.textContent = isConnected ? "Online & Synced" : "Webhook Active";
  }
}

/**
 * Update real-time live sync badge in header
 */
function updateLiveSyncBadge(statusText) {
  const text = document.getElementById("liveSyncText");
  if (text) {
    text.textContent = `🟢 Live Sync: ${statusText}`;
  }
}

/**
 * Show notice banner if Google Sheet Apps Script needs 1-minute update for cross-device sync
 */
function showAppsScriptUpdateNotice() {
  const banner = document.getElementById("cloudScriptAlertBanner");
  if (banner) banner.style.display = "flex";
}

function hideAppsScriptUpdateNotice() {
  const banner = document.getElementById("cloudScriptAlertBanner");
  if (banner) banner.style.display = "none";
}

/**
 * Update candidate verification status live across Google Sheet (Cloud),
 * local cache, and local SQLite backend if available.
 */
async function updateVerificationStatus(usn, code, isVerified, id = null) {
  const newStatusInt = isVerified ? 1 : 0;
  const statusStr = isVerified ? "Verified" : "Pending";
  const cleanUsn = (usn || "").trim().toUpperCase();
  const cleanCode = (code || "").trim().toUpperCase();

  // 1. Set local modification lock (12s) to prevent incoming polls from overwriting before cloud persists
  const now = Date.now();
  if (cleanUsn) recentlyModified.set(cleanUsn, { is_verified: newStatusInt, timestamp: now });
  if (cleanCode) recentlyModified.set(cleanCode, { is_verified: newStatusInt, timestamp: now });

  // 2. Immediately update in-memory registrations (optimistic UI update)
  allRegistrations = allRegistrations.map(r => {
    const matchUsn = cleanUsn && r.usn && r.usn.toUpperCase() === cleanUsn;
    const matchCode = cleanCode && r.verification_code && r.verification_code.toUpperCase() === cleanCode;
    const matchId = id && r.id == id;
    if (matchUsn || matchCode || matchId) {
      return { ...r, is_verified: newStatusInt };
    }
    return r;
  });

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations));
  } catch (e) {}

  updateKpis(allRegistrations);
  applyFiltersAndRender();

  // 3. Transmit status update to Google Sheet (Universal Cloud Webhook for all devices)
  let cloudSucceeded = false;
  if (GOOGLE_SHEET_SCRIPT_URL) {
    try {
      const queryParams = new URLSearchParams({
        action: "update_status",
        usn: cleanUsn,
        code: cleanCode,
        status: statusStr,
        _t: Date.now().toString()
      });
      const getUrl = `${GOOGLE_SHEET_SCRIPT_URL}?${queryParams.toString()}`;
      const cloudRes = await fetch(getUrl);
      const json = await cloudRes.json();

      if (json && (json.status === "success" || json.updated_rows !== undefined)) {
        cloudSucceeded = true;
        updateCloudBadge(true, `☁️ Google Sheet: Synced (${statusStr})`);
        hideAppsScriptUpdateNotice();
      } else if (json && json.data && Array.isArray(json.data)) {
        // Returned all rows without updating -> old Apps Script running in user's sheet
        showAppsScriptUpdateNotice();
      }
    } catch (err) {
      // Fallback: try POST with form urlencoded
      try {
        const postData = new URLSearchParams({
          action: "update_status",
          usn: cleanUsn,
          code: cleanCode,
          status: statusStr
        });
        await fetch(GOOGLE_SHEET_SCRIPT_URL, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: postData.toString()
        });
        cloudSucceeded = true;
      } catch (pErr) {
        console.warn("Google Sheet status update notice:", pErr);
      }
    }
  }

  // 4. Update local SQLite backend (/api/admin/toggle-verify) if server is running
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  try {
    await safeFetchJson("/api/admin/toggle-verify", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        id: id ? parseInt(id, 10) : undefined,
        usn: cleanUsn,
        verification_code: cleanCode,
        is_verified: newStatusInt
      })
    });
  } catch (beErr) {
    // Backend offline is expected in static / cloud mode
  }

  return cloudSucceeded;
}

/**
 * Real-time background sync loop.
 * Runs every 4 seconds to detect status changes made by coordinators on other devices.
 */
function startLiveSync() {
  if (liveSyncIntervalId) clearInterval(liveSyncIntervalId);
  liveSyncIntervalId = setInterval(syncLiveUpdates, 4000);
  updateLiveSyncBadge("Active (4s)");
}

function stopLiveSync() {
  if (liveSyncIntervalId) {
    clearInterval(liveSyncIntervalId);
    liveSyncIntervalId = null;
  }
}

async function syncLiveUpdates() {
  const dash = document.getElementById("adminDashboard");
  if (!dash || dash.style.display === "none") return;
  if (isLiveSyncInProgress) return;
  if (document.hidden) return; // Don't poll when tab is inactive to save battery
  if (!GOOGLE_SHEET_SCRIPT_URL) return;

  isLiveSyncInProgress = true;
  try {
    const res = await fetch(`${GOOGLE_SHEET_SCRIPT_URL}?_t=${Date.now()}`);
    const json = await res.json();

    if (json && json.status === "success" && Array.isArray(json.data)) {
      const cloudRows = json.data;
      let hasChanges = false;
      const changedUsns = new Set();

      const currentMap = new Map();
      allRegistrations.forEach(r => {
        if (r.usn) currentMap.set(r.usn.toUpperCase(), r);
      });

      cloudRows.forEach(cr => {
        const u = (cr.usn || "").toUpperCase();
        if (!u) return;

        const recentMod = recentlyModified.get(u);
        const isLocked = recentMod && (Date.now() - recentMod.timestamp < 12000);

        if (!currentMap.has(u)) {
          // New candidate registered on another device!
          currentMap.set(u, cr);
          hasChanges = true;
          changedUsns.add(u);
        } else {
          const existing = currentMap.get(u);
          const cloudStatus = cr.is_verified ? 1 : 0;
          const existingStatus = existing.is_verified ? 1 : 0;

          // Status changed in cloud by another coordinator on another device!
          if (!isLocked && cloudStatus !== existingStatus) {
            existing.is_verified = cloudStatus;
            hasChanges = true;
            changedUsns.add(u);
          }

          if (!existing.verification_code && cr.verification_code) {
            existing.verification_code = cr.verification_code;
            hasChanges = true;
          }
        }
      });

      if (hasChanges) {
        allRegistrations = Array.from(currentMap.values());
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations));
        } catch (e) {}

        updateKpis(allRegistrations);

        // Preserve search input focus & cursor if coordinator is currently typing
        const activeEl = document.activeElement;
        const isSearchFocused = activeEl && activeEl.id === "searchInput";
        const selStart = isSearchFocused ? activeEl.selectionStart : null;
        const selEnd = isSearchFocused ? activeEl.selectionEnd : null;

        applyFiltersAndRender();

        if (isSearchFocused) {
          const searchInput = document.getElementById("searchInput");
          if (searchInput) {
            searchInput.focus();
            if (selStart !== null && selEnd !== null) {
              searchInput.setSelectionRange(selStart, selEnd);
            }
          }
        }

        // Apply real-time highlight flash animation to changed rows
        changedUsns.forEach(u => {
          const safeId = "row-" + u.replace(/[^a-zA-Z0-9]/g, "");
          const rowEl = document.getElementById(safeId);
          if (rowEl) {
            rowEl.classList.add("row-live-updated");
            setTimeout(() => {
              if (rowEl) rowEl.classList.remove("row-live-updated");
            }, 2500);
          }
        });

        // Update candidate card if verify modal is open
        if (typeof currentCandidate !== "undefined" && currentCandidate && currentCandidate.usn) {
          const updatedCand = currentMap.get(currentCandidate.usn.toUpperCase());
          if (updatedCand && updatedCand.is_verified !== currentCandidate.is_verified) {
            currentCandidate.is_verified = updatedCand.is_verified;
            if (typeof renderCandidateCard === "function") {
              renderCandidateCard(currentCandidate);
            }
          }
        }

        updateLiveSyncBadge("Updated just now ⚡");
        setTimeout(() => updateLiveSyncBadge("Active (4s)"), 2000);
      }
    }
  } catch (err) {
    // Network intermittent glitch — silent retry
  } finally {
    isLiveSyncInProgress = false;
  }
}


/**
 * Background helper to sync cloud records into local SQLite and Excel if backend server is running
 */
async function syncRegistrationsToBackend(items) {
  if (!items || items.length === 0) return;
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) return;
  try {
    await safeFetchJson("/api/admin/import-batch", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ registrations: items })
    });
  } catch (e) {
    // Backend may be offline (e.g. running on static GitHub Pages) - expected
  }
}

/**
 * Fetch registrations from SQL API, Google Sheet Cloud Webhook, and Offline Cache
 */
async function fetchRegistrations() {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  let localData = [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    localData = raw ? JSON.parse(raw) : [];
  } catch (e) {
    localData = [];
  }

  // Pre-populate with local cache immediately so coordinator doesn't see an empty screen
  if (allRegistrations.length === 0 && localData.length > 0) {
    allRegistrations = localData;
    updateKpis(allRegistrations);
    applyFiltersAndRender();
  }

  const mergedMap = new Map();
  // 1. Seed with local offline cache
  localData.forEach(r => {
    if (r.usn) mergedMap.set(r.usn.toUpperCase(), r);
  });

  // 2. Fetch from local SQL backend if running
  let backendActive = false;
  try {
    const { ok, data } = await safeFetchJson("/api/admin/registrations", {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (ok && data.status === "success" && Array.isArray(data.data)) {
      backendActive = true;
      data.data.forEach(r => {
        if (r.usn) mergedMap.set(r.usn.toUpperCase(), r);
      });
      const beBadge = document.getElementById("backendStatusBadge");
      if (beBadge) beBadge.textContent = `Live SQL Active (${data.data.length})`;
    }
  } catch (err) {
    const beBadge = document.getElementById("backendStatusBadge");
    if (beBadge) beBadge.textContent = "Client / Cloud Mode";
  }

  // 3. Fetch live cloud submissions from Google Sheet Webhook
  let cloudItems = [];
  if (GOOGLE_SHEET_SCRIPT_URL) {
    try {
      const res = await fetch(GOOGLE_SHEET_SCRIPT_URL);
      const cloudRes = await res.json();
      if (cloudRes && cloudRes.status === "success" && Array.isArray(cloudRes.data)) {
        cloudItems = cloudRes.data;
        cloudItems.forEach(cr => {
          const u = (cr.usn || "").toUpperCase();
          if (!u) return;
          if (!mergedMap.has(u)) {
            mergedMap.set(u, cr);
          } else {
            const ex = mergedMap.get(u);
            if (!ex.verification_code && cr.verification_code) {
              ex.verification_code = cr.verification_code;
            }
            // Synchronize verified status from cloud!
            const recentMod = recentlyModified.get(u);
            if (recentMod && (Date.now() - recentMod.timestamp < 12000)) {
              ex.is_verified = recentMod.is_verified;
            } else {
              ex.is_verified = cr.is_verified ? 1 : 0;
            }
            // Fill any missing details from cloud
            if (!ex.name && cr.name) ex.name = cr.name;
            if (!ex.email && cr.email) ex.email = cr.email;
            if (!ex.phone && cr.phone) ex.phone = cr.phone;
            if (!ex.year && cr.year) ex.year = cr.year;
            if (!ex.branch && cr.branch) ex.branch = cr.branch;
          }
        });
        updateCloudBadge(true, `☁️ Google Sheet: ${cloudItems.length} Synced`);
      } else if (cloudRes && cloudRes.status === "active") {
        updateCloudBadge(false, `☁️ Google Sheet: Active (Update script for auto-read)`);
      }
    } catch (cErr) {
      console.warn("Google Sheet sync notice:", cErr);
      updateCloudBadge(false, `☁️ Google Sheet: Standby`);
    }
  }

  allRegistrations = Array.from(mergedMap.values());
  // Save merged state into localStorage
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations));
  } catch (e) {}

  // If local server is running and we discovered cloud records, sync them to SQLite & Excel on disk
  if (backendActive && cloudItems.length > 0) {
    syncRegistrationsToBackend(cloudItems);
  }

  updateKpis(allRegistrations);
  applyFiltersAndRender();
}

/**
 * Update KPI metrics cards
 */
function updateKpis(data) {
  const kpiTotalEl = document.getElementById("kpiTotal");
  if (kpiTotalEl) kpiTotalEl.textContent = data.length;

  const verifiedCount = data.filter(r => Boolean(r.is_verified)).length;
  const kpiVerifiedEl = document.getElementById("kpiVerified");
  if (kpiVerifiedEl) {
    const pct = data.length > 0 ? Math.round((verifiedCount / data.length) * 100) : 0;
    kpiVerifiedEl.textContent = `${verifiedCount} (${pct}%)`;
  }

  const firstYears = data.filter(r => (r.year || "").includes("1st")).length;
  const secondYears = data.filter(r => (r.year || "").includes("2nd")).length;
  const seniorYears = data.filter(r => (r.year || "").includes("3rd") || (r.year || "").includes("4th")).length;

  const kpiFirst = document.getElementById("kpiFirstYears");
  const kpiSecond = document.getElementById("kpiSecondYears");
  const kpiSenior = document.getElementById("kpiSeniorYears");
  if (kpiFirst) kpiFirst.textContent = firstYears;
  if (kpiSecond) kpiSecond.textContent = secondYears;
  if (kpiSenior) kpiSenior.textContent = seniorYears;
}

/**
 * Initialize Dashboard Controls: Search, Filters, Refresh, Excel Download, Modals
 */
function initDashboardControls() {
  const searchInput = document.getElementById("searchInput");
  const branchFilter = document.getElementById("branchFilter");
  const yearFilter = document.getElementById("yearFilter");
  const statusFilter = document.getElementById("statusFilter");
  const refreshBtn = document.getElementById("refreshBtn");
  const downloadExcelBtn = document.getElementById("downloadExcelBtn");
  const openScriptBannerBtn = document.getElementById("openScriptUpdateFromBanner");

  if (openScriptBannerBtn) {
    openScriptBannerBtn.addEventListener("click", () => {
      const modal = document.getElementById("importModal");
      if (modal) {
        modal.style.display = "flex";
        const tabBtns = modal.querySelectorAll(".import-tab-btn");
        const tabContents = modal.querySelectorAll(".import-tab-content");
        tabBtns.forEach(b => b.classList.remove("active"));
        tabContents.forEach(c => c.style.display = "none");
        const sheetTabBtn = modal.querySelector('[data-tab="tabGoogleSheet"]');
        if (sheetTabBtn) sheetTabBtn.classList.add("active");
        const sheetTabContent = document.getElementById("tabGoogleSheet");
        if (sheetTabContent) sheetTabContent.style.display = "block";
      }
    });
  }

  if (searchInput) searchInput.addEventListener("input", applyFiltersAndRender);
  if (branchFilter) branchFilter.addEventListener("change", applyFiltersAndRender);
  if (yearFilter) yearFilter.addEventListener("change", applyFiltersAndRender);
  if (statusFilter) statusFilter.addEventListener("change", applyFiltersAndRender);

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      refreshBtn.disabled = true;
      refreshBtn.innerHTML = `<span>⏳ Refreshing...</span>`;
      fetchRegistrations().finally(() => {
        setTimeout(() => {
          refreshBtn.disabled = false;
          refreshBtn.innerHTML = `<span>🔄 Refresh Data</span>`;
        }, 300);
      });
    });
  }

  const syncGoogleSheetBtn = document.getElementById("syncGoogleSheetBtn");
  if (syncGoogleSheetBtn) {
    syncGoogleSheetBtn.addEventListener("click", () => {
      syncGoogleSheetBtn.disabled = true;
      syncGoogleSheetBtn.innerHTML = `<span>⏳ Syncing...</span>`;
      fetchRegistrations().finally(() => {
        setTimeout(() => {
          syncGoogleSheetBtn.disabled = false;
          syncGoogleSheetBtn.innerHTML = `<span>☁️ Sync Sheet</span>`;
        }, 500);
      });
    });
  }

  if (downloadExcelBtn) {
    downloadExcelBtn.addEventListener("click", triggerExcelDownload);
  }

  const tbody = document.getElementById("adminTableBody");
  if (tbody) {
    tbody.addEventListener("click", handleTableActions);
  }

  initVerifyModal();
  initEmailSettingsModal();
  initPasscodeModal();
  initImportModal();
}

/**
 * Filter registrations and render in table
 */
function applyFiltersAndRender() {
  const query = (document.getElementById("searchInput")?.value || "").toLowerCase().trim();
  const selectedBranch = document.getElementById("branchFilter")?.value || "all";
  const selectedYear = document.getElementById("yearFilter")?.value || "all";
  const selectedStatus = document.getElementById("statusFilter")?.value || "all";

  const filtered = allRegistrations.filter(r => {
    // 1. Text Search across Name, USN, Code, Email, Phone
    if (query) {
      const matchName = (r.name || "").toLowerCase().includes(query);
      const matchUsn = (r.usn || "").toLowerCase().includes(query);
      const matchCode = (r.verification_code || "").toLowerCase().includes(query);
      const matchEmail = (r.email || "").toLowerCase().includes(query);
      const matchPhone = (r.phone || "").toLowerCase().includes(query);
      if (!matchName && !matchUsn && !matchCode && !matchEmail && !matchPhone) return false;
    }

    // 2. Branch Filter
    if (selectedBranch !== "all") {
      if (!(r.branch || "").toLowerCase().includes(selectedBranch.toLowerCase())) {
        return false;
      }
    }

    // 3. Year Filter
    if (selectedYear !== "all") {
      if (!(r.year || "").toLowerCase().includes(selectedYear.toLowerCase())) {
        return false;
      }
    }

    // 4. Status Filter
    if (selectedStatus === "verified" && !r.is_verified) return false;
    if (selectedStatus === "pending" && r.is_verified) return false;

    return true;
  });

  renderTable(filtered);
  const resultsCount = document.getElementById("resultsCount");
  if (resultsCount) {
    resultsCount.textContent = `Showing ${filtered.length} of ${allRegistrations.length} applicants`;
  }
}

/**
 * Render table rows with verification code, status badges, and quick actions
 */
function renderTable(data) {
  const tbody = document.getElementById("adminTableBody");
  if (!tbody) return;

  if (data.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12" class="text-center py-5 text-muted">
          <div style="font-size: 2rem; margin-bottom: 8px;">📋</div>
          <div>No applicants match the selected search/filter criteria.</div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = data.map((r, i) => {
    const code = r.verification_code || "—";
    const isVerified = Boolean(r.is_verified);
    const emailSent = Boolean(r.email_sent);
    const emailError = r.email_error || "";
    const safeUsnId = "row-" + (r.usn || "").replace(/[^a-zA-Z0-9]/g, "");

    return `
      <tr id="${safeUsnId}" data-usn="${escapeHtml(r.usn || '')}">
        <td><span style="color: #64748b; font-weight: 600;">${i + 1}</span></td>
        <td><span style="font-size: 0.82rem; color: #94a3b8;">${escapeHtml(r.timestamp || "")}</span></td>
        <td><strong style="color: #ffffff;">${escapeHtml(r.name || "")}</strong></td>
        <td><span class="usn-badge">${escapeHtml(r.usn || "")}</span></td>
        <td>
          <div class="code-badge-wrapper">
            <span class="verification-code-tag">${escapeHtml(code)}</span>
            ${code !== "—" ? `<button type="button" class="btn-copy-code-pill" data-code="${escapeHtml(code)}" title="Copy verification code">📋</button>` : ""}
          </div>
        </td>
        <td><span class="year-pill">${escapeHtml(r.year || "")}</span></td>
        <td><span style="color: #cbd5e1;">${escapeHtml(r.branch || "")}</span></td>
        <td><a href="mailto:${escapeHtml(r.email)}" class="email-link">${escapeHtml(r.email || "")}</a></td>
        <td><span class="phone-tag">${escapeHtml(r.phone || "")}</span></td>
        <td style="text-align: center;">
          <button type="button" class="status-pill status-pill-toggle ${isVerified ? 'verified' : 'pending'}" 
                  data-id="${r.id || ''}" data-usn="${escapeHtml(r.usn || '')}" data-code="${escapeHtml(code)}" data-status="${isVerified ? '1' : '0'}" 
                  title="Click to toggle candidate check-in status (updates live on all devices)">
            ${isVerified ? 'Verified ✅' : 'Pending ⏳'}
          </button>
        </td>
        <td style="text-align: center;">
          <span class="email-pill ${emailSent ? 'sent' : (emailError ? 'error' : 'pending')}" 
                title="${escapeHtml(emailError || (emailSent ? 'Delivered successfully' : 'Pending or SMTP not configured'))}">
            ${emailSent ? 'Sent ✉️' : (emailError ? 'Failed ⚠️' : 'Pending ⏳')}
          </span>
        </td>
        <td style="text-align: center;">
          <div class="d-inline-flex gap-1">
            <button type="button" class="btn-table-action btn-resend-email" 
                    data-id="${r.id || ''}" data-usn="${escapeHtml(r.usn || '')}" data-name="${escapeHtml(r.name || '')}" data-email="${escapeHtml(r.email || '')}" 
                    title="Resend email confirmation with code">
              ✉️
            </button>
            <button type="button" class="btn-table-action btn-delete-row" 
                    data-id="${r.id || ''}" data-usn="${escapeHtml(r.usn || '')}" data-code="${escapeHtml(code)}" data-name="${escapeHtml(r.name || '')}" 
                    title="Delete applicant">
              🗑️
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

/**
 * Handle clicks inside table: Delete, Resend Email, Toggle Verification Status, Copy Code
 */
async function handleTableActions(e) {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);

  // 1. Copy Code Button
  const copyBtn = e.target.closest(".btn-copy-code-pill");
  if (copyBtn) {
    const code = copyBtn.getAttribute("data-code");
    try {
      await navigator.clipboard.writeText(code);
      copyBtn.textContent = "✓";
      setTimeout(() => { copyBtn.textContent = "📋"; }, 2000);
    } catch (err) {}
    return;
  }

  // 2. Toggle Verification Status (Live cloud & multi-device sync)
  const statusBtn = e.target.closest(".status-pill-toggle");
  if (statusBtn) {
    const id = statusBtn.getAttribute("data-id");
    const usn = statusBtn.getAttribute("data-usn");
    const code = statusBtn.getAttribute("data-code");
    const currentStatus = statusBtn.getAttribute("data-status") === "1";
    const newStatus = !currentStatus;

    statusBtn.disabled = true;
    statusBtn.textContent = "⏳...";

    await updateVerificationStatus(usn, code, newStatus, id);
    return;
  }

  // 3. Resend Confirmation Email
  const resendBtn = e.target.closest(".btn-resend-email");
  if (resendBtn) {
    const id = resendBtn.getAttribute("data-id");
    const usn = resendBtn.getAttribute("data-usn");
    const name = resendBtn.getAttribute("data-name");
    const email = resendBtn.getAttribute("data-email");

    if (!window.confirm(`Resend official confirmation email with verification code to:\n"${name}" (${email})?`)) {
      return;
    }

    resendBtn.disabled = true;
    resendBtn.textContent = "⏳";

    try {
      const { ok, data } = await safeFetchJson("/api/admin/resend-email", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          id: id ? parseInt(id, 10) : undefined,
          usn: usn
        })
      });

      if (ok && data.status === "success") {
        resendBtn.textContent = "✅";
        setTimeout(() => { resendBtn.textContent = "✉️"; resendBtn.disabled = false; }, 2500);
        alert(`Email confirmation successfully queued for ${email}!`);
      } else {
        alert(data.message || "Failed to resend confirmation email. Please verify SMTP settings.");
        resendBtn.textContent = "✉️";
        resendBtn.disabled = false;
      }
    } catch (err) {
      alert("Error sending request to server: " + err.message);
      resendBtn.textContent = "✉️";
      resendBtn.disabled = false;
    }
    return;
  }

  // 4. Delete Registration
  const deleteBtn = e.target.closest(".btn-delete-row");
  if (deleteBtn) {
    const id = deleteBtn.getAttribute("data-id");
    const usn = deleteBtn.getAttribute("data-usn");
    const name = deleteBtn.getAttribute("data-name");

    const confirmMsg = `Are you sure you want to remove:\n"${name}" (${usn})?\n\nThis will permanently delete this student from the SQL database and update the Excel spreadsheet.`;
    if (!window.confirm(confirmMsg)) return;

    deleteBtn.disabled = true;
    deleteBtn.textContent = "⏳";

    try {
      const { ok, data } = await safeFetchJson("/api/admin/delete-registration", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ id: id ? parseInt(id, 10) : undefined, usn: usn })
      });

      if (ok && data.status === "success") {
        allRegistrations = allRegistrations.filter(r => (id ? r.id != id : r.usn !== usn));
        try {
          localStorage.setItem("nie_robotics_recruitment_registrations", JSON.stringify(allRegistrations));
        } catch (lsErr) {}
        updateKpis(allRegistrations);
        applyFiltersAndRender();
      } else {
        alert(`Error deleting record: ${data.message || "Failed"}`);
        deleteBtn.disabled = false;
        deleteBtn.textContent = "🗑️";
      }
    } catch (err) {
      console.warn("Server delete API failed, updating local state:", err);
      allRegistrations = allRegistrations.filter(r => r.usn !== usn);
      try {
        localStorage.setItem("nie_robotics_recruitment_registrations", JSON.stringify(allRegistrations));
      } catch (lsErr) {}
      updateKpis(allRegistrations);
      applyFiltersAndRender();
    }
    return;
  }
}

/**
 * Initialize Code Verification Modal
 */
function initVerifyModal() {
  const modal = document.getElementById("verifyModal");
  const openBtn = document.getElementById("openVerifyModalBtn");
  const closeBtn = document.getElementById("closeVerifyModal");
  const form = document.getElementById("verifyCodeForm");
  const input = document.getElementById("verifyInputCode");
  const resultBox = document.getElementById("verifyResultBox");
  const errorBox = document.getElementById("verifyModalError");
  const btnToggleCheckin = document.getElementById("btnToggleCheckin");
  const btnResend = document.getElementById("btnResendFromVerify");

  let currentCandidate = null;

  function closeModal() {
    modal.style.display = "none";
    form.reset();
    resultBox.style.display = "none";
    errorBox.style.display = "none";
    currentCandidate = null;
  }

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      modal.style.display = "flex";
      input.focus();
    });
  }

  if (closeBtn) closeBtn.addEventListener("click", closeModal);

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const code = input.value.trim().toUpperCase();
      if (!code) return;

      errorBox.style.display = "none";
      resultBox.style.display = "none";
      const btn = document.getElementById("btnRunVerify");
      btn.disabled = true;
      btn.innerHTML = `<span>Searching...</span>`;

      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);

      try {
        const { ok, data } = await safeFetchJson("/api/admin/verify-code", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({ code: code, mark_verified: false })
        });

        if (ok && data.status === "success" && data.data) {
          currentCandidate = data.data;
          renderCandidateCard(currentCandidate);
          resultBox.style.display = "block";
        } else {
          errorBox.textContent = data.message || `No applicant found with code or USN: "${code}".`;
          errorBox.style.display = "block";
        }
      } catch (err) {
        // Fallback local search
        const found = allRegistrations.find(r => 
          (r.verification_code && r.verification_code.toUpperCase() === code) ||
          (r.usn && r.usn.toUpperCase() === code)
        );
        if (found) {
          currentCandidate = found;
          renderCandidateCard(found);
          resultBox.style.display = "block";
        } else {
          errorBox.textContent = err.message || `No applicant found matching "${code}".`;
          errorBox.style.display = "block";
        }
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Verify</span>`;
      }
    });
  }

  function renderCandidateCard(cand) {
    const isVerified = Boolean(cand.is_verified);
    document.getElementById("vCardStatus").textContent = isVerified ? "VERIFIED (ATTENDED) ✅" : "PENDING VERIFICATION ⏳";
    document.getElementById("vCardStatus").className = "v-status-badge " + (isVerified ? "verified" : "pending");
    document.getElementById("vCardCode").textContent = cand.verification_code || "RC26-XXXX";
    document.getElementById("vCardName").textContent = cand.name ? (cand.name.charAt(0).toUpperCase() + cand.name.slice(1)) : "—";
    document.getElementById("vCardUsn").textContent = (cand.usn || "—").toUpperCase();
    
    const yr = cand.year ? cand.year.trim() : "";
    const br = cand.branch ? cand.branch.trim() : "";
    document.getElementById("vCardYearBranch").textContent = (yr && br) ? `${yr} • ${br}` : (yr || br || "—");

    document.getElementById("vCardEmail").textContent = cand.email || "—";
    document.getElementById("vCardPhone").textContent = cand.phone || "—";

    btnToggleCheckin.innerHTML = isVerified 
      ? `<span>Mark as Unverified / Reset</span>` 
      : `<span>Mark as Verified (Checked In) &check;</span>`;
  }

  // Toggle check-in button
  if (btnToggleCheckin) {
    btnToggleCheckin.addEventListener("click", async () => {
      if (!currentCandidate) return;
      const newStatus = !Boolean(currentCandidate.is_verified);

      btnToggleCheckin.disabled = true;
      btnToggleCheckin.innerHTML = `<span>Updating live...</span>`;

      try {
        await updateVerificationStatus(
          currentCandidate.usn,
          currentCandidate.verification_code,
          newStatus,
          currentCandidate.id
        );
        currentCandidate.is_verified = newStatus ? 1 : 0;
        renderCandidateCard(currentCandidate);
      } finally {
        btnToggleCheckin.disabled = false;
      }
    });
  }

  // Resend email from verify modal
  if (btnResend) {
    btnResend.addEventListener("click", async () => {
      if (!currentCandidate) return;
      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);

      btnResend.disabled = true;
      btnResend.textContent = "Sending...";

      try {
        const { ok, data } = await safeFetchJson("/api/admin/resend-email", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({ id: currentCandidate.id, usn: currentCandidate.usn })
        });

        if (ok && data.status === "success") {
          alert(`Confirmation email sent to ${currentCandidate.email}!`);
        } else {
          alert(data.message || "Failed to send email. Check SMTP settings.");
        }
      } catch (err) {
        alert("Server error: " + err.message);
      } finally {
        btnResend.disabled = false;
        btnResend.textContent = "Resend Email";
      }
    });
  }
}

/**
 * Initialize Email & SMTP Settings Modal
 */
function initEmailSettingsModal() {
  const modal = document.getElementById("emailSettingsModal");
  const openBtn = document.getElementById("openEmailSettingsBtn");
  const closeBtn = document.getElementById("closeEmailSettingsModal");
  const cancelBtn = document.getElementById("cancelEmailSettingsBtn");
  const form = document.getElementById("emailSettingsForm");
  const msgEl = document.getElementById("emailSettingsMsg");

  const hostInput = document.getElementById("smtpHostInput");
  const portInput = document.getElementById("smtpPortInput");
  const userInput = document.getElementById("smtpUserInput");
  const passInput = document.getElementById("smtpPassInput");
  const fromNameInput = document.getElementById("smtpFromNameInput");
  const fromEmailInput = document.getElementById("smtpFromEmailInput");

  const testEmailInput = document.getElementById("testEmailInput");
  const btnSendTestEmail = document.getElementById("btnSendTestEmail");
  const testFeedback = document.getElementById("testEmailFeedback");

  function closeModal() {
    modal.style.display = "none";
    msgEl.style.display = "none";
    testFeedback.style.display = "none";
  }

  if (openBtn) {
    openBtn.addEventListener("click", async () => {
      modal.style.display = "flex";
      msgEl.style.display = "none";
      testFeedback.style.display = "none";

      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
      try {
        const { ok, data } = await safeFetchJson("/api/admin/email-settings", {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (ok && data.data) {
          hostInput.value = data.data.smtp_host || "smtp.gmail.com";
          portInput.value = data.data.smtp_port || "587";
          userInput.value = data.data.smtp_user || "";
          fromNameInput.value = data.data.smtp_from_name || "Robotics Club NIE";
          fromEmailInput.value = data.data.smtp_from_email || "roboticsclubnie@nie.ac.in";
          passInput.placeholder = data.data.has_password ? "•••••••••••• (Configured — leave blank to keep)" : "16-character Google App Password";
        }
      } catch (err) {
        console.warn("Could not fetch SMTP settings:", err);
      }
    });
  }

  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
      const saveBtn = document.getElementById("saveEmailSettingsBtn");

      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";

      const payload = {
        smtp_host: hostInput.value.trim(),
        smtp_port: portInput.value.trim(),
        smtp_user: userInput.value.trim(),
        smtp_from_name: fromNameInput.value.trim(),
        smtp_from_email: fromEmailInput.value.trim(),
        smtp_reply_to: fromEmailInput.value.trim(),
        smtp_enabled: true
      };

      if (passInput.value.trim()) {
        payload.smtp_pass = passInput.value.trim();
      }

      try {
        const { ok, data } = await safeFetchJson("/api/admin/email-settings", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify(payload)
        });

        if (ok && data.status === "success") {
          msgEl.className = "modal-alert-msg success";
          msgEl.textContent = "SMTP Email settings saved successfully!";
          msgEl.style.display = "block";
          setTimeout(() => { msgEl.style.display = "none"; }, 3000);
        } else {
          msgEl.className = "modal-alert-msg error";
          msgEl.textContent = data.message || "Failed to save settings.";
          msgEl.style.display = "block";
        }
      } catch (err) {
        msgEl.className = "modal-alert-msg error";
        msgEl.textContent = "Error saving settings: " + err.message;
        msgEl.style.display = "block";
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save Email Settings";
      }
    });
  }

  // Send Test Email
  if (btnSendTestEmail) {
    btnSendTestEmail.addEventListener("click", async () => {
      const recipient = testEmailInput.value.trim();
      if (!recipient || !recipient.includes("@")) {
        testFeedback.style.display = "block";
        testFeedback.style.color = "#f87171";
        testFeedback.textContent = "Please enter a valid recipient email address for testing.";
        return;
      }

      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
      btnSendTestEmail.disabled = true;
      btnSendTestEmail.textContent = "Sending...";
      testFeedback.style.display = "block";
      testFeedback.style.color = "#00eaff";
      testFeedback.textContent = `Connecting to ${hostInput.value.trim()}:${portInput.value.trim()} and sending test message...`;

      try {
        const { ok, data } = await safeFetchJson("/api/admin/test-email", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            recipient_email: recipient,
            smtp_host: hostInput.value.trim(),
            smtp_port: portInput.value.trim(),
            smtp_user: userInput.value.trim(),
            smtp_pass: passInput.value.trim() || undefined,
            smtp_from_name: fromNameInput.value.trim(),
            smtp_from_email: fromEmailInput.value.trim()
          })
        });

        if (ok && data.status === "success") {
          testFeedback.style.color = "#34d399";
          testFeedback.innerHTML = `✅ <strong>Success!</strong> Test email delivered to <u>${escapeHtml(recipient)}</u>. Check your inbox!`;
        } else {
          testFeedback.style.color = "#f87171";
          testFeedback.innerHTML = `❌ <strong>Failed:</strong> ${escapeHtml(data.message || 'SMTP Connection failed.')}`;
        }
      } catch (err) {
        testFeedback.style.color = "#f87171";
        testFeedback.textContent = "Request notice: " + (err.message || err);
      } finally {
        btnSendTestEmail.disabled = false;
        btnSendTestEmail.textContent = "Send Test";
      }
    });
  }
}

/**
 * Trigger Excel (.xlsx) Download
 */
function triggerExcelDownload() {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  const base = getApiBaseUrl();
  const directUrl = `${base}/api/admin/export-excel?token=${encodeURIComponent(token)}`;

  fetch(directUrl, { method: "HEAD" })
    .then(res => {
      if (res.ok) {
        window.location.href = directUrl;
      } else {
        fallbackClientExcelExport();
      }
    })
    .catch(() => {
      fallbackClientExcelExport();
    });
}

/**
 * Fallback Excel generator using SheetJS in browser
 */
function fallbackClientExcelExport() {
  if (allRegistrations.length === 0) {
    alert("No registrations available to export.");
    return;
  }

  const exportData = allRegistrations.map((r, i) => ({
    "SL No.": i + 1,
    "Registered At": r.timestamp || "",
    "Full Name": r.name || "",
    "USN": r.usn || "",
    "Verification Code": r.verification_code || "—",
    "Year of Study": r.year || "",
    "Branch": r.branch || "",
    "Email ID": r.email || "",
    "Phone Number": r.phone || "",
    "Verification Status": r.is_verified ? "Verified" : "Pending",
    "Email Status": r.email_sent ? "Sent" : "Pending"
  }));

  if (typeof XLSX !== "undefined") {
    const ws = XLSX.utils.json_to_sheet(exportData);
    ws["!cols"] = [
      { wch: 8 },  // SL No.
      { wch: 22 }, // Registered At
      { wch: 28 }, // Full Name
      { wch: 16 }, // USN
      { wch: 20 }, // Verification Code
      { wch: 14 }, // Year
      { wch: 32 }, // Branch
      { wch: 30 }, // Email ID
      { wch: 16 }, // Phone Number
      { wch: 16 }, // Status
      { wch: 16 }  // Email Status
    ];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Recruitment 2026");

    const dateStr = new Date().toISOString().slice(0, 10);
    XLSX.writeFile(wb, `Robotics_Club_NIE_Recruitment_2026_${dateStr}.xlsx`);
  } else {
    // CSV fallback
    let csv = "SL No.,Registered At,Full Name,USN,Verification Code,Year,Branch,Email ID,Phone Number,Status,Email Status\n";
    allRegistrations.forEach((r, i) => {
      csv += `"${i + 1}","${r.timestamp || ''}","${r.name}","${r.usn}","${r.verification_code || '—'}","${r.year}","${r.branch}","${r.email}","${r.phone}","${r.is_verified ? 'Verified' : 'Pending'}","${r.email_sent ? 'Sent' : 'Pending'}"\n`;
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `Robotics_Club_NIE_Recruitment_2026.csv`;
    link.click();
  }
}

/**
 * Initialize Change Passcode Modal
 */
function initPasscodeModal() {
  const modal = document.getElementById("passcodeModal");
  const openBtn = document.getElementById("changePasscodeBtn");
  const closeBtn = document.getElementById("closePasscodeModal");
  const cancelBtn = document.getElementById("cancelPasscodeBtn");
  const form = document.getElementById("changePasscodeForm");
  const msgEl = document.getElementById("passcodeModalMsg");

  if (!modal) return;

  function closeModal() {
    modal.style.display = "none";
    form.reset();
    msgEl.style.display = "none";
  }

  if (openBtn) openBtn.addEventListener("click", () => { modal.style.display = "flex"; });
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const currentPasscode = document.getElementById("currentPasscodeInput").value;
      const newPasscode = document.getElementById("newPasscodeInput").value;
      const confirmPasscode = document.getElementById("confirmPasscodeInput").value;

      if (newPasscode !== confirmPasscode) {
        msgEl.className = "modal-alert-msg error";
        msgEl.textContent = "New passcodes do not match.";
        msgEl.style.display = "block";
        return;
      }

      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);

      try {
        const { ok, data } = await safeFetchJson("/api/admin/change-passcode", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            current_passcode: currentPasscode,
            new_passcode: newPasscode
          })
        });

        if (ok && data.status === "success") {
          msgEl.className = "modal-alert-msg success";
          msgEl.textContent = "Passcode changed successfully!";
          msgEl.style.display = "block";
          setTimeout(closeModal, 1500);
        } else {
          msgEl.className = "modal-alert-msg error";
          msgEl.textContent = data.message || "Failed to change passcode.";
          msgEl.style.display = "block";
        }
      } catch (err) {
        msgEl.className = "modal-alert-msg error";
        msgEl.textContent = "Server error while changing passcode: " + err.message;
        msgEl.style.display = "block";
      }
    });
  }
}

/**
 * HTML Escaping helper
 */
function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/[&<>'"]/g, tag => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[tag] || tag));
}

// Full updated Apps Script source code for 1-click clipboard copy
const UPDATED_APPS_SCRIPT_CODE = `function doGet(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getActiveSheet();
    var p = (e && e.parameter) ? e.parameter : {};
    
    // 1. LIVE STATUS UPDATE via GET (High CORS compatibility across mobile & desktop)
    if (p.action === "update_status" || p.action === "toggle_verify") {
      var result = updateCandidateStatus(sheet, p.usn, p.code, p.status);
      return ContentService
        .createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. DELETE CANDIDATE via GET
    if (p.action === "delete_candidate") {
      var delResult = deleteCandidateRow(sheet, p.usn, p.code);
      return ContentService
        .createTextOutput(JSON.stringify(delResult))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 3. DEFAULT: Return all rows for live roster sync
    var data = sheet.getDataRange().getValues();
    if (!data || data.length < 2) {
      return ContentService
        .createTextOutput(JSON.stringify({ status: "success", count: 0, data: [] }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    var rows = [];
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      if (!row[1] && !row[2]) continue;
      
      var isVerified = (String(row[8] || "").toLowerCase() === "verified" || String(row[8] || "") === "1");
      
      rows.push({
        id: i,
        timestamp: row[0] ? String(row[0]) : "",
        name: row[1] ? String(row[1]).trim() : "",
        usn: row[2] ? String(row[2]).trim().toUpperCase() : "",
        verification_code: row[3] ? String(row[3]).trim() : "",
        year: row[4] ? String(row[4]).trim() : "",
        branch: row[5] ? String(row[5]).trim() : "",
        email: row[6] ? String(row[6]).trim() : "",
        phone: row[7] ? String(row[7]).trim() : "",
        is_verified: isVerified ? 1 : 0,
        email_sent: 1
      });
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({ status: "success", count: rows.length, data: rows }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getActiveSheet();
    var p = (e && e.parameter) ? e.parameter : {};
    
    if (e && e.postData && e.postData.contents) {
      try {
        var parsed = JSON.parse(e.postData.contents);
        for (var key in parsed) { p[key] = parsed[key]; }
      } catch(parseErr) {}
    }
    
    // 1. STATUS UPDATE via POST
    if (p.action === "update_status" || p.action === "toggle_verify") {
      var result = updateCandidateStatus(sheet, p.usn, p.code, p.status);
      return ContentService
        .createTextOutput(JSON.stringify(result))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 2. DELETE CANDIDATE via POST
    if (p.action === "delete_candidate") {
      var delResult = deleteCandidateRow(sheet, p.usn, p.code);
      return ContentService
        .createTextOutput(JSON.stringify(delResult))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 3. NEW REGISTRATION SUBMISSION (from recruitment.html)
    var timestamp = p.timestamp || new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
    var name = p.name || "Applicant";
    var usn = (p.usn || "").toUpperCase();
    var year = p.year || "";
    var branch = p.branch || "";
    var email = (p.email || "").trim();
    var phone = p.phone || "";
    var verificationCode = p.verification_code || ("RC26-" + Math.random().toString(36).substring(2, 6).toUpperCase());
    var status = p.status || "Pending";
    
    if (!name && !usn) {
      return ContentService
        .createTextOutput(JSON.stringify({ status: "ignored", message: "Empty name and USN" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    sheet.appendRow([timestamp, name, usn, verificationCode, year, branch, email, phone, status]);
    
    if (email && email.indexOf("@") !== -1) {
      try {
        var subject = "Registration Confirmed: Recruitment 2026 — Robotics Club NIE [Code: " + verificationCode + "]";
        var htmlBody = 
          '<div style="font-family: Arial, sans-serif; background: #000814; color: #f1f5f9; padding: 30px; border-radius: 12px; max-width: 600px; margin: auto;">' +
            '<div style="text-align: center; border-bottom: 2px solid #00eaff; padding-bottom: 15px; margin-bottom: 20px;">' +
              '<h2 style="color: #ffffff; margin: 0; letter-spacing: 1px;">THE ROBOTICS CLUB</h2>' +
              '<p style="color: #00eaff; font-size: 13px; margin: 4px 0 0 0;">The National Institute of Engineering, Mysuru</p>' +
            '</div>' +
            '<p>Dear <strong>' + name + '</strong>,</p>' +
            '<p>Thank you for registering for the 2026 Recruitment Drive at The Robotics Club, NIE Mysuru!</p>' +
            '<div style="background: #001b3a; border: 2px dashed #00eaff; border-radius: 10px; padding: 20px; text-align: center; margin: 25px 0;">' +
              '<div style="font-size: 11px; text-transform: uppercase; color: #00eaff; letter-spacing: 2px; font-weight: bold;">Your Verification Code</div>' +
              '<div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #ffffff; padding: 8px 0; font-family: monospace;">' + verificationCode + '</div>' +
              '<div style="font-size: 12px; color: #94a3b8;">Present this code during orientation & interview rounds.</div>' +
            '</div>' +
            '<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; color: #cbd5e1;">' +
              '<tr><td style="padding: 6px 0; color: #64748b;">USN:</td><td style="font-weight: bold; color: #ffffff;">' + usn + '</td></tr>' +
              '<tr><td style="padding: 6px 0; color: #64748b;">Year & Branch:</td><td style="color: #ffffff;">' + year + ' — ' + branch + '</td></tr>' +
              '<tr><td style="padding: 6px 0; color: #64748b;">Phone:</td><td style="color: #ffffff;">' + phone + '</td></tr>' +
            '</table>' +
            '<p style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 15px;">' +
              'For queries: <a href="mailto:roboticsclubnie@nie.ac.in" style="color: #00eaff;">roboticsclubnie@nie.ac.in</a> | Instagram: @roboticsclub_nie' +
            '</p>' +
          '</div>';

        MailApp.sendEmail({
          to: email,
          subject: subject,
          htmlBody: htmlBody,
          name: "Robotics Club NIE"
        });
      } catch (mailErr) {
        Logger.log("Mail delivery notice: " + mailErr);
      }
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({ 
        status: "success", 
        message: "Registration recorded successfully", 
        verification_code: verificationCode 
      }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", error: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function updateCandidateStatus(sheet, usn, code, status) {
  var data = sheet.getDataRange().getValues();
  var targetUsn = (usn || "").toString().trim().toUpperCase();
  var targetCode = (code || "").toString().trim().toUpperCase();
  
  var isV = (status === true || status === 1 || String(status).toLowerCase() === "verified" || String(status) === "1");
  var statusText = isV ? "Verified" : "Pending";
  
  if (!targetUsn && !targetCode) {
    return { status: "error", message: "Missing USN and verification code for status update" };
  }
  
  var updatedCount = 0;
  for (var i = 1; i < data.length; i++) {
    var rowUsn = data[i][2] ? String(data[i][2]).trim().toUpperCase() : "";
    var rowCode = data[i][3] ? String(data[i][3]).trim().toUpperCase() : "";
    
    if ((targetUsn && rowUsn === targetUsn) || (targetCode && rowCode === targetCode)) {
      sheet.getRange(i + 1, 9).setValue(statusText);
      updatedCount++;
    }
  }
  
  if (updatedCount > 0) {
    return { 
      status: "success", 
      message: "Applicant status updated to " + statusText,
      usn: targetUsn,
      is_verified: isV ? 1 : 0,
      updated_rows: updatedCount 
    };
  } else {
    return { 
      status: "not_found", 
      message: "No applicant found matching USN " + targetUsn + " or code " + targetCode 
    };
  }
}

function deleteCandidateRow(sheet, usn, code) {
  var data = sheet.getDataRange().getValues();
  var targetUsn = (usn || "").toString().trim().toUpperCase();
  var targetCode = (code || "").toString().trim().toUpperCase();
  
  for (var i = data.length - 1; i >= 1; i--) {
    var rowUsn = data[i][2] ? String(data[i][2]).trim().toUpperCase() : "";
    var rowCode = data[i][3] ? String(data[i][3]).trim().toUpperCase() : "";
    
    if ((targetUsn && rowUsn === targetUsn) || (targetCode && rowCode === targetCode)) {
      sheet.deleteRow(i + 1);
      return { status: "success", message: "Applicant row removed from Google Sheet" };
    }
  }
  return { status: "not_found", message: "Applicant not found in sheet" };
}`;

/**
 * Intelligent parser to extract candidate data from Gmail sent emails
 */
function parseSentEmailsText(text) {
  if (!text || !text.trim()) return [];

  // Split into chunks based on email delimiters
  const chunks = text.split(/(?=(?:From:\s*Robotics|Subject:\s*Registration Confirmed|\n\s*---\s*\n|\bDear\s+[A-Za-z]))/i);
  const candidates = [];
  const seenUsns = new Set();
  const seenCodes = new Set();

  for (const chunk of chunks) {
    if (!chunk.trim()) continue;

    // 1. Verification Code (RC26-XXXX)
    const codeMatch = chunk.match(/\b(RC26-[A-Z0-9]{4,6})\b/i);
    const code = codeMatch ? codeMatch[1].toUpperCase() : "";

    // 2. USN
    let usnMatch = chunk.match(/\b(4[A-Za-z]{2}\d{2}[A-Za-z]{2}\d{3})\b/);
    if (!usnMatch) {
      usnMatch = chunk.match(/USN:\s*([A-Za-z0-9]+)/i);
    }
    const usn = usnMatch ? usnMatch[1].toUpperCase() : "";

    // Skip chunk if it contains neither a USN nor a verification code
    if (!usn && !code) continue;

    // Deduplicate within this paste session
    if (usn && seenUsns.has(usn)) continue;
    if (code && seenCodes.has(code)) continue;
    if (usn) seenUsns.add(usn);
    if (code) seenCodes.add(code);

    // 3. Name
    let name = "";
    const dearMatch = chunk.match(/Dear\s+([^,\n\r<]+)/i);
    if (dearMatch) {
      name = dearMatch[1].trim();
    } else {
      const nameMatch = chunk.match(/(?:Full\s*Name|Candidate\s*Name|Name):\s*([^\n\r]+)/i);
      if (nameMatch) name = nameMatch[1].trim();
    }
    name = name.replace(/<[^>]*>/g, "").trim();

    // 4. Phone
    let phone = "";
    const phoneExplicit = chunk.match(/Phone(?:\/WhatsApp)?:\s*([0-9]{10})/i);
    if (phoneExplicit) {
      phone = phoneExplicit[1];
    } else {
      const phoneDigits = chunk.match(/\b([6-9]\d{9})\b/);
      if (phoneDigits) phone = phoneDigits[1];
    }

    // 5. Email Address
    let email = "";
    const toMatch = chunk.match(/To:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/i);
    if (toMatch && !toMatch[1].toLowerCase().includes("roboticsclub")) {
      email = toMatch[1].trim();
    } else {
      const allEmails = chunk.match(/\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b/g) || [];
      const nonClub = allEmails.filter(e => !e.toLowerCase().includes("roboticsclub"));
      if (nonClub.length > 0) email = nonClub[0];
    }

    // 6. Year & Branch
    let year = "";
    let branch = "";
    const ybMatch = chunk.match(/Year\s*(?:&|and)\s*Branch:\s*([^\n\r]+)/i);
    if (ybMatch) {
      const rawYb = ybMatch[1].replace(/<[^>]*>/g, "").trim();
      const parts = rawYb.split(/\s*[—–-]\s*/);
      year = parts[0] ? parts[0].trim() : "";
      branch = parts[1] ? parts[1].trim() : "";
    } else {
      const yMatch = chunk.match(/Year(?:\s*of\s*Study)?:\s*([^\n\r]+)/i);
      if (yMatch) year = yMatch[1].replace(/<[^>]*>/g, "").trim();
      const bMatch = chunk.match(/(?:Branch|Department):\s*([^\n\r]+)/i);
      if (bMatch) branch = bMatch[1].replace(/<[^>]*>/g, "").trim();
    }

    if (!branch) {
      const branches = [
        "Computer Science & Engineering (CSE)", "Computer Science", "CSE",
        "Information Science & Engineering (ISE)", "Information Science", "ISE",
        "Electronics & Communication Engineering (ECE)", "Electronics & Communication", "ECE",
        "Electrical & Electronics Engineering (EEE)", "Electrical & Electronics", "EEE",
        "Mechanical Engineering (ME)", "Mechanical", "ME",
        "Civil Engineering (CV)", "Civil", "CV",
        "Artificial Intelligence & Machine Learning (AIML)", "AIML",
        "Industrial & Production Engineering (IPE)", "IPE"
      ];
      for (const b of branches) {
        if (chunk.toLowerCase().includes(b.toLowerCase())) {
          branch = b;
          break;
        }
      }
    }

    if (!year) {
      const yMatches = chunk.match(/\b(1st|2nd|3rd|4th)\s*Year\b/i);
      if (yMatches) year = `${yMatches[1]} Year`;
    }

    // 7. Timestamp
    let timestamp = "";
    const dateMatch = chunk.match(/Date:\s*([^\n\r]+)/i);
    if (dateMatch) {
      timestamp = dateMatch[1].trim();
    } else {
      timestamp = new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
    }

    candidates.push({
      timestamp,
      name: name || "Applicant",
      usn: usn || "4NI26RC000",
      verification_code: code || `RC26-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
      year: year || "1st Year",
      branch: branch || "Engineering",
      email: email || "",
      phone: phone || "",
      is_verified: 0,
      email_sent: 1
    });
  }

  return candidates;
}

/**
 * Initialize Import & Cloud Sync Center Modal
 */
function initImportModal() {
  const modal = document.getElementById("importModal");
  const openBtn = document.getElementById("openImportModalBtn");
  const closeBtn = document.getElementById("closeImportModal");
  const cancelBtn = document.getElementById("cancelImportModalBtn");

  if (!modal) return;

  function showModal() {
    modal.style.display = "flex";
  }

  function hideModal() {
    modal.style.display = "none";
  }

  if (openBtn) openBtn.addEventListener("click", showModal);
  if (closeBtn) closeBtn.addEventListener("click", hideModal);
  if (cancelBtn) cancelBtn.addEventListener("click", hideModal);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) hideModal();
  });

  // Tab switching logic
  const tabBtns = modal.querySelectorAll(".import-tab-btn");
  const tabContents = modal.querySelectorAll(".import-tab-content");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      tabBtns.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.style.display = "none");

      btn.classList.add("active");
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.style.display = "block";
    });
  });

  // 1. Copy Apps Script Code button
  const copyScriptBtn = document.getElementById("btnCopyAppsScriptCode");
  const copyScriptText = document.getElementById("copyScriptText");
  if (copyScriptBtn) {
    copyScriptBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(UPDATED_APPS_SCRIPT_CODE);
        if (copyScriptText) copyScriptText.textContent = "✅ Copied Updated Apps Script Code!";
        setTimeout(() => {
          if (copyScriptText) copyScriptText.textContent = "📋 Copy Updated Apps Script Code";
        }, 3000);
      } catch (e) {
        alert("Please copy manually from GOOGLE_SHEET_SETUP.md");
      }
    });
  }

  // 2. Fetch Now from Google Sheet button
  const btnRunCloudSync = document.getElementById("btnRunCloudSync");
  const cloudSyncFeedback = document.getElementById("cloudSyncFeedback");

  if (btnRunCloudSync) {
    btnRunCloudSync.addEventListener("click", async () => {
      btnRunCloudSync.disabled = true;
      btnRunCloudSync.innerHTML = `<span>⏳ Connecting to Google Sheet...</span>`;
      if (cloudSyncFeedback) {
        cloudSyncFeedback.style.display = "block";
        cloudSyncFeedback.className = "alert alert-info py-2";
        cloudSyncFeedback.textContent = "Connecting to Google Apps Script cloud webhook...";
      }

      try {
        const res = await fetch(GOOGLE_SHEET_SCRIPT_URL);
        const json = await res.json();

        if (json && json.status === "success" && Array.isArray(json.data)) {
          const cloudRows = json.data;
          let newCount = 0;
          const map = new Map();
          allRegistrations.forEach(r => { if (r.usn) map.set(r.usn.toUpperCase(), r); });

          cloudRows.forEach(cr => {
            const u = (cr.usn || "").toUpperCase();
            if (!u) return;
            if (!map.has(u)) {
              map.set(u, cr);
              newCount++;
            } else {
              const ex = map.get(u);
              if (!ex.verification_code && cr.verification_code) {
                ex.verification_code = cr.verification_code;
              }
            }
          });

          allRegistrations = Array.from(map.values());
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations)); } catch (e) {}

          // Background sync to SQLite & Excel if local server is active
          syncRegistrationsToBackend(cloudRows);

          updateKpis(allRegistrations);
          applyFiltersAndRender();
          updateCloudBadge(true, `☁️ Google Sheet: ${cloudRows.length} Synced`);

          if (cloudSyncFeedback) {
            cloudSyncFeedback.className = "alert alert-success py-2";
            cloudSyncFeedback.textContent = `✅ Successfully synchronized! Loaded ${cloudRows.length} applicants from Google Sheet (${newCount} new added). Total roster: ${allRegistrations.length}.`;
          }
        } else if (json && json.status === "active") {
          if (cloudSyncFeedback) {
            cloudSyncFeedback.className = "alert alert-warning py-2";
            cloudSyncFeedback.innerHTML = `
              <strong>⚡ Google Apps Script Webhook is active, but auto-reading is not yet deployed!</strong><br>
              In your Google Sheet &rarr; <strong>Extensions</strong> &rarr; <strong>Apps Script</strong>:
              Paste the updated code (click "Copy Updated Apps Script Code" below), Save, then click <strong>Deploy &rarr; Manage deployments &rarr; Edit (pencil) &rarr; New version &rarr; Deploy</strong>.
              <br><small>Tip: In the meantime, you can copy-paste your sent confirmation emails in the next tab to import immediately!</small>
            `;
          }
        } else {
          throw new Error(json.message || "Invalid response format from script.");
        }
      } catch (err) {
        if (cloudSyncFeedback) {
          cloudSyncFeedback.className = "alert alert-danger py-2";
          cloudSyncFeedback.textContent = `Sync failed: ${err.message}. Ensure internet connection is active.`;
        }
      } finally {
        btnRunCloudSync.disabled = false;
        btnRunCloudSync.innerHTML = `<span>🔄 Fetch Now from Google Sheet</span>`;
      }
    });
  }

  // 3. Tab: Sent Emails Parser
  const pasteEmailInput = document.getElementById("pasteEmailInput");
  const btnParseEmails = document.getElementById("btnParseEmails");
  const btnClearEmailPaste = document.getElementById("btnClearEmailPaste");
  const previewArea = document.getElementById("emailParsePreviewArea");
  const parsedCandidatesCount = document.getElementById("parsedCandidatesCount");
  const parsedTableBody = document.getElementById("parsedCandidatesTableBody");
  const btnImportParsedCandidates = document.getElementById("btnImportParsedCandidates");

  let parsedList = [];

  if (btnClearEmailPaste && pasteEmailInput) {
    btnClearEmailPaste.addEventListener("click", () => {
      pasteEmailInput.value = "";
      parsedList = [];
      if (previewArea) previewArea.style.display = "none";
    });
  }

  if (btnParseEmails && pasteEmailInput) {
    btnParseEmails.addEventListener("click", () => {
      const rawText = pasteEmailInput.value;
      if (!rawText.trim()) {
        alert("Please paste confirmation email text into the box first.");
        return;
      }

      parsedList = parseSentEmailsText(rawText);

      if (parsedList.length === 0) {
        alert("Could not detect candidate details. Ensure your pasted text includes either a USN (e.g. 4NI23EC111) or verification code (e.g. RC26-XXXX).");
        if (previewArea) previewArea.style.display = "none";
        return;
      }

      if (parsedCandidatesCount) {
        parsedCandidatesCount.textContent = `Found ${parsedList.length} Candidate${parsedList.length > 1 ? 's' : ''}:`;
      }

      if (parsedTableBody) {
        parsedTableBody.innerHTML = parsedList.map((c, i) => `
          <tr>
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td><code>${escapeHtml(c.usn)}</code></td>
            <td><span class="badge bg-info text-dark">${escapeHtml(c.verification_code)}</span></td>
            <td>${escapeHtml(c.year)} • ${escapeHtml(c.branch)}</td>
            <td>${escapeHtml(c.phone || "—")}</td>
            <td>${escapeHtml(c.email || "—")}</td>
          </tr>
        `).join("");
      }

      if (previewArea) {
        previewArea.style.display = "block";
      }
    });
  }

  if (btnImportParsedCandidates) {
    btnImportParsedCandidates.addEventListener("click", async () => {
      if (parsedList.length === 0) return;

      btnImportParsedCandidates.disabled = true;
      btnImportParsedCandidates.innerHTML = `<span>⏳ Importing...</span>`;

      let newCount = 0;
      const map = new Map();
      allRegistrations.forEach(r => { if (r.usn) map.set(r.usn.toUpperCase(), r); });

      parsedList.forEach(c => {
        const u = c.usn.toUpperCase();
        if (!map.has(u)) {
          map.set(u, c);
          newCount++;
        } else {
          const ex = map.get(u);
          if (c.name && c.name !== "Applicant") ex.name = c.name;
          if (c.verification_code) ex.verification_code = c.verification_code;
          if (c.email) ex.email = c.email;
          if (c.phone) ex.phone = c.phone;
          if (c.year) ex.year = c.year;
          if (c.branch) ex.branch = c.branch;
        }
      });

      allRegistrations = Array.from(map.values());
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations)); } catch (e) {}

      // Background sync to SQLite & Excel if local server is active
      syncRegistrationsToBackend(parsedList);

      updateKpis(allRegistrations);
      applyFiltersAndRender();

      alert(`✅ Success! Imported ${parsedList.length} applicant records into your active roster (${newCount} new candidates registered).`);
      
      btnImportParsedCandidates.disabled = false;
      btnImportParsedCandidates.innerHTML = `<span>✅ Import All Into Dashboard</span>`;
      hideModal();
    });
  }

  // 4. Tab: File Upload (CSV / XLSX)
  const dropzone = document.getElementById("fileDropzone");
  const fileInput = document.getElementById("fileUploadInput");
  const fileFeedback = document.getElementById("fileUploadFeedback");

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleSpreadsheetFile(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleSpreadsheetFile(e.target.files[0]);
      }
    });
  }

  function handleSpreadsheetFile(file) {
    if (!file) return;
    if (fileFeedback) {
      fileFeedback.style.display = "block";
      fileFeedback.className = "alert alert-info py-2";
      fileFeedback.textContent = `Reading ${file.name}...`;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const data = new Uint8Array(e.target.result);
        if (typeof XLSX === "undefined") {
          throw new Error("SheetJS library is loading. Please try again in 2 seconds.");
        }
        const workbook = XLSX.read(data, { type: "array" });
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];
        const jsonRows = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

        if (!jsonRows || jsonRows.length < 2) {
          throw new Error("The file has no data rows.");
        }

        const headers = jsonRows[0].map(h => String(h || "").toLowerCase());
        // Find column indices
        const colName = headers.findIndex(h => h.includes("name"));
        const colUsn = headers.findIndex(h => h.includes("usn"));
        const colCode = headers.findIndex(h => h.includes("code") || h.includes("verification"));
        const colYear = headers.findIndex(h => h.includes("year"));
        const colBranch = headers.findIndex(h => h.includes("branch") || h.includes("dept"));
        const colEmail = headers.findIndex(h => h.includes("email"));
        const colPhone = headers.findIndex(h => h.includes("phone") || h.includes("contact") || h.includes("mobile"));
        const colTime = headers.findIndex(h => h.includes("time") || h.includes("date"));

        const imported = [];
        for (let i = 1; i < jsonRows.length; i++) {
          const row = jsonRows[i];
          if (!row || row.length === 0) continue;

          const usnVal = (colUsn !== -1 ? row[colUsn] : row[2]) || row[3] || "";
          const nameVal = (colName !== -1 ? row[colName] : row[1]) || "";
          if (!nameVal && !usnVal) continue;

          imported.push({
            timestamp: (colTime !== -1 ? row[colTime] : row[0]) || new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
            name: String(nameVal).trim() || "Applicant",
            usn: String(usnVal).trim().toUpperCase(),
            verification_code: (colCode !== -1 ? row[colCode] : row[3]) || `RC26-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
            year: (colYear !== -1 ? row[colYear] : row[4]) || "1st Year",
            branch: (colBranch !== -1 ? row[colBranch] : row[5]) || "Engineering",
            email: (colEmail !== -1 ? row[colEmail] : row[6]) || "",
            phone: (colPhone !== -1 ? row[colPhone] : row[7]) || "",
            is_verified: 0,
            email_sent: 1
          });
        }

        if (imported.length === 0) {
          throw new Error("No valid candidate rows could be found in this file.");
        }

        let newCount = 0;
        const map = new Map();
        allRegistrations.forEach(r => { if (r.usn) map.set(r.usn.toUpperCase(), r); });

        imported.forEach(c => {
          const u = c.usn.toUpperCase();
          if (!map.has(u)) {
            map.set(u, c);
            newCount++;
          }
        });

        allRegistrations = Array.from(map.values());
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(allRegistrations)); } catch (err) {}

        syncRegistrationsToBackend(imported);
        updateKpis(allRegistrations);
        applyFiltersAndRender();

        if (fileFeedback) {
          fileFeedback.className = "alert alert-success py-2";
          fileFeedback.textContent = `✅ Successfully imported ${imported.length} applicants from ${file.name} (${newCount} new added). Total roster: ${allRegistrations.length}.`;
        }

        setTimeout(hideModal, 1800);
      } catch (err) {
        if (fileFeedback) {
          fileFeedback.className = "alert alert-danger py-2";
          fileFeedback.textContent = `Error reading file: ${err.message}`;
        }
      }
    };
    reader.readAsArrayBuffer(file);
  }
}

