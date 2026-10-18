(() => {
  const search = document.getElementById('stage-search');
  const summary = document.getElementById('selected-stage-copy');
  const radios = document.querySelectorAll('input[name="destination_stage_id"]');
  if (search) {
    search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase();
      document.querySelectorAll('[data-stage-name]').forEach((row) => {
        row.hidden = !row.dataset.stageName.includes(query);
      });
    });
  }
  radios.forEach((radio) => radio.addEventListener('change', () => {
    const label = radio.closest('label')?.querySelector('strong')?.textContent;
    if (summary && label) summary.textContent = `Selected: ${label}`;
    navigator.vibrate?.(10);
  }));
})();
