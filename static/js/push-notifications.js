(() => {
  const panels = document.querySelectorAll('[data-push-controls]');
  if (!panels.length) return;

  function decodeKey(value) {
    const padded = value + '='.repeat((4 - value.length % 4) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  }

  function isIosNonStandalone() {
    const isIos = /iPad|iPhone|iPod/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isStandalone = window.matchMedia?.('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
    return isIos && !isStandalone;
  }

  async function getReadyRegistration() {
    const existing = await navigator.serviceWorker.getRegistration();
    if (existing) {
      return Promise.race([
        navigator.serviceWorker.ready,
        new Promise((resolve) => window.setTimeout(() => resolve(existing), 4000)),
      ]);
    }
    return Promise.race([
      navigator.serviceWorker.ready,
      new Promise((_, reject) => window.setTimeout(() => reject(new Error('Service worker timed out.')), 5000)),
    ]);
  }

  panels.forEach((panel) => {
    const enableButton = panel.querySelector('[data-push-enable]');
    const disableButton = panel.querySelector('[data-push-disable]');
    const testButton = panel.querySelector('[data-push-test]');
    const status = panel.querySelector('[data-push-status]');
    const endpoint = panel.dataset.subscriptionUrl;
    const testUrl = panel.dataset.testUrl || '';
    const isCompact = panel.dataset.compact === 'true';
    const csrf = panel.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

    function setStatus(message) {
      if (status) status.textContent = message;
    }

    async function request(url, options = {}) {
      const response = await fetch(url, {
        credentials: 'same-origin',
        ...options,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {}) },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Could not update notification settings.');
      return data;
    }

    async function refresh() {
      if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
        setStatus('Phone notifications require HTTPS.');
        if (enableButton) enableButton.disabled = true;
        if (isCompact) panel.hidden = true;
        return;
      }
      if (isIosNonStandalone()) {
        setStatus('On iPhone, tap Share → Add to Home Screen, then open Matatu254 from your Home Screen to enable phone notifications.');
        if (enableButton) enableButton.hidden = true;
        if (isCompact) panel.hidden = false;
        return;
      }
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        setStatus('Phone notifications are not supported by this browser.');
        if (enableButton) enableButton.hidden = true;
        if (isCompact) panel.hidden = true;
        return;
      }
      if (!panel.dataset.publicKey) {
        setStatus('Phone notifications are not configured on the server yet.');
        if (enableButton) enableButton.disabled = true;
        if (isCompact) panel.hidden = true;
        return;
      }
      if (Notification.permission === 'denied') {
        setStatus('Notifications are blocked in your browser settings. Allow them there to enable phone alerts.');
        if (enableButton) enableButton.disabled = true;
        if (isCompact) panel.hidden = true;
        return;
      }

      const registration = await getReadyRegistration();
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await request(endpoint, { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
      }
      if (enableButton) {
        enableButton.hidden = Boolean(subscription);
        enableButton.disabled = Boolean(subscription);
      }
      if (disableButton) disableButton.hidden = !subscription;
      if (testButton) testButton.hidden = !subscription || !testUrl;
      if (isCompact) {
        panel.hidden = Boolean(subscription);
      }
      if (subscription) setStatus('Phone notifications are enabled on this device.');
    }

    enableButton?.addEventListener('click', async () => {
      enableButton.disabled = true;
      try {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') throw new Error('Allow notifications in the prompt to receive journey alerts.');
        const { publicKey } = await request(endpoint);
        if (!publicKey) throw new Error('Phone notifications are not configured on the server yet.');
        const registration = await getReadyRegistration();
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: decodeKey(publicKey),
        });
        await request(endpoint, { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
        await refresh();
      } catch (error) {
        setStatus(error.message || 'Could not enable phone notifications.');
        enableButton.disabled = false;
      }
    });

    disableButton?.addEventListener('click', async () => {
      disableButton.disabled = true;
      try {
        const registration = await getReadyRegistration();
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
          await request(endpoint, { method: 'DELETE', body: JSON.stringify({ endpoint: subscription.endpoint }) });
          await subscription.unsubscribe();
        }
        setStatus('Phone notifications are off on this device.');
        await refresh();
      } catch (error) {
        setStatus(error.message || 'Could not turn off phone notifications.');
      } finally {
        disableButton.disabled = false;
      }
    });

    testButton?.addEventListener('click', async () => {
      if (!testUrl) return;
      testButton.disabled = true;
      try {
        await request(testUrl, { method: 'POST', body: JSON.stringify({}) });
        setStatus('Test notification sent — check your phone alerts.');
      } catch (error) {
        setStatus(error.message || 'Could not send test notification.');
      } finally {
        testButton.disabled = false;
      }
    });

    refresh().catch(() => {
      if (isCompact) panel.hidden = true;
      else setStatus('Could not check notification settings. Try again when online.');
    });
  });
})();
