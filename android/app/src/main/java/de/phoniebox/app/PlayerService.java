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
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.widget.RemoteViews;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

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
    private static final String STATE = "player_state";
    /** true, solange der Dienst mit sichtbarer Benachrichtigung läuft. */
    static volatile boolean running;
    private static final long FAST = 5_000L;
    private static final long SLOW = 15_000L;
    private static final long GIVE_UP = 2 * 60_000L;

    private final Handler main = new Handler(Looper.getMainLooper());
    private HandlerThread thread;
    private Handler worker;
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
        if (!Box.playerEnabled(context)) {
            note(context, "ausgeschaltet");
        } else if (Box.pin(context) == null) {
            note(context, "wartet auf das bestätigte Zertifikat der Box");
        } else {
            try {
                context.startForegroundService(new Intent(context, PlayerService.class));
            } catch (RuntimeException e) {
                // Etwa: Android erlaubt den Start aus dem Hintergrund nicht; beim Öffnen der App erneut.
                note(context, "Start von Android abgelehnt: " + e);
            }
        }
    }

    /** Merkt sich, was der Player zuletzt getan hat, für die Diagnose in Menü und Seitenleiste. */
    static void note(Context context, String state) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.GERMANY).format(new Date());
        Box.prefs(context).edit().putString(STATE, time + " " + state).apply();
    }

    /** Ob Android die Player-Benachrichtigung gerade führt. */
    static boolean visible(Context context) {
        for (android.service.notification.StatusBarNotification n
                : context.getSystemService(NotificationManager.class).getActiveNotifications()) {
            if (n.getId() == ID) {
                return true;
            }
        }
        return false;
    }

    /** Alles, was bestimmt, ob der Player zu sehen ist. */
    static String diagnosis(Context context) {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        NotificationChannel channel = manager.getNotificationChannel(CHANNEL);
        String permission = Build.VERSION.SDK_INT < 33 ? "nicht nötig (vor Android 13)"
                : context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                == android.content.pm.PackageManager.PERMISSION_GRANTED ? "erteilt" : "nicht erteilt";
        return "Android " + Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT + "), "
                + Build.MANUFACTURER + " " + Build.MODEL
                + "\nBenachrichtigungen erlaubt: " + (manager.areNotificationsEnabled() ? "ja" : "nein")
                + "\nBerechtigung: " + permission
                + "\nKanal „Player“: " + (channel == null ? "fehlt"
                : channel.getImportance() == NotificationManager.IMPORTANCE_NONE ? "ausgeschaltet"
                : "an (Wichtigkeit " + channel.getImportance() + ")")
                + "\nPlayer eingeschaltet: " + (Box.playerEnabled(context) ? "ja" : "nein")
                + "\nDienst läuft: " + (running ? "ja" : "nein")
                + "\nBenachrichtigung aktiv: " + (visible(context) ? "ja" : "nein")
                + "\nZuletzt: " + Box.prefs(context).getString(STATE, "noch nie gestartet");
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


        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        registerReceiver(screen, filter);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Android verlangt die Benachrichtigung sofort nach dem Start.
        try {
            startForeground(ID, build(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } catch (RuntimeException e) {
            note(this, "Benachrichtigung von Android abgelehnt: " + e);
            stopSelf();
            return START_NOT_STICKY;
        }
        running = true;
        note(this, "läuft, Benachrichtigung gezeigt");
        String action = intent == null ? null : intent.getStringExtra(ACTION);
        if (STOP.equals(action)) {
            // Weggewischt: bis zum nächsten Öffnen der App kein Player.
            note(this, "weggewischt, kommt beim nächsten Öffnen der App wieder");
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
        running = false;
        unregisterReceiver(screen);
        worker.removeCallbacksAndMessages(null);
        thread.quitSafely();
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

    /** Fragt die Box und aktualisiert die Benachrichtigung. */
    private void refresh() {
        JSONObject state;
        try {
            state = Box.player(this);
        } catch (Exception e) {
            long now = SystemClock.elapsedRealtime();
            if (unreachableSince == 0) {
                unreachableSince = now;
            } else if (now - unreachableSince > GIVE_UP) {
                note(this, "beendet, Box 2 Minuten nicht erreichbar: " + e.getMessage());
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
            while (Math.max(bounds.outWidth, bounds.outHeight) / (options.inSampleSize * 2) >= 192) {
                options.inSampleSize *= 2;
            }
            Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
            if (bitmap == null) {
                throw new IOException("Kein Bild");
            }
            // Klein halten: Das Bild reist zweimal (ein- und ausgeklappt) zur Systemoberfläche.
            int size = Math.max(bitmap.getWidth(), bitmap.getHeight());
            if (size > 192) {
                bitmap = Bitmap.createScaledBitmap(bitmap, bitmap.getWidth() * 192 / size,
                        bitmap.getHeight() * 192 / size, true);
            }
            return bitmap;
        } finally {
            connection.disconnect();
        }
    }

    /** Fortschritt in Promille, für den Balken im ausgeklappten Player. */
    private volatile int progress;

    /** Überträgt den Stand in die Benachrichtigung. */
    private void publish(JSONObject state) {
        long duration = state == null ? 0 : state.optLong("duration");
        progress = duration > 0 ? (int) Math.min(1000, state.optLong("progress") * 1000 / duration) : 0;
        manager.notify(ID, build());
    }

    /**
     * Eine gewöhnliche Benachrichtigung mit eigenem Layout statt Android-Mediensteuerung:
     * Samsung (One UI) zeigt die Mediensitzung einer App, die selbst nichts abspielt, nirgends an,
     * und die Mediensitzung würde außerdem Kopfhörertasten statt Spotify auf dem Handy bekommen.
     */
    private Notification build() {
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_bars)
                .setContentTitle(title)
                .setContentText(text)
                .setCustomContentView(controls(R.layout.player_small))
                .setCustomBigContentView(controls(R.layout.player_big))
                .setStyle(new Notification.DecoratedCustomViewStyle())
                .setContentIntent(openApp())
                .setDeleteIntent(command(STOP, 9))
                .setOngoing(playing)
                .setShowWhen(false)
                .setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setCategory(Notification.CATEGORY_TRANSPORT)
                .build();
    }

    private RemoteViews controls(int layout) {
        RemoteViews views = new RemoteViews(getPackageName(), layout);
        views.setTextViewText(R.id.title, title);
        views.setTextViewText(R.id.artist, text);
        Bitmap image = cover;
        if (image != null) {
            views.setImageViewBitmap(R.id.cover, image);
        } else {
            views.setImageViewResource(R.id.cover, R.drawable.ic_cover);
        }
        views.setImageViewResource(R.id.play, playing ? R.drawable.ic_pause : R.drawable.ic_play);
        views.setContentDescription(R.id.play, playing ? "Pause" : "Start");
        views.setOnClickPendingIntent(R.id.prev, command("previous", 1));
        views.setOnClickPendingIntent(R.id.play, playing ? command("pause", 2) : command("play", 3));
        views.setOnClickPendingIntent(R.id.next, command("next", 4));
        if (layout == R.layout.player_big) {
            views.setProgressBar(R.id.progress, 1000, progress, false);
        }
        return views;
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
