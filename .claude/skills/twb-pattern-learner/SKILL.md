---
name: twb-pattern-learner
description: >
  Tableau Public VizのURLからTWBXをダウンロード・解析し、再利用可能なXMLパターンを
  twb-patterns.mdに自動追記する学習スキル。既存パターンとの照合・新規パターン検出・
  テンプレート化・早見表更新まで一気通貫で実行。
  「パターン学習」「TWBパターン」「Vizからパターン抽出」でトリガー。
---

# TWB Pattern Learner

## トリガー
- 「パターン学習」「TWBパターン」「Vizからパターン抽出」「このVizのパターンを学習して」
- Tableau Public URLが渡され、パターン抽出の意図が明確な時

## 使い方
```
/twb-pattern-learner URL1 [URL2 ...]
```

## ワークフロー

### Step 1: スニペット抽出 + 全体解析

2つのスクリプトを**並列実行**する:

```bash
# カテゴリ別スニペット抽出（本スキル）
python .claude/skills/twb-pattern-learner/learn.py "URL"

# 全体解析レポート（既存スキル）
python ../tableau-public-twb-analyzer/analyze.py "URL"
```

出力:
- `out/research/YYYYMMDD_{repoUrl}_pattern_learning.md` — カテゴリ別スニペット
- `out/research/YYYYMMDD_{repoUrl}_twb_analysis.md` — 全体解析

### Step 2: 既存パターン把握

`docs/twb-patterns.md` を読み込み、以下を確認:
- 現在の最大パターン番号
- 既存25パターンの一覧（早見表で概要把握）

### Step 3: パターン照合

Step 1の出力を読み、各カテゴリのスニペットについて:

**a. 既存パターンにマッチするもの**
- 記録する（「このVizはPattern 1-1, 5, 12-1を使用」）
- 既存テンプレートと比較し、重要な差分があればメモ

**b. 既存パターンにないもの → 新規候補**
- 再利用性があるか判断（1回限りの特殊構造はスキップ）
- 他のVizでも使いそうな構造のみ候補とする

### Step 4: 新規パターン作成

候補について、以下のフォーマットでエントリを作成:

```markdown
## N. パターンタイトル

### N-1. サブパターン名 (xml-element-name)
` ` `xml
<element caption="{{CAPTION}}" name="{{NAME}}">
  <!-- 汎化済みXML -->
</element>
` ` `

- 説明1: この要素の役割
- 説明2: 重要な属性値の意味
- 学習元: {Viz名} ({Author})
```

#### フォーマットルール

| ルール | 詳細 |
|--------|------|
| 番号 | 既存最大+1から連番 |
| プレースホルダー | `{{DS_NAME}}`, `{{DB_NAME}}`, `{{WS_NAME}}`, `{{PARAM_NAME}}`, `{{FIELD_NAME}}`, `{{GUID}}` |
| サフィックス保持 | `:nk`(dimension), `:qk`(measure), `:ok`(ordinal), `:tdy`(trunc day year) |
| 集約プレフィックス保持 | `sum:`, `none:`, `attr:`, `avg:`, `cnt:`, `usr:` |
| 学習元 | 各エントリに `学習元: {Viz名} ({Author})` を追加 |

### Step 5: twb-patterns.md 更新

Edit toolで以下を実施:
1. 新パターンを**早見表セクション（`## パターン組合せ早見表`）の直前**に挿入
2. 早見表に新パターンの組合せ行を追加
3. ヘッダー（1-8行目）の学習元情報を更新

### Step 6: 検証

```bash
python .claude/skills/twb-pattern-learner/learn.py --verify
```

エラー0を確認。エラーがあれば修正して再検証。

### Step 7: サマリー報告

```
パターン学習完了:
- 対象Viz: {Viz名}
- 既存パターンマッチ: N件 (1-1, 5, 12-1, ...)
- 新規パターン追加: M件 (26, 27, ...)
- twb-patterns.md: {最終パターン数}パターン
```

## 既存analyzerとの使い分け

| スキル | 目的 | 出力 |
|--------|------|------|
| tableau-public-twb-analyzer | Vizの構造を理解する | 解析レポート（読むだけ） |
| twb-pattern-learner | パターンを学習してカタログに追加する | twb-patterns.md更新 |

analyzerは「読むため」、learnerは「書くため」。learnerは内部でanalyzerも実行する。

## Ralph対応

- 最大ループ: 2回
- 完了基準:
  1. `learn.py --verify` がエラー0
  2. 新規パターンが1件以上 twb-patterns.md に追記済み（既存パターンのみの場合はマッチレポートのみで完了）
  3. 早見表に対応行が存在
- 失敗時: verify結果のエラーを修正して再実行
- 同一エラー2回連続 → 停止してユーザーに報告

## 参照ファイル

- `docs/twb-patterns.md` — パターンカタログ本体（更新対象）
- `../twb-generator/SKILL.md` — TWB XML生成ルール
- `shared/memory/feedback_twb_xml_generation.md` — TWB生成の既知問題・修正パターン
