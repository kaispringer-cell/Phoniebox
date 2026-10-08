package de.phoniebox.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/**
 * Macht aus der Antwort von /api/notifications Android-Benachrichtigungen.
 *
 * Jedes Problem hat eine feste ID (bluetooth, audio, player, reader, spotify) und einen
 * Zeitpunkt "since". Eine Benachrichtigung erscheint einmal, wenn ein Problem neu auftritt,
 * und verschwindet, sobald die Box es nicht mehr meldet. Wischt man sie weg, kommt sie erst
 * beim nächsten Auftreten wieder.
 */
final class Notifier {
    static final String CHANNEL = "status";
    private static final String ACTIVE = "active";
    private static final int ID = 1;

    private Notifier() {
    }

    static void createChannel(Context context) {
        NotificationChannel channel = new NotificationChannel(
                CHANNEL, "Probleme der Phoniebox", NotificationManager.IMPORTANCE_DEFAULT);
        channel.setDescription("Zum Beispiel: Bluetooth nicht verbunden, NFC-Reader nicht bereit");
        context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    /** Gleicht die Benachrichtigungen mit dem Stand der Box ab. Gibt die Zahl der Probleme zurück. */
    static synchronized int apply(Context context, JSONObject status) throws JSONException {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        JSONArray list = status.getJSONArray("notifications");
        String box = status.optString("name", "Phoniebox");
        Set<String> previous = new HashSet<>(
                Box.prefs(context).getStringSet(ACTIVE, Collections.emptySet()));
        Set<String> current = new HashSet<>();
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < list.length(); i++) {
            JSONObject problem = list.getJSONObject(i);
            String id = problem.getString("id");
            ids.add(id);
            current.add(id + "@" + problem.optLong("since"));
        }
        for (String key : previous) {
            String id = key.substring(0, key.lastIndexOf('@'));
            if (!ids.contains(id)) {
                manager.cancel(id, ID);
            }
        }
        boolean enabled = Box.notificationsEnabled(context);
        for (int i = 0; i < list.length(); i++) {
            JSONObject problem = list.getJSONObject(i);
            String id = problem.getString("id");
            if (enabled && !previous.contains(id + "@" + problem.optLong("since"))) {
                manager.notify(id, ID, build(context, box, problem));
            }
        }
        Box.prefs(context).edit().putStringSet(ACTIVE, current).apply();
        return list.length();
    }

    static synchronized void clear(Context context) {
        context.getSystemService(NotificationManager.class).cancelAll();
        Box.prefs(context).edit().remove(ACTIVE).apply();
    }

    private static Notification build(Context context, String box, JSONObject problem) {
        Intent open = new Intent(context, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent tap = PendingIntent.getActivity(
                context, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        String text = problem.optString("text");
        return new Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_bars)
                .setContentTitle(problem.optString("title", "Phoniebox"))
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setSubText(box)
                .setWhen(problem.optLong("since") * 1000)
                .setShowWhen(true)
                .setContentIntent(tap)
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_STATUS)
                .build();
    }
}
