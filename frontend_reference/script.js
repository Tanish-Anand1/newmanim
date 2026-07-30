/* ══════════════════════════════════════════
   VIVACITY — SCRIPT v2
   ══════════════════════════════════════════ */

/* ── Mobile nav toggle ── */
// Old toggle logic removed in favor of new fullscreen mobile menu at bottom of file

/* ── Hero textarea auto-resize ── */
const heroInput = document.getElementById('heroInput');
if (heroInput) {
  heroInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
  });
  heroInput.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!this.value.trim()) return;
      this.value = '';
      this.style.height = 'auto';
    }
  });
}

/* ── Video Play/Pause Toggle ── */
document.querySelectorAll('.vc-play-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const wrap = btn.closest('.video-wrap');
    const video = wrap.querySelector('video');
    const iconPlay = btn.querySelector('.icon-play');
    const iconPause = btn.querySelector('.icon-pause');

    if (video) {
      if (video.paused) {
        video.play();
        iconPlay.style.display = 'none';
        iconPause.style.display = 'block';
      } else {
        video.pause();
        iconPlay.style.display = 'block';
        iconPause.style.display = 'none';
      }
    }
  });
});

/* ── Scroll reveal ── */
const revealSections = document.querySelectorAll('.reveal-section');
const io = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      io.unobserve(entry.target);
    }
  });
}, { threshold: 0.05, rootMargin: '-60px 0px' });

revealSections.forEach(el => io.observe(el));

/* ── FAQ accordion ── */
document.querySelectorAll('details.faq-item').forEach(detail => {
  detail.addEventListener('toggle', () => {
    if (detail.open) {
      document.querySelectorAll('details.faq-item').forEach(other => {
        if (other !== detail) other.open = false;
      });
    }
  });
});

/* ── Smooth scroll ── */
document.querySelectorAll('a[href^="#"]').forEach(link => {
  const hash = link.getAttribute('href');
  if (hash === '#') return;
  link.addEventListener('click', e => {
    const target = document.querySelector(hash);
    if (target) {
      e.preventDefault();
      const offset = 56;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  });
});

// ══════════════════════════════════════════
// COOKIE BANNER
// ══════════════════════════════════════════
const cbAccept = document.getElementById('cbAccept');
const cbDeny = document.getElementById('cbDeny');
const cookieBanner = document.getElementById('cookieBanner');

if (cookieBanner) {
  if (cbAccept) {
    cbAccept.addEventListener('click', () => {
      cookieBanner.classList.add('hidden');
    });
  }
  if (cbDeny) {
    cbDeny.addEventListener('click', () => {
      cookieBanner.classList.add('hidden');
    });
  }
}

// ══════════════════════════════════════════
// MOBILE MENU
// ══════════════════════════════════════════
const navBurger = document.getElementById('navBurger');
const mobileMenu = document.getElementById('mobileMenu');

if (navBurger && mobileMenu) {
  navBurger.addEventListener('click', () => {
    const isActive = mobileMenu.classList.contains('active');
    if (isActive) {
      mobileMenu.classList.remove('active');
      document.body.style.overflow = '';
    } else {
      mobileMenu.classList.add('active');
      document.body.style.overflow = 'hidden'; // Prevent scroll
    }
  });

  // Close menu when clicking a link
  const mmLinks = mobileMenu.querySelectorAll('.mm-link');
  mmLinks.forEach(link => {
    link.addEventListener('click', () => {
      mobileMenu.classList.remove('active');
      document.body.style.overflow = '';
    });
  });
}

// ══════════════════════════════════════════
// HERO PROMPT REDIRECT
// ══════════════════════════════════════════
const promptInput = document.getElementById('heroInput') || document.getElementById('promptInput');
const heroSubmit = document.getElementById('heroSubmit');

if (promptInput) {
  const triggerRedirect = () => {
    const val = promptInput.value.trim();
    if (val) {
      window.location.href = `signup.html?prompt=${encodeURIComponent(val)}`;
    } else {
      window.location.href = 'signup.html';
    }
  };

  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      triggerRedirect();
    }
  });

  if (heroSubmit) {
    heroSubmit.addEventListener('click', (e) => {
      e.preventDefault();
      triggerRedirect();
    });
  }
}

// ══════════════════════════════════════════
// VIDEO LIGHTBOX (FULLSCREEN AUDIO)
// ══════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  const lightbox = document.createElement('div');
  lightbox.id = 'lightbox';
  
  const closeBtn = document.createElement('button');
  closeBtn.className = 'close-lightbox';
  closeBtn.innerHTML = '&times;';
  
  const lightboxVideo = document.createElement('video');
  lightboxVideo.controls = true;
  lightboxVideo.autoplay = true;
  
  lightbox.appendChild(closeBtn);
  lightbox.appendChild(lightboxVideo);
  document.body.appendChild(lightbox);
  
  const openLightbox = (src) => {
    lightboxVideo.src = src;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
  };
  
  const closeLightbox = () => {
    lightbox.classList.remove('active');
    lightboxVideo.pause();
    lightboxVideo.src = '';
    document.body.style.overflow = '';
  };
  
  closeBtn.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closeLightbox();
  });
  
  document.querySelectorAll('.h-video, .vc-video').forEach(vid => {
    vid.addEventListener('click', (e) => {
      e.preventDefault();
      openLightbox(vid.getAttribute('src'));
    });
  });
});
