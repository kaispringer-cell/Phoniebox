package de.phoniebox.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;

import javax.net.ssl.HttpsURLConnection;

/**
 * Der Player in der Benachrichtigungsleiste: Albumcover, Titel, Interpret und Zurück,
 * Start/Pause, Weiter, wie bei einem Musikplayer. Antippen öffnet die App.
 *
 * Läuft als Vordergrunddienst, solange die Box erreichbar ist, und fragt GET /api/player ab:
 * bei laufender Musik alle 5 Sekunden, sonst alle 15, bei ausgeschaltetem Bildschirm gar nicht.
 * Ist die Box länger als 2 Minuten nicht erreichbar (Handy nicht zu Hause), beendet er sich;
 * beim nächsten Öffnen der App startet er wieder.
 */
public class PlayerService extends Service {
    static final String CHANNEL = "playback";
    private static final int ID = 2;
    private static final String ACTION = "action";
    private static final String STOP = "stop";
    private static final long FAST = 5_000L;
    private static final long SLOW = 15_000L;
    private static final long GIVE_UP = 2 * 60_000L;

    private final Handler main = new Handler(Looper.getMainLooper());
    private HandlerThread thread;
    private Handler worker;
    private MediaSession session;
    private NotificationManager manager;

    /** Schreibt nur der Worker-Thread; build() liest sie auch im UI-Thread. */
    private volatile boolean playing;
    private volatile long unreachableSince;
    private String coverUrl = "";
    private volatile Bitmap cover;
    private volatile String title = "Phoniebox";
    private volatile String text = "Verbinde …";

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            refresh();
            worker.removeCallbacks(this);
            if (screenOn()) {
                worker.postDelayed(this, playing ? FAST : SLOW);
            }
        }
    };

    private final BroadcastReceiver screen = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            worker.removeCallbacks(poll);
            if (Intent.ACTION_SCREEN_ON.equals(intent.getAction())) {
                // Nach dem Einschalten zeigt der Player sofort den aktuellen Stand.
                unreachableSince = 0;
                worker.post(poll);
            }
        }
    };

    /** Startet den Player, wenn er eingeschaltet und das Zertifikat der Box bestätigt ist. */
    static void start(Context context) {
        if (Box.playerEnabled(context) && Box.pin(context) != null) {
            try {
                context.startForegroundService(new Intent(context, PlayerService.class));
            } catch (IllegalStateException ignored) {
                // Android erlaubt den Start aus dem Hintergrund nicht; beim Öffnen der App erneut.
            }
        }
    }

    static void stop(Context context) {
        context.stopService(new Intent(context, PlayerService.class));
    }

    static void createChannel(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        // 1.3.0 hatte "player" mit niedriger Wichtigkeit: Viele Handys zeigen dafür kein Icon
        // in der Statusleiste. Die Wichtigkeit eines Kanals lässt sich nicht mehr ändern.
        manager.deleteNotificationChannel("player");
        NotificationChannel channel = new NotificationChannel(
                CHANNEL, "Player", NotificationManager.IMPORTANCE_DEFAULT);
        channel.setDescription("Was auf der Phoniebox läuft, mit Zurück, Start/Pause und Weiter");
        channel.setSound(null, null);
        channel.enableVibration(false);
        channel.setShowBadge(false);
        manager.createNotificationChannel(channel);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        manager = getSystemService(NotificationManager.class);
        createChannel(this);
        thread = new HandlerThread("phoniebox-player");
        thread.start();
        worker = new Handler(thread.getLooper());

        session = new MediaSession(this, "Phoniebox");
        session.setSessionActivity(openApp());
        session.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                send("play");
            }

            @Override
            public void onPause() {
                send("pause");
            }

            @Override
            public void onSkipToNext() {
                send("next");
            }

            @Override
            public void onSkipToPrevious() {
                send("previous");
            }

            @Override
            public void onStop() {
                send("pause");
            }
        });
        session.setActive(true);

        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        registerReceiver(screen, filter);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Android verlangt die Benachrichtigung sofort nach dem Start.
        startForeground(ID, build(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        String action = intent == null ? null : intent.getStringExtra(ACTION);
        if (STOP.equals(action)) {
            // Weggewischt: bis zum nächsten Öffnen der App kein Player.
            stopSelf();
        } else if (action != null) {
            send(action);
        } else {
            unreachableSince = 0;
            worker.post(poll);
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        unregisterReceiver(screen);
        worker.removeCallbacksAndMessages(null);
        thread.quitSafely();
        session.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private boolean screenOn() {
        return getSystemService(PowerManager.class).isInteractive();
    }

    /** Befehl an die Box, danach den Player zweimal kurz nacheinander aktualisieren. */
    private void send(String action) {
        worker.post(() -> {
            try {
                Box.command(this, action);
                if ("play".equals(action) || "pause".equals(action)) {
                    // Sofort umschalten, die Box braucht einen Moment für ihren neuen Stand.
                    playing = "play".equals(action);
                    publish(null);
                }
            } catch (Exception e) {
                String message = e.getMessage();
                main.post(() -> Toast.makeText(this, message, Toast.LENGTH_LONG).show());
            }
            worker.removeCallbacks(poll);
            worker.postDelayed(poll, 1_000L);
            worker.postDelayed(this::refresh, 3_000L);
        });
    }

    /** Fragt die Box und aktualisiert Benachrichtigung und Mediensitzung. */
    private void refresh() {
        JSONObject state;
        try {
            state = Box.player(this);
        } catch (Exception e) {
            long now = SystemClock.elapsedRealtime();
            if (unreachableSince == 0) {
                unreachableSince = now;
            } else if (now - unreachableSince > GIVE_UP) {
                stopSelf();
                return;
            }
            playing = false;
            title = "Phoniebox nicht erreichbar";
            text = "Ist das Handy im WLAN der Box?";
            setCover("");
            publish(null);
            return;
        }
        unreachableSince = 0;
        if (!state.optBoolean("active")) {
            playing = false;
            title = "Gerade läuft nichts";
            text = state.optString("message", "Karte auflegen oder Start drücken.");
            setCover("");
            publish(null);
            return;
        }
        playing = state.optBoolean("playing");
        title = state.optString("title", "Ohne Titel");
        text = state.optString("artist", "");
        setCover(state.optString("cover", ""));
        publish(state);
    }

    /** Lädt das Cover nur, wenn es sich geändert hat. Nur Spotify-Bilder, siehe /api/player. */
    private void setCover(String url) {
        if (url.equals(coverUrl)) {
            return;
        }
        coverUrl = url;
        cover = null;
        if (url.startsWith("https://")) {
            try {
                cover = download(url);
            } catch (IOException ignored) {
                // Ohne Cover weiter; beim nächsten Titel neuer Versuch.
            }
        }
    }

    private static Bitmap download(String url) throws IOException {
        HttpsURLConnection connection = (HttpsURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(8000);
        try (InputStream in = connection.getInputStream()) {
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            byte[] buffer = new byte[16384];
            int n;
            while ((n = in.read(buffer)) > 0) {
                body.write(buffer, 0, n);
                if (body.size() > 4 * 1024 * 1024) {
                    throw new IOException("Cover zu groß");
                }
            }
            byte[] bytes = body.toByteArray();
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = 1;
            while (Math.max(bounds.outWidth, bounds.outHeight) / (options.inSampleSize * 2) >= 512) {
                options.inSampleSize *= 2;
            }
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
            if (bitmap == null) {
                throw new IOException("Kein Bild");
            }
            return bitmap;
        } finally {
            connection.disconnect();
        }
    }

    /** Überträgt den Stand in Mediensitzung und Benachrichtigung. */
    private void publish(JSONObject state) {
        MediaMetadata.Builder metadata = new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, text);
        if (cover != null) {
            metadata.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, cover);
        }
        long duration = state == null ? 0 : state.optLong("duration");
        if (duration > 0) {
            metadata.putLong(MediaMetadata.METADATA_KEY_DURATION, duration);
        }
        session.setMetadata(metadata.build());

        long position = state == null ? PlaybackState.PLAYBACK_POSITION_UNKNOWN : state.optLong("progress");
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                        | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
                        | PlaybackState.ACTION_SKIP_TO_PREVIOUS)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        position, playing && duration > 0 ? 1f : 0f)
                .build());
        manager.notify(ID, build());
    }

    private Notification build() {
        Notification.Builder builder = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_bars)
                .setContentTitle(title)
                .setContentText(text)
                .setLargeIcon(cover)
                .setContentIntent(openApp())
                .setDeleteIntent(command(STOP, 9))
                .setOngoing(playing)
                .setShowWhen(false)
                .setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setCategory(Notification.CATEGORY_TRANSPORT)
                .addAction(action(android.R.drawable.ic_media_previous, "Zurück", "previous", 1))
                .addAction(playing
                        ? action(android.R.drawable.ic_media_pause, "Pause", "pause", 2)
                        : action(android.R.drawable.ic_media_play, "Start", "play", 3))
                .addAction(action(android.R.drawable.ic_media_next, "Weiter", "next", 4))
                .setStyle(new Notification.MediaStyle()
                        .setMediaSession(session.getSessionToken())
                        .setShowActionsInCompactView(0, 1, 2));
        return builder.build();
    }

    private Notification.Action action(int icon, String label, String name, int request) {
        return new Notification.Action.Builder(Icon.createWithResource(this, icon), label,
                command(name, request)).build();
    }

    private PendingIntent command(String name, int request) {
        Intent intent = new Intent(this, PlayerService.class).putExtra(ACTION, name);
        return PendingIntent.getForegroundService(this, request, intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private PendingIntent openApp() {
        Intent open = new Intent(this, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
