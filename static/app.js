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
    $('sp-title').textContent = p.active ? (p.title || 'Ohne Titel') : 'Gerade läuft nichts.';
    $('sp-artist').textContent = p.active ? [p.artist, p.playing ? 'Wiedergabe läuft' : 'Pausiert'].filter(Boolean).join(' · ') : (p.message || '');
    $('sp-cover').hidden = !p.cover; $('sp-placeholder').hidden = !!p.cover;
    if (p.cover) $('sp-cover').src = p.cover; else $('sp-cover').removeAttribute('src');
    if (Number.isInteger(p.volume) && document.activeElement !== $('sp-volume')) { $('sp-volume').value=p.volume; $('sp-volume-value').textContent=p.volume+' %'; }
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
$('volume').addEventListener('change', async () => {$('sp-volume').value=$('volume').value; $('sp-volume-value').textContent=$('volume').value+' %'; try {await api('/api/player/volume',{volume:$('volume').value});} catch(e){feedback(e.message);}});
let clearCardSearch=()=>{};
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
// One search result or album title as a card with action buttons.
function musicCard(item, buttons) {
  const article=document.createElement('article'); article.className='card';
  const blank=()=>{ const span=document.createElement('span'); span.className='thumb'; return span; };
  if (item.image) {
    const img=document.createElement('img'); img.src=item.image; img.alt=''; img.className='thumb';
    img.addEventListener('error',()=>img.replaceWith(blank()));
    article.appendChild(img);
  } else article.appendChild(blank());
  const info=document.createElement('div');
  const h3=document.createElement('h3'); h3.textContent=(item.number ? item.number+'. ' : '')+item.name; info.appendChild(h3);
  const p=document.createElement('p'); p.className='uri';
  p.textContent=(searchLabels[item.type]||item.type)+(item.artist ? ' · '+item.artist : '');
  info.appendChild(p);
  article.appendChild(info);
  const actions=document.createElement('div'); actions.className='actions';
  buttons.forEach(({label, quiet, onClick})=>{
    const button=document.createElement('button'); button.type='button'; button.textContent=label;
    if (quiet) button.className='quiet';
    button.addEventListener('click',()=>onClick(item,button));
    actions.appendChild(button);
  });
  article.appendChild(actions);
  return article;
}
// Spotify search with results to pick from; used by the card form, the "Neue Karte" dialog
// and the Spotify tab. 'buttons' replaces the single "Übernehmen" button.
function spotifySearch(ids, pick, buttons) {
  let timer, token=0;
  const clear=()=>{ clearTimeout(timer); token++; $(ids.query).value=''; $(ids.status).textContent=''; $(ids.results).hidden=true; $(ids.results).textContent=''; };
  function render(items) {
    const box=$(ids.results);
    box.textContent='';
    box.hidden=!items.length;
    $(ids.status).textContent=items.length ? '' : 'Nichts gefunden.';
    items.forEach(item=>box.appendChild(musicCard(item, buttons ? buttons(item) : [{label:'Übernehmen', onClick:pick}])));
  }
  function run(delay) {
    clearTimeout(timer);
    const query=$(ids.query).value.trim();
    $(ids.results).hidden=true; $(ids.results).textContent='';
    if (query.length<2) { $(ids.status).textContent=''; return; }
    $(ids.status).textContent='Suche läuft …';
    timer=setTimeout(async ()=>{
      const current=++token;
      try {
        const type=$(ids.type).value;
        const r=await api('/api/spotify/search?q='+encodeURIComponent(query)+(type ? '&type='+encodeURIComponent(type) : ''));
        if (current!==token) return; // a newer search has started meanwhile
        render(r.results);
      } catch(e) { if (current===token) $(ids.status).textContent=e.message; }
    },delay);
  }
  $(ids.query).addEventListener('input',()=>run(400));
  $(ids.type).addEventListener('change',()=>run(0));
  return clear;
}
clearCardSearch=spotifySearch(
  {query:'card-search',type:'card-search-type',status:'card-search-status',results:'card-search-results'},
  item=>{ $('card-uri').value=item.uri; if (!$('card-name').value.trim()) $('card-name').value=item.name; clearCardSearch(); }
);
$('learn').addEventListener('click',async () => {try {await api('/api/learn',{}); loadCard(null); $('uid').value=''; $('card-name').value=''; $('card-uri').value=''; $('learn-status').textContent='Jetzt Karte auflegen. 60 Sekunden Zeit; Musik bleibt beim Anlernen aus.';}catch(e){feedback(e.message);}});
$('cancel-learn').addEventListener('click',async () => {try {await api('/api/learn/cancel',{}); $('learn-status').textContent='Anlernen beendet.';}catch(e){feedback(e.message);}});
// "Neue Karte": wait for a card in silent learn mode, then search Spotify and save the card.
// The M301 reader cannot write to cards, so the card's ID is linked to the chosen music.
const newCard={uid:'', waiting:false, timer:null, preset:null};
function newCardStep(step) {
  ['scan','search','save'].forEach(name=>{
    $('nc-'+name).hidden=name!==step;
    if (name===step) $('nc-mark-'+name).setAttribute('aria-current','step'); else $('nc-mark-'+name).removeAttribute('aria-current');
  });
  $('nc-uid').hidden=step==='scan';
}
function newCardPick(item) {
  $('nc-form-uri').value=item.uri;
  $('nc-name').value=item.name;
  $('nc-pick-name').textContent=item.name;
  $('nc-pick-info').textContent=(searchLabels[item.type]||item.type)+(item.artist ? ' · '+item.artist : '');
  $('nc-thumb').hidden=!item.image;
  if (item.image) $('nc-thumb').src=item.image; else $('nc-thumb').removeAttribute('src');
  newCardStep('save');
  $('nc-name').focus();
}
const clearNewCardSearch=spotifySearch(
  {query:'nc-query',type:'nc-type',status:'nc-search-status',results:'nc-results'},
  newCardPick
);
async function newCardWait() {
  clearTimeout(newCard.timer);
  newCard.uid=''; newCard.waiting=true;
  $('nc-retry').hidden=true;
  $('nc-scan-status').textContent=newCard.preset
    ? 'Bitte jetzt die NFC-Karte für „'+newCard.preset.name+'“ auf die Phoniebox legen.'
    : 'Bitte jetzt die neue NFC-Karte auf die Phoniebox legen.';
  newCardStep('scan');
  try { await api('/api/learn',{}); }
  catch(e) { newCard.waiting=false; $('nc-scan-status').textContent=e.message; $('nc-retry').hidden=false; return; }
  const poll=async()=>{
    if (!newCard.waiting) return;
    try {
      const h=await api('/api/hardware');
      if (!newCard.waiting) return;
      if (h.learned) {
        newCard.waiting=false; newCard.uid=h.learned;
        // The ID is captured; the box plays cards normally again from here on.
        api('/api/learn/cancel',{}).catch(()=>{});
        $('nc-form-uid').value=h.learned;
        $('nc-uid').textContent=h.card
          ? 'Karte '+h.learned+' erkannt. Sie startet bisher „'+h.card.name+'“; die neue Auswahl ersetzt das.'
          : 'Karte '+h.learned+' erkannt.'+(newCard.preset ? '' : ' Jetzt die Musik für diese Karte suchen.');
        clearNewCardSearch();
        if (newCard.preset) { newCardPick(newCard.preset); return; }
        newCardStep('search');
        $('nc-query').focus();
        return;
      }
      if (!h.learning) {
        newCard.waiting=false;
        $('nc-scan-status').textContent='Keine Karte erkannt. Reader-Status: '+h.reader+'.';
        $('nc-retry').hidden=false;
        return;
      }
    } catch(e) { $('nc-scan-status').textContent=e.message; }
    newCard.timer=setTimeout(poll,800);
  };
  poll();
}
// preset: music chosen in the Spotify tab; the dialog then only asks for the card.
function openNewCard(preset) {
  newCard.preset=preset || null;
  $('nc-form-uid').value=''; $('nc-form-uri').value=''; $('nc-name').value='';
  clearNewCardSearch();
  $('new-card').showModal();
  newCardWait();
}
$('new-card-open').addEventListener('click',()=>openNewCard(null));
$('nc-retry').addEventListener('click',newCardWait);
$('nc-back').addEventListener('click',()=>{ newCard.preset=null; newCardStep('search'); $('nc-query').focus(); });
$('new-card-close').addEventListener('click',()=>$('new-card').close());
$('new-card').addEventListener('close',()=>{
  clearTimeout(newCard.timer);
  if (newCard.waiting) { newCard.waiting=false; api('/api/learn/cancel',{}).catch(()=>{}); }
});
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
$('sp-cover').addEventListener('error', () => { $('sp-cover').hidden = true; $('sp-placeholder').hidden = false; });

