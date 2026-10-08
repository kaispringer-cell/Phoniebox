package de.phoniebox.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;

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
        String pin = pin(context);
        if (pin == null) {
            throw new IOException("Die App einmal öffnen und das Zertifikat der Phoniebox bestätigen.");
        }
        HttpsURLConnection connection = (HttpsURLConnection) new URL(URL + "api/notifications").openConnection();
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
        connection.setRequestProperty("Accept", "application/json");
        try {
            int code = connection.getResponseCode();
            if (code != 200) {
                throw new IOException("Phoniebox antwortet mit HTTP " + code
                        + (code == 404 ? " (App auf dem Pi älter als 1.20.0?)" : ""));
            }
            try (InputStream in = connection.getInputStream()) {
                ByteArrayOutputStream body = new ByteArrayOutputStream();
                byte[] buffer = new byte[4096];
                int n;
                while ((n = in.read(buffer)) > 0 && body.size() < 65536) {
                    body.write(buffer, 0, n);
                }
                return new JSONObject(body.toString(StandardCharsets.UTF_8.name()));
            }
        } finally {
            connection.disconnect();
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
