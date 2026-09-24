/**
 * ROBOTICS CLUB NIE — rikishi.js
 * Advanced, ultra-smooth category filtering, touch navigation, and fullscreen Lightbox Modal.
 */

document.addEventListener("DOMContentLoaded", () => {
  initNavbarScroll();
  initGalleryFilters();
  initGalleryLightbox();
});

/**
 * Navbar background update on scroll
 */
function initNavbarScroll() {
  const navbar = document.getElementById("custom-navbar");
  if (!navbar) return;

  function updateNavbar() {
    if (window.scrollY > 30) {
      navbar.classList.add("scrolled");
    } else {
      navbar.classList.remove("scrolled");
    }
  }

  window.addEventListener("scroll", updateNavbar, { passive: true });
  updateNavbar();
}

/**
 * Filter gallery exhibits by category tab with staggered smooth reveal
 */
function initGalleryFilters() {
  const filterBtns = document.querySelectorAll(".gallery-filter-btn");
  const cards = document.querySelectorAll(".interactive-gallery-card");

  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const filterValue = btn.getAttribute("data-filter");
      let visibleCounter = 0;

      cards.forEach(card => {
        const category = card.getAttribute("data-category");

        if (filterValue === "all" || category === filterValue) {
          card.classList.remove("hide");
          card.classList.add("show");
          card.style.animationDelay = `${visibleCounter * 0.05}s`;
          visibleCounter++;
        } else {
          card.classList.remove("show");
          card.classList.add("hide");
          card.style.animationDelay = "0s";
        }
      });
    });
  });
}

/**
 * Advanced Interactive Fullscreen Lightbox Modal for Expo Gallery
 */
