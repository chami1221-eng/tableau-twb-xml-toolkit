---
name: feedback-view-image-serial
description: view 画像の取得（tools/tableau_rest.py view-image）は1件ずつ順に。並列にすると 429/401 が多発する
metadata:
  type: feedback
---

view 画像の取得は**並列実行しない**。`python tools/tableau_rest.py view-image ...` は内部で1件ずつ取りに行く。自分で複数プロセスを同時に立てない。

**Why:** 5つのダッシュボードを5並列で取得したら 429（レート制限）と 401（認証）が多発し、1件しか取れなかった。同じ PAT で同時にサインインすると、互いのセッションを無効化する。

**How to apply:**
- 複数の view は順番に取る（1 view あたり数秒なので順番でも十分速い）
- publish の直後に続けて取るときも、同じ PAT で別プロセスを同時に動かさない（→ `reference_twb_publish_error_codes.md` の 401002）
- 🚨 **静止画は実画面の再現ではない**。フィルターの「(すべて)」行・スクロールバー・実画面の行の高さは描かれない（→ `feedback_twb_static_render_vs_live.md`）
