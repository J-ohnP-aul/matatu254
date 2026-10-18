(() => {
  const button = document.getElementById('use-current-location');
  const status = document.getElementById('location-status');
  const latitude = document.getElementById('stage-latitude');
  const longitude = document.getElementById('stage-longitude');
  if (!button || !status || !latitude || !longitude) return;

  function announce(message, state) {
    status.textContent = message;
    status.className = `location-status${state ? ` is-${state}` : ''}`;
  }
  button.addEventListener('click', () => {
    if (!navigator.geolocation) {
      announce('Geolocation is not supported by this browser.', 'error');
      return;
    }
    announce('Fetching current location…', 'loading');
    navigator.geolocation.getCurrentPosition((position) => {
      latitude.value = position.coords.latitude.toFixed(6);
      longitude.value = position.coords.longitude.toFixed(6);
      announce(`Location set: ${latitude.value}, ${longitude.value}`, 'success');
    }, () => announce('Unable to access your current location.', 'error'), {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
    });
  });
})();