// Spotify tab: search an album, title or playlist, play it or put it on an NFC card.
async function spotifyPlay(item, button) {
  button.disabled=true;
  $('sp-message').textContent='„'+item.name+'“ wird gestartet …';
  try { await api('/api/player/play',{uri:item.uri}); $('sp-message').textContent='„'+item.name+'“ gestartet.'; setTimeout(player,1200); setTimeout(player,4000); }
  catch(e) { $('sp-message').textContent=e.message; }
  finally { button.disabled=false; }
}
const spotifyButtons=item=>[
  {label:'Abspielen', onClick:spotifyPlay},
  ...(item.type==='album' ? [{label:'Titel', quiet:true, onClick:showAlbum}] : []),
  {label:'Mit NFC verbinden', quiet:true, onClick:openNewCard},
];
spotifySearch({query:'sp-query',type:'sp-type',status:'sp-search-status',results:'sp-results'}, null, spotifyButtons);
let albumToken=0;
function closeAlbum() {
  albumToken++;
  $('sp-album').hidden=true;
  $('sp-results').hidden=!$('sp-results').children.length;
  $('sp-query').focus();
}
async function showAlbum(item) {
  const current=++albumToken;
  $('sp-results').hidden=true;
  $('sp-album').hidden=false;
  $('sp-album-head').replaceChildren(musicCard(item, spotifyButtons(item).filter(b=>b.label!=='Titel')));
  $('sp-tracks').textContent='';
  $('sp-album-status').textContent='Titel werden geladen …';
  $('sp-album').scrollIntoView({block:'start'});
  try {
    const r=await api('/api/spotify/album?uri='+encodeURIComponent(item.uri));
    if (current!==albumToken) return;
    $('sp-album-status').textContent=r.tracks.length ? r.tracks.length+' Titel' : 'Keine Titel gefunden.';
    r.tracks.forEach(track=>$('sp-tracks').appendChild(musicCard(track, spotifyButtons(track))));
  } catch(e) { if (current===albumToken) $('sp-album-status').textContent=e.message; }
}
$('sp-album-back').addEventListener('click',closeAlbum);
$('sp-query').addEventListener('input',()=>{ if (!$('sp-album').hidden) { albumToken++; $('sp-album').hidden=true; } });
$('sp-type').addEventListener('change',()=>{ if (!$('sp-album').hidden) { albumToken++; $('sp-album').hidden=true; } });
$('sp-volume').addEventListener('input', () => $('sp-volume-value').textContent=$('sp-volume').value+' %');
$('sp-volume').addEventListener('change', async () => {
  $('volume').value=$('sp-volume').value; $('volume-value').textContent=$('sp-volume').value+' %';
  try {await api('/api/player/volume',{volume:$('sp-volume').value});} catch(e){$('sp-message').textContent=e.message;}
});
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
