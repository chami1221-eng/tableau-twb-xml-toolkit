---
name: verify-twb-publish-render
description: TWBをTableau Cloudにpublish.pyでパブリッシュした直後、list-views + get-view-imageで全ビューが実際に描画されるか確認してから完了報告する。publish成功＝描画成功ではない（XML構造起因の空ビュー・500/403が残る）。Anthropic公式「Product Verification（出力を実システムで検証）」カテゴリ。
---

# verify-twb-publish-render — TWB パブリッシュ後の描画検証

`publish.py` が成功を返しても、**ビューが実際に描画されているとは限らない**。
XML構造の誤り（window cards/simple-id欠落、filter zone属性、datasource構造）はpublishを通っても
Cloud上で空ビュー・エラーになる。**publish成功＝描画成功ではない。** 必ず実画像で確認してから報告する。

> このスキルは PostToolUse hook（`publish.py` 実行検出→本検証を促すリマインダ注入）の判断側。
> hook が「確認なしの完了報告は禁止」と促す。本スキルがその確認手順を定義する。

## 起動タイミング

以下の **直後**:
- `python tools/publish.py <twb> <csv_dir> --name "<name>"` 実行後
- twb-cloud-dl-xml-inject / twb-visual-iterator でのre-publish後
- Tableau Cloud上のWBを更新する全操作の後

## 検証手順

### Step 1: publish結果のWB/View一覧取得
```
python tools/tableau_rest.py list-workbooks --name "<WB名>"   # 脱MCP: プロジェクト/LUID確認
python tools/tableau_rest.py list-views --workbook "<WB名>"   # 脱MCP: 全ビュー列挙
```
- **publish前に** `list-workbooks filter=name:eq:<name>` で既存WBのプロジェクトを確認し `--name`/`--project` を一致させる（不一致だと別WBが作成される）。

### Step 2: 全ビューを get-view-image で描画確認【順次実行必須】
```
python tools/tableau_rest.py view-image --workbook "<WB名>" --out ./verify   # 脱MCP: 全view PNG保存 → 目視 (view1)
# ↑ 上の1コマンドで全viewが ./verify/verify_*.png に出るので view2 以降も同時取得済
...
```
- **並列実行禁止**: 並列で 429/401 が頻発する（feedback_view_image_serial）。**1件ずつ順次**。
- 各画像を Read で目視: 空ビュー・凡例だけ・"An error occurred"・真っ白 が無いか。

### Step 3: 描画NG時の切り分け
publish成功なのに描画NG → **PATではなくXML構造を疑う**（reference_twb_publish_error_codes.md / feedback_twb_cloud_compat.md）:
- 500000: window cards/simple-id欠落・filter zone追加attribute・ManifestByVersion残存・旧action XML
- 400011: XML parse / cross-table calc
- 403132: CSVパス / 401002: PAT競合
- 空ビュー: datasource構造（federated wrap / 型コード）/ Marks未設定

修正は twb-cloud-dl-xml-inject（lxmlベース・**ElementTree禁止=最重要ルール**）で行い、再publish→再度本検証。

### Step 4: 報告
全ビュー描画✅を確認してから「パブリッシュ完了」を報告する。**確認なしの完了報告は禁止。**
前回からの視覚変化を追う場合は twb-visual-iterator（全view画像取得→前回差分比較）を使う。

## 失敗パターン (避けるべき)

### ❌ 悪い例
```
publish.py → "Success" 出力 → そのまま「パブリッシュ完了しました」と報告
→ 実際はCloud上で空ビュー（filter zone属性誤り）。顧客デモ直前に発覚。
```

### ✅ 正しい例
```
publish.py → Success
→ [PostToolUse hookリマインダ受信]
→ list-views で5ビュー確認 → get-view-image を1件ずつ5回 → 全て正常描画を目視
→ 「全5ビュー描画確認済み。パブリッシュ完了」と報告
```

## 連携
- `feedback_view_image_serial.md` — get-view-image順次実行必須
- `reference_twb_publish_error_codes.md` / `feedback_twb_cloud_compat.md` — 描画NG時のエラーコード切り分け
- `twb-visual-iterator` — 反復publish時の前回差分比較
- `twb-cloud-dl-xml-inject` — 描画NG修正（lxmlベース）
- **PostToolUse Bash hook**（publish.py検出→本検証リマインダ。settings.json/settings.local.json両方に同期）

## 注意事項
- **publish成功 ≠ 描画成功。** 必ず実画像（get-view-image）で確認する。
- get-view-image は **順次**（並列は429/401）。
- 描画NGは PAT ではなく **XML構造** を最初に疑う（最重要ルール）。
