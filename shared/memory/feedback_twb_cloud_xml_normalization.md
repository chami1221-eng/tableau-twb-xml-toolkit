---
name: twb-cloud-xml-normalization
description: Cloud publishでDS名・column-instance名・format等が正規化される。XML注入時はCloud DL後の実名で参照必須
metadata:
  type: feedback
---

# TWB Cloud Publish時 XML正規化 落とし穴

generatorで指定したDS名・column-instance名・format-stringは **Cloud publish時に正規化** される。XML注入で WB を再編集する際、generator側の名前で参照すると **silent fail** する。

## ルール

**Cloud DLしたWBにXML注入する際は、必ず DLしたWBのXMLから実名を再抽出して参照すること**。
generator side の定数 (DS_HUB, column-instance name等) で参照しない。

## Why

2026-06-03 サンプル市v10 BAN×5 calc差し替えXML注入で発生:

| 項目 | generator指定 | Cloud正規化後 |
|------|---------------|---------------|
| DS name | `federated.city_hub` | **`federated.ds_city_daily_hub`** |
| Column-instance | `[sum:表示回数_pages:qk]` | **`[sum:表示回数 (pages_master.csv):qk]`** |
| CountD instance | `[ctd:ページタイトル:nk]` | **`[ctd:ページタイトル:qk]`** |

私のXML注入スクリプトは generator側の名前で `text encoding` 置換を試みたため **何もマッチせず silent fail**。
エラーも出ないため「publish成功 = 反映成功」と誤認 → DLして実XML確認するまで気づかず20分浪費。

その他の正規化:
- `calc_直行率` formula が `AVG([直帰率 (pages_master.csv)])` → `(SUM([表示回数 (pages_master.csv)]) / SUM([表示回数]))` に Cloud側で再正規化された痕跡あり (ユーザー操作か自動かは不明)
- `default-format='p1'` の挙動が想定と違う (1.0以上の値で「1」表示に丸まる罠)
- worksheet/dashboard `<simple-id uuid='...'/>` が publish毎に更新される

## How to apply

XML注入workflow:

```
1. Cloud DL (tableauserverclient.workbooks.download)
2. .twbx unzip → .twb抽出
3. ★ Read .twb XML → 対象worksheet/calc/columnの実名を grep で再抽出 ★
   - DS name: <datasource name='(federated.[^']+)'>
   - column-instance: <column-instance ... name='([^']+)' ...>
   - calc ID: <column caption='calc_XXX' ... name='\[(Calculation_[^\]]+)\]'>
4. 実名を変数に格納してXML編集
5. re-zip → publish
```

スクリプトテンプレ:
```python
import re
twb_xml = Path(twb_path).read_text(encoding='utf-8')

# 実DS名抽出
ds_match = re.search(r"<datasource\s+name='(federated\.[^']+)'", twb_xml)
ds_name = ds_match.group(1)
print(f"Cloud DS name: {ds_name}")

# 実column-instance名抽出 (caption指定)
ci_match = re.search(r"<column[^>]*caption='表示回数'.*?<column-instance[^>]*name='([^']+)'", twb_xml, re.DOTALL)
col_instance = ci_match.group(1)
print(f"Cloud column-instance: {col_instance}")

# その実名でXML編集
old_ref = f"[{ds_name}].{col_instance}"
new_ref = f"[{ds_name}].[usr:Calculation_xxxx:qk]"
twb_xml = twb_xml.replace(old_ref, new_ref)
```

## How to avoid (予防)

- generator側でCloud正規化を想定 → 短く・simpleな命名 (column-instance に空白・括弧入れない) → 正規化との差分最小化
- どうしてもgenerator名前で参照したい場合: publish直後にDLして実名を確認 → そこから XML注入は実名ベース
- silent fail防止: 置換後の文字列を `count('[new_ref]')` で確認、0なら警告ログ

## 関連

- [[twb-publish-error-codes]] - 400011/500000 早見表
- [[twb-ban-kpi-card-pattern]] - BAN XML pattern (Cloud描画動作確認済)
- [[twb-relation-calc-limitation]] - relation DS LOD 制限
- [[twb-cloud-compat]] - Public Desktop互換性
