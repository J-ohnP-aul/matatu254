/**
 * QR scanner — strict finite state machine.
 *
 * IDLE -> SCANNING -> PROCESSING -> COMPLETED   (terminal, navigates)
 *                     \-> FAILED -> IDLE        (retryable)
 *
 * Guards:
 * - Only one transition path runs at a time; the detector loop, camera
 *   errors and submit paths all funnel through `transition()`, which
 *   rejects any event not legal in the current state.
 * - The scan cannot be reset or restarted while PROCESSING; the form
 *   submits exactly once and a 10s watchdog converts a stuck submit
 *   into FAILED instead of hanging forever.
 * - pagehide during SCANNING/PROCESSING stops the camera and (if a code
 *   was captured) still submits it, so a completed capture is never lost.
 */
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

  const STATE = {
    IDLE: 'idle',
    SCANNING: 'scanning',
    PROCESSING: 'processing',
    COMPLETED: 'completed',
    FAILED: 'failed',
  };
  // Legal transitions — anything else is ignored (this is what stops
  // background updates / double clicks from resetting a scan mid-flight).
  const TRANSITIONS = {
    [STATE.IDLE]: [STATE.SCANNING, STATE.PROCESSING],
    [STATE.SCANNING]: [STATE.PROCESSING, STATE.IDLE],
    [STATE.PROCESSING]: [STATE.COMPLETED, STATE.FAILED],
    [STATE.COMPLETED]: [],
    [STATE.FAILED]: [STATE.IDLE, STATE.PROCESSING],
  };

  let state = STATE.IDLE;
  let stream = null;
  let detector = null;
  let animationFrame = null;
  let submitWatchdog = null;

  function transition(next) {
    if (!TRANSITIONS[state].includes(next)) return false;
    state = next;
    return true;
  }

  function setStatus(message) {
    if (status) status.textContent = message;
  }

  function stopCamera() {
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    animationFrame = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    frame?.classList.remove('is-scanning');
  }

  function submitCode(rawCode) {
    const code = String(rawCode || '').trim();
    if (!code) {
      setStatus('Enter the code printed below the QR.');
      manualCode.focus();
      return;
    }
    if (!transition(STATE.PROCESSING)) return; // already processing/completed
    startButton.disabled = true;
    startButton.textContent = 'Saving…';
    setStatus('Processing the vehicle code…');
    codeInput.value = code;
    navigator.vibrate?.(10);
    // Watchdog: a submit that never completes becomes FAILED, never a hang.
    submitWatchdog = window.setTimeout(() => {
      if (state === STATE.PROCESSING) {
        transition(STATE.FAILED);
        setStatus('The scan could not be saved. Check your connection and try again.');
        resetToIdle();
      }
    }, 10000);
    form.requestSubmit();
  }

  function resetToIdle() {
    if (submitWatchdog) window.clearTimeout(submitWatchdog);
    submitWatchdog = null;
    transition(STATE.IDLE);
    startButton.disabled = false;
    startButton.textContent = 'Scan again';
  }

  async function detectFrame() {
    if (state !== STATE.SCANNING) return;
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      animationFrame = requestAnimationFrame(detectFrame);
      return;
    }
    try {
      const [result] = await detector.detect(video);
      if (result?.rawValue) {
        setStatus('Matatu QR found. Opening its route…');
        stopCamera();
        submitCode(result.rawValue); // SCANNING -> PROCESSING (guarded)
        return;
      }
    } catch (_) {
      // A frame may not be decodable while the camera is moving; keep scanning.
    }
    if (state === STATE.SCANNING) animationFrame = requestAnimationFrame(detectFrame);
  }

  startButton.addEventListener('click', async () => {
    if (state === STATE.PROCESSING || state === STATE.COMPLETED) return;
    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      setStatus('Camera needs a secure connection. Enter the printed code below instead.');
      manualCode.focus();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !('BarcodeDetector' in window)) {
      setStatus('This browser cannot scan QR codes here. Enter the printed code below instead.');
      manualCode.focus();
      return;
    }

    if (!transition(STATE.SCANNING)) return;
    startButton.disabled = true;
    startButton.textContent = 'Opening camera…';
    setStatus('Allow camera access and hold the matatu QR inside the frame.');
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
      startButton.textContent = 'Camera is scanning';
      setStatus('Scanning — hold the QR code steady inside the frame.');
      animationFrame = requestAnimationFrame(detectFrame);
    } catch (error) {
      stopCamera();
      transition(STATE.FAILED);
      startButton.disabled = false;
      startButton.textContent = 'Try camera again';
      setStatus(error.name === 'NotAllowedError'
        ? 'Camera permission was denied. Enter the printed code below or allow camera access in your browser settings.'
        : 'Camera could not start. Enter the printed code below instead.');
      manualCode.focus();
      transition(STATE.IDLE);
    }
  });

  submitManual.addEventListener('click', () => submitCode(manualCode.value));
  manualCode.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      submitCode(manualCode.value);
    }
  });

  window.addEventListener('pagehide', () => {
    stopCamera();
    if (submitWatchdog) window.clearTimeout(submitWatchdog);
  }, { once: true });
})();
