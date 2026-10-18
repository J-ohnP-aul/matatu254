(() => {
  const form = document.getElementById('add-config-form');
  const toggle = document.getElementById('toggle-config-form');
  const cancel = document.getElementById('cancel-config-form');
  if (!form || !toggle) return;
  toggle.addEventListener('click', () => {
    form.hidden = !form.hidden;
    toggle.setAttribute('aria-expanded', String(!form.hidden));
    if (!form.hidden) document.getElementById('new-config-key')?.focus();
  });
  cancel?.addEventListener('click', () => {
    form.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.focus();
  });
})();
