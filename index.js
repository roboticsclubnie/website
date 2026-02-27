
//_______________________________________________________________________________________________________________________

// B-falling-in-the-logo animation
function logo(){
    y = (y === logos.length - 1) ? 0 : y + 1;
    document.getElementById("logo").src = logos[y];
}

function startTimer() {
    setInterval(logo, 250);
}

var logos = [], y = -1;

logos[0] = "images/logo1.png";
logos[1] = "images/logo2.png";
logos[2] = "images/logo3.png";
logos[3] = "images/logo4.png";
logos[4] = "images/logo5.png";

//_______________________________________________________________________________________________________________________

// Gallery Hover Effect:
for (let i = 1; i <= 6; i++) {
    const parent = document.querySelector(`.up${i}`);
    const child = parent.querySelector(`.desc${i}`);

    parent.addEventListener('mouseover', () => {
      child.style.transition = 'all 2s ease-in-out';
      child.style.display = 'block';
    });
  
    parent.addEventListener('mouseout', () => {
      child.style.transition = 'all 2s ease-in-out';
      child.style.display = 'none';
    });
}

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

// Preloader
function hidePreloader() {
  const preloader = document.getElementById("preloader");
  const preloaderLogo = document.getElementById("preloader-logo");
  preloader.style.display = 'none';
  preloaderLogo.style.display = 'none';
}
setTimeout(hidePreloader, 1750);

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