// ============================================================
// Robotics Club NIE — index.js
// Responsive + Animated (Accommodations-page aligned)
// ============================================================

// ────────────────────────────────────────────────────────────
// Logo flip animation
// ────────────────────────────────────────────────────────────
var logos = [], y = -1;
logos[0] = "images/logo1.png";
logos[1] = "images/logo2.png";
logos[2] = "images/logo3.png";
logos[3] = "images/logo4.png";
logos[4] = "images/logo5.png";

function logo() {
  y = (y === logos.length - 1) ? 0 : y + 1;
  const el = document.getElementById("logo");
  if (el) el.src = logos[y];
}

function startTimer() {
  setInterval(logo, 250);
}

// ────────────────────────────────────────────────────────────
// Preloader — hide after 1.75s
// ────────────────────────────────────────────────────────────
function hidePreloader() {
  const preloader = document.getElementById("preloader");
  if (preloader) {
    preloader.style.transition = "opacity 0.4s ease";
    preloader.style.opacity = "0";
    setTimeout(() => { preloader.style.display = "none"; }, 420);
  }
}
setTimeout(hidePreloader, 1750);

// ────────────────────────────────────────────────────────────
// Navbar — scroll effect (shrink + solid background)
// ────────────────────────────────────────────────────────────
function navOnScroll() {
  const navbar = document.getElementById("custom-navbar");
  const navlogo = document.querySelector("#navlogo img");
  if (!navbar) return;

  const scrolled = window.scrollY > window.innerHeight / 5;

  if (scrolled) {
    navbar.style.background = "rgba(0, 33, 69, 0.97)";
    navbar.style.backdropFilter = "blur(10px)";
    navbar.style.boxShadow = "0 2px 20px rgba(0,0,0,0.5)";
    if (navlogo && window.innerWidth >= 992) {
      navlogo.style.width = "clamp(50px,13vmin,90px)";
    }
  } else {
    navbar.style.background = "linear-gradient(0deg, rgba(0,33,69,0), rgba(0,33,69,0.75))";
    navbar.style.backdropFilter = "none";
    navbar.style.boxShadow = "none";
    if (navlogo && window.innerWidth >= 992) {
      navlogo.style.width = "clamp(60px,20vmin,120px)";
    }
  }
}

window.addEventListener("scroll", navOnScroll, { passive: true });

// ────────────────────────────────────────────────────────────
// Hamburger menu — CSS class toggle (no jQuery slideToggle)
// ────────────────────────────────────────────────────────────
const toggler = document.querySelector(".navbar-toggler");
const navPanel = document.getElementById("navbarNav");

if (toggler && navPanel) {
  toggler.addEventListener("click", function () {
    navPanel.classList.toggle("show");
  });

  // Close when a nav link is tapped on mobile
  navPanel.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.innerWidth < 992) {
        navPanel.classList.remove("show");
      }
    });
  });
}

// Close nav on outside click
document.addEventListener("click", function (e) {
  if (navPanel && toggler &&
    !navPanel.contains(e.target) &&
    !toggler.contains(e.target)) {
    navPanel.classList.remove("show");
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

  // Show on hover (desktop) — CSS opacity handles the transition
  parent.addEventListener("mouseenter", function () {
    child.style.display = "block";
    // Allow browser to paint before triggering transition
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        child.style.opacity = "1";
        child.style.transform = "translateY(0)";
      });
    });
  });

  parent.addEventListener("mouseleave", function () {
    child.style.opacity = "0";
    child.style.transform = "translateY(20px)";
    // Wait for transition to finish before hiding
    child.addEventListener("transitionend", function handler() {
      child.style.display = "none";
      child.removeEventListener("transitionend", handler);
    });
  });

  // Touch-tap toggle for mobile
  parent.addEventListener("touchstart", function (e) {
    const visible = child.style.display === "block" && child.style.opacity === "1";
    if (visible) {
      child.style.opacity = "0";
      child.style.transform = "translateY(20px)";
      setTimeout(function () { child.style.display = "none"; }, 400);
    } else {
      child.style.display = "block";
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          child.style.opacity = "1";
          child.style.transform = "translateY(0)";
        });
      });
    }
  }, { passive: true });
}

// ────────────────────────────────────────────────────────────
// Scroll-reveal for sections
// ────────────────────────────────────────────────────────────
function addRevealClass() {
  const targets = [
    ".About",
    ".gallery h1",
    ".gallery-separator",
    ".grid-item",
    "#contact-heading",
    "#add", "#lec", "#team",
    ".transparent3"
  ];

  targets.forEach(function (sel) {
    document.querySelectorAll(sel).forEach(function (el) {
      el.classList.add("reveal");
    });
  });
}

function handleReveal() {
  document.querySelectorAll(".reveal").forEach(function (el) {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight - 60) {
      el.classList.add("visible");
    }
  });
}

// Init reveal classes then observe
addRevealClass();
window.addEventListener("scroll", handleReveal, { passive: true });
window.addEventListener("load", handleReveal);
handleReveal(); // run once immediately in case already in view

// ────────────────────────────────────────────────────────────
// Resize handler — reset mobile-specific styles on widen
// ────────────────────────────────────────────────────────────
window.addEventListener("resize", function () {
  if (window.innerWidth >= 992) {
    if (navPanel) navPanel.classList.remove("show");
  }
});
