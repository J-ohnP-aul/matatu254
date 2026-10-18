(() => {
  const root = document.documentElement;
  const supportsTransitions = 'startViewTransition' in document;
  root.classList.add(supportsTransitions ? 'has-view-transitions' : 'has-page-transition-fallback');

  // Browsers without cross-document View Transitions use one short compositor-only entrance.
  const back = sessionStorage.getItem('matatu-nav-direction') === 'back';
  if (back) root.dataset.navDirection = 'back';
  sessionStorage.removeItem('matatu-nav-direction');
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-nav-direction]');
    if (link) sessionStorage.setItem('matatu-nav-direction', link.dataset.navDirection);
  });

  const tabBar = document.querySelector('.bottom-tabs');
  if (tabBar) {
    let lastY = window.scrollY;
    let scheduled = false;
    window.addEventListener('scroll', () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        const nextY = window.scrollY;
        const movingDown = nextY > lastY && nextY > 96;
        tabBar.classList.toggle('is-hidden', movingDown);
        tabBar.classList.toggle('is-visible', !movingDown);
        lastY = nextY;
        scheduled = false;
      });
    }, { passive: true });
  }

  const offlineBanner = document.getElementById('offline-banner');
  const refreshConnectivity = () => {
    if (offlineBanner) offlineBanner.hidden = navigator.onLine;
  };
  window.addEventListener('online', refreshConnectivity);
  window.addEventListener('offline', refreshConnectivity);
  refreshConnectivity();

  let installPrompt = null;
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    installPrompt = event;
    document.querySelectorAll('[data-install-app]').forEach((button) => {
      button.hidden = false;
      button.addEventListener('click', async () => {
        if (!installPrompt) return;
        installPrompt.prompt();
        await installPrompt.userChoice;
        installPrompt = null;
        button.hidden = true;
      }, { once: true });
    });
  });

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((error) => {
        console.warn('Matatu254 offline support could not start.', error);
      });
    }, { once: true });
  }

  document.querySelectorAll('[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-vibrate]').forEach((control) => {
    control.addEventListener('click', () => navigator.vibrate?.(10));
  });
})();
