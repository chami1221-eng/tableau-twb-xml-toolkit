---
name: twb-xml-structure-diff
description: >
  2つのTWBファイル(参考TWB vs 編集中TWB / SAFE backup vs 現在TWB 等)のXML構造を
  カテゴリ別(datasource/zone/filter/action/calc/parameter)に比較し、集合差+unified diff
  をMarkdownレポート化する read-only ツール。
  paramctrl 3段ネスト・filter zone 必須属性・connection class(textscan/federated)等の
  構造差をTWB編集前/publish失敗時に事前検出する。
  「TWB diff」「TWB構造比較」「XML差分」「publish前検証」「参考TWBと突合」
  「paramctrl確認」「zone構造比較」「SAFE backupと比較」でトリガー。
---

# twb-xml-structure-diff — TWB XML構造比較 (read-only)

## トリガー

```bash
python .claude/skills/twb-xml-structure-diff/diff.py \
  <twb_a> <twb_b> [--focus zone|datasource|filter|action|calc|parameter|all] \
  [--out PATH] [--head N]
```

**自然言語**:
- 「編集中のTWBと参考TWBの構造比較して」
- 「publish失敗したのでSAFE backupと現在TWBをdiff取って」
- 「paramctrl の zone tree が unified版と一致してるか確認して」

## ⚠️ 最重要ルール 必須遵守

本スキルは **lxml の parse / iter のみ使用** する read-only ツール。
以下のAPIは **絶対に使用しない**(diff.py 内に1箇所も存在しない):

- ❌ `tree.write()` / `etree.tostring()` (TWB全体書出 → textscan attribute正規化で 403132)
- ❌ `SubElement` / `Element.append` / `Element.remove` (構造変更)
- ❌ `Element.set(attr, value)` / `Element.attrib[k]=v` (attribute書換)

出力は **Markdownレポートのみ**。TWBファイルは絶対に変更しない。
(feedback_twb_no_elementtree.md C-002 + feedback_twb_lxml_write_forbidden.md 準拠)

検証コマンド: `grep -nE "tree\.write|etree\.tostring|\.SubElement|\.append\(|\.remove\(|\.set\(|\.attrib\[" diff.py` → 0 hit 必須

## 用途

### 1. TWB編集前の事前チェック
参考TWB(動作実証済の参考版)と編集中TWBを比較し、paramctrl・zone tree・
filter属性の構造差を **編集着手前** に検出。手戻りを先回りで潰す。

```bash
python .claude/skills/twb-xml-structure-diff/diff.py \
  path/to/reference.twb \
  path/to/editing.twb \
  --focus zone
```

### 2. publish失敗時の構造退化検出
publish 403132/500000 等が出たら、直前の SAFE backup と現在TWBを diff。
lxml write由来の attribute正規化差・要素消失を即特定。

```bash
python .claude/skills/twb-xml-structure-diff/diff.py \
  v11new_city.twb.SAFE_publishable_2026-06-11 \
  v11new_city.twb \
  --focus all
```

### 3. 学習用
動作実績のあるTWB間のXML差分を可視化し、Cloud render に効く構造ルールを抽出。

## 比較項目とカテゴリ別判定

### Identity Key (Layer 1: 同一エンティティ判定)

| カテゴリ | identity key |
|---|---|
| datasource | `name` |
| calc | `name` (column内 calculation 子要素を持つもの) |
| zone | 親 dashboard 名 + `id` |
| filter | `column` + `class` |
| action | `name` (action element の name attribute) |
| parameter | `name` |

### 比較対象 attribute (Layer 2: 「変更」検出)

identity 一致時、以下の **許可リスト attribute のみ** 比較。全attribute比較は
lxml順序差/空白差で誤検知地獄になるため。