function initGalleryLightbox() {
  const modal = document.getElementById("galleryLightboxModal");
  if (!modal) return;

  const modalStage = document.getElementById("galleryLightboxStage");
  const modalImg = document.getElementById("galleryLightboxImg");
  const modalTitle = document.getElementById("galleryLightboxTitle");
  const modalSubtitle = document.getElementById("galleryLightboxSubtitle");
  const modalDesc = document.getElementById("galleryLightboxDesc");
  const modalTag = document.getElementById("galleryLightboxTag");
  const modalCounter = document.getElementById("galleryLightboxCounter");
  const thumbnailsContainer = document.getElementById("galleryLightboxThumbnails");
  const zoomBtn = document.getElementById("galleryLightboxZoom");
  const closeBtn = document.getElementById("galleryLightboxClose");
  const prevBtn = document.getElementById("galleryLightboxPrev");
  const nextBtn = document.getElementById("galleryLightboxNext");

  const cards = Array.from(document.querySelectorAll(".interactive-gallery-card"));
  let currentIndex = 0;
  let isZoomed = false;

  function getVisibleCards() {
    return cards.filter(c => !c.classList.contains("hide"));
  }

  function renderThumbnails(visibleCards) {
    if (!thumbnailsContainer) return;
    thumbnailsContainer.innerHTML = "";

    visibleCards.forEach((card, idx) => {
      const img = card.querySelector("img");
      const title = card.querySelector(".gallery-card-title");
      if (!img) return;

      const thumb = document.createElement("button");
      thumb.type = "button";
      thumb.className = `gallery-thumb-item ${idx === currentIndex ? "active" : ""}`;
      thumb.setAttribute("aria-label", `Jump to ${title ? title.textContent : `Exhibit ${idx + 1}`}`);
      
      const thumbImg = document.createElement("img");
      thumbImg.src = img.src;
      thumbImg.alt = img.alt || "Thumbnail";
      thumbImg.loading = "lazy";

      thumb.appendChild(thumbImg);
      thumb.addEventListener("click", () => {
        if (currentIndex === idx) return;
        currentIndex = idx;
        updateModalContent(visibleCards);
      });

      thumbnailsContainer.appendChild(thumb);
    });

    scrollActiveThumbnailIntoView();
  }

  function scrollActiveThumbnailIntoView() {
    if (!thumbnailsContainer) return;
    const activeThumb = thumbnailsContainer.children[currentIndex];
    if (activeThumb) {
      activeThumb.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }

  function openLightbox(cardElement) {
    const visibleCards = getVisibleCards();
    if (visibleCards.length === 0) return;

    const visibleIdx = visibleCards.indexOf(cardElement);
    currentIndex = visibleIdx !== -1 ? visibleIdx : 0;

    resetZoom();
    renderThumbnails(visibleCards);
    updateModalContent(visibleCards, false);

    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  function updateModalContent(visibleCards, animate = true) {
    const card = visibleCards[currentIndex];
    if (!card) return;

    const img = card.querySelector("img");
    const title = card.querySelector(".gallery-card-title");
    const subtitle = card.querySelector(".gallery-card-subtitle");
    const desc = card.querySelector(".gallery-card-desc");
    const tag = card.querySelector(".gallery-badge-tag");

    resetZoom();

    if (animate && modalImg) {
      modalImg.classList.add("fade-out");
      setTimeout(() => {
        applyData();
        modalImg.classList.remove("fade-out");
      }, 150);
    } else {
      applyData();
      if (modalImg) modalImg.classList.remove("fade-out");
    }

    function applyData() {
      if (modalImg && img) {
        modalImg.src = img.src;
        modalImg.alt = img.alt || "Exhibit build photo";
      }
      if (modalTitle) modalTitle.textContent = title ? title.textContent : "";
      if (modalSubtitle) modalSubtitle.textContent = subtitle ? subtitle.textContent : "";
      if (modalDesc) modalDesc.textContent = desc ? desc.textContent : "";
      if (modalTag) modalTag.textContent = tag ? tag.textContent : "";
      if (modalCounter) modalCounter.textContent = `${currentIndex + 1} / ${visibleCards.length}`;

      // Update active thumbnail
      if (thumbnailsContainer) {
        Array.from(thumbnailsContainer.children).forEach((thumb, idx) => {
          thumb.classList.toggle("active", idx === currentIndex);
        });
        scrollActiveThumbnailIntoView();
      }
    }
  }

  function resetZoom() {
    isZoomed = false;
    if (modalStage) modalStage.classList.remove("is-zoomed");
    if (zoomBtn) zoomBtn.textContent = "🔍";
  }

  function toggleZoom() {
    isZoomed = !isZoomed;
    if (modalStage) modalStage.classList.toggle("is-zoomed", isZoomed);
    if (zoomBtn) zoomBtn.textContent = isZoomed ? "➖" : "🔍";
  }

  function showNext() {
    const visibleCards = getVisibleCards();
    if (visibleCards.length === 0) return;
    currentIndex = (currentIndex + 1) % visibleCards.length;
    updateModalContent(visibleCards, true);
  }

  function showPrev() {
    const visibleCards = getVisibleCards();
    if (visibleCards.length === 0) return;
    currentIndex = (currentIndex - 1 + visibleCards.length) % visibleCards.length;
    updateModalContent(visibleCards, true);
  }

  function closeLightbox() {
    modal.classList.remove("active");
    resetZoom();
    document.body.style.overflow = "";
  }

  // Attach card click handlers
  cards.forEach(card => {
    card.addEventListener("click", () => {
      openLightbox(card);
    });

    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openLightbox(card);
      }
    });
  });

  if (closeBtn) closeBtn.addEventListener("click", closeLightbox);
  if (nextBtn) nextBtn.addEventListener("click", showNext);
  if (prevBtn) prevBtn.addEventListener("click", showPrev);
  if (zoomBtn) zoomBtn.addEventListener("click", toggleZoom);

  // Click stage to toggle zoom or backdrop to close
  if (modalStage) {
    modalStage.addEventListener("click", (e) => {
      if (e.target === modalImg) {
        toggleZoom();
      }
    });
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeLightbox();
    }
  });

  // Touch Swipe Gesture for mobile and tablets
  let touchStartX = 0;
  let touchStartY = 0;
  modal.addEventListener("touchstart", (e) => {
    touchStartX = e.changedTouches[0].clientX;
    touchStartY = e.changedTouches[0].clientY;
  }, { passive: true });

  modal.addEventListener("touchend", (e) => {
    if (isZoomed) return; // Allow panning when zoomed
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const diffX = touchEndX - touchStartX;
    const diffY = touchEndY - touchStartY;

    // Horizontal swipe threshold 45px, more horizontal than vertical
    if (Math.abs(diffX) > 45 && Math.abs(diffX) > Math.abs(diffY)) {
      if (diffX < 0) {
        showNext();
      } else {
        showPrev();
      }
    }
  }, { passive: true });

  // Keyboard navigation
  document.addEventListener("keydown", (e) => {
    if (!modal.classList.contains("active")) return;

    if (e.key === "Escape") {
      closeLightbox();
    } else if (e.key === "ArrowRight") {
      showNext();
    } else if (e.key === "ArrowLeft") {
      showPrev();
    } else if (e.key === "z" || e.key === "Z") {
      toggleZoom();
    }
  });
}
