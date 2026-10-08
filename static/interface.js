(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById('theme-toggle');
  const themeLabel = document.getElementById('theme-label');
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  // Nur in der Android-App vorhanden: Brücke zu Menü und Statusleiste.
  const app = window.PhonieboxApp;
  let preference = null;
  try { preference = localStorage.getItem('phoniebox-theme'); } catch (_) {}
  const applyTheme = () => {
    const dark = preference ? preference === 'dark' : media.matches;
    root.dataset.theme = dark ? 'dark' : 'light';
    themeLabel.textContent = dark ? 'Hell' : 'Dunkel';
    themeButton.title = dark ? 'Hell' : 'Dunkel';
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

  // Seitenleiste: breit immer ausgeklappt (CSS), mittel als Symbolleiste, schmal versteckt.
  // Ausgeklappt über breit/schmal hinweg legt sie sich über die Seite.
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('side-backdrop');
  const toggles = [document.getElementById('side-toggle'), document.getElementById('side-open')];
  const wide = window.matchMedia('(min-width: 1100px)');
  const setOpen = open => {
    open = open && !wide.matches;
    root.classList.toggle('nav-open', open);
    backdrop.hidden = !open;
    toggles.forEach(button => {
      button.setAttribute('aria-expanded', String(open));
      button.setAttribute('aria-label', open ? 'Menü schließen' : 'Menü öffnen');
    });
  };
  toggles.forEach(button => button.addEventListener('click', () => setOpen(!root.classList.contains('nav-open'))));
  backdrop.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
  wide.addEventListener('change', () => setOpen(false));
  sidebar.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => setOpen(false)));

  const panel = document.getElementById('app-panel');
  if (app && panel) {
    panel.hidden = false;
    // In der Symbolleiste klappt das App-Symbol die Leiste aus.
    document.getElementById('app-title').addEventListener('click', () => {
      if (!wide.matches && !root.classList.contains('nav-open')) setOpen(true);
    });
    // Ältere Apps (1.1.0) kennen nur ihr eigenes Menü.
    if (typeof app.version !== 'function') {
      const menu = document.getElementById('app-menu');
      menu.hidden = false;
      menu.addEventListener('click', () => app.openMenu());
    } else {
      document.getElementById('app-controls').hidden = false;
      const status = document.getElementById('app-status');
      const badge = document.getElementById('app-badge');
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
          badge.textContent = String(list.length);
          badge.hidden = !list.length;
          app.checkNow();
        } catch (error) {
          status.replaceChildren(note('notice error', 'Status nicht abrufbar', error.message));
        }
      };
      // Ab Android-App 1.3.0: Player in der Benachrichtigungsleiste.
      const player = document.getElementById('app-player');
      const hasPlayer = typeof app.playerEnabled === 'function';
      if (hasPlayer) {
        document.getElementById('app-player-row').hidden = false;
        player.addEventListener('change', () => app.setPlayer(player.checked));
      }
      // Ab Android-App 1.3.2: Befund, warum der Player (nicht) zu sehen ist.
      const diag = document.getElementById('app-player-diag');
      if (hasPlayer && typeof app.playerDiagnosis === 'function') {
        const diagText = document.getElementById('app-player-diag-text');
        const showDiag = () => { diagText.textContent = app.playerDiagnosis(); };
        diag.hidden = false;
        diag.addEventListener('toggle', () => { if (diag.open) showDiag(); });
        document.getElementById('app-player-start').addEventListener('click', () => {
          app.startPlayer();
          diagText.textContent = 'Player wird gestartet …';
          setTimeout(showDiag, 1500);
        });
      }
      // Ab Android-App 1.3.1: Hinweis, wenn Android die Benachrichtigungen blockiert.
      const blocked = document.getElementById('app-blocked');
      const canAsk = typeof app.notificationsAllowed === 'function';
      if (canAsk) document.getElementById('app-allow').addEventListener('click', () => app.openNotificationSettings());
      // Schalter zeigen den Stand der App; nach einem Ausflug in die Android-Einstellungen neu.
      const sync = () => {
        notify.checked = app.notificationsEnabled();
        if (hasPlayer) player.checked = app.playerEnabled();
        if (canAsk) blocked.hidden = app.notificationsAllowed();
      };
      sync();
      document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
      document.getElementById('app-version').textContent = 'Phoniebox-App ' + app.version();
      document.getElementById('app-check').addEventListener('click', loadStatus);
      notify.addEventListener('change', () => app.setNotifications(notify.checked));
      document.getElementById('app-reload').addEventListener('click', () => location.reload());
      document.getElementById('app-cert').addEventListener('click', () => {
        if (confirm('Zertifikat der Box neu bestätigen? Das ist nur nach einer Neuinstallation der Box nötig.')) app.resetCertificate();
      });
      loadStatus();
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
