package de.phoniebox.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.security.cert.X509Certificate;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Zeigt die Weboberfläche der Phoniebox und gleicht dabei die Benachrichtigungen ab. */
public class MainActivity extends Activity {
    /** Solange die App offen ist, so oft nachsehen. */
    private static final long FOREGROUND_INTERVAL = 30_000L;

    private static final int MENU_RELOAD = 1;
    private static final int MENU_CHECK = 2;
    private static final int MENU_NOTIFY = 3;
    private static final int MENU_CERTIFICATE = 4;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService background = Executors.newSingleThreadExecutor();
    private WebView web;
    private View errorPanel;
    private TextView errorText;
    private boolean failed;
    private AlertDialog certificateDialog;

    private final Runnable poll = new Runnable() {
        @Override
        public void run() {
            check(false);
            handler.postDelayed(this, FOREGROUND_INTERVAL);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Notifier.createChannel(this);
        if (Box.notificationsEnabled(this)) {
            StatusJob.schedule(this);
            askForNotificationPermission();
        }

        FrameLayout root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        errorPanel = buildErrorPanel();
        errorPanel.setVisibility(View.GONE);
        root.addView(errorPanel, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        // Ohne WebChromeClient liefert confirm() in der Weboberfläche stumm "false".
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new BoxClient());

        if (state != null) {
            web.restoreState(state);
        }
        if (web.getUrl() == null) {
            web.loadUrl(Box.URL);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        web.saveState(state);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        handler.post(poll);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(poll);
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        background.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(Menu.NONE, MENU_RELOAD, 1, "Neu laden");
        menu.add(Menu.NONE, MENU_CHECK, 2, "Status jetzt prüfen");
        menu.add(Menu.NONE, MENU_NOTIFY, 3, "Benachrichtigungen").setCheckable(true);
        menu.add(Menu.NONE, MENU_CERTIFICATE, 4, "Zertifikat neu bestätigen");
        return true;
    }

    @Override
    public boolean onPrepareOptionsMenu(Menu menu) {
        menu.findItem(MENU_NOTIFY).setChecked(Box.notificationsEnabled(this));
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case MENU_RELOAD:
                reload();
                return true;
            case MENU_CHECK:
                check(true);
                return true;
            case MENU_NOTIFY:
                boolean enable = !Box.notificationsEnabled(this);
                Box.prefs(this).edit().putBoolean(Box.NOTIFY, enable).apply();
                if (enable) {
                    StatusJob.schedule(this);
                    askForNotificationPermission();
                    check(false);
                } else {
                    StatusJob.cancel(this);
                    Notifier.clear(this);
                }
                Toast.makeText(this, enable ? "Benachrichtigungen an" : "Benachrichtigungen aus",
                        Toast.LENGTH_SHORT).show();
                return true;
            case MENU_CERTIFICATE:
                Box.clearPin(this);
                web.clearSslPreferences();
                reload();
                return true;
            default:
                return super.onOptionsItemSelected(item);
        }
    }

    private void reload() {
        if (web.getUrl() == null || !Box.HOST.equals(Uri.parse(web.getUrl()).getHost())) {
            web.loadUrl(Box.URL);
        } else {
            web.reload();
        }
    }

    private void askForNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
    }

    /** Fragt /api/notifications ab; mit report=true meldet ein Toast das Ergebnis. */
    private void check(boolean report) {
        if (Box.pin(this) == null) {
            if (report) {
                Toast.makeText(this, "Erst die Weboberfläche laden und das Zertifikat bestätigen.",
                        Toast.LENGTH_LONG).show();
            }
            return;
        }
        background.execute(() -> {
            String result;
            try {
                JSONObject status = Box.status(this);
                int problems = Notifier.apply(this, status);
                result = problems == 0 ? "Alles in Ordnung."
                        : problems == 1 ? "1 Problem, siehe Benachrichtigung."
                        : problems + " Probleme, siehe Benachrichtigungen.";
            } catch (Exception e) {
                result = "Phoniebox nicht erreichbar: " + e.getMessage();
            }
            if (report) {
                String message = result;
                runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_LONG).show());
            }
        });
    }

    private View buildErrorPanel() {
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(pad, pad, pad, pad);
        panel.setBackgroundColor(Color.parseColor("#F4F6F4"));
        TextView title = new TextView(this);
        title.setText("Phoniebox nicht erreichbar");
        title.setTextSize(22);
        title.setTextColor(Color.parseColor("#203630"));
        title.setGravity(Gravity.CENTER);
        errorText = new TextView(this);
        errorText.setTextColor(Color.parseColor("#62756B"));
        errorText.setGravity(Gravity.CENTER);
        errorText.setPadding(0, pad / 2, 0, pad);
        Button retry = new Button(this);
        retry.setText("Erneut versuchen");
        retry.setOnClickListener(v -> reload());
        panel.addView(title);
        panel.addView(errorText);
        panel.addView(retry);
        return panel;
    }

    private void showError(String detail) {
        failed = true;
        errorText.setText("Ist das Handy im selben WLAN wie die Box und die Box eingeschaltet?\n\n"
                + Box.URL + "\n" + detail);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void askToTrust(SslErrorHandler ssl, String fingerprint, boolean changed) {
        if (certificateDialog != null && certificateDialog.isShowing()) {
            ssl.cancel();
            return;
        }
        String message = (changed
                ? "Das Zertifikat der Phoniebox hat sich geändert. Das ist normal nach einer "
                + "Neuinstallation der Box. Sonst nicht bestätigen.\n\n"
                : "Die Box nutzt ein eigenes Zertifikat. Der Fingerabdruck steht am Ende der "
                + "Installation und lässt sich auf dem Pi mit\n"
                + "openssl x509 -in /etc/phoniebox/tls.crt -noout -fingerprint -sha256\n"
                + "anzeigen.\n\n")
                + "SHA-256:\n" + fingerprint;
        certificateDialog = new AlertDialog.Builder(this)
                .setTitle(changed ? "Neues Zertifikat" : "Phoniebox vertrauen?")
                .setMessage(message)
                .setCancelable(false)
                .setPositiveButton("Vertrauen", (d, w) -> {
                    Box.setPin(this, fingerprint);
                    ssl.proceed();
                    check(false);
                })
                .setNegativeButton("Abbrechen", (d, w) -> {
                    ssl.cancel();
                    showError("Zertifikat nicht bestätigt.");
                })
                .show();
    }

    private final class BoxClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            if (Box.HOST.equals(url.getHost()) && "https".equals(url.getScheme())) {
                return false;
            }
            // Spotify-Links und alles andere im Browser bzw. in der Spotify-App öffnen.
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, url));
            } catch (ActivityNotFoundException ignored) {
                // Nichts installiert, das den Link öffnen kann.
            }
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            failed = false;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (!failed) {
                errorPanel.setVisibility(View.GONE);
            }
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showError(String.valueOf(error.getDescription()));
            }
        }

        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler ssl, SslError error) {
            X509Certificate certificate = error.getCertificate().getX509Certificate();
            if (certificate == null || !Box.HOST.equals(Uri.parse(error.getUrl()).getHost())) {
                ssl.cancel();
                return;
            }
            String fingerprint = Box.fingerprint(certificate);
            String pin = Box.pin(MainActivity.this);
            if (fingerprint.equals(pin)) {
                ssl.proceed();
            } else {
                askToTrust(ssl, fingerprint, pin != null);
            }
        }
    }
}
