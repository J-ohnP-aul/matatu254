(() => {
  const panel = document.querySelector('[data-push-controls]');
  if (!panel) return;

  const enableButton = panel.querySelector('[data-push-enable]');
  const disableButton = panel.querySelector('[data-push-disable]');
  const status = panel.querySelector('[data-push-status]');
  const endpoint = panel.dataset.subscriptionUrl;
  const csrf = panel.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  function setStatus(message) {
    status.textContent = message;
  }

  function decodeKey(value) {
    const padded = value + '='.repeat((4 - value.length % 4) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
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
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
      setStatus('Phone notifications are not supported by this browser.');
      enableButton.hidden = true;
      return;
    }
    if (!panel.dataset.publicKey) {
      setStatus('Phone notifications are not configured on the server yet.');
      enableButton.disabled = true;
      return;
    }
    if (Notification.permission === 'denied') {
      setStatus('Notifications are blocked in your browser settings. Allow them there to enable phone alerts.');
      enableButton.disabled = true;
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await request(endpoint, { method: 'POST', body: JSON.stringify(subscription.toJSON()) });
    }
    enableButton.hidden = Boolean(subscription);
    disableButton.hidden = !subscription;
    if (subscription) setStatus('Phone notifications are enabled on this device.');
  }

  enableButton.addEventListener('click', async () => {
    enableButton.disabled = true;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') throw new Error('Allow notifications in the prompt to receive journey alerts.');
      const { publicKey } = await request(endpoint);
      if (!publicKey) throw new Error('Phone notifications are not configured on the server yet.');
      const registration = await navigator.serviceWorker.ready;
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

  disableButton.addEventListener('click', async () => {
    disableButton.disabled = true;
    try {
      const registration = await navigator.serviceWorker.ready;
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

  refresh().catch(() => setStatus('Could not check notification settings. Try again when online.'));
})();
