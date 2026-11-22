package com.aodilab.filehelper;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

final class ConnectOverlay extends FrameLayout {
    interface Listener {
        void onManualConnect(String rawUrl);
        void onAutoDiscover();
        void onCancel();
    }

    private final TextView statusView;
    private final EditText inputView;
    private final Button connectBtn;
    private final TextView retryBtn;
    private final TextView cancelBtn;

    ConnectOverlay(Context ctx, Listener listener) {
        super(ctx);
        setBackgroundColor(Color.parseColor("#EDEDED"));
        setClickable(true);
        setFocusable(true);

        float d = ctx.getResources().getDisplayMetrics().density;
        int dp24 = Math.round(24 * d), dp16 = Math.round(16 * d), dp12 = Math.round(12 * d), dp8 = Math.round(8 * d);

        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp24, dp24, dp24, dp16);
        GradientDrawable cardBg = new GradientDrawable();
        cardBg.setColor(Color.WHITE);
        cardBg.setCornerRadius(14 * d);
        card.setBackground(cardBg);
        card.setElevation(6 * d);

        TextView title = new TextView(ctx);
        title.setText("文件传输助手");
        title.setTextColor(Color.parseColor("#111111"));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        card.addView(title);

        statusView = new TextView(ctx);
        statusView.setText("正在搜索同一 Wi-Fi 下的电脑…");
        statusView.setTextColor(Color.parseColor("#8E8E93"));
        statusView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        statusView.setGravity(Gravity.CENTER_HORIZONTAL);
        LinearLayout.LayoutParams stLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        stLp.topMargin = dp8;
        card.addView(statusView, stLp);

        inputView = new EditText(ctx);
        inputView.setHint("电脑局域网地址，如 192.168.1.5:8899");
        inputView.setHintTextColor(Color.parseColor("#AEAEB2"));
        inputView.setTextColor(Color.parseColor("#111111"));
        inputView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        inputView.setSingleLine(true);
        inputView.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        inputView.setImeOptions(EditorInfo.IME_ACTION_GO);
        inputView.setPadding(dp12, dp12, dp12, dp12);
        GradientDrawable inBg = new GradientDrawable();
        inBg.setColor(Color.parseColor("#F5F5F7"));
        inBg.setCornerRadius(8 * d);
        inputView.setBackground(inBg);
        LinearLayout.LayoutParams inLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        inLp.topMargin = Math.round(18 * d);
        card.addView(inputView, inLp);

        connectBtn = new Button(ctx);
        connectBtn.setText("连接电脑");
        connectBtn.setAllCaps(false);
        connectBtn.setTextColor(Color.WHITE);
        connectBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        connectBtn.setTypeface(Typeface.DEFAULT_BOLD);
        GradientDrawable btnBg = new GradientDrawable();
        btnBg.setColor(Color.parseColor("#07C160"));
        btnBg.setCornerRadius(8 * d);
        connectBtn.setBackground(btnBg);
        connectBtn.setStateListAnimator(null);
        LinearLayout.LayoutParams btnLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, Math.round(44 * d));
        btnLp.topMargin = dp12;
        card.addView(connectBtn, btnLp);

        retryBtn = new TextView(ctx);
        retryBtn.setText("重新自动搜索局域网电脑");
        retryBtn.setTextColor(Color.parseColor("#576B95"));
        retryBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        retryBtn.setGravity(Gravity.CENTER);
        retryBtn.setPadding(dp8, dp12, dp8, dp8);
        LinearLayout.LayoutParams rLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        rLp.topMargin = Math.round(6 * d);
        card.addView(retryBtn, rLp);

        cancelBtn = new TextView(ctx);
        cancelBtn.setText("返回聊天");
        cancelBtn.setTextColor(Color.parseColor("#8E8E93"));
        cancelBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        cancelBtn.setGravity(Gravity.CENTER);
        cancelBtn.setPadding(dp8, dp8, dp8, dp8);
        cancelBtn.setVisibility(View.GONE);
        card.addView(cancelBtn);

        FrameLayout.LayoutParams cardLp = new FrameLayout.LayoutParams(
                Math.min(Math.round(330 * d), ctx.getResources().getDisplayMetrics().widthPixels - Math.round(48 * d)),
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER);
        addView(card, cardLp);

        connectBtn.setOnClickListener(v -> listener.onManualConnect(inputView.getText().toString()));
        inputView.setOnEditorActionListener((v, actionId, ev) -> {
            if (actionId == EditorInfo.IME_ACTION_GO) {
                listener.onManualConnect(inputView.getText().toString());
                return true;
            }
            return false;
        });
        retryBtn.setOnClickListener(v -> listener.onAutoDiscover());
        cancelBtn.setOnClickListener(v -> listener.onCancel());
    }

    void setState(String status, String currentUrl, boolean busy, boolean canCancel) {
        statusView.setText(status);
        if (currentUrl != null && !currentUrl.isEmpty() && inputView.getText().length() == 0) {
            inputView.setText(currentUrl.replace("http://", ""));
        }
        connectBtn.setEnabled(!busy);
        connectBtn.setAlpha(busy ? 0.6f : 1.0f);
        retryBtn.setEnabled(!busy);
        cancelBtn.setVisibility(canCancel ? View.VISIBLE : View.GONE);
    }

    void setInputUrl(String url) {
        if (url != null) inputView.setText(url.replace("http://", ""));
    }
}
