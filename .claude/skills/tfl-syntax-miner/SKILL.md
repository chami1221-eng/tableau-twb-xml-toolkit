---
name: tfl-syntax-miner
description: 'Tableau Prep のフロー（.tfl / flow JSON）を書く・直す前に、Prep Builder 自身が保存した実物（手本）から正しい書き方を抜き出す。書いた後は tableau-prep-cli で GUI を開かずに実行して確かめる（Prep Builder がある PC のみ）。Triggers: 「Prep のフローを作って」「.tfl を直して」「Prep のこの設定はどう書く」「データインタープリターを有効にしたい」「フローがエラーになる」「計算フィールドが参照エラー」。'
---

# tfl-syntax-miner — Prep のフローを実物の手本から書く

知見の本体は `shared/memory/reference_prep_tfl_knowhow.md`。**作業前に読む**（ファイル構造・編集の作法・新規ノードは複製から・1ノードずつ足す）。

## いつ使うか

1. `.tfl` のノード・設定を書こうとしていて、手本を持っていない
2. Prep の画面のチェックボックスが JSON でどう書かれるか分からない
3. フローが「エラーが発生しました」としか言わない／計算フィールドが参照エラーになる
4. `.tfl` を直した直後（→ `verify.py` で確かめる）

## 手本（コーパス）

| 置き場所 | 中身 |
|---|---|
| `examples/corpus/tfl/` | 同梱の手本。Prep ハンズオン教材のフロー2本（入力・ユニオン・結合・ピボット・集計・計算・フィルター・出力を一通り含む。データは同梱していない） |
| `out/` | 利用者が作った・添付した .tfl |
| `~/Documents/マイ Tableau Prep リポジトリ` | 利用者の PC で Prep Builder が保存したフロー（あれば） |

**手本を増やすには、Prep Builder で作って保存した .tfl を `out/` に置いてもらう。**
同梱の手本に無い書き方が要るときは、利用者に Prep Builder でそのノードを1つだけ作って保存してもらい、添付してもらう（操作は1〜3ステップで示す）。

## 掘る（mine.py・読み取り専用）

```bash
python .claude/skills/tfl-syntax-miner/mine.py --corpus-report            # 手本の一覧と Tier
python .claude/skills/tfl-syntax-miner/mine.py --node-types               # 実在するノード型
python .claude/skills/tfl-syntax-miner/mine.py --node LoadExcel           # ノード型の実物（キー一覧つき）
python .claude/skills/tfl-syntax-miner/mine.py --node SuperJoin --full    # ノードの全文（複製の元にする）
python .claude/skills/tfl-syntax-miner/mine.py --keys interpret           # キー名の部分一致で全階層を探す（一番効く）
python .claude/skills/tfl-syntax-miner/mine.py --values cleaning          # そのキーに実際に入る値
python .claude/skills/tfl-syntax-miner/mine.py --recipe list              # よく使う書き方の一覧
python .claude/skills/tfl-syntax-miner/mine.py --recipe excel-data-interpreter
```

- **`--keys` は短く切る**（`interpreter` ではなく `interpret`）。語尾違いで空振りする
- `--corpus <フォルダ>` で手本の置き場所を足せる

### 読み方

| Tier | 意味 | 判定 |
|---|---|---|
| **A** | **Prep Builder が開いて保存した実物** | 入力ノードに解決済みの `fields[]` がある |
| B | スクリプトで作った・出所不明 | `fields` が空 |

- **`✅ Tier A 実績あり` の書き方を使う**
- `⚠️ Tier B のみ` は使わない（自作物にしか無い＝造語の疑い）
- `該当なし` は「書けない」ではない。まず語を短くして引き直す。それでも無ければ利用者に1ノードだけ作ってもらう

## 確かめる（verify.py）

```bash
python .claude/skills/tfl-syntax-miner/verify.py <flow.tfl>
python .claude/skills/tfl-syntax-miner/verify.py <flow.tfl> --expect-rows 213 --expect-cols "列A,列B"
python .claude/skills/tfl-syntax-miner/verify.py <flow.tfl> --no-run      # 実行せず既存の出力だけ検査
```

- Prep Builder 同梱の `tableau-prep-cli` を探して実行し、出力（hyper）の行数・列名まで測る
- 「Finished running the flow successfully」だけで成功と読まない。`F1`/`F2` 形式の壊れた列・0行・想定列の欠けを必ず見る
- 実行すると出力先（hyper / csv）は上書きされる。先頭に表示される出力先を確かめてから流す
- **Prep Builder が無い環境（Claude Cowork のクラウド側など）では動かない。** その場合は利用者に Prep Builder で開いて実行してもらう。
  エラーが出たらメッセージをそのまま貼ってもらい、3回やりとりしても直らなければ、該当ノードだけ利用者に作ってもらって手本にする（`はじめに.md` の 4-1 と同じ考え方）

## 守ること

- `mine.py` は読み取り専用（zip を読み取りモードでしか開かない）
- `.tfl` の編集は `flow` のテキスト置換だけ。JSON 全体を書き出し直さない
- 新しいノードは手本を `copy.deepcopy` して作る。ゼロから書かない
- 利用者のデータ（入力ファイル）に個人情報が含まれていないか、読み込む前に確かめる
