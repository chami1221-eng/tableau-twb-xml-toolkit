---
name: reference-prep-tfl-knowhow
description: Tableau Prep のフロー（.tfl）を Claude が書く・直すときの知見。ファイル構造／データインタープリター／新規ノードは実物の複製から／1ノードずつ足す／GUIなしの実行検証／Cloud への publish
---

# Tableau Prep の .tfl を書く・直すときの知見

道具は `.claude/skills/tfl-syntax-miner/`（掘る＝`mine.py`、確かめる＝`verify.py`）。
手本は `examples/corpus/tfl/`（Prep Builder が保存した実物＝Tier A）。

## 1. ファイルの中身

`.tfl` / `.tflx` は **ZIP**。

| エントリ | 中身 |
|---|---|
| `flow` | 本体。改行の無い JSON（`initialNodes` / `nodes` / `connections` / `connectionIds` / `dataConnections` / `majorVersion` / `minorVersion`） |
| `displaySettings` | キャンバス上のノード座標・列順・非表示列 |
| `maestroMetadata` | バージョン等 |
| `flowGraphThumbnail.svg` | サムネイル |

- ノードは `baseType`（input / transform / superNode / output）を持ち、`nextNodes` でつながる。結合は `namespace='Left'/'Right'` で左右を区別する
- 接続（`connections`）は CSV なら `class='textscan'`、Excel なら `class='excel-direct'`
- `.tflx` はデータファイル（`Data/…`）も同梱した版

## 2. 編集の作法

- **`flow` のテキスト置換だけで直す。JSON 全体を読み込んで書き出し直さない。** 他のエントリはバイト列のまま持ち回る（TWB を XML ライブラリで書き出すと壊れるのと同じ理由。`feedback_twb_lxml_write_forbidden.md`）
- 書く前に `json.loads()` で構文を確かめ、書いた後に読み直してノード数を確かめる
- 直す前に元ファイルを別名で残す

## 3. 新しいノードは実物を複製して作る（ゼロから書かない）

入力（`LoadCsvInputUnion` は必須フィールドが20以上）や結合（`SuperJoin` の namespace）など、
**見えない必須フィールドが多い**。ゼロから書くと Prep は「エラーが発生しました」としか言わず、原因が分からない。

- 手本の同じ型のノードを `copy.deepcopy` し、`id` / `name` / `connectionId` / `nextNodes` だけ書き換える
- 型の実物は `python mine.py --node SuperJoin --full` で出る

## 4. 一度に全部作らない

最小の骨組み（入力 → 出力）を作って動くのを確かめ、**1ノードずつ足して毎回確かめる**。
まとめて作ると、どのノードで壊れたか分からなくなる。

- ノード ID は新しく UUID を振る
- Windows のパスはバックスラッシュ（JSON 内では `\\`）
- zip は `ZIP_DEFLATED` で固める

## 5. データインタープリター（1行目がタイトル行の Excel）

「データ インタープリターを使用」は、**接続の `connectionAttributes` に2キー足すだけ**。`LoadExcel` ノード側は変えない。

```json
"connectionAttributes": {
  "cleaning": "yes",
  "filename": "…\\レポート.xlsx",
  "interpretationMode": "1",
  "class": "excel-direct"
}
```

- 無効のままだと列名が `F1` / `F2` … になり、後ろの計算フィールド（AddColumn）が参照エラーで全滅する。
  **エラーは入力ではなく計算フィールド側に出る**ので、式の書き間違いと誤診しやすい
- このキーは `interpreter` で検索しても出ない（`interpretationMode`）。**探す語は短く切る**（`--keys interpret`）。
  「該当なし」は「無い」ではなく「その語では当たらない」

## 6. 確かめ方（Prep Builder を開かずに）

```bash
python .claude/skills/tfl-syntax-miner/verify.py <flow.tfl> --expect-rows 213 --expect-cols "列A,列B"
```

- Prep Builder 同梱の `tableau-prep-cli` でフローを実行し、出力（hyper）の行数・列名まで見る
- **「Finished running the flow successfully」を成功と読まない。** 列名が `F1`/`F2` に化けていてもフローは成功する
- **Prep Builder が入っている PC でしか動かない。** Claude Cowork のクラウド環境などでは、利用者に Prep Builder で開いてもらって確かめる
  （エラーが出たら、メッセージをそのまま貼ってもらう）

## 7. Tableau Cloud への publish

- REST（`tableauserverclient` の `server.flows.publish`）で publish・実行できる（サイトで Prep Conductor が有効な場合）
- **スクリプトで作っただけの .tfl は、Prep Builder では開けてもサーバーに `280003`（Problem reading the provided Flow file）で拒否されることがある。**
  Prep Builder で一度開いて保存し直したものは通る
- ジョブ結果の照会は管理者権限が要る。成否は出力（hyper・データソース）ができたかで確かめる
