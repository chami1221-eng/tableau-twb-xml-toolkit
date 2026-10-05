---
name: tableau-public-reference-finder
description: >
  設計の起点になる「参考 Viz」を Tableau Public から探す。社内に豊富な参照Viz（デモ環境）が
  無くても、テーマ/キーワードから実在の Tableau Public Viz を推薦する。
  「参考Vizを探して」「Tableau Publicで探す」「お手本ダッシュボードを見つけて」でトリガー。
---

# tableau-public-reference-finder — 参考Vizを Tableau Public から探す

TWB をゼロから設計する前に、**「どんな見せ方・構造にするか」の起点になる実在の参考Viz** を
Tableau Public から見つけるスキル。手元に参照できるダッシュボード資産が無い環境でも、
テーマ/キーワードを渡すだけで候補が出る。

- **Static**（既定）: 同梱の `data/viz_index.yaml`（手キュレートした実在Viz）から theme/keyword で Top-N。**オフラインで動く**。
- **Dynamic**（`--dynamic`・任意）: `data/featured_authors.yaml` の Author の公式 Workbook API を叩いて、title 一致した未収録Vizを補完。**外向きHTTPS必須**。ネット不通環境では付けなければ Static のみで動作する（API失敗時もクラッシュせず Static は返る）。

## 位置づけ（設計フローの起点）

```
① 参考Vizを探す（このスキル）
        ↓ 良いVizのURL
② 構造を解析する（../tableau-public-twb-analyzer/）: TWBXをDL→XML解析
        ↓ 構造・カラム・calc の理解
③ 自分のTWBを設計・生成する（../twb-generator/）
```

## セットアップ

```bash
pip install pyyaml   # 依存はこれだけ（他は Python 標準ライブラリ）
```

## 使い方（このスキルフォルダから実行）

```bash
# リポジトリ直下から実行する

# テーマ/キーワードで探す（オフラインOK・Staticのみ）
python .claude/skills/tableau-public-reference-finder/recommend.py --themes "transport,industry" --keywords "commuting KPI"

# ラベルを付けて、公式APIのDynamic補完も使う（要ネット）
python .claude/skills/tableau-public-reference-finder/recommend.py --label "売上ダッシュボード" --keywords "sales retail" --dynamic

# research/brief の .md からテーマ・キーワードを自動抽出
python .claude/skills/tableau-public-reference-finder/recommend.py --from-md path/to/brief.md --top-n 5
```

主なオプション:

| オプション | 説明 |
|---|---|
| `--themes "a,b"` | カンマ区切りの自由語（例: `transport,industry`）。`references/tag_taxonomy.md` の17語に正規化される |
| `--keywords "..."` | 自由文キーワード（title/tag/pitch に部分一致） |
| `--from-md PATH` | 任意の markdown からテーマ・キーワードを自動抽出 |
| `--dynamic` | 公式 Workbook API による補完を有効化（**要ネット**。不通なら Static のみ） |
| `--top-n N` | Static の上位N件（既定5） |
| `--label "..."` | 出力見出しに付ける任意ラベル |
| `--emit-json PATH` | スコア済み結果を JSON でも出力 |

## 出力

`recommend.py` が Markdown 表を標準出力に吐く（Static＝推薦理由付き、Dynamic＝title一致の実在候補）。
気に入った Viz は **URL を開いて構造を確認 → `../tableau-public-twb-analyzer/` で TWBX を DL・XML解析** し、
自分の TWB 設計の起点にする。

## Index を育てる

- `data/viz_index.yaml` に1エントリ追記すれば Static 候補が増える（`id/url/title/tags/themes/pitch` を埋める）。
- `data/featured_authors.yaml` に `profile_name` を1行足すと、その Author の全Vizが Dynamic 候補になる。
- theme key の語彙は `references/tag_taxonomy.md`（17語）。`recommend.py` の `THEME_ALIASES` と同期して維持する。

## 注意

- Tableau Public の Workbook API は認証不要の public domain（`/public/apis/workbooks`）。API キー不要。
- Dynamic は外向きHTTPS必須。実行環境のサンドボックスが外部通信不可なら `--dynamic` を外して Static で使う。
- Static Index は小さな Seed。品質の担保は「実在URLのみ・中身を見て pitch を書く」こと。
