// ============================================================
// Robotics Club NIE — index.js
// Responsive + Animated
// ============================================================

// ────────────────────────────────────────────────────────────
// Logo flip animation
// The frames used to be driven by <body onload="startTimer()">. That inline
// handler is gone; the animation now starts itself, and the frames are warmed
// up first so the first cycle doesn't flash while each PNG downloads.
// ────────────────────────────────────────────────────────────
const LOGO_FRAMES = [
  "images/logo1.png",
  "images/logo2.png",
  "images/logo3.png",
  "images/logo4.png",
  "images/logo5.png"
];

let logoFrame = 0;
let logoIntervalId = null;

function preloadLogoFrames() {
  LOGO_FRAMES.forEach(function (src) {
    const img = new Image();
    img.src = src;
  });
}

function advanceLogoFrame() {
  const el = document.getElementById("logo");
  if (!el) return;
  logoFrame = (logoFrame + 1) % LOGO_FRAMES.length;
  el.src = LOGO_FRAMES[logoFrame];
}

function startLogoAnimation() {
  if (logoIntervalId !== null) return;
  if (!document.getElementById("logo")) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  preloadLogoFrames();
  logoIntervalId = setInterval(advanceLogoFrame, 250);
}

function stopLogoAnimation() {
  if (logoIntervalId === null) return;
  clearInterval(logoIntervalId);
  logoIntervalId = null;
}

startLogoAnimation();

// Don't burn a timer in a background tab.
document.addEventListener("visibilitychange", function () {
  if (document.hidden) {
    stopLogoAnimation();
  } else {
    startLogoAnimation();
  }
});

// ────────────────────────────────────────────────────────────
// Preloader — hide after 1.75s
// index.css also fades it out on its own, so a JS failure can't leave the page
// permanently covered. This just removes it from the layer stack.
// ────────────────────────────────────────────────────────────
function hidePreloader() {
  const preloader = document.getElementById("preloader");
  if (!preloader) return;
  preloader.style.transition = "opacity 0.4s ease";
  preloader.style.opacity = "0";
  setTimeout(function () { preloader.style.display = "none"; }, 420);
}
setTimeout(hidePreloader, 1750);

// ────────────────────────────────────────────────────────────
// Navbar — scroll effect (shrink + solid background)
// ────────────────────────────────────────────────────────────
const navbarEl = document.getElementById("custom-navbar");
const navbarLogo = document.querySelector("#navlogo img");
let navTicking = false;

function navOnScroll() {
  if (!navbarEl) return;
  const scrolled = window.scrollY > 30;
  navbarEl.classList.toggle("scrolled", scrolled);
}

// Coalesce scroll events into one style write per frame.
window.addEventListener("scroll", function () {
  if (navTicking) return;
  navTicking = true;
  requestAnimationFrame(function () {
    navOnScroll();
    navTicking = false;
  });
}, { passive: true });

navOnScroll();

// ────────────────────────────────────────────────────────────
// Hamburger menu — CSS class toggle (no jQuery slideToggle)
// ────────────────────────────────────────────────────────────
const toggler = document.querySelector(".navbar-toggler");
const navPanel = document.getElementById("navbarNav");

function setNavOpen(open) {
  if (!navPanel) return;
  navPanel.classList.toggle("show", open);
  if (toggler) toggler.setAttribute("aria-expanded", open ? "true" : "false");
}

if (toggler && navPanel) {
  toggler.addEventListener("click", function () {
    setNavOpen(!navPanel.classList.contains("show"));
  });

  // Close when a nav link is tapped on mobile
  navPanel.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.innerWidth < 992) setNavOpen(false);
    });
  });
}

// Close nav on outside click
document.addEventListener("click", function (e) {
  if (navPanel && toggler &&
    !navPanel.contains(e.target) &&
    !toggler.contains(e.target)) {
    setNavOpen(false);
  }
});

// Close nav on Escape
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && navPanel && navPanel.classList.contains("show")) {
    setNavOpen(false);
    if (toggler) toggler.focus();
  }
});

