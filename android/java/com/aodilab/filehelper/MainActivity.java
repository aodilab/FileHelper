package com.aodilab.filehelper;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Display;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.PrintWriter;
import java.io.StringWriter;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String PREFS = "filehelper_prefs";
    private static final String KEY_URL = "server_url";
    private static final String KEY_CID = "device_cid";
    private static final int REQ_FILE_PICK = 1001;

    private final ExecutorService ioPool = Executors.newCachedThreadPool();
    private FrameLayout root;
    private WebView webView;
    private ConnectOverlay connectOverlay;
    private ValueCallback<Uri[]> fileCallback;
    private String activeBaseUrl = "";
    private boolean pageReady = false;
    private boolean lightStatusBar = true;
    private float sysTopDp = 0f;
    private float sysBottomDp = 0f;
    private long lastBackTs = 0L;
    private Intent pendingShareIntent;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            initUi();
        } catch (Throwable t) {
            showFatalFallback(t);
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void initUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#F7F7F7"));
        setContentView(root);
        configureWindow();

        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#EDEDED"));
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setTextZoom(100);
        ws.setAllowFileAccess(true);
        ws.setAllowContentAccess(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setUseWideViewPort(true);
        ws.setLoadWithOverviewMode(true);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        ws.setUserAgentString(ws.getUserAgentString() + " FileHelperAndroid/1.0");
        webView.addJavascriptInterface(new NativeBridge(), "FileHelperAndroid");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pageReady = true;
                injectInsets();
                connectOverlay.setVisibility(View.GONE);
                flushPendingShare();
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req != null && req.isForMainFrame()) {
                    pageReady = false;
                    showConnect("无法连接电脑，请确认电脑端已开启或点下方重新搜索", false, false);
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                recreate();
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = cb;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                try {
                    startActivityForResult(Intent.createChooser(intent, "选择照片、视频或文件"), REQ_FILE_PICK);
                    return true;
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
            }
        });

        webView.setDownloadListener((url, ua, disp, mime, len) ->
                downloadInBackground(url, guessNameFromDisposition(disp, url), mime != null && mime.startsWith("image/") ? "image" : mime != null && mime.startsWith("video/") ? "video" : "file"));

        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        connectOverlay = new ConnectOverlay(this, new ConnectOverlay.Listener() {
            @Override public void onManualConnect(String rawUrl) { tryManualConnect(rawUrl); }
            @Override public void onAutoDiscover() { startBootstrap(false); }
            @Override public void onCancel() {
                if (pageReady) connectOverlay.setVisibility(View.GONE);
            }
        });
        root.addView(connectOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        bindInsets();
        captureShareIntent(getIntent());
        startBootstrap(true);
    }

    private void showFatalFallback(Throwable t) {
        StringWriter sw = new StringWriter();
        t.printStackTrace(new PrintWriter(sw));
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.parseColor("#F7F7F7"));
        TextView tv = new TextView(this);
        int pad = Math.round(20 * getResources().getDisplayMetrics().density);
        tv.setPadding(pad, pad * 2, pad, pad);
        tv.setTextColor(Color.parseColor("#111111"));
        tv.setTextSize(13f);
        tv.setTextIsSelectable(true);
        tv.setText("启动异常，请截图反馈：\n\n" + sw);
        sv.addView(tv);
        setContentView(sv);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        captureShareIntent(intent);
        if (pageReady) flushPendingShare();
    }

    private void configureWindow() {
        try {
            Window w = getWindow();
            if (w == null) return;
            w.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            w.setStatusBarColor(Color.TRANSPARENT);
            w.setNavigationBarColor(Color.TRANSPARENT);
            WindowManager.LayoutParams lp = w.getAttributes();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                w.setStatusBarContrastEnforced(false);
                w.setNavigationBarContrastEnforced(false);
            }
            unlockHighRefreshRate(lp);
            w.setAttributes(lp);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                w.setDecorFitsSystemWindows(false);
            }
            if (root != null) {
                root.post(() -> applyStatusBarAppearance(true));
            } else {
                applyStatusBarAppearance(true);
            }
        } catch (Throwable ignored) {}
    }

    private void unlockHighRefreshRate(WindowManager.LayoutParams lp) {
        try {
            Display display = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                    ? getDisplay() : getWindowManager().getDefaultDisplay();
            if (display == null) return;
            Display.Mode cur = display.getMode();
            if (cur == null) return;
            Display.Mode best = cur;
            for (Display.Mode m : display.getSupportedModes()) {
                if (m.getPhysicalWidth() == cur.getPhysicalWidth()
                        && m.getPhysicalHeight() == cur.getPhysicalHeight()
                        && m.getRefreshRate() > best.getRefreshRate()) {
                    best = m;
                }
            }
            lp.preferredDisplayModeId = best.getModeId();
            lp.preferredRefreshRate = best.getRefreshRate();
        } catch (Throwable ignored) {}
    }

    private void applyStatusBarAppearance(boolean light) {
        try {
            lightStatusBar = light;
            Window w = getWindow();
            if (w == null) return;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                WindowInsetsController ctrl = w.getInsetsController();
                if (ctrl != null) {
                    int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                            | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                    ctrl.setSystemBarsAppearance(light ? mask : 0, mask);
                }
            } else {
                int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION;
                if (light) flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                if (light && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                }
                w.getDecorView().setSystemUiVisibility(flags);
            }
        } catch (Throwable ignored) {}
    }

    private void bindInsets() {
        float density = getResources().getDisplayMetrics().density;
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            try {
                int topPx, padBottom, cssBottomPx;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    int sysTop = insets.getInsets(WindowInsets.Type.statusBars() | WindowInsets.Type.displayCutout()).top;
                    int navBot = insets.getInsets(WindowInsets.Type.navigationBars()).bottom;
                    int tapBot = insets.getInsets(WindowInsets.Type.tappableElement()).bottom;
                    int imeBot = insets.getInsets(WindowInsets.Type.ime()).bottom;
                    topPx = sysTop;
                    if (imeBot > 0) {
                        padBottom = imeBot;
                        cssBottomPx = 0;
                    } else if (tapBot > 0) {
                        padBottom = tapBot;
                        cssBottomPx = 0;
                    } else {
                        padBottom = 0;
                        cssBottomPx = navBot;
                    }
                } else {
                    topPx = insets.getSystemWindowInsetTop();
                    padBottom = insets.getSystemWindowInsetBottom();
                    cssBottomPx = 0;
                }
                root.setPadding(0, 0, 0, padBottom);
                sysTopDp = topPx / density;
                sysBottomDp = cssBottomPx / density;
                injectInsets();
            } catch (Throwable ignored) {}
            return insets;
        });
        root.requestApplyInsets();
    }

    private void injectInsets() {
        if (webView == null) return;
        try {
            String js = "document.documentElement.style.setProperty('--sys-top','" + String.format(java.util.Locale.US, "%.2f", sysTopDp) + "px');"
                    + "document.documentElement.style.setProperty('--sys-bottom','" + String.format(java.util.Locale.US, "%.2f", sysBottomDp) + "px');";
            webView.evaluateJavascript(js, null);
        } catch (Throwable ignored) {}
    }

    private void startBootstrap(boolean trySavedFirst) {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        String saved = sp.getString(KEY_URL, "");
        String builtIn = BuildDefaults.DEFAULT_SERVER_URL;
        showConnect("正在搜索同一 Wi-Fi 下的电脑…", true, false);
        ioPool.execute(() -> {
            if (trySavedFirst && !saved.isEmpty() && LanHelper.pingServer(saved, 650)) {
                runOnUiThread(() -> connectTo(saved));
                return;
            }
            if (trySavedFirst && !builtIn.isEmpty() && !builtIn.equals(saved) && LanHelper.pingServer(builtIn, 650)) {
                sp.edit().putString(KEY_URL, builtIn).apply();
                runOnUiThread(() -> connectTo(builtIn));
                return;
            }
            String found = LanHelper.discoverLanServer();
            if (found != null) {
                sp.edit().putString(KEY_URL, found).apply();
                runOnUiThread(() -> connectTo(found));
                return;
            }
            if (!builtIn.isEmpty() && LanHelper.pingServer(builtIn, 900)) {
                sp.edit().putString(KEY_URL, builtIn).apply();
                runOnUiThread(() -> connectTo(builtIn));
                return;
            }
            runOnUiThread(() -> showConnect("未自动找到电脑，请确认电脑端已开启或手动输入地址", false, pageReady));
        });
    }

    private void tryManualConnect(String raw) {
        String normalized = LanHelper.normalizeBaseUrl(raw);
        if (normalized.isEmpty()) {
            Toast.makeText(this, "请输入有效地址，如 192.168.1.5:8899", Toast.LENGTH_SHORT).show();
            return;
        }
        showConnect("正在连接 " + normalized.replace("http://", "") + "…", true, pageReady);
        ioPool.execute(() -> {
            boolean ok = LanHelper.pingServer(normalized, 1800);
            runOnUiThread(() -> {
                if (ok) {
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_URL, normalized).apply();
                    connectTo(normalized);
                } else {
                    showConnect("连接失败：请确认手机与电脑在同一 Wi-Fi 且电脑端已打开", false, pageReady);
                }
            });
        });
    }

    private void connectTo(String baseUrl) {
        activeBaseUrl = baseUrl;
        connectOverlay.setInputUrl(baseUrl);
        webView.loadUrl(baseUrl + "/");
    }

    private void showConnect(String msg, boolean busy, boolean canCancel) {
        String saved = getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_URL, activeBaseUrl);
        if (saved == null || saved.isEmpty()) saved = BuildDefaults.DEFAULT_SERVER_URL;
        connectOverlay.setState(msg, saved, busy, canCancel);
        connectOverlay.setVisibility(View.VISIBLE);
    }

    private String getDeviceCid() {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        String cid = sp.getString(KEY_CID, "");
        if (cid.isEmpty()) {
            cid = "android_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
            sp.edit().putString(KEY_CID, cid).apply();
        }
        return cid;
    }

    private void captureShareIntent(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        if (Intent.ACTION_SEND.equals(action) || Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            pendingShareIntent = new Intent(intent);
        }
    }

    private void flushPendingShare() {
        if (pendingShareIntent == null || activeBaseUrl.isEmpty()) return;
        Intent intent = pendingShareIntent;
        pendingShareIntent = null;
        String action = intent.getAction();
        String cid = getDeviceCid();
        Toast.makeText(this, "正在发送分享内容…", Toast.LENGTH_SHORT).show();
        ioPool.execute(() -> {
            int ok = 0, total = 0;
            if (Intent.ACTION_SEND.equals(action)) {
                Uri stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
                String text = intent.getStringExtra(Intent.EXTRA_TEXT);
                if (stream != null) {
                    total = 1;
                    if (LanHelper.uploadUri(this, activeBaseUrl, stream, cid)) ok = 1;
                } else if (text != null && !text.trim().isEmpty()) {
                    total = 1;
                    if (LanHelper.sendText(activeBaseUrl, text.trim(), cid)) ok = 1;
                }
            } else if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
                List<Uri> uris = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
                if (uris != null) {
                    total = uris.size();
                    for (Uri u : uris) {
                        if (u != null && LanHelper.uploadUri(this, activeBaseUrl, u, cid)) ok++;
                    }
                }
            }
            int finalOk = ok, finalTotal = total;
            runOnUiThread(() -> {
                if (finalTotal > 0) {
                    Toast.makeText(this, finalOk == finalTotal ? "已发送至文件传输助手" : "已发送 " + finalOk + "/" + finalTotal, Toast.LENGTH_SHORT).show();
                    if (webView != null) webView.evaluateJavascript("window.__refreshFromNative && window.__refreshFromNative();", null);
                }
            });
        });
    }

    private void downloadInBackground(String url, String name, String kind) {
        runOnUiThread(() -> Toast.makeText(this, "正在保存…", Toast.LENGTH_SHORT).show());
        ioPool.execute(() -> {
            try {
                String msg = LanHelper.saveMedia(this, url, name, kind);
                runOnUiThread(() -> Toast.makeText(this, msg, Toast.LENGTH_SHORT).show());
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "保存失败：" + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        });
    }

    private static String guessNameFromDisposition(String disp, String url) {
        if (disp != null) {
            int idx = disp.indexOf("filename=");
            if (idx >= 0) {
                String s = disp.substring(idx + 9).replace("\"", "").trim();
                int semi = s.indexOf(';');
                if (semi > 0) s = s.substring(0, semi).trim();
                if (!s.isEmpty()) return s;
            }
        }
        String seg = Uri.parse(url).getLastPathSegment();
        return seg != null && !seg.isEmpty() ? seg : "file.bin";
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_FILE_PICK && fileCallback != null) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null) {
                ClipData clip = data.getClipData();
                if (clip != null && clip.getItemCount() > 0) {
                    List<Uri> uris = new ArrayList<>();
                    for (int i = 0; i < clip.getItemCount(); i++) {
                        Uri u = clip.getItemAt(i).getUri();
                        if (u != null) uris.add(u);
                    }
                    result = uris.toArray(new Uri[0]);
                } else if (data.getData() != null) {
                    result = new Uri[]{data.getData()};
                }
            }
            fileCallback.onReceiveValue(result);
            fileCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (connectOverlay.getVisibility() == View.VISIBLE && pageReady) {
            connectOverlay.setVisibility(View.GONE);
            return;
        }
        if (webView != null && pageReady) {
            webView.evaluateJavascript("window.__handleAndroidBack ? window.__handleAndroidBack() : false;", val -> {
                if ("true".equals(val)) return;
                long now = System.currentTimeMillis();
                if (now - lastBackTs < 2000) {
                    finish();
                } else {
                    lastBackTs = now;
                    Toast.makeText(this, "再按一次退出", Toast.LENGTH_SHORT).show();
                }
            });
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        ioPool.shutdownNow();
        if (webView != null) webView.destroy();
    }

    private final class NativeBridge {
        @JavascriptInterface
        public void saveMedia(String url, String name, String kind) {
            downloadInBackground(url, name, kind);
        }

        @JavascriptInterface
        public void copyText(String text) {
            runOnUiThread(() -> {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("FileHelper", text == null ? "" : text));
            });
        }

        @JavascriptInterface
        public void setLightStatusBar(boolean light) {
            runOnUiThread(() -> {
                if (light != lightStatusBar) applyStatusBarAppearance(light);
            });
        }

        @JavascriptInterface
        public void openConnect() {
            runOnUiThread(() -> showConnect("当前已连 " + activeBaseUrl.replace("http://", ""), false, true));
        }

        @JavascriptInterface
        public String getDeviceCid() {
            return MainActivity.this.getDeviceCid();
        }
    }
}
