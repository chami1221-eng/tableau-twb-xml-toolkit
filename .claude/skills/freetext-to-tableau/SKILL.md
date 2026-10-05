---
name: freetext-to-tableau
description: >
  アンケート・広聴・問い合わせなどの自由記述（1行1件のCSV/Excel）を、形態素解析・感情・共起・関係図の座標まで前処理して、
  Tableau のテキスト分析ダッシュボード（単語ランキング／ワードクラウド／リレーションマップ／地域×テーマ／原文一覧）にする。
  MCP は使わない（Python と Tableau の REST API だけ）。
  Use whenever: 自由記述をTableauで分析したい／市民の声・意見を語・感情・地域で見たい／テキストマイニングの結果をTableauに載せたい。
  Triggers: 「自由記述を分析」「テキスト分析」「ワードクラウド」「共起ネットワーク」「区民の声」「アンケートの自由回答」。
---

# freetext-to-tableau — 自由記述 → Tableau

**Tableau が担うのは「見る・絞り込む・原文に戻る」。語に分ける・感情を付ける・共起を数える・関係図の配置を決める、は Tableau の機能ではない。**
このスキルはその前処理を Python で先に済ませ、雛形ダッシュボードに差し込める CSV を作る。

```
自由記述CSV ──preprocess.py──▶ freetext_union.csv ──build_twbx.py──▶ .twbx ──▶ Desktop で開く / tools/publish.py で Cloud へ
              （語・感情・共起・座標）                 （雛形＋上位語・色の差し替え）
```

## 準備（初回のみ）

```bash
pip install janome openpyxl tableauserverclient
```

- Janome は辞書込みの純 Python 形態素解析器（Apache-2.0）。別途の辞書インストールは不要
- Cloud に publish するときだけ `.env.tableau`（リポジトリ直下。`.env.tableau.template` を参照）

## 手順（Claude Code はこの順で進める）

### 1. 入力を確かめる
1行＝1件。**自由記述の列は必須**、ほかは任意。列名は何でもよい（引数で指定する）。

| 引数 | 中身 | 無いとき |
|---|---|---|
| `--text`（必須） | 自由記述 | — |
| `--id` | ID | 行番号 |
| `--area` | 地域（区・地区など） | （地域なし） |
| `--source` | データの種類（広聴／意識調査など、複数ソースを1つにまとめるとき） | （種類なし） |
| `--group` | 分野（関係図の色） | 全体 |
| `--theme` | テーマ（ヒートマップの行） | （テーマなし） → 手順4で Claude に分類させてもよい |
| `--date` | 日付（年月に丸める） | （日付なし） |
| `--sentiment` | 感情（ポジティブ／ニュートラル／ネガティブ） | 手順4 |

### 2. 1回流して、語の切れ方を見る
```bash
python .claude/skills/freetext-to-tableau/preprocess.py 入力.csv --text 意見 --area 区 --date 受付日 --out out
```
`out/word_freq.csv` の上位を見る。**意味を持たないのに上位にいる語**（定型句の「改善」「お願い」など）は除外語へ、
**同じものの書き分け**（保育所／保育園）は言い換えへ。

### 3. 辞書を足して流し直す
- 除外語: 1行1語のテキスト → `--stopwords my_stop.txt`
- 言い換え: `元,正` の CSV → `--synonyms my_syn.csv`
- 複合語を1語にしたい（「地域包括支援センター」など）: Janome 簡易辞書 `表層形,カスタム名詞,読み` → `--userdict my_dict.csv`
- 既定の辞書は `dict/`（stopwords.txt / synonyms.csv / sentiment.csv）

### 4. 感情・テーマを Claude に判定させる（精度が要るとき）
既定の感情は `dict/sentiment.csv` の**簡易辞書**（良い語＋1・悪い語－1 の合計）。
**「高い」「多い」のように文脈で意味が変わる語は辞書では決まらない**（「保育料が高い」と「安全性が高い」）。精度が要るときはこう回す:

