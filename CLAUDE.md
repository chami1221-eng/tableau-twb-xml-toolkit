# このリポジトリで作業する Claude Code へ

Tableau のワークブック（.twb / .twbx）を、**MCP サーバを使わずに** Python と Tableau の REST API だけで作る・直す・publish する・確認するためのツールキット。
スキルは `.claude/skills/` にあり、Claude Code が自動で読み込む。**コマンドはすべてリポジトリ直下から実行する**（パスは `tools/…` `.claude/skills/…`）。

**利用者が何をしたいか言わずに始めたとき、または「はじめに.md を読んで」と頼まれたときは、[はじめに.md](はじめに.md) の手順で進める**（準備 → サンプルで動作確認 → 利用者のデータ）。

## 入口（やりたいこと → スキル）

| やりたいこと | スキル |
|---|---|
| **自由記述（アンケート・市民の声）を分析するダッシュボードを作る** | `freetext-to-tableau` |
| CSV から新しいワークブックを作る | `twb-generator` |
| Cloud 上の既存ワークブックを落として XML を直し、出し直す | `twb-cloud-dl-xml-inject` |
| publish 後に描画を確認する | `verify-twb-publish-render` |
| Desktop / Tableau Public で開ける twbx にする | `twb-public-export` |
| 2つの TWB の構造差分を取る | `twb-xml-structure-diff` |
| TWB の XML 要素・属性の正しい書き方を手本から取る | `twb-xml-syntax-miner` |
| Tableau Public の Viz を探す・twbx を落として構造を読む | `tableau-public-reference-finder` / `tableau-public-twb-analyzer` |
| **Tableau Prep のフロー（.tfl）を作る・直す・検証する** | `tfl-syntax-miner`（知見 = `shared/memory/reference_prep_tfl_knowhow.md`） |

**書き方の手本は `examples/corpus/`**（`twb/` = Tableau Desktop が保存した実物、`tfl/` = Prep Builder が保存した実物）。
手本に無い書き方が要るときは、Tableau Public から落として足すか、利用者に該当部分だけ作って保存・添付してもらう。

## Tableau Cloud への接続（MCP 不要）

- 認証はリポジトリ直下の `.env.tableau`（`.env.tableau.template` を写して PAT など4項目を記入）。**中身を表示・出力しない**
- 一覧・画像: `python tools/tableau_rest.py list-workbooks|list-views|view-image …`
- publish: `python tools/publish.py <twb> <csv_dir> --name "WB名"` または `python tools/publish.py <twbx> --name "WB名"`

## 必ず守ること（事故の実績があるもの）

1. **TWB の XML はテキスト置換で編集する。ElementTree / lxml で読み込んで書き出さない。** 名前空間（`user:`）や属性が書き換わり、publish が 403 になる
2. **publish は必ず `--name` を付ける。** 省略すると既存の別のワークブックを上書きする
3. **publish が通っても描画が正しいとは限らない。** `tools/tableau_rest.py view-image` で全ビューを1件ずつ見る（並列にしない）。
   **静止画は実画面と違う**（フィルターの「(すべて)」行・行の高さが描かれない）ので、最後は Cloud の画面で確認する
4. **知らない XML 要素・属性を推測で書かない。** まず `twb-xml-syntax-miner` で手本を引く。無ければ Tableau（Desktop か Web Edit）で同じものを1つ作って保存し、その XML を読んでから書く（Prep の .tfl も同じ。`tfl-syntax-miner`）。
   自己流の属性は publish エラー（400011/500000）か、エラーも出ずに無視される
5. **Desktop / Public で開くなら `twb-public-export` を通す。** Cloud で通る XML でも Desktop は止まることがある（`shared/memory/feedback_twb_desktop_2026_gates.md`）
6. publish が 400/403/500 で落ちたら、PAT より先に **XML の構造を疑う**。`shared/memory/reference_twb_publish_error_codes.md` を最初に開く

## ナレッジ

失敗事例と直し方は `shared/memory/feedback_*.md` / `reference_*.md`。スキルの手順書から参照される。XML パターン集は `docs/twb-patterns.md`。

## 免責

個人の検証用ツールで、Salesforce / Tableau の公式な推奨・サポート対象ではない（TWB の直接編集は公式サポート外）。
作ったものは**提案用の試作**として扱い、継続運用するなら利用者側で作り直すか、Tableau 公式のアクセラレーター等をベースにすること。
