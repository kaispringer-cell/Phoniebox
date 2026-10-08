(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById('theme-toggle');
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  // Nur in der Android-App vorhanden: Brücke zu Menü und Statusleiste.
  const app = window.PhonieboxApp;
  let preference = null;
  try { preference = localStorage.getItem('phoniebox-theme'); } catch (_) {}
  const applyTheme = () => {
    const dark = preference ? preference === 'dark' : media.matches;
    root.dataset.theme = dark ? 'dark' : 'light';
    themeButton.textContent = dark ? '☀ Hell' : '☾ Dunkel';
    themeButton.setAttribute('aria-label', dark ? 'Hellen Modus aktivieren' : 'Dunklen Modus aktivieren');
    // In der Android-App färbt die App ihre Statusleiste passend ein.
    if (app) app.setTheme(dark);
  };
  applyTheme();
  themeButton.hidden = false;
  themeButton.addEventListener('click', () => {
    preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('phoniebox-theme', preference); } catch (_) {}
    applyTheme();
  });
  media.addEventListener('change', applyTheme);
  const appButton = document.getElementById('app-menu');
  if (app && appButton) {
    appButton.hidden = false;
    appButton.addEventListener('click', () => app.openMenu());
  }

  const links = [...document.querySelectorAll('nav[aria-label="Bereiche"] a')];
  const panels = [...document.querySelectorAll('[data-view]')];
  const names = links.map(link => link.hash.slice(1));
  const showView = () => {
    const name = names.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'player';
    panels.forEach(panel => { panel.hidden = panel.dataset.view !== name; });
    links.forEach(link => {
      if (link.hash === '#' + name) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  };
  showView();
  window.addEventListener('hashchange', showView);
  // Keep the relevant view after a successful form submission and redirect.
  document.querySelectorAll('[data-view] form').forEach(form => {
    form.addEventListener('submit', () => {
      try { sessionStorage.setItem('phoniebox-return-view', form.closest('[data-view]').dataset.view); } catch (_) {}
    });
  });
  try {
    const restore = sessionStorage.getItem('phoniebox-return-view');
    sessionStorage.removeItem('phoniebox-return-view');
    if (names.includes(restore) && !location.hash) {
      history.replaceState(null, '', '#' + restore);
      showView();
    }
  } catch (_) {}
})();