```bash
python .claude/skills/freetext-to-tableau/preprocess.py 入力.csv --text 意見 --id ID --export-labels 感情 --batch 100 --out out
```
→ `out/labels_todo/感情_001.jsonl …` ができる（1行＝`{"意見ID", "原文"}`）。
**Claude Code は各束を読み、1件ずつ ポジティブ／ニュートラル／ネガティブ を判定して `out/labels_感情.csv`（`意見ID,感情`）に追記する。**
判定の目安: 要望だけ＝ニュートラル／困りごと・不満＝ネガティブ／評価・感謝＝ポジティブ／**前半ほめて後半不満はネガティブ**。
終わったら `--labels-sentiment out/labels_感情.csv` を付けて手順2のコマンドを流し直す。
テーマも同じ（`--export-labels テーマ` → `--labels-theme`）。**テーマの候補は先に利用者と決めてから**分類する。

- 🚨 個人情報（氏名・住所・電話番号）が原文に入っているデータを外部のサービスに送らない。判定は手元の Claude Code の中で行う
- 判定結果は必ず原文一覧で抜き取り確認する（ダッシュボードの原文一覧に感情が並ぶ）

### 5. ダッシュボードにする
```bash
python .claude/skills/freetext-to-tableau/build_twbx.py out/freetext_union.csv -o out/自由記述分析.twbx --title "区民の声を、言葉から読む"
```
- Tableau Desktop / Tableau Public Desktop で開ける
- Cloud へ: `python tools/publish.py out/自由記述分析.twbx --project "プロジェクト名" --name "WB名"`（`--name` 必須。既存WBの上書き事故防止）
- publish 後の確認: `python tools/tableau_rest.py view-image --workbook "WB名" --out ./verify`
  - 🚨 **静止画は実画面と違う**（フィルターの「(すべて)」行や行の高さは描かれない）。最後は Cloud の画面で見る

## 雛形ダッシュボード（template/freetext_dashboard.twb）

| 場所 | 中身 | クリック |
|---|---|---|
| 上段左 | 単語ランキング（品詞ごとの上位20語・色＝感情）／ワードクラウド | 語 → 原文一覧が絞られる |
| 上段右 | リレーションマップ（丸＝件数・線＝同じ意見に一緒に出る語・色＝分野） | 丸 → 原文一覧が絞られる |
| 中段 | 地域 × テーマ　ネガティブな意見の割合（％） | — |
| 下段 | 意見の原文（既定400件を抽出。`--log-sample 0` で全件） | — |
| タイトル下 | 絞り込み5つ（品詞・データの種類・分野・地域・年月）＝全グラフに効く | — |

- **雛形の XML を手で直すときは ElementTree / lxml で書き出さない**（名前空間が壊れて publish が 403 になる）。テキスト置換だけ
- 地域・テーマ・分野の**見出し名を変えたいときは Tableau 上で「名前の変更」**をする（CSV の列名は変えない。雛形と一致しなくなる）
- 関係図の配置は事前計算。**データが増えると配置が変わる**ので、月ごとに見比べる運用なら座標を固定する（preprocess.py の `force_layout` の結果を保存して使い回す）

## 落とし穴（実際に踏んだもの）

- **「分かりにくい」が「分かる」に化ける** → 「〜にくい／〜やすい」は直前の動詞とつなげて1語にしている
- **定型句の語が上位を占める**（「改善をお願いします」の「改善」） → 手順3の除外語
- **ランキングに Top N フィルターを使わない** → Top N は品詞などの絞り込みより先に効くので「名詞の上位20」にならない。build_twbx.py が上位語を数え直して書き込む
- 原文一覧を数千件にすると、Cloud の静止画（view-image）が灰色のまま描かれないことがある。画面で見るぶんには問題ない

## 免責
これは個人の検証用ツールで、Salesforce／Tableau の公式な推奨・サポート対象ではない。
**提案用の試作であり、継続運用は利用者側で作り直すか、Tableau 公式のアクセラレーター等をベースにすること。**
