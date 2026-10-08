package de.phoniebox.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Adresse, Zertifikat und Statusabfrage der Phoniebox.
 *
 * Die Box hat ein selbst erzeugtes Zertifikat für phoniebox.local. Beim ersten Öffnen bestätigt
 * der Nutzer dessen SHA-256-Fingerabdruck; danach vertraut die App genau diesem Zertifikat und
 * sonst keinem (Zertifikat-Pinning statt "alles akzeptieren").
 */
final class Box {
    static final String HOST = "phoniebox.local";
    static final String URL = "https://" + HOST + "/";

    private static final String PREFS = "phoniebox";
    private static final String PIN = "certificate_sha256";
    static final String NOTIFY = "notify";
    static final String PLAYER = "player";

    /** Sitzungs-Cookie und CSRF-Token der Box für Befehle aus der Benachrichtigung. */
    private static final Map<String, String> COOKIES = new HashMap<>();
    private static volatile String csrf;

    private Box() {
    }

    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static String pin(Context context) {
        return prefs(context).getString(PIN, null);
    }

    static void setPin(Context context, String fingerprint) {
        prefs(context).edit().putString(PIN, fingerprint).apply();
    }

    static void clearPin(Context context) {
        prefs(context).edit().remove(PIN).apply();
    }

    static boolean notificationsEnabled(Context context) {
        return prefs(context).getBoolean(NOTIFY, true);
    }

    static boolean playerEnabled(Context context) {
        return prefs(context).getBoolean(PLAYER, true);
    }

    /** SHA-256 im Format von "openssl x509 -fingerprint -sha256" (AB:CD:...). */
    static String fingerprint(X509Certificate certificate) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded());
            StringBuilder text = new StringBuilder();
            for (byte b : digest) {
                if (text.length() > 0) {
                    text.append(':');
                }
                text.append(String.format("%02X", b));
            }
            return text.toString();
        } catch (GeneralSecurityException e) {
            return "";
        }
    }

    /** GET /api/notifications. Wirft IOException, wenn die Box nicht erreichbar ist. */
    static JSONObject status(Context context) throws IOException, JSONException {
        return get(context, "api/notifications", " (App auf dem Pi älter als 1.20.0?)");
    }

    /** GET /api/player: was gerade läuft, mit Cover, Fortschritt und Lautstärke. */
    static JSONObject player(Context context) throws IOException, JSONException {
        return get(context, "api/player", "");
    }

    /**
     * POST /api/player/&lt;action&gt; (play, pause, next, previous). Die Box verlangt dafür das
     * CSRF-Token ihrer Sitzung, das die App über GET /api/csrf holt (ab App 1.22.0 auf dem Pi).
     * Wirft IOException mit der Meldung der Box, etwa "Bluetooth-Lautsprecher ist noch nicht verbunden".
     */
    static void command(Context context, String action) throws IOException, JSONException {
        for (int attempt = 0; ; attempt++) {
            String token = csrf;
            if (token == null) {
                token = get(context, "api/csrf", " (App auf dem Pi älter als 1.22.0?)").getString("csrf");
                csrf = token;
            }
            HttpsURLConnection connection = open(context, "api/player/" + action);
            try {
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setRequestProperty("X-CSRF-Token", token);
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(new byte[0]);
                }
                int code = connection.getResponseCode();
                remember(connection);
                if (code == 403 && attempt == 0) {
                    // Sitzung abgelaufen, etwa nach einem Neustart der Box: neues Token holen.
                    csrf = null;
                    continue;
                }
                if (code != 200) {
                    String message;
                    try {
                        message = new JSONObject(read(connection.getErrorStream())).optString("error");
                    } catch (IOException | JSONException e) {
                        message = "";
                    }
                    throw new IOException(message.isEmpty() ? "Phoniebox antwortet mit HTTP " + code : message);
                }
                return;
            } finally {
                connection.disconnect();
            }
        }
    }

    private static JSONObject get(Context context, String path, String hint404) throws IOException, JSONException {
        HttpsURLConnection connection = open(context, path);
        try {
            connection.setRequestProperty("Accept", "application/json");
            int code = connection.getResponseCode();
            remember(connection);
            if (code != 200) {
                throw new IOException("Phoniebox antwortet mit HTTP " + code + (code == 404 ? hint404 : ""));
            }
            return new JSONObject(read(connection.getInputStream()));
        } finally {
            connection.disconnect();
        }
    }

    /** Verbindung zur Box mit gepinntem Zertifikat und dem Sitzungs-Cookie der App. */
    private static HttpsURLConnection open(Context context, String path) throws IOException {
        String pin = pin(context);
        if (pin == null) {
            throw new IOException("Die App einmal öffnen und das Zertifikat der Phoniebox bestätigen.");
        }
        HttpsURLConnection connection = (HttpsURLConnection) new URL(URL + path).openConnection();
        try {
            SSLContext tls = SSLContext.getInstance("TLS");
            tls.init(null, new TrustManager[]{new PinnedTrust(pin)}, null);
            connection.setSSLSocketFactory(tls.getSocketFactory());
        } catch (GeneralSecurityException e) {
            throw new IOException(e);
        }
        // Das gepinnte Zertifikat weist die Box aus; der Name muss trotzdem stimmen.
        connection.setHostnameVerifier((hostname, session) -> HOST.equals(hostname));
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(8000);
        synchronized (COOKIES) {
            if (!COOKIES.isEmpty()) {
                StringBuilder header = new StringBuilder();
                for (Map.Entry<String, String> cookie : COOKIES.entrySet()) {
                    if (header.length() > 0) {
                        header.append("; ");
                    }
                    header.append(cookie.getKey()).append('=').append(cookie.getValue());
                }
                connection.setRequestProperty("Cookie", header.toString());
            }
        }
        return connection;
    }

    /** Merkt sich die Cookies der Box; nur die Sitzung, für die das CSRF-Token gilt. */
    private static void remember(HttpsURLConnection connection) {
        synchronized (COOKIES) {
            for (Map.Entry<String, List<String>> field : connection.getHeaderFields().entrySet()) {
                if ("Set-Cookie".equalsIgnoreCase(field.getKey())) {
                    for (String header : field.getValue()) {
                        store(header);
                    }
                }
            }
        }
    }

    private static void store(String header) {
        String pair = header.split(";", 2)[0];
        int equals = pair.indexOf('=');
        if (equals > 0) {
            COOKIES.put(pair.substring(0, equals).trim(), pair.substring(equals + 1).trim());
            csrf = null;
        }
    }

    private static String read(InputStream stream) throws IOException {
        if (stream == null) {
            throw new IOException("Leere Antwort");
        }
        try (InputStream in = stream) {
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) > 0 && body.size() < 65536) {
                body.write(buffer, 0, n);
            }
            return body.toString(StandardCharsets.UTF_8.name());
        }
    }

    private static final class PinnedTrust implements X509TrustManager {
        private final String pin;

        PinnedTrust(String pin) {
            this.pin = pin;
        }

        @Override
        public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            throw new CertificateException("Keine Client-Zertifikate");
        }

        @Override
        public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            if (chain == null || chain.length == 0 || !pin.equals(fingerprint(chain[0]))) {
                throw new CertificateException("Zertifikat der Phoniebox hat sich geändert");
            }
        }

        @Override
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
    }
}
