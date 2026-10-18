(() => {
  const video = document.getElementById('scanner');
  const status = document.getElementById('scan-status');
  const form = document.getElementById('scan-form');
  const codeInput = document.getElementById('code-value');
  const manualCode = document.getElementById('manual-code');
  const submitManual = document.getElementById('submit-manual');
  const startButton = document.getElementById('start-scan');
  const frame = document.querySelector('.scanner-frame');
  if (!video || !form || !manualCode || !startButton) return;

  let stream = null;
  let detector = null;
  let animationFrame = null;
  let scanning = false;

  function stopCamera() {
    scanning = false;
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    frame?.classList.remove('is-scanning');
  }

  function submitCode(rawCode) {
    const code = rawCode.trim();
    if (!code) {
      status.textContent = 'Enter the code printed below the QR.';
      manualCode.focus();
      return;
    }
    codeInput.value = code;
    navigator.vibrate?.(10);
    form.requestSubmit();
  }

  async function detectFrame() {
    if (!scanning || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      animationFrame = requestAnimationFrame(detectFrame);
      return;
    }
    try {
      const [result] = await detector.detect(video);
      if (result?.rawValue) {
        status.textContent = 'Matatu QR found. Opening its route…';
        stopCamera();
        submitCode(result.rawValue);
        return;
      }
    } catch (_) {
      // A frame may not be decodable while the camera is moving; keep scanning.
    }
    animationFrame = requestAnimationFrame(detectFrame);
  }

  startButton.addEventListener('click', async () => {
    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      status.textContent = 'Camera needs a secure connection. Enter the printed code below instead.';
      manualCode.focus();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !('BarcodeDetector' in window)) {
      status.textContent = 'This browser cannot scan QR codes here. Enter the printed code below instead.';
      manualCode.focus();
      return;
    }

    startButton.disabled = true;
    startButton.textContent = 'Opening camera…';
    status.textContent = 'Allow camera access and hold the matatu QR inside the frame.';
    try {
      detector = new BarcodeDetector({ formats: ['qr_code'] });
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' } },
      });
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      frame?.classList.add('is-scanning');
      scanning = true;
      startButton.textContent = 'Camera is scanning';
      animationFrame = requestAnimationFrame(detectFrame);
    } catch (error) {
      stopCamera();
      startButton.disabled = false;
      startButton.textContent = 'Try camera again';
      status.textContent = error.name === 'NotAllowedError'
        ? 'Camera permission was denied. Enter the printed code below or allow camera access in your browser settings.'
        : 'Camera could not start. Enter the printed code below instead.';
      manualCode.focus();
    }
  });

  submitManual.addEventListener('click', () => submitCode(manualCode.value));
  manualCode.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      submitCode(manualCode.value);
    }
  });
  window.addEventListener('pagehide', stopCamera, { once: true });
})();
