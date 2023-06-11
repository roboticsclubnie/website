function displayNextImage() {
              x = (x === images.length - 1) ? 0 : x + 1;
              document.getElementById("image").src = images[x];
          }

function logoo(){
	y = (y === images.length - 1) ? 0 : y + 1;
	document.getElementById("logo").src = logos[y];
}
function startTimer() {
    setInterval(displayNextImage, 2000);
    setInterval(logoo,300);
          }

var images = [], x = -1;
var logos = [],y=-1;
images[0] = "imagess/2.jpg";
images[1] = "imagess/3.jpg";
images[2] = "imagess/4.jpg";
images[3] = "imagess/5.jpg";
images[4] = "imagess/1.jpg";
      
logos[0] = "imagess/logo1.png";
logos[1] = "imagess/logo2.png";
logos[2] = "imagess/logo3.png";
logos[3] = "imagess/logo4.png";
logos[4] = "imagess/logo5.png";


