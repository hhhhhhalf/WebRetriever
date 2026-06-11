window.HELP_IMPROVE_VIDEOJS = false;

var INTERP_BASE = "./static/interpolation/stacked";
var NUM_INTERP_FRAMES = 240;

var interp_images = [];
function preloadInterpolationImages() {
  for (var i = 0; i < NUM_INTERP_FRAMES; i++) {
    var path = INTERP_BASE + '/' + String(i).padStart(6, '0') + '.jpg';
    interp_images[i] = new Image();
    interp_images[i].src = path;
  }
}

function setInterpolationImage(i) {
  var image = interp_images[i];
  image.ondragstart = function() { return false; };
  image.oncontextmenu = function() { return false; };
  $('#interpolation-image-wrapper').empty().append(image);
}


$(document).ready(function() {
    const carousel = document.querySelector('.carousel-container-videos');
    const track = document.querySelector('.carousel-track-videos');
    let isScrolling = false;
    let startX;
    let scrollLeft;
    let currentlyPlayingVideo = null;
    let scrollInterval;

    track.innerHTML += track.innerHTML;

    function startAutoScroll() {
        if (isScrolling) return;
        isScrolling = true;
        scrollInterval = setInterval(() => {
            track.scrollLeft += 1;
            if (track.scrollLeft >= (track.scrollWidth / 2)) {
                track.scrollLeft = 0;
            }
        }, 50);
    }

    function stopAutoScroll() {
        isScrolling = false;
        clearInterval(scrollInterval);
    }

    function pauseAllVideos() {
        document.querySelectorAll('.publication-video iframe').forEach(iframe => {
            iframe.contentWindow.postMessage('{"event":"command","func":"pauseVideo","args":""}', '*');
        });
    }

    function playVideo(iframe) {
        iframe.contentWindow.postMessage('{"event":"command","func":"playVideo","args":""}', '*');
    }

    carousel.addEventListener('mouseenter', () => {
        stopAutoScroll();
        track.style.animationPlayState = 'paused';
    });

    carousel.addEventListener('mouseleave', () => {
        if (!currentlyPlayingVideo) {
            startAutoScroll();
            track.style.animationPlayState = 'running';
        }
    });

    carousel.addEventListener('mousedown', (e) => {
        stopAutoScroll();
        startX = e.pageX - carousel.offsetLeft;
        scrollLeft = carousel.scrollLeft;
    });

    carousel.addEventListener('mousemove', (e) => {
        if (!startX) return;
        const x = e.pageX - carousel.offsetLeft;
        const walk = (x - startX) * 2;
        carousel.scrollLeft = scrollLeft - walk;
    });

    carousel.addEventListener('mouseup', () => {
        startX = null;
    });

    document.querySelectorAll('.publication-video iframe').forEach(iframe => {
        iframe.addEventListener('load', () => {
            iframe.contentWindow.postMessage('{"event":"listening"}', '*');
        });

        iframe.parentElement.addEventListener('click', (e) => {
            e.preventDefault();
            pauseAllVideos();
            playVideo(iframe);
            currentlyPlayingVideo = iframe;
            stopAutoScroll();
        });
    });

    window.addEventListener('message', (event) => {
        if (event.data && typeof event.data === 'string') {
            const data = JSON.parse(event.data);
            if (data.event === 'onStateChange') {
                if (data.info === 1) { // video started playing
                    stopAutoScroll();
                    if (currentlyPlayingVideo && currentlyPlayingVideo !== event.source.frameElement) {
                        pauseAllVideos();
                        currentlyPlayingVideo = event.source.frameElement;
                    }
                } else if (data.info === 0 || data.info === 2) { // video ended or paused
                    if (currentlyPlayingVideo === event.source.frameElement) {
                        currentlyPlayingVideo = null;
                        if (!carousel.matches(':hover')) {
                            startAutoScroll();
                        }
                    }
                }
            }
        }
    });

    startAutoScroll();
});

// Analysis Carousel Scrolling
  function scrollLeft() {
    const carousel = document.getElementById('findings-carousel');
    carousel.scrollBy({
      left: -300,
      behavior: 'smooth'
    });
  }

  function scrollRight() {
    const carousel = document.getElementById('findings-carousel');
    carousel.scrollBy({
      left: 300,
      behavior: 'smooth'
    });
  }

  // Videos Carousel Scrolling
  const carouselVideos = document.querySelector('.carousel-container-videos');
  const trackVideos = document.querySelector('.carousel-track-videos');

  // Duplicate items to create continuous scroll effect
  trackVideos.innerHTML += trackVideos.innerHTML;

  // Pause animation on mouse enter and resume on mouse leave
  carouselVideos.addEventListener('mouseenter', () => {
        trackVideos.style.animationPlayState = 'paused';
        if (currentlyPlayingVideo) {
            pauseVideo(currentlyPlayingVideo);
        }
    });

  carouselVideos.addEventListener('mouseleave', () => {
    trackVideos.style.animationPlayState = 'running';
  });