| カテゴリ | 比較対象 attribute |
|---|---|
| datasource | `connection/@class`, named-connections の有無 |
| calc | `datatype`, `formula`, `default-format` |
| zone | `type-v2`, `x/y/w/h`, `param`, **親 zone の type-v2 チェーン** |
| filter | `class`, `include-values`, `level` |
| action | `class`, `source-sheet`, `target-sheet` |
| parameter | `datatype`, `current-value` |

**zone の parent chain** は paramctrl 3段ネスト要件
(layout-basic→layout-flow(horz)→layout-flow(vert)→paramctrl) を検出するため必須。
深度3固定(それ以上は誤検知率が上がる)。

## CLI仕様

```
diff.py <twb_a> <twb_b> [options]

positional:
  twb_a, twb_b           比較対象の .twb ファイル(絶対パス or 相対パス)

options:
  --focus {zone,datasource,filter,action,calc,parameter,all}
                         比較するカテゴリ(default=all)
  --out PATH             出力Markdown先(default=out/reports/YYYYMMDD_twb_diff_{a}_vs_{b}.md)
  --head N               各カテゴリ表示件数上限(default=20、0で無制限)
  --no-write             stdout にのみ出力、ファイル書出しない
```

## 出力フォーマット

```markdown
# TWB Structure Diff: A vs B
- A: city_test_unified.twb (datasource=41, zone=16, filter=10, action=1)
- B: v11new_city.twb (datasource=26, zone=N, filter=19, action=1)
- focus: all / generated: 2026-06-12 14:32

## Datasources (only_in_a=X, only_in_b=Y, changed=Z)
| Status | name | caption | connection class |
|---|---|---|---|
| only_in_a | federated.ds_pages_master | ページマスタ | federated |
| only_in_b | federated.ds_city_hub_v11 | ハブv11 | federated |
| changed   | federated.ds_daily | 日別 | textscan→federated |

<details><summary>変更詳細 (3件)</summary>

\`\`\`diff
--- a: federated.ds_daily
+++ b: federated.ds_daily
- <connection class='textscan' directory='...' />
+ <connection class='federated'><named-connections>...</named-connections></connection>
\`\`\`
</details>

## Zones
...
```

## 既知の限界

- zone parent_chain は深度3固定(paramctrl 3段検出が目的)
- TWBサイズ 100MB超 は parse に時間がかかる
- calc の identity key は `name`(自動採番 Calculation_xxxxxxx) を使うため、
  TWB間で同じ caption の calc でも内部ID違いだと「別物」判定になる
  → 将来 `caption` 優先の identity key に切り替える可能性あり

## 関連スキル・メモリ

- `twb-generator` — 新規TWB生成(書き込み側、本スキルの対象を生成する)
- `twb-cloud-dl-xml-inject` — Cloud TWB の DL→編集→republish(書き込み側、publish前に本スキル推奨)
- `verify-twb-publish-render` — publish後の描画検証(本スキルは publish 前)
- `shared/memory/feedback_twb_no_elementtree.md` — C-002 ElementTree ラウンドトリップ編集禁止
- `shared/memory/feedback_twb_lxml_write_forbidden.md` — lxml write/tostring も禁止
- `shared/memory/feedback_twb_paramctrl_layout_nesting.md` — paramctrl 3段ネスト要件(本スキルで検出)
- `shared/memory/feedback_twb_cloud_compat.md` — Cloud publish 失敗の構造原因まとめ

## 動作実績テスト (Smoke Test)

```bash
# A) 参照TWB vs 編集中TWB の全体差分
python .claude/skills/twb-xml-structure-diff/diff.py \
  path/to/reference.twb \
  path/to/editing.twb \
  --focus all
# 期待: datasource only_in_b が多数, action only_in_b 数件（例）

# B) zone構造（paramctrl等）の差分検出
python .claude/skills/twb-xml-structure-diff/diff.py \
  path/to/base.twb \
  path/to/variant.twb \
  --focus zone
# 期待: paramctrl zone の parent_chain 差を検出
```
