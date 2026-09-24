/**
 * ROBOTICS CLUB NIE — admin.js
 * Host Admin Portal logic: Passcode verification, live SQL roster fetch,
 * candidate verification by unique code & USN, automated SMTP email configuration,
 * client-side search & filtering, real-time Excel download, and passcode management.
 */

const AUTH_TOKEN_KEY = "rc_host_token";
let allRegistrations = [];

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
}

function hideDashboard() {
  document.getElementById("adminDashboard").style.display = "none";
  document.getElementById("passcodeGate").style.display = "flex";
  document.getElementById("logoutBtn").style.display = "none";
  const passcodeInput = document.getElementById("passcodeInput");
  if (passcodeInput) passcodeInput.focus();
}

/**
 * Fetch registrations from SQL API
 */
async function fetchRegistrations() {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);

  try {
    const { ok, data } = await safeFetchJson("/api/admin/registrations", {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (ok && data.status === "success") {
      allRegistrations = data.data || [];
    } else {
      throw new Error(data.message || "Could not fetch registrations.");
    }
  } catch (err) {
    console.warn("SQL API fetch notice, checking local device backup:", err);
    try {
      const local = localStorage.getItem("nie_robotics_recruitment_registrations");
      allRegistrations = local ? JSON.parse(local) : [];
    } catch (e) {
      allRegistrations = [];
    }
  }

  updateKpis(allRegistrations);
  applyFiltersAndRender();
}

/**
 * Update KPI metrics cards
 */
function updateKpis(data) {
  document.getElementById("kpiTotal").textContent = data.length;

  const firstYears = data.filter(r => (r.year || "").includes("1st")).length;
  const secondYears = data.filter(r => (r.year || "").includes("2nd")).length;
  const seniorYears = data.filter(r => (r.year || "").includes("3rd") || (r.year || "").includes("4th")).length;

  document.getElementById("kpiFirstYears").textContent = firstYears;
  document.getElementById("kpiSecondYears").textContent = secondYears;
  document.getElementById("kpiSeniorYears").textContent = seniorYears;
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

    return `
      <tr>
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
                  data-id="${r.id || ''}" data-usn="${escapeHtml(r.usn || '')}" data-status="${isVerified ? '1' : '0'}" 
                  title="Click to toggle candidate check-in status">
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
                    data-id="${r.id || ''}" data-usn="${escapeHtml(r.usn || '')}" data-name="${escapeHtml(r.name || '')}" 
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

  // 2. Toggle Verification Status
  const statusBtn = e.target.closest(".status-pill-toggle");
  if (statusBtn) {
    const id = statusBtn.getAttribute("data-id");
    const usn = statusBtn.getAttribute("data-usn");
    const currentStatus = statusBtn.getAttribute("data-status") === "1";
    const newStatus = !currentStatus;

    statusBtn.disabled = true;
    statusBtn.textContent = "⏳";

    try {
      const { ok, data } = await safeFetchJson("/api/admin/toggle-verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({
          id: id ? parseInt(id, 10) : undefined,
          usn: usn,
          is_verified: newStatus
        })
      });

      if (ok && data.status === "success") {
        allRegistrations = allRegistrations.map(r => {
          if ((id && r.id == id) || (usn && r.usn === usn)) {
            return { ...r, is_verified: newStatus ? 1 : 0 };
          }
          return r;
        });
        applyFiltersAndRender();
      } else {
        alert(data.message || "Failed to update status.");
        statusBtn.disabled = false;
        statusBtn.textContent = currentStatus ? "Verified ✅" : "Pending ⏳";
      }
    } catch (err) {
      allRegistrations = allRegistrations.map(r => {
        if ((id && r.id == id) || (usn && r.usn === usn)) {
          return { ...r, is_verified: newStatus ? 1 : 0 };
        }
        return r;
      });
      applyFiltersAndRender();
    }
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
    document.getElementById("vCardName").textContent = cand.name || "—";
    document.getElementById("vCardUsn").textContent = cand.usn || "—";
    document.getElementById("vCardYearBranch").textContent = `${cand.year || '—'}, ${cand.branch || '—'}`;
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
      const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
      const newStatus = !Boolean(currentCandidate.is_verified);

      btnToggleCheckin.disabled = true;
      btnToggleCheckin.innerHTML = `<span>Updating...</span>`;

      try {
        const { ok, data } = await safeFetchJson("/api/admin/toggle-verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({
            id: currentCandidate.id,
            usn: currentCandidate.usn,
            is_verified: newStatus
          })
        });

        if (ok && data.status === "success") {
          currentCandidate.is_verified = newStatus ? 1 : 0;
          renderCandidateCard(currentCandidate);
          allRegistrations = allRegistrations.map(r => r.usn === currentCandidate.usn ? { ...r, is_verified: newStatus ? 1 : 0 } : r);
          applyFiltersAndRender();
        }
      } catch (err) {
        currentCandidate.is_verified = newStatus ? 1 : 0;
        renderCandidateCard(currentCandidate);
        allRegistrations = allRegistrations.map(r => r.usn === currentCandidate.usn ? { ...r, is_verified: newStatus ? 1 : 0 } : r);
        applyFiltersAndRender();
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
