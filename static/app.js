'use strict';
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
function feedback(message) { $('feedback').textContent = message; $('feedback').hidden = !message; }
async function api(path, data) {
  const options = {cache:'no-store'};
  if (data !== undefined) { options.method = 'POST'; options.headers = {'X-CSRF-Token':csrf}; options.body = new URLSearchParams(data); }
  const r = await fetch(path,options);
  if (r.status === 401) { window.location.assign('/login'); throw new Error('Bitte anmelden.'); }
  if (!r.headers.get('content-type')?.includes('application/json')) throw new Error('Anfrage fehlgeschlagen. Seite neu laden.');
  const result = await r.json();
  if (!r.ok) throw new Error(result.error || 'Anfrage fehlgeschlagen.');
  return result;
}
let refreshTimer;
let playerBusy = false;
async function player() {
  if (playerBusy) return;
  clearTimeout(refreshTimer);
  if (document.hidden) { refreshTimer = setTimeout(player,20000); return; }
  try {
    playerBusy = true;
    const p = await api('/api/player');
    $('player-message').textContent = p.active ? (p.playing ? 'Wiedergabe läuft' : 'Pausiert') : p.message;
    $('playback-status').textContent = $('player-message').textContent;
    $('title').textContent = p.title || 'Bereit für deine Musik.';
    $('artist').textContent = p.artist || '';
    $('cover').hidden = !p.cover; $('placeholder').hidden = !!p.cover;
    $('cover').classList.toggle('station-logo', p.source === 'radio');
    $('cover').alt = p.source === 'radio' ? 'Senderlogo: ' + p.title : 'Albumcover';
    if (p.cover) $('cover').src = p.cover; else $('cover').removeAttribute('src');
    $('progress').max = p.duration || 1; $('progress').value = p.progress || 0;
    if (Number.isInteger(p.volume) && document.activeElement !== $('volume')) { $('volume').value=p.volume; $('volume-value').textContent=p.volume+' %'; }
    $('spotify-link').href = /^https:\/\/open\.spotify\.com\//.test(p.url || '') ? p.url : 'https://open.spotify.com';
  } catch(e) { $('player-message').textContent=e.message; $('playback-status').textContent=e.message; }
  finally { playerBusy = false; }
  refreshTimer = setTimeout(player,20000);
}
document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', async () => {
  button.disabled = true;
  try { await api('/api/player/'+button.dataset.action, {uri:button.dataset.uri || ''}); feedback('Wiedergabebefehl gesendet.'); setTimeout(player,1200); }
  catch(e) {feedback(e.message);} finally {button.disabled=false;}
}));
$('volume').addEventListener('input', () => $('volume-value').textContent=$('volume').value+' %');
$('volume').addEventListener('change', async () => {try {await api('/api/player/volume',{volume:$('volume').value});} catch(e){feedback(e.message);}});
function clearCardSearch() {
  $('card-search').value='';
  $('card-search-status').textContent='';
  $('card-search-results').hidden=true;
  $('card-search-results').textContent='';
}
function cardFields() {
  const action=$('card-action').value;
  $('card-name').required=action==='music';
  const names={pause:'Stop / Pause',play:'Wiedergabe fortsetzen',next:'Nächster Titel',previous:'Vorheriger Titel',volume_up:'Lauter',volume_down:'Leiser',volume:'Lautstärke'};
  names.radio='Sendername (optional)';
  $('card-name').placeholder=names[action] || 'Kinderlieder';
  $('card-search-type-label').hidden=action!=='music';
  $('card-search-label').hidden=action!=='music';
  $('card-uri-label').hidden=action!=='music';
  $('card-station-label').hidden=action!=='radio';
  $('card-station').disabled=action!=='radio';
  $('card-uri').required=action==='music';
  $('card-value-label').hidden=!['volume','volume_up','volume_down'].includes(action);
  $('card-value').disabled=!['volume','volume_up','volume_down'].includes(action);
  $('card-value').min=action==='volume'?'0':'1';
  if (action!=='music') clearCardSearch();
}
function loadCard(card) {
  $('card-action').value=card?.action || 'music';
  $('card-value').value=card?.value ?? 10;
  if (card?.station) $('card-station').value=card.station;
  clearCardSearch();
  cardFields();
}
$('card-action').addEventListener('change',cardFields);
cardFields();
const searchLabels={track:'Titel',album:'Album',playlist:'Playlist'};
function renderCardSearchResults(items) {
  const box=$('card-search-results');
  box.textContent='';
  box.hidden=!items.length;
  $('card-search-status').textContent=items.length ? '' : 'Nichts gefunden.';
  items.forEach(item=>{
    const article=document.createElement('article'); article.className='card';
    if (item.image) { const img=document.createElement('img'); img.src=item.image; img.alt=''; img.className='thumb'; article.appendChild(img); }
    const info=document.createElement('div');
    const h3=document.createElement('h3'); h3.textContent=item.name; info.appendChild(h3);
    const p=document.createElement('p'); p.className='uri';
    p.textContent=(searchLabels[item.type]||item.type)+(item.artist ? ' · '+item.artist : '');
    info.appendChild(p);
    article.appendChild(info);
    const actions=document.createElement('div'); actions.className='actions';
    const button=document.createElement('button'); button.type='button'; button.textContent='Übernehmen';
    button.addEventListener('click',()=>{
      $('card-uri').value=item.uri;
      if (!$('card-name').value.trim()) $('card-name').value=item.name;
      clearCardSearch();
    });
    actions.appendChild(button); article.appendChild(actions);
    box.appendChild(article);
  });
}
let cardSearchTimer, cardSearchToken=0;
function runCardSearch(delay) {
  clearTimeout(cardSearchTimer);
  const query=$('card-search').value.trim();
  $('card-search-results').hidden=true; $('card-search-results').textContent='';
  if (query.length<2) { $('card-search-status').textContent=''; return; }
  $('card-search-status').textContent='Suche läuft …';
  cardSearchTimer=setTimeout(async ()=>{
    const token=++cardSearchToken;
    try {
      const type=$('card-search-type').value;
      const r=await api('/api/spotify/search?q='+encodeURIComponent(query)+(type ? '&type='+encodeURIComponent(type) : ''));
      if (token!==cardSearchToken) return; // a newer search has started meanwhile
      renderCardSearchResults(r.results);
    } catch(e) { if (token===cardSearchToken) $('card-search-status').textContent=e.message; }
  },delay);
}
$('card-search').addEventListener('input',()=>runCardSearch(400));
$('card-search-type').addEventListener('change',()=>runCardSearch(0));
$('learn').addEventListener('click',async () => {try {await api('/api/learn',{}); loadCard(null); $('uid').value=''; $('card-name').value=''; $('card-uri').value=''; $('learn-status').textContent='Jetzt Karte auflegen. 60 Sekunden Zeit; Musik bleibt beim Anlernen aus.';}catch(e){feedback(e.message);}});
$('cancel-learn').addEventListener('click',async () => {try {await api('/api/learn/cancel',{}); $('learn-status').textContent='Anlernen beendet.';}catch(e){feedback(e.message);}});
document.querySelectorAll('.edit-card').forEach(button=>button.addEventListener('click',()=>{
  loadCard({action:button.dataset.cardAction,value:Number(button.dataset.value),station:button.dataset.station});
  $('uid').value=button.dataset.uid; $('card-name').value=button.dataset.name; $('card-uri').value=button.dataset.uri; $('uid').scrollIntoView({block:'center'}); $('card-name').focus();
}));
document.querySelectorAll('.delete-card').forEach(form=>form.addEventListener('submit',event=>{if(!confirm('Diese Kartenzuordnung löschen?'))event.preventDefault();}));
let wasLearning=false;
let displayedScan=null;
// A card changes the music without anything on this page being clicked. Without this the
// start page kept showing the previous album for up to 20 seconds (plus the server cache).
let playedScan=null;
function refreshAfterCard(scanKey){
  if(playedScan===null){ playedScan=scanKey; return; }
  if(scanKey===playedScan) return;
  playedScan=scanKey;
  setTimeout(player,1500); setTimeout(player,5000);
}
let hardwareTimer, hardwareBusy = false;
async function hardware() {
  if (hardwareBusy) return;
  clearTimeout(hardwareTimer);
  hardwareBusy = true;
  try {
    if (!document.hidden) {
      const h=await api('/api/hardware');
      $('reader-status').textContent=h.reader; $('librespot-status').textContent=h.player; $('hardware-message').textContent=h.message || 'Noch keine Meldung.';
      const scanKey = h.scan_revision+':'+h.last_uid;
      refreshAfterCard(h.scan_revision+':'+h.message);
      if(h.last_uid && scanKey !== displayedScan){
        displayedScan=scanKey;
        loadCard(h.card);
        $('uid').value=h.last_uid;
        $('card-name').value=h.card?.name || '';
        $('card-uri').value=h.card?.uri || '';
        $('learn-status').textContent=h.card
          ? 'Karte erkannt. Aktion, Name oder Spotify-Link ändern und speichern.'
          : 'Neue Karte erkannt. Aktion wählen, Angaben ergänzen und speichern.';
      } else if(h.learning && !h.learned){
        $('learn-status').textContent='Jetzt Karte auflegen. Musik bleibt beim Anlernen aus.';
      } else if(wasLearning && !h.learning){
        $('learn-status').textContent='Die Kartendaten können bearbeitet und gespeichert werden.';
      }
      wasLearning=h.learning;
    }
  } catch(e){$('reader-status').textContent=e.message; $('librespot-status').textContent='Nicht erreichbar: '+e.message;}
  finally { hardwareBusy = false; }
  hardwareTimer = setTimeout(hardware,1500);
}
player(); hardware();

