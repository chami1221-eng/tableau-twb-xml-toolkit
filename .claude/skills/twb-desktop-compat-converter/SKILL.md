---
name: twb-desktop-compat-converter
description: >
  generator製TWB(Cloud REST publish)やCloud Web Edit由来TWBをTableau Desktop 2026.1互換に変換する。
  21項目+αのXML修正を自動適用(manifest 17要素・BasicButtonObject・storyboard・nav button含む)。
  「Desktop互換変換」「TWBXをDesktopで開けるように」「ラウンドトリップ」でトリガー。
---

# TWB Desktop Compat Converter

generator製TWB / Cloud Web Edit由来TWB を Tableau Desktop 2026.1 で開ける形に変換する。

確立済みレシピ: `shared/memory/feedback_twb_cloud_to_desktop_roundtrip.md`

## トリガー

| 入力 | 動作 |
|------|------|
| `twb-desktop-compat-converter {twbx_path}` | フル変換（21項目自動適用） |
| 「Desktop互換変換 {path}」 | 同上 |
| 「{TWBX} をDesktopで開けるように」 | 同上 |
| 「Cloud→Desktopラウンドトリップ」 | 同上 |

## 実行

```bash
python .claude/skills/twb-desktop-compat-converter/convert.py {input_twbx} [-o {output_twbx}] [--with-buttons] [--with-storyboard]
```

オプション:
- `--with-buttons` : button要素含む場合 manifest にBasicButtonObject追加
- `--with-storyboard` : ストーリーボード保持 (storyboard XML仕様適用)
- `-o` : 出力先（省略時は同名 _desktop_compat suffix付き）

## 適用される21項目

| # | 修正内容 |
|---|---------|
| 1 | manifest 17要素フルセット（Extensions/VizExtensions含む） |
| 1.5 | button含む場合 BasicButtonObject + BasicButtonObjectTextSupport 追加 |
| 2 | source-build 2025.2.0完全番号化 |
| 3 | source-platform 削除 |
| 4 | _.fcp.VizExtensions プレフィックス全削除 |
| 5 | layout dim-percentage/measure-percentage 削除 |
| 6 | formatted-text 中身保持(削除でなく)・zone内順序入替 |
| 7 | devicelayouts ブロック削除 |
| 8 | worksheet simple-id 追加（不足分） |
| 9 | slices/aggregation 順序入替 |
| 10 | encoding内 detail 削除 |
| 11 | reference-lines ブロック削除 |
| 12 | style-rule (rows-axis-tick-labels/mark-labels) 削除 |
| 13 | button関連（manifest追加 OR 削除） |
| 14 | encoding-id 属性削除 |
| 15 | pane内 view 追加（欠落分のみ） |
| 16 | referenced-views 中身（referenced-view）追加 |
| 17 | 末尾 actions 削除 |
| 18 | datasource column順序入替 |
| 19 | 重複 mark 削除（Automatic+VizExtension） |
| 20 | storyboard XML仕様（window class='dashboard'） |
| 21 | nav button XML仕様（dashboard-object zone） |

## 落とし穴

- **Tableau Desktop保存後はzone座標が再計算される**（show-title='false' 後など）→ 既に保存済みTWBXに対する追加編集は実機構造を grep で確認してから
- **button要素持ちは manifest BasicButtonObject 必須**（無いと `no declaration found for element 'button'`）
- **storyboard window は class='dashboard'** + viewpoints/active構造（class='story' は無効）
- **formatted-text は削除しない**（中身保持）。前バージョンレシピの誤り
- **pane内viewは欠落分のみ追加**（v9 memory「追加禁止」は誤り）
- 最重要ルール準拠: XML編集は **テキスト置換のみ**（ElementTree/lxml禁止）

## 注意

- 入力TWBXがTableau Cloudから直接DLされた場合と、Tableau Desktopで一度開いて保存した後の場合で構造が異なる
- 全21項目を必ず適用するわけではない（既に正しい構造の項目はスキップ）
- 不一致エラーが出た場合は項目ごとにテキストでも調査可能

## 実証実績

- 2026-06-16: サンプル市 v11new で 21項目+α 適用成功
- 2026-06-16: 検証用サイト「サンキーダイアグラム」DL→17要素manifest確認
- 2026-06-16: 観光統計デモWB (Desktop 2026.1ネイティブ) → BasicButtonObject manifest + nav button XML仕様抽出
