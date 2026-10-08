---
name: twb-xml-syntax-miner
description: 'TWB の XML 要素・属性を書く前に、Tableau 自身が保存したワークブック（手本）から正しい書き方を抜き出す読み取り専用ツール。自己流の属性は publish 400011/500000 や Desktop で開けない原因になるので、必ず実物から取る。Triggers: 「この属性で合ってる?」「軸の固定はどう書く?」「zone の type-v2 に何が入る?」「publish 400011 が出た」「知らない XML 要素を書く」。twb-generator / twb-cloud-dl-xml-inject から呼ばれる下請け。'
---

# twb-xml-syntax-miner — 実物の手本から TWB の XML を書く

## なぜ要るか

TWB の XML を「たぶんこう書く」で書くと、publish が落ちるか、通っても効かない。実際にあった例:

| 場面 | 自己流で書いたもの | 正解（Tableau が書いた実物） | 結果 |
|---|---|---|---|
| 軸の固定 | `<encoding class='quantitative' …>` | `class='0'` + `attr='space'` + `type='space'` の属性セット | publish 400011 |
| マークラベル | `<style-rule element='mark-labels'>` | `<style-rule element='mark'>` の中に `<format attr='mark-labels-show'/>` | 通るが効かない |
| フィルターの zone | 属性を足しすぎ（mode / values / show-domain） | `pane-specification-id` + `name` + `param` の3属性 | publish 500000 |
| window | `<window … />` の自己閉じ | `cards` と `simple-id` が必須 | publish 500000 |

## いつ使うか

1. XML の要素・属性を書こうとしていて、動作実績のある書き方を手元に持っていない
2. 書いたことはあるが、正確な属性名・値・順序を思い出せない
3. publish が 400011 / 500000 / 403132 で落ちた
4. 「たぶんこう書く」と思っている（これが一番危ない）

## 手本（コーパス）

| 置き場所 | 中身 |
|---|---|
| `examples/corpus/twb/` | 同梱の手本（Tableau Desktop が保存した実物）。棒・円・ヒートマップ・ハイライト・ネイティブのサンキー・自由記述分析のダッシュボード（フィルター・凡例・アクション入り） |
| `out/` | `tableau-public-twb-analyzer --keep-twbx` で落とした Tableau Public の手本など |
| `~/Documents/マイ Tableau リポジトリ/ワークブック` | 利用者の PC で Desktop が保存したワークブック（あれば） |

**手本が足りないときは Tableau Public から足す**（他の人の作品なので同梱はせず、使うたびに落とす）:

```bash
python .claude/skills/tableau-public-reference-finder/recommend.py --help     # 似た Viz を探す
python .claude/skills/tableau-public-twb-analyzer/analyze.py "<Viz URL>" --output-dir out/public --keep-twbx
```

それでも無ければ、利用者に Tableau Desktop で該当部分だけ作って保存してもらい、添付してもらう（操作は1〜3ステップで示す）。

## 使い方

```bash
python .claude/skills/twb-xml-syntax-miner/mine.py --recipe list                      # よく使う書き方の一覧
python .claude/skills/twb-xml-syntax-miner/mine.py --recipe axis-fixed
python .claude/skills/twb-xml-syntax-miner/mine.py --element zone --eq type-v2=filter  # 任意の要素を掘る
python .claude/skills/twb-xml-syntax-miner/mine.py --element zone --values type-v2     # 属性に実在する値
python .claude/skills/twb-xml-syntax-miner/mine.py --recipe filter-zone --tier-a-only  # Tableau が書いたものだけ
python .claude/skills/twb-xml-syntax-miner/mine.py --recipe action-link --values expression   # 値を復号して対応関係を読む
```

- `--decode` を付けると、属性値の URL エンコードと XML エンティティを解いて表示する（`<link expression>` のように値の中にフィールド参照が埋まっている構文で使う）
- `--corpus <フォルダ>` で手本の置き場所を足せる

## 読み方

| Tier | 意味 | 判定 |
|---|---|---|
| **A** | **Tableau（Desktop / Cloud）が書き出した** | 先頭に `<!-- build 2…… -->` コメントがある |
| B | スクリプトで作った・出所不明 | build コメントなし |

- **`✅ Tier A 実績あり` の書き方を使う。** 件数ではなく「Tier A に1件でもあるか」で見る
- `⚠️ Tier B のみ` は使わない（造語の疑い）
- `該当なし` のときは書かない。Tableau Public から手本を足すか、利用者に作ってもらう
- **親要素も見る。** 要素が正しくても置き場所が違うと効かない
- 出力を `| grep` で絞ったときは「無かった」と結論しない（省略の警告は stderr に出る）

## よく使う書き方（`--recipe list` で最新を確認）

| recipe | 用途 |
|---|---|
| `axis-fixed` | 軸の範囲の固定 |
| `dual-axis` | 二重軸 |
| `filter-zone` / `legend-zone` / `web-zone` / `paramctrl` | ダッシュボードのフィルター・凡例・Web・パラメーター |
| `button` | シートへ移動・表示切替ボタン |
| `slices` | フィルターの選択肢が先頭の値1つになるのを防ぐ |
| `computed-sort` | 並べ替え |
| `reference-line` | 参照線 |
| `action` / `action-link` | フィルター・ハイライト・パラメーターのアクション／フィールドの対応 |
| `mark-labels` | マークラベル |
| `cards` | `<window>` 直下に必須 |
| `map-layer` / `geometry` / `color-palette` / `datasource-connection` | 地図・空間・色・接続 |

## 守ること

- 読み取り専用。TWB を変更しない（lxml は parse / iter / getparent だけ使う）
- Prep のフロー（.tfl）は対象外 → `tfl-syntax-miner`
