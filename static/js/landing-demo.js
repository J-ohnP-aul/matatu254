(() => {
  const choices = document.querySelectorAll('input[name="demo-destination"]');
  const destination = document.getElementById('demo-destination');
  const current = document.getElementById('demo-current-stage');
  if (!destination || !current) return;

  choices.forEach((choice) => choice.addEventListener('change', () => {
    destination.textContent = choice.value === 'Adams' ? 'Adams' : 'Kawangware';
    current.textContent = choice.value === 'Adams' ? 'Yaya' : 'Adams';
  }));
})();
