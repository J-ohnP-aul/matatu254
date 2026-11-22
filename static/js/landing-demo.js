/**
 * Landing route preview — the demo matatu advances when the visitor picks
 * their stage: passed stops turn green, the chosen stop gets the live ring.
 */
(() => {
  const choices = document.querySelectorAll('input[name="demo-destination"]');
  const destination = document.getElementById('demo-destination');
  const current = document.getElementById('demo-current-stage');
  if (!choices.length || !destination || !current) return;

  const stops = [...document.querySelectorAll('.route-demo-track .demo-stop')];

  choices.forEach((choice) => choice.addEventListener('change', () => {
    const chosen = choice.value;               // 'Adams' | 'Kawangware'
    const chosenIndex = stops.findIndex((stop) => stop.id === 'demo-destination' || stop.textContent.trim().startsWith(chosen));
    destination.textContent = chosen;
    current.textContent = chosen === 'Adams' ? 'Yaya' : 'Adams';

    stops.forEach((stop, index) => {
      const isChosen = stop.id === 'demo-destination';
      const stopName = isChosen ? destination.textContent
        : stop.id === 'demo-current-stage' ? current.textContent
        : stop.textContent.trim();
      const passed = index < chosenIndex || stopName === chosen && !isChosen;
      stop.classList.toggle('is-past', index < chosenIndex);
      stop.classList.toggle('is-current', isChosen);
    });
  }));
})();
