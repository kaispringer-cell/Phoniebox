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
  const appDialog = document.getElementById('app-dialog');
  if (app && appButton) {
    appButton.hidden = false;
    // Ältere Apps (1.1.0) kennen nur ihr eigenes Menü.
    if (!appDialog || typeof app.version !== 'function') {
      appButton.addEventListener('click', () => app.openMenu());
    } else {
      const status = document.getElementById('app-status');
      const notify = document.getElementById('app-notify');
      const note = (cls, title, text) => {
        const p = document.createElement('p');
        p.className = cls;
        const strong = document.createElement('strong');
        strong.textContent = title;
        p.append(strong, text);
        return p;
      };
      const loadStatus = async () => {
        status.replaceChildren(note('hint', '', 'Status wird geladen …'));
        try {
          const response = await fetch('/api/notifications', {headers: {Accept: 'application/json'}});
          if (!response.ok) throw new Error('HTTP ' + response.status);
          const list = (await response.json()).notifications || [];
          status.replaceChildren(...(list.length
            ? list.map(n => note('notice error', n.title, n.text))
            : [note('notice', 'Alles in Ordnung', 'Die Box meldet gerade keine Probleme.')]));
          app.checkNow();
        } catch (error) {
          status.replaceChildren(note('notice error', 'Status nicht abrufbar', error.message));
        }
      };
      // Ab Android-App 1.3.0: Player in der Benachrichtigungsleiste.
      const player = document.getElementById('app-player');
      const hasPlayer = player && typeof app.playerEnabled === 'function';
      if (hasPlayer) {
        document.getElementById('app-player-row').hidden = false;
        player.addEventListener('change', () => app.setPlayer(player.checked));
      }
      appButton.addEventListener('click', () => {
        notify.checked = app.notificationsEnabled();
        if (hasPlayer) player.checked = app.playerEnabled();
        document.getElementById('app-version').textContent = 'Phoniebox-App ' + app.version();
        appDialog.showModal();
        loadStatus();
      });
      document.getElementById('app-dialog-close').addEventListener('click', () => appDialog.close());
      document.getElementById('app-check').addEventListener('click', loadStatus);
      notify.addEventListener('change', () => app.setNotifications(notify.checked));
      document.getElementById('app-reload').addEventListener('click', () => location.reload());
      document.getElementById('app-cert').addEventListener('click', () => {
        if (confirm('Zertifikat der Box neu bestätigen? Das ist nur nach einer Neuinstallation der Box nötig.')) app.resetCertificate();
      });
    }
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