// ────────────────────────────────────────────────────────────
// Gallery hover — description overlay
// ────────────────────────────────────────────────────────────
for (let i = 1; i <= 6; i++) {
  const parent = document.querySelector(`.up${i}`);
  if (!parent) continue;
  const child = parent.querySelector(`.desc${i}`);
  if (!child) continue;

  function showDesc() {
    child.style.display = "block";
    // Allow the browser to paint the display change before transitioning.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        child.style.opacity = "1";
        child.style.transform = "translateY(0)";
      });
    });
  }

  function hideDesc() {
    child.style.opacity = "0";
    child.style.transform = "translateY(20px)";
    child.addEventListener("transitionend", function handler() {
      // Guard against a re-show landing between the two events.
      if (child.style.opacity === "0") child.style.display = "none";
      child.removeEventListener("transitionend", handler);
    });
  }

  parent.addEventListener("mouseenter", showDesc);
  parent.addEventListener("mouseleave", hideDesc);

  // Touch-tap toggle for mobile
  parent.addEventListener("touchstart", function () {
    const visible = child.style.display === "block" && child.style.opacity === "1";
    if (visible) {
      hideDesc();
    } else {
      showDesc();
    }
  }, { passive: true });
}

// ────────────────────────────────────────────────────────────
// Scroll-reveal for sections
// Uses IntersectionObserver instead of measuring every .reveal element on every
// scroll event, which forced a layout on each tick.
// ────────────────────────────────────────────────────────────
const REVEAL_TARGETS = [
  ".About",
  ".gallery h1",
  ".gallery-separator",
  ".grid-item",
  ".contact-header-wrap",
  "#add", "#lec", "#team",
  ".contact-terminal-box",
  ".transparent3"
];

function initReveal() {
  const elements = [];
  REVEAL_TARGETS.forEach(function (sel) {
    document.querySelectorAll(sel).forEach(function (el) {
      el.classList.add("reveal");
      elements.push(el);
    });
  });

  // No IntersectionObserver (or motion is unwelcome): show everything at once
  // rather than leaving it stuck at opacity 0.
  if (!("IntersectionObserver" in window) ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    elements.forEach(function (el) { el.classList.add("visible"); });
    return;
  }

  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("visible");
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -60px 0px", threshold: 0 });

  elements.forEach(function (el) { observer.observe(el); });
}

initReveal();

// ────────────────────────────────────────────────────────────
// Interactive Contact Us Section (Copy, Toasts, Email Dispatcher)
// ────────────────────────────────────────────────────────────
function showContactToast(message) {
  const toast = document.getElementById("contactToast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(function () {
    toast.classList.remove("show");
  }, 2600);
}

function initContactInteractions() {
  // One-click copy buttons (phone numbers & campus address)
  const copyBtns = document.querySelectorAll(".copy-btn");
  copyBtns.forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      const text = btn.getAttribute("data-copy");
      if (!text) return;

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          showContactToast("✓ Copied " + text + " to clipboard!");
        }).catch(function () {
          fallbackCopy(text);
        });
      } else {
        fallbackCopy(text);
      }
    });
  });

  function fallbackCopy(text) {
    const input = document.createElement("textarea");
    input.value = text;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    try {
      document.execCommand("copy");
      showContactToast("✓ Copied " + text + " to clipboard!");
    } catch (err) {
      showContactToast("Clipboard copy failed");
    }
    document.body.removeChild(input);
  }

  // Quick message dispatcher form
  const qcForm = document.getElementById("quickContactForm");
  if (qcForm) {
    qcForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const name = (document.getElementById("qcName") || {}).value || "";
      const email = (document.getElementById("qcEmail") || {}).value || "";
      const subject = (document.getElementById("qcSubject") || {}).value || "General Inquiry";
      const message = (document.getElementById("qcMessage") || {}).value || "";

      const emailSubject = encodeURIComponent(`[Robotics Club NIE] ${subject} - from ${name}`);
      const emailBody = encodeURIComponent(
        `Dear Robotics Club NIE Leadership,\n\n` +
        `Sender Name: ${name}\n` +
        `Contact Info: ${email}\n` +
        `Inquiry Category: ${subject}\n\n` +
        `Message:\n${message}\n\n` +
        `Sent via Robotics Club NIE Portal`
      );

      const mailtoUrl = `mailto:roboticsclubnie@nie.ac.in?subject=${emailSubject}&body=${emailBody}`;
      window.location.href = mailtoUrl;

      showContactToast("✓ Dispatching to roboticsclubnie@nie.ac.in...");
    });
  }
}

initContactInteractions();

// ────────────────────────────────────────────────────────────
// Resize handler — reset mobile-specific styles on widen
// ────────────────────────────────────────────────────────────
window.addEventListener("resize", function () {
  if (window.innerWidth >= 992) setNavOpen(false);
});

