/**
 * ROBOTICS CLUB NIE — alumni.js
 * Interactive filtering, hover micro-interactions, and lightbox modal for Alumni & Core Gallery.
 */

document.addEventListener("DOMContentLoaded", () => {
  initGalleryFilters();
  initLightbox();
});

/**
 * Filter gallery items by category
 */
function initGalleryFilters() {
  const filterBtns = document.querySelectorAll(".filter-btn");
  const cards = document.querySelectorAll(".interactive-gallery-card");

  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      // Update active button state
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const filterValue = btn.getAttribute("data-filter");

      cards.forEach(card => {
        const cardCategory = card.getAttribute("data-category");

        if (filterValue === "all" || cardCategory === filterValue) {
          card.classList.remove("hide");
          card.classList.add("show");
        } else {
          card.classList.remove("show");
          card.classList.add("hide");
        }
      });
    });
  });
}

/**
 * Interactive Lightbox Modal
 */
function initLightbox() {
  const modal = document.getElementById("lightboxModal");
  if (!modal) return;

  const modalImg = document.getElementById("lightboxImg");
  const modalTitle = document.getElementById("lightboxTitle");
  const modalDesc = document.getElementById("lightboxDesc");
  const modalTag = document.getElementById("lightboxTag");
  const modalCounter = document.getElementById("lightboxCounter");
  const closeBtn = document.getElementById("lightboxClose");
  const prevBtn = document.getElementById("lightboxPrev");
  const nextBtn = document.getElementById("lightboxNext");

  const cards = Array.from(document.querySelectorAll(".interactive-gallery-card"));
  let currentIndex = 0;

  function openLightbox(index) {
    // Only cycle through currently visible cards if filtered
    const visibleCards = cards.filter(c => !c.classList.contains("hide"));
    if (visibleCards.length === 0) return;

    const targetCard = cards[index];
    const visibleIdx = visibleCards.indexOf(targetCard);
    currentIndex = visibleIdx !== -1 ? visibleIdx : 0;
    
    updateModalContent(visibleCards);
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  function updateModalContent(visibleCards) {
    const card = visibleCards[currentIndex];
    if (!card) return;

    const img = card.querySelector("img");
    const title = card.querySelector(".gallery-card-title");
    const desc = card.querySelector(".gallery-card-desc");
    const tag = card.querySelector(".gallery-badge-tag");

    modalImg.src = img.src;
    modalImg.alt = img.alt || "Gallery image";
    modalTitle.textContent = title ? title.textContent : "";
    modalDesc.textContent = desc ? desc.textContent : "";
    modalTag.textContent = tag ? tag.textContent : "";
    modalCounter.textContent = `${currentIndex + 1} / ${visibleCards.length}`;
  }

  function showNext() {
    const visibleCards = cards.filter(c => !c.classList.contains("hide"));
    if (visibleCards.length === 0) return;
    currentIndex = (currentIndex + 1) % visibleCards.length;
    updateModalContent(visibleCards);
  }

  function showPrev() {
    const visibleCards = cards.filter(c => !c.classList.contains("hide"));
    if (visibleCards.length === 0) return;
    currentIndex = (currentIndex - 1 + visibleCards.length) % visibleCards.length;
    updateModalContent(visibleCards);
  }

  function closeLightbox() {
    modal.classList.remove("active");
    document.body.style.overflow = "";
  }

  // Attach card click listeners
  cards.forEach((card, index) => {
    card.addEventListener("click", () => {
      openLightbox(index);
    });

    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openLightbox(index);
      }
    });
  });

  // Modal controls
  if (closeBtn) closeBtn.addEventListener("click", closeLightbox);
  if (nextBtn) nextBtn.addEventListener("click", showNext);
  if (prevBtn) prevBtn.addEventListener("click", showPrev);

  // Close when clicking modal backdrop
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.classList.contains("lightbox-backdrop")) {
      closeLightbox();
    }
  });

  // Keyboard navigation
  document.addEventListener("keydown", (e) => {
    if (!modal.classList.contains("active")) return;

    if (e.key === "Escape") {
      closeLightbox();
    } else if (e.key === "ArrowRight") {
      showNext();
    } else if (e.key === "ArrowLeft") {
      showPrev();
    }
  });
}
