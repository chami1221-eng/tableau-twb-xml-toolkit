# 変更履歴

## v2.3.0（2026-10-28）

- **`table-to-tableau` を追加** — 表のデータ（自由記述の列が無い CSV）を1コマンドで Desktop で開ける twbx にする
  - 項目別の横棒（最大3枚）・項目×項目のクロス表・明細・ダッシュボード（全シートに効く絞り込み最大4つ）
  - 表を何本渡しても縦に積まず、1表＝1データソース・1ダッシュボード
  - 列の型は自動判定。「ID・コード・番号・年度・年・月」で終わる数字の列は項目扱い、「率・割合・平均・単価・％」は平均で集計、数字のカンマは外す、文章の列はグラフに使わず警告
  - `freetext-to-tableau/build_twbx.py` と同じ Desktop 互換変換・内容モデル検査を通し、同じ形の「検査」行を出す
  - XML はすべて手本から（雛形 TWB と同じ形＋Tableau が保存した TWB にある `filter-group` の形）
  - 架空サンプル `examples/table/sample_facility_usage.csv`（施設の月別利用状況 288行）
- **`はじめに.md` の手順1を変更** — 既定で自由記述の分析に進めない。最初に「自由記述（文章）の列があり、その言葉を分析したいか」を確かめ、表のデータなら `table-to-tableau` へ。手順3のサンプル・手順5の聞き取りも道ごとに分けた
- **表のデータを `freetext_union.csv` の形に詰め込まない**ことを明記（`はじめに.md`・`CLAUDE.md` の「必ず守ること」7・`freetext-to-tableau/SKILL.md`）。
  雛形の列（座標X・ネガティブ件数 など）を別の意味に流用し、複数の表を「表」の列で縦に積んだ結果、区のランキングに区でないものが並ぶ・同じ人を二重に数える、が実際に起きたため
- `freetext-to-tableau/build_twbx.py` が列の不一致で止まったとき、`table-to-tableau` を案内するように

## v2.2.0

- `twb-xml-syntax-miner` / `tfl-syntax-miner` を追加 — 書き方の手本（`examples/corpus/`）から、Tableau・Prep Builder が実際に書いている表現を抜き出す。Prep のフローは tableau-prep-cli で実行検証まで
- Prep の知見を追加（`shared/memory/reference_prep_tfl_knowhow.md`）
- `freetext-to-tableau` が Desktop で開ける twbx を直接出すように（Desktop 互換変換と内容モデル検査を内蔵・データ量の警告）
- `model_check.py` が空の `ManifestByVersion` を検出するように
- `tableau-public-twb-analyzer` が Linux（Claude Cowork のクラウド環境）でも twbx を落とせるように。`--keep-twbx` で手本として残せる
- `はじめに.md`: Claude Cowork の Web 版（ZIP 添付）に対応。Desktop での確認は最後の1回だけ／エラー時の進め方／Tableau Cloud での自動確認の提案

## v2.1.0

- `freetext-to-tableau` を追加 — 自由記述 → 形態素解析（Janome）・感情・共起・関係図座標 → テキスト分析ダッシュボードの雛形
- Claude Code 向けに構成を変更 — スキルを `.claude/skills/` へ移動、`CLAUDE.md` を追加、手順書のパスをリポジトリ直下基準に統一
- `twb-public-export` を作り直し — Desktop / Public 2026.1 で止まる4点（ManifestByVersion・action の形・並べ替えの位置・抽出）に対応。自己テスト付き
- `tools/publish.py` が `.twbx` をそのまま受け付けるように
- 実戦ナレッジを7本追加

## v2.0.0

- エージェント用スキル10本と実戦ナレッジ27本（`shared/memory/`）を追加
- `docs/twb-patterns.md` を57パターンに拡充
- `tools/tableau_rest.py` を追加 — MCPサーバなしで参照系（list/view-image）が完結
- `tools/publish.py` に `.env.tableau` 多段フォールバック探索を追加
- 位置づけを「脱MCP汎用ツールキット」として再定義
