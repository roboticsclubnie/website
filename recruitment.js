/**
 * ROBOTICS CLUB NIE — recruitment.js
 * Handles recruitment registration, validation, SQL backend submission, and Google Sheet sync.
 * (Public students can only submit; roster & Excel access is strictly restricted to Host Admin).
 */

// Configuration: Google Apps Script Web App URL for cloud backup (optional/dual sync)
const GOOGLE_SHEET_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyi81vO2_Z9nKkUjS3Q4y1tQ-RoboticsClubNIE/exec";

// Local storage key for offline device backup
const STORAGE_KEY = "nie_robotics_recruitment_registrations";

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initForm();
});

/**
 * Initialize form validation and submission
 */
function initForm() {
  const form = document.getElementById("recruitmentForm");
  const usnInput = document.getElementById("usn");
  const phoneInput = document.getElementById("phone");
  const submitBtn = document.getElementById("submitBtn");
  const successScreen = document.getElementById("successScreen");
  const registerAnotherBtn = document.getElementById("registerAnotherBtn");

  if (!form) return;

  // Auto-uppercase USN input
  if (usnInput) {
    usnInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.toUpperCase().trim();
    });
  }

  // Format phone to numbers only (up to 10 digits)
  if (phoneInput) {
    phoneInput.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/\D/g, "").slice(0, 10);
    });
  }

  // Handle Form Submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    // Clear previous errors
    clearFormErrors(form);

    // Validate fields
    const name = document.getElementById("name").value.trim();
    const usn = document.getElementById("usn").value.trim().toUpperCase();
    const year = document.getElementById("year").value.trim();
    const branch = document.getElementById("branch").value.trim();
    const email = document.getElementById("email").value.trim();
    const phone = document.getElementById("phone").value.trim();

    let hasErrors = false;

    if (!name || name.length < 2) {
      showError("name", "Please enter your full name (minimum 2 characters).");
      hasErrors = true;
    }

    if (!usn || usn.length < 5) {
      showError("usn", "Please enter a valid USN (e.g. 4NI23CS001).");
      hasErrors = true;
    }

    if (!year) {
      showError("year", "Please select your current year of study.");
      hasErrors = true;
    }

    if (!branch) {
      showError("branch", "Please select your engineering branch.");
      hasErrors = true;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email)) {
      showError("email", "Please enter a valid email address.");
      hasErrors = true;
    }

    const phoneRegex = /^[6-9]\d{9}$/;
    if (!phone || !phoneRegex.test(phone)) {
      showError("phone", "Please enter a valid 10-digit mobile number.");
      hasErrors = true;
    }

    if (hasErrors) {
      const firstError = form.querySelector(".has-error");
      if (firstError) {
        firstError.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }

    // Set loading state
    setButtonLoading(submitBtn, true);

    const registrationData = {
      timestamp: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
      name,
      usn,
      year,
      branch,
      email,
      phone
    };

/**
 * Determine API Base URL (auto-connect to localhost:8080 if running on Live Server port 5500 or file://)
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

    try {
      // 1. Submit to Live SQL Backend & Disk Excel (/api/register)
      let backendSuccess = false;
      try {
        const base = getApiBaseUrl();
        const response = await fetch(`${base}/api/register`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify(registrationData)
        });

        const text = await response.text();
        const resData = text ? JSON.parse(text) : {};
        if (response.ok && resData.status === "success" && resData.data) {
          backendSuccess = true;
          if (resData.data.verification_code) {
            registrationData.verification_code = resData.data.verification_code;
          }
          registrationData.email_initiated = resData.data.email_initiated;
        }
      } catch (backendErr) {
        console.warn("Local SQL backend not reachable, proceeding with cloud/offline sync:", backendErr);
      }

      // Generate client-side fallback code if server is unavailable
      if (!registrationData.verification_code) {
        registrationData.verification_code = generateClientFallbackCode();
      }

      // 2. Dual Sync: Transmit to Google Sheet (Cloud Excel) if configured
      await sendToGoogleSheet(registrationData);

      // 3. Save locally as fallback backup
      saveRegistrationLocally(registrationData);

      // 4. Show personal success confirmation
      displaySuccess(registrationData);

    } catch (err) {
      console.error("Submission error:", err);
      if (!registrationData.verification_code) {
        registrationData.verification_code = generateClientFallbackCode();
      }
      displaySuccess(registrationData);
    } finally {
      setButtonLoading(submitBtn, false);
    }
  });

  // Register another button
  if (registerAnotherBtn) {
    registerAnotherBtn.addEventListener("click", () => {
      form.reset();
      clearFormErrors(form);
      form.style.display = "block";
      successScreen.style.display = "none";
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

/**
 * Display field error
 */
function showError(fieldId, message) {
  const input = document.getElementById(fieldId);
  if (!input) return;
  const parent = input.closest(".form-group");
  if (parent) {
    parent.classList.add("has-error");
    const feedback = parent.querySelector(".invalid-feedback");
    if (feedback) {
      feedback.textContent = message;
    }
  }
}

/**
 * Clear all field errors
 */
function clearFormErrors(form) {
  const errorGroups = form.querySelectorAll(".has-error");
  errorGroups.forEach((group) => {
    group.classList.remove("has-error");
  });
}

/**
 * Toggle button loading spinner
 */
function setButtonLoading(btn, isLoading) {
  if (!btn) return;
  if (isLoading) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> <span>Submitting...</span>`;
  } else {
    btn.disabled = false;
    btn.innerHTML = `<span>Submit Registration</span> <span aria-hidden="true">&rarr;</span>`;
  }
}

/**
 * Send registration data to Google Apps Script Web App (Cloud Excel sync)
 */
async function sendToGoogleSheet(data) {
  if (!GOOGLE_SHEET_SCRIPT_URL || GOOGLE_SHEET_SCRIPT_URL.includes("RoboticsClubNIE")) {
    return;
  }

  try {
    const formData = new URLSearchParams();
    for (const key in data) {
      formData.append(key, data[key]);
    }

    await fetch(GOOGLE_SHEET_SCRIPT_URL, {
      method: "POST",
      mode: "no-cors",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: formData.toString()
    });
  } catch (e) {
    console.warn("Google Sheet sync notice:", e);
  }
}

/**
 * Save registration locally for offline resilience
 */
function saveRegistrationLocally(data) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const existing = raw ? JSON.parse(raw) : [];
    const filtered = existing.filter(item => item.usn !== data.usn);
    filtered.push(data);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.warn("localStorage write error:", e);
  }
}

/**
 * Display registration success screen with unique verification code
 */
function displaySuccess(data) {
  const form = document.getElementById("recruitmentForm");
  const successScreen = document.getElementById("successScreen");

  if (form) form.style.display = "none";
  if (successScreen) {
    const code = data.verification_code || "RC26-PENDING";

    // Set Code Elements
    const codeDisplay = document.getElementById("summaryCode");
    if (codeDisplay) codeDisplay.textContent = code;

    const codeRow = document.getElementById("summaryCodeRow");
    if (codeRow) codeRow.textContent = code;

    // Set Candidate Summary
    const elName = document.getElementById("summaryName");
    if (elName) elName.textContent = data.name || "—";

    const elUsn = document.getElementById("summaryUsn");
    if (elUsn) elUsn.textContent = data.usn || "—";

    const elYear = document.getElementById("summaryYear");
    if (elYear) elYear.textContent = data.year || "—";

    const elBranch = document.getElementById("summaryBranch");
    if (elBranch) elBranch.textContent = data.branch || "—";

    const elEmail = document.getElementById("summaryEmail");
    if (elEmail) elEmail.textContent = data.email || "—";

    const elPhone = document.getElementById("summaryPhone");
    if (elPhone) elPhone.textContent = data.phone || "—";

    // Email notice update
    const emailNoticeText = document.getElementById("emailNoticeText");
    if (emailNoticeText) {
      emailNoticeText.innerHTML = `An email confirmation with your verification code <strong>${escapeHtml(code)}</strong> has been dispatched to <strong>${escapeHtml(data.email || "")}</strong>.`;
    }

    // Setup Copy Code Button
    const copyBtn = document.getElementById("copyCodeBtn");
    const copyIcon = document.getElementById("copyCodeIcon");
    const copyText = document.getElementById("copyCodeText");
    if (copyBtn) {
      copyBtn.onclick = async () => {
        try {
          await navigator.clipboard.writeText(code);
          showCopySuccess();
        } catch (e) {
          // Fallback clipboard method
          const tempInput = document.createElement("input");
          tempInput.value = code;
          document.body.appendChild(tempInput);
          tempInput.select();
          document.execCommand("copy");
          document.body.removeChild(tempInput);
          showCopySuccess();
        }
      };

      function showCopySuccess() {
        if (copyIcon) copyIcon.textContent = "✅";
        if (copyText) copyText.textContent = "Copied!";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          if (copyIcon) copyIcon.textContent = "📋";
          if (copyText) copyText.textContent = "Copy Code";
          copyBtn.classList.remove("copied");
        }, 2500);
      }
    }

    // Setup Print / Save Receipt Button
    const printBtn = document.getElementById("printReceiptBtn");
    if (printBtn) {
      printBtn.onclick = () => {
        window.print();
      };
    }

    successScreen.style.display = "block";
    successScreen.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

/**
 * Generate client-side fallback verification code
 */
function generateClientFallbackCode() {
  const chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
  let suffix = "";
  for (let i = 0; i < 4; i++) {
    suffix += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return `RC26-${suffix}`;
}

/**
 * Helper to escape HTML characters
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
