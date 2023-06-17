
//_______________________________________________________________________________________________________________________

// Navbar Scroll effect
function navOnScroll() {
    const navbar = document.getElementById("custom-navbar");
    const navlogo = document.getElementById("navlogo").firstChild;
    const navitems = document.getElementById("navbarNav");
    const ul = document.getElementById("unlist");
  
    if(window.scrollY > window.innerHeight/4 - 100) {
      navbar.style.background = 'rgba(0, 33, 69, 1)';
      navbar.style.height = '8vh';
      navlogo.style.width = '13.33vmin';
      navitems.style.height = '6.66vmin';
      navitems.style.margin = '0 0 0 32vw';
      ul.style.margin = '2vmin';
    }
    else {
      navbar.style.background = 'linear-gradient(0, rgba(0, 33, 69, 0), rgba(0, 33, 69, 0.7))';
      navbar.style.height = '12vmin';
      navlogo.style.width = '20vmin';
      navitems.style.height = '10vmin';
      navitems.style.margin = '0 0 0 28vw';
      ul.style.margin = '4vmin';
    }
}
window.addEventListener('scroll', navOnScroll);
  
//_______________________________________________________________________________________________________________________

// Hamburger Menu
$('.navbar-toggler').click(function() {
  $('#navbarNav').slideToggle();
  $('#navbarNav ul').addClass('navitems-ul-sm');
  $('.navitems ul li a').hover(function () {
    if ($(window).width() >= 500) {
      $('.navitems ul li a').removeClass('hover-rounding-sm');
    }
    else {
      $('.navitems ul li a').addClass('hover-rounding-sm');
    }

  }); 
});

//_______________________________________________________________________________________________________________________

// Phone desktop segregation of classes
if ($(window).width() < 500) {
  $('.navitems ul li a').removeClass('animate__animated').removeClass('animate__fadeInUp').removeClass('animate__delay-2s').removeClass('animate__delay-2s').removeClass('animate__delay-2s');
  $('#club').removeClass('animate__delay-2s').addClass('animate__delay-2s');
  $('.flex-wrapper2').removeClass('animate__delay-2s').addClass('animate__delay-3s');
  for(let i = 1; i <= 6; i++) {
    $(`.up${i} img`).addClass("up-img");
  }
}
else {
  $('#navbarNav ul').removeClass('navitems-ul-sm');
  for(let i = 1; i <= 6; i++) {
    $(`.up${i} img`).removeClass("up-img");
  }
}

//_______________________________________________________________________________________________________________________

// Class segregation in case the viewport is resized
window.addEventListener('resize', function () {
  if ($(window).width() >= 500) {
    $('#navbarNav ul').removeClass('navitems-ul-sm');
    for(let i = 1; i <= 6; i++) {
      $(`.up${i} img`).removeClass("up-img");
    }
  }
  else {
    $('.navitems ul li a').removeClass('animate__animated').removeClass('animate__fadeInUp').removeClass('animate__delay-3s').removeClass('animate__delay-4s').removeClass('animate__delay-5s');
    $('#club').removeClass('animate__delay-4s').addClass('animate__delay-2s');
    $('.flex-wrapper2').removeClass('animate__delay-5s').addClass('animate__delay-3s');
    for(let i = 1; i <= 6; i++) {
      $(`.up${i} img`).addClass("up-img");
    }
  }
});

//_______________________________________________________________________________________________________________________

// Gallery Modal
const imgContainers = document.querySelectorAll(".container");

for (let i = 0; i < imgContainers.length; i++) {
  const modal = imgContainers[i].parentNode.lastElementChild;
  const closeBtn = modal.getElementsByClassName("close")[0];

  imgContainers[i].onclick = function() {
    modal.classList.add("is-open");
  };

  closeBtn.onclick = function() {
    modal.classList.remove("is-open");
  };
}

//_______________________________________________________________________________________________________________________
