/**
 * ROBOTICS CLUB NIE — project.js
 * Interactive category filtering and fullscreen Lightbox Modal for Project builds.
 */

document.addEventListener("DOMContentLoaded", () => {
  initProjectFilters();
  initProjectLightbox();
});

/**
 * Filter projects by category tab
 */
function initProjectFilters() {
  const filterBtns = document.querySelectorAll(".project-filter-btn");
  const cards = document.querySelectorAll(".interactive-project-card");

  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const filterValue = btn.getAttribute("data-filter");

      cards.forEach(card => {
        const category = card.getAttribute("data-category");

        if (filterValue === "all" || category === filterValue) {
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
 * Interactive Fullscreen Lightbox Modal for Projects
 */
function initProjectLightbox() {
  const modal = document.getElementById("projectLightboxModal");
  if (!modal) return;

  const modalImg = document.getElementById("projectLightboxImg");
  const modalTitle = document.getElementById("projectLightboxTitle");
  const modalDesc = document.getElementById("projectLightboxDesc");
  const modalTag = document.getElementById("projectLightboxTag");
  const modalCounter = document.getElementById("projectLightboxCounter");
  const closeBtn = document.getElementById("projectLightboxClose");
  const prevBtn = document.getElementById("projectLightboxPrev");
  const nextBtn = document.getElementById("projectLightboxNext");

  const cards = Array.from(document.querySelectorAll(".interactive-project-card"));
  let currentIndex = 0;

  function openLightbox(index) {
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
    const title = card.querySelector(".project-card-title");
    const desc = card.querySelector(".project-card-desc");
    const tag = card.querySelector(".project-badge-tag");

    modalImg.src = img.src;
    modalImg.alt = img.alt || "Project photo";
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

  // Attach card click handlers
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

  if (closeBtn) closeBtn.addEventListener("click", closeLightbox);
  if (nextBtn) nextBtn.addEventListener("click", showNext);
  if (prevBtn) prevBtn.addEventListener("click", showPrev);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeLightbox();
    }
  });

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
