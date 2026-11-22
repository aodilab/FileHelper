package com.aodilab.filehelper;

import android.app.DownloadManager;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.res.AssetFileDescriptor;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;
import java.util.LinkedHashSet;
import java.util.Set;

final class LanHelper {
    private static final int DEFAULT_PORT = 8899;

    static String normalizeBaseUrl(String raw) {
        if (raw == null) return "";
        String s = raw.trim();
        if (s.isEmpty()) return "";
        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            s = "http://" + s;
        }
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        try {
            URL u = new URL(s);
            int p = u.getPort();
            String host = u.getHost();
            if (host == null || host.isEmpty()) return "";
            if (p <= 0 && !s.substring(u.getProtocol().length() + 3).contains(":")) {
                return u.getProtocol() + "://" + host + ":" + DEFAULT_PORT;
            }
            return u.getProtocol() + "://" + host + (p > 0 ? ":" + p : "");
        } catch (Exception e) {
            return "";
        }
    }

    static boolean pingServer(String baseUrl, int timeoutMs) {
        if (baseUrl == null || baseUrl.isEmpty()) return false;
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(baseUrl + "/api/ping?probe=1").openConnection();
            conn.setConnectTimeout(timeoutMs);
            conn.setReadTimeout(timeoutMs);
            conn.setRequestProperty("User-Agent", "FileHelper-Android");
            if (conn.getResponseCode() != 200) return false;
            try (BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
                JSONObject obj = new JSONObject(sb.toString());
                return "FileHelper".equals(obj.optString("app"));
            }
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    static String discoverLanServer() {
        byte[] probe = "FILEHELPER_DISCOVER".getBytes(StandardCharsets.UTF_8);
        Set<InetAddress> targets = new LinkedHashSet<>();
        try {
            Enumeration<NetworkInterface> ifaces = NetworkInterface.getNetworkInterfaces();
            while (ifaces != null && ifaces.hasMoreElements()) {
                NetworkInterface ni = ifaces.nextElement();
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    if (ia.getAddress() instanceof Inet4Address && ia.getBroadcast() != null) {
                        targets.add(ia.getBroadcast());
                    }
                }
            }
        } catch (Exception ignored) {}
        try {
            targets.add(InetAddress.getByName("255.255.255.255"));
        } catch (Exception ignored) {}

        try (DatagramSocket sock = new DatagramSocket()) {
            sock.setBroadcast(true);
            sock.setSoTimeout(600);
            byte[] buf = new byte[512];
            for (int round = 0; round < 2; round++) {
                for (InetAddress addr : targets) {
                    try {
                        sock.send(new DatagramPacket(probe, probe.length, addr, DEFAULT_PORT));
                    } catch (Exception ignored) {}
                }
                long deadline = System.currentTimeMillis() + 650;
                while (System.currentTimeMillis() < deadline) {
                    try {
                        DatagramPacket resp = new DatagramPacket(buf, buf.length);
                        sock.receive(resp);
                        String json = new String(resp.getData(), 0, resp.getLength(), StandardCharsets.UTF_8).trim();
                        JSONObject obj = new JSONObject(json);
                        if ("FileHelper".equals(obj.optString("app"))) {
                            int port = obj.optInt("port", DEFAULT_PORT);
                            String srcIp = resp.getAddress().getHostAddress();
                            String candidate = "http://" + srcIp + ":" + port;
                            if (pingServer(candidate, 800)) return candidate;
                            String host = obj.optString("host", "");
                            if (!host.isEmpty()) {
                                String alt = "http://" + host + ":" + port;
                                if (pingServer(alt, 800)) return alt;
                            }
                        }
                    } catch (Exception ignored) {
                        break;
                    }
                }
            }
        } catch (Exception ignored) {}
        return null;
    }

    static String guessMime(String name, String kind, String headerMime) {
        if (headerMime != null && !headerMime.isEmpty() && !"application/octet-stream".equalsIgnoreCase(headerMime)) {
            int semi = headerMime.indexOf(';');
            return semi > 0 ? headerMime.substring(0, semi).trim() : headerMime.trim();
        }
        int dot = name != null ? name.lastIndexOf('.') : -1;
        if (dot >= 0 && dot + 1 < name.length()) {
            String ext = name.substring(dot + 1).toLowerCase();
            String guessed = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
            if (guessed != null && !guessed.isEmpty()) return guessed;
        }
        if ("image".equals(kind)) return "image/jpeg";
        if ("video".equals(kind)) return "video/mp4";
        return "application/octet-stream";
    }

    static String saveMedia(Context ctx, String urlStr, String fileName, String kind) throws Exception {
        String safeName = (fileName == null || fileName.trim().isEmpty())
                ? ("image".equals(kind) ? "image.png" : "video".equals(kind) ? "video.mp4" : "file.bin")
                : fileName.trim().replace("/", "_").replace("\\", "_");

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
            if (dm != null) {
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(urlStr));
                req.setTitle(safeName);
                req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                String dir = "image".equals(kind) ? Environment.DIRECTORY_PICTURES
                        : "video".equals(kind) ? Environment.DIRECTORY_MOVIES : Environment.DIRECTORY_DOWNLOADS;
                req.setDestinationInExternalPublicDir(dir, safeName);
                dm.enqueue(req);
                return "image".equals(kind) || "video".equals(kind) ? "已开始保存到相册" : "已开始下载到本地";
            }
        }

        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(30000);
        conn.setRequestProperty("User-Agent", "FileHelper-Android");
        int code = conn.getResponseCode();
        if (code != 200) {
            conn.disconnect();
            throw new IllegalStateException("HTTP " + code);
        }

        String mime = guessMime(safeName, kind, conn.getContentType());
        ContentResolver cr = ctx.getContentResolver();
        Uri collection;
        String relPath;
        String doneMsg;
        if ("image".equals(kind)) {
            collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
            relPath = Environment.DIRECTORY_PICTURES + "/FileHelper";
            doneMsg = "已保存到相册";
        } else if ("video".equals(kind)) {
            collection = MediaStore.Video.Media.EXTERNAL_CONTENT_URI;
            relPath = Environment.DIRECTORY_MOVIES + "/FileHelper";
            doneMsg = "视频已保存到相册";
        } else {
            collection = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
            relPath = Environment.DIRECTORY_DOWNLOADS + "/FileHelper";
            doneMsg = "已保存到「下载/FileHelper」";
        }

        ContentValues cv = new ContentValues();
        cv.put(MediaStore.MediaColumns.DISPLAY_NAME, safeName);
        cv.put(MediaStore.MediaColumns.MIME_TYPE, mime);
        cv.put(MediaStore.MediaColumns.RELATIVE_PATH, relPath);
        cv.put(MediaStore.MediaColumns.IS_PENDING, 1);

        Uri itemUri = cr.insert(collection, cv);
        if (itemUri == null) {
            conn.disconnect();
            throw new IllegalStateException("MediaStore insert failed");
        }

        try (InputStream in = conn.getInputStream(); OutputStream out = cr.openOutputStream(itemUri)) {
            if (out == null) throw new IllegalStateException("Cannot open output stream");
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            out.flush();
        } catch (Exception e) {
            cr.delete(itemUri, null, null);
            throw e;
        } finally {
            conn.disconnect();
        }

        ContentValues fin = new ContentValues();
        fin.put(MediaStore.MediaColumns.IS_PENDING, 0);
        cr.update(itemUri, fin, null, null);
        return doneMsg;
    }

    static boolean sendText(String baseUrl, String text, String cid) {
        HttpURLConnection conn = null;
        try {
            JSONObject body = new JSONObject();
            body.put("text", text);
            body.put("sender", "android");
            body.put("sender_id", cid);
            body.put("sender_label", "Android");
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            conn = (HttpURLConnection) new URL(baseUrl + "/api/text").openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(15000);
            conn.setFixedLengthStreamingMode(bytes.length);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            try (OutputStream out = conn.getOutputStream()) {
                out.write(bytes);
            }
            return conn.getResponseCode() == 200;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    static boolean uploadUri(Context ctx, String baseUrl, Uri uri, String cid) {
        ContentResolver cr = ctx.getContentResolver();
        String name = queryDisplayName(cr, uri);
        String mime = cr.getType(uri);
        if (mime == null || mime.isEmpty()) mime = guessMime(name, "", null);
        long size = querySize(cr, uri);
        File temp = null;
        HttpURLConnection conn = null;
        try {
            InputStream src;
            if (size >= 0) {
                src = cr.openInputStream(uri);
            } else {
                temp = File.createTempFile("fh_share_", ".tmp", ctx.getCacheDir());
                try (InputStream raw = cr.openInputStream(uri); OutputStream tmpOut = new FileOutputStream(temp)) {
                    if (raw == null) return false;
                    byte[] buf = new byte[65536];
                    int n;
                    while ((n = raw.read(buf)) != -1) tmpOut.write(buf, 0, n);
                }
                size = temp.length();
                src = new FileInputStream(temp);
            }
            if (src == null) return false;
            String q = "name=" + URLEncoder.encode(name, "UTF-8")
                    + "&mime=" + URLEncoder.encode(mime, "UTF-8")
                    + "&sender=android&cid=" + URLEncoder.encode(cid, "UTF-8")
                    + "&dev=Android";
            conn = (HttpURLConnection) new URL(baseUrl + "/api/upload?" + q).openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(60000);
            conn.setFixedLengthStreamingMode(size);
            conn.setRequestProperty("Content-Type", mime);
            try (InputStream in = src; OutputStream out = conn.getOutputStream()) {
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
                out.flush();
            }
            return conn.getResponseCode() == 200;
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
            if (temp != null) temp.delete();
        }
    }

    private static String queryDisplayName(ContentResolver cr, Uri uri) {
        try (Cursor c = cr.query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                String v = c.getString(0);
                if (v != null && !v.trim().isEmpty()) return v.trim();
            }
        } catch (Exception ignored) {}
        String seg = uri.getLastPathSegment();
        return (seg != null && !seg.trim().isEmpty()) ? seg.replace("/", "_") : "手机文件.bin";
    }

    private static long querySize(ContentResolver cr, Uri uri) {
        try (Cursor c = cr.query(uri, new String[]{OpenableColumns.SIZE}, null, null, null)) {
            if (c != null && c.moveToFirst() && !c.isNull(0)) {
                long s = c.getLong(0);
                if (s >= 0) return s;
            }
        } catch (Exception ignored) {}
        try (AssetFileDescriptor afd = cr.openAssetFileDescriptor(uri, "r")) {
            if (afd != null && afd.getLength() >= 0) return afd.getLength();
        } catch (Exception ignored) {}
        return -1;
    }
}