$('radio-start').addEventListener('click',async()=>{try{await api('/api/media/start',{source:'radio',choice:$('radio-station').value,volume:$('radio-volume').value});player();}catch(e){feedback(e.message);}});
$('tone-test').addEventListener('click',async()=>{try{await api('/api/media/start',{source:'tone',choice:$('tone-choice').value,volume:$('radio-volume').value});player();}catch(e){feedback(e.message);}});
$('media-stop').addEventListener('click',async()=>{try{await api('/api/media/stop',{});player();}catch(e){feedback(e.message);}});
document.querySelectorAll('.alarm-test').forEach(button=>button.addEventListener('click',async()=>{
  button.disabled=true;
  try{await api('/api/alarm/test',{id:button.dataset.id}); feedback('Wecker wird getestet. „Radio / Wecker stoppen“ beendet ihn.'); player();}
  catch(e){feedback(e.message);} finally{button.disabled=false;}
}));
document.querySelectorAll('.delete-alarm').forEach(form=>form.addEventListener('submit',event=>{if(!confirm('Diesen Wecker löschen?'))event.preventDefault();}));
// "Bearbeiten" opens /?alarm=<id>#alarm; bring the form below the list into view.
if (new URLSearchParams(location.search).get('alarm') && location.hash==='#alarm') $('alarm-form-title').scrollIntoView({block:'start'});
let mediaTimer, mediaBusy = false, mediaIdentity = '';
async function mediaStatus(){
  if(mediaBusy) return;
  clearTimeout(mediaTimer); mediaBusy=true;
  try { if(!document.hidden){
    const m=await api('/api/media');
    const identity = JSON.stringify([m.source, m.cover, m.paused]);
    if (identity !== mediaIdentity) { mediaIdentity = identity; player(); }
    $('media-message').textContent=m.message || (m.source?m.title:'');
    $('local-status').textContent=m.message || (m.source?m.title:'Keine lokale Wiedergabe aktiv.');
    $('alarm-clock').textContent='Uhrzeit auf der Phoniebox: '+m.clock+' · Europe/Berlin';
    $('clock-status').textContent=m.clock+' · Europe/Berlin';
  }} catch(e){$('media-message').textContent=e.message; $('local-status').textContent=e.message; $('clock-status').textContent='Nicht erreichbar.';}
  finally { mediaBusy=false; }
  mediaTimer=setTimeout(mediaStatus,5000);
}
mediaStatus();

