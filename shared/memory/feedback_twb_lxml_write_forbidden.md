---
name: twb-lxml-write-forbidden
description: TWB XML編集時 lxml の write()/tostring() も 最重要ルール「ElementTree禁止」と同等。textscan connection の attribute order/quote形式が変質しCloud publish 403132を起こす実害あり
metadata:
  type: feedback
---

# TWB XML編集に lxml の全体 write/tostring も禁止（最重要ルール拡張）

最重要ルール に「TWB XML編集にElementTree禁止」とあるが、**lxml の `tree.write()` / `etree.tostring()` でファイル全体を書き出すパターンも同等に禁止**。

**Why:**
2026-06-12 サンプル市v11new TWB の dashboard zone tree 再構築（A2 layout-flow 3段ネスト）を lxml で実装し、`tree.write(TWB, encoding='utf-8', xml_declaration=True, standalone=True)` で書き出した。
- parse は OK（user: namespace 保持・XML健全性OK）
- 結果: Tableau Cloud publish で `403132: Forbidden - failed to establish a connection to your datasource`
- 原因: lxml が `<connection class="textscan" directory="..." filename="..."/>` などの attribute を**アルファベット順にソート**し、さらに single quote → double quote に変換した
- Tableau Server 側の textscan connection parser がこの正規化された attribute 形式を期待通り解釈できず、CSV パス解決失敗

**How to apply:**

**OK:**
- lxml で `parse` してツリーを analyze（読み取りのみ）
- lxml で個別 element の attribute を確認
- テキスト置換（正規表現 / `str.replace`）で限定的に書き換える

**NG（Cloud 403/破壊リスク）:**
- `tree.write(path, ...)` でファイル全体を書き出す
- `etree.tostring(root, ...)` で再構築した XML を保存
- lxml の `SubElement` / `append` / `remove` で構造変更した後の保存

### 復元手段必須

lxml 全体 write を試す前に**publish可能 state のSAFE backupを別名で必ず作成**:
```bash
cp v11new_city.twb v11new_city.twb.SAFE_publishable_YYYY-MM-DD
```

失敗時の復元（1コマンド + 再publish）:
```bash
cp v11new_city.twb.SAFE_publishable_YYYY-MM-DD v11new_city.twb && \
python tools/publish.py "<twb>" "<csv_dir>" --name "<name>" --project <project>
```

### 構造変換が必要な場合の正攻法

DB の zone tree のように大規模構造変更が必要な場合は:
1. テキスト置換で **新規 element ブロックを文字列として注入** (例: `<zone type-v2='layout-flow' ...>...</zone>` 全体を1個の string として generate)
2. 既存 element ブロックを `re.sub` で削除/置換
3. 親要素の開始/終了タグを文字列レベルで特定 (`rfind('</zone>')` 等)
4. インデント/改行は手動制御
5. 既存 attribute の quote 形式 (single quote) を維持

関連:
- [[feedback_twb_cloud_compat]] — Cloud publish失敗時の判別
- [[reference_twb_publish_error_codes]] — 403132等エラーコード意味
- [[feedback_twb_paramctrl_layout_nesting]] — 3段ネスト要件（lxml で全体write したくなる典型ケース）
