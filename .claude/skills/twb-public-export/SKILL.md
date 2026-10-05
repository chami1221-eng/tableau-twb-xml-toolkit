---
name: twb-public-export
description: >
  generator 製 TWB（Cloud の REST publish 向け）を Tableau Public／Tableau Desktop 2026.1 で開ける twbx にする。
  伏せ字置換→接続パス相対化→並べ替え位置の自動修正→Desktop互換変換→内容モデル検査→公開NG語検査→twbx化→抽出手順、を1コマンドで通す。
  Triggers: 「Public用に変換」「Tableau Publicに出す」「twbxで渡したい」「Desktopで開いたら D2E8DA72」。
---

# TWB Public Export

generator で作った TWB は、Tableau Cloud への REST publish では通っても、**Tableau Desktop / Public Desktop（2026.1）で開くと止まる**。
実際に4段で止まった（エラーコード D2E8DA72）。このスキルはそれを1コマンドで通す。

## 実行

```bash
python .claude/skills/twb-public-export/export.py <twb> --csv-dir <CSVフォルダ> -o <out.twbx> \
  [--replace 元の語=伏せ字 ...] [--ng 残っていたら止める語 ...]
```
`.twbx` を入力にしてもよい（CSV は中から拾う）。

## 通すもの（順番どおり）

| # | 処理 | 自動で直す？ | 理由 |
|---|---|---|---|
| 1 | 伏せ字の置換（TWB と CSV の両方） | ○ | Public は全世界公開で、誰でもダウンロードできる |
| 2 | textscan の接続パスを `Data` に | ○ | 絶対パスだと PC のユーザー名が残る |
| 3 | 並べ替え（computed-sort 等）を filter 群の直後・`<slices>` の前へ | ○ | Desktop の内容モデル `(…, filter, sort, perspectives, shelf-sorts, slices?, aggregation)`。**削除ではなく移動**なので並べ替えは残る |
| 4 | Desktop 互換変換（空の `ManifestByVersion` → manifest 等） | ○ | `twb-desktop-compat-converter` の `apply_21_items` を呼ぶ |
| 5 | 内容モデル検査 | **×（止めるだけ）** | action は `(activation?, source?, link, command)`＝**クリック元1シート・link 必須**。どの列を渡すかは作り手が決めることなので自動では直さない |
| 6 | 公開NG語の検査 | ×（止めるだけ） | 既定＝実行ユーザー名・`C:\Users`・社外秘・Confidential・取扱注意 ＋ `--ng` |
| 7 | twbx 化と抽出手順の表示 | — | Public は抽出が必須 |

5で止まったら、生成器側でクリック元のシートごとに action を1本に分け、`<source … worksheet=…/>` の直後に
`<link expression='tsl:…'>` を置く。手本は `.claude/skills/freetext-to-tableau/template/freetext_dashboard.twb` の `<actions>`。
`special-fields='all'` ＋受け口（`group user:auto-column='sheet_link'`）の形は Cloud では動くが Desktop では開けない。

## 伏せ字の決め方

県名・市名を消しても、**固有の施設名や「〇〇区が18ある」のような数で場所が特定できる**ことがある。
特定の組織向けに作ったデモを公開に転用するときは、その組織に固有の名前を `--ng` に入れて検査する。

## Public に保存する前に（手作業）

1. Public Desktop で twbx を開き、**実画面で**絞り込み・凡例・タイトルが切れていないか見る
   （view 画像の静止画は「(すべて)」行・スクロールバー・実画面の行の高さを再現しない → `shared/memory/feedback_twb_static_render_vs_live.md`）
2. データ → {データソース名} → データの抽出… → 何も変えずに「**設定の保存**」（2026.1 のボタン名。旧版は「抽出」）
3. .hyper の保存先を聞かれたら twbx と同じフォルダ
4. ファイル → Tableau Public に保存

## テスト

```bash
python .claude/skills/twb-public-export/selftest.py
```
陽性1本＋並べ替えの自動修正1本＋陰性1本。`model_check.py` を変えたら必ず回す。**陰性が通らない検査は、検査として働いていない。**

| ファイル | 役割 |
|---|---|
| `export.py` | 入口（上の7段） |
| `model_check.py` | 内容モデル検査（単体でも `python .claude/skills/twb-public-export/model_check.py <twb|twbx>`） |
| `selftest.py` | 自己テスト3本 |
| `convert_legacy.py` | 旧版（旧 Public Desktop 向けの7項目）。2026.1 では使わない |