function btDevice(device, buttons, active) {
  const article = document.createElement('article'); article.className = 'card';
  const info = document.createElement('div');
  const h3 = document.createElement('h3'); h3.textContent = device.name || device.mac; info.appendChild(h3);
  const mono = document.createElement('p'); mono.className = 'mono'; mono.textContent = device.mac; info.appendChild(mono);
  if ('connected' in device) {
    const status = document.createElement('p'); status.className = 'uri';
    let text = device.bonded ? (device.connected ? 'Dauerhaft gekoppelt · Verbunden' : 'Dauerhaft gekoppelt · Nicht verbunden') : 'Bekannt · Nicht dauerhaft gekoppelt';
    if (active) text += ' · Aktueller Audioausgang';
    status.textContent = text;
    info.appendChild(status);
  }
  article.appendChild(info);
  const actions = document.createElement('div'); actions.className = 'actions';
  buttons.forEach(({label, quiet, danger, onClick}) => {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
    if (quiet) button.className = 'quiet'; if (danger) button.className = 'danger';
    button.addEventListener('click', async () => {
      button.disabled = true;
      // Note is set AFTER the refresh below, not before: loadBluetooth() always
      // overwrites #bt-status with its own generic summary, which previously erased
      // whatever error or success message this action had just shown.
      let note = null;
      try { const r = await onClick(); note = (r && r.message) || null; }
      catch(e) { note = e.message; }
      await loadBluetooth();
      if (note) $('bt-status').textContent = note;
    });
    actions.appendChild(button);
  });
  article.appendChild(actions);
  return article;
}
function useAsOutput(device) {
  return async () => {
    const r = await api('/api/bluetooth/use', {mac:device.mac});
    const field = document.querySelector('#settings input[name="audio"]');
    if (field) field.value = r.audio;
    feedback('Audioausgang gewechselt. Der Player startet neu.');
    return r;
  };
}
function renderBluetooth(paired, found, active) {
  const pairedList = $('bt-paired'); pairedList.textContent = '';
  if (paired.length) paired.forEach(device => {
    const isActive = active && device.mac === active;
    const buttons = [
      !device.bonded
        ? {label:'Dauerhaft koppeln', onClick:() => api('/api/bluetooth/pair', {mac:device.mac})}
        : device.connected
        ? {label:'Trennen', quiet:true, onClick: async () => ({message:'Getrennt.', ...await api('/api/bluetooth/disconnect', {mac:device.mac})})}
        : {label:'Verbinden', onClick: async () => ({message:'Verbunden.', ...await api('/api/bluetooth/connect', {mac:device.mac})})},
    ];
    // Switching directly to a device that is not yet the active output; already-active
    // needs no such button, since that is the point of the "Aktueller Audioausgang" label.
    if (!isActive && device.bonded) buttons.push({label:'Als Audioausgang verwenden', quiet:true, onClick:useAsOutput(device)});
    buttons.push({label:'Entfernen', danger:true, onClick: async () => ({message:'Entfernt.', ...await api('/api/bluetooth/forget', {mac:device.mac})})});
    pairedList.appendChild(btDevice(device, buttons, isActive));
  });
  else { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'Noch keine Bluetooth-Geräte bekannt.'; pairedList.appendChild(p); }
  const foundList = $('bt-found'); if (found !== null) foundList.textContent = '';
  if (found) found.forEach(device => foundList.appendChild(btDevice(device, [
    {label:'Koppeln', onClick:() => api('/api/bluetooth/pair', {mac:device.mac})},
  ])));
}
let bluetoothBusy = false;
async function loadBluetooth() {
  if(bluetoothBusy) return;
  bluetoothBusy=true;
  try {
    const r = await api('/api/bluetooth');
    if(r.adapter && r.adapter.state!=='ready') {
      $('bt-status').textContent=r.adapter.message;
      $('bluetooth-status').textContent=r.adapter.message;
      return;
    }
    renderBluetooth(r.paired, null, r.active);
    const connected=r.paired.filter(d=>d.connected);
    $('bluetooth-status').textContent=connected.length ? 'Verbunden: '+connected.map(d=>d.name || d.mac).join(', ') : 'Bluetooth bereit · '+r.paired.length+' bekannt, kein Gerät verbunden.';
    if (r.reconnect && !connected.length) $('bluetooth-status').textContent += ' · ' + r.reconnect;
    $('bt-status').textContent = r.paired.length ? (r.reconnect || '') : 'Noch keine Bluetooth-Geräte gekoppelt. „Nach neuen Geräten suchen“ verwenden.';
  } catch(e) { $('bt-status').textContent=e.message; $('bluetooth-status').textContent=e.message; }
  finally { bluetoothBusy=false; }
}
async function refreshStatus(){
  $('refresh-status').disabled=true;
  $('status-refresh-note').textContent='Status wird abgefragt …';
  try { await Promise.all([player(),hardware(),mediaStatus(),loadBluetooth()]);
    $('status-refresh-note').textContent='Abfrage abgeschlossen. Ergebnisse stehen oben.';
  } finally { $('refresh-status').disabled=false; }
}
$('refresh-status').addEventListener('click',refreshStatus);
function visibleBluetoothStatus(){
  if(!document.hidden && ['#settings','#bluetooth'].includes(location.hash)) loadBluetooth();
}
window.addEventListener('hashchange',visibleBluetoothStatus);
setInterval(visibleBluetoothStatus,10000);
$('bt-scan').addEventListener('click', async () => {
  $('bt-scan').disabled = true; $('bt-status').textContent = 'Suche läuft (bis zu 10 Sekunden) – Lautsprecher jetzt in den Kopplungsmodus versetzen …';
  try { const r = await api('/api/bluetooth/scan', {}); renderBluetooth(r.paired, r.found, r.active); $('bt-status').textContent = r.found.length ? '' : 'Keine neuen Geräte gefunden. Lautsprecher einschalten, in Reichweite bringen und in den Kopplungsmodus versetzen.'; }
  catch(e) { $('bt-status').textContent = e.message; }
  finally { $('bt-scan').disabled = false; }
});
loadBluetooth();

$('cover').addEventListener('error', () => { $('cover').hidden = true; $('placeholder').hidden = false; });
$('reboot-pi').addEventListener('click', async () => {
  if (!window.confirm('Phoniebox wirklich neu starten? Laufende Musik wird beendet.')) return;
  const button = $('reboot-pi'); button.disabled = true;
  try {
    const result = await api('/api/system/reboot', {});
    $('reboot-message').textContent = result.message;
  } catch (e) {
    $('reboot-message').textContent = e.message;
    button.disabled = false;
  }
});
