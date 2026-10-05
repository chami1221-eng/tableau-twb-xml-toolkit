---
name: twb-relation-calc-limitation
description: リレーションDS内のcross-table calc参照は publish 400011で失敗する。Cloud Web Edit手動追加が安全
metadata:
  type: feedback
---

# リレーションDS内 cross-table calc は publish 400011 で失敗

## ルール
1 federated DS 内の複数論理テーブルをまたぐ計算フィールド（calculated field）を generator 生成 XML で注入してはいけない。
特に以下のパターンは **400011 Bad Request "Tableau encountered an error while parsing the workbook"** で失敗する：

```python
# NG: cross-table calc 注入
"formula": "SUM([表示回数 (pages_master.csv)]) / SUM([表示回数])"  # ハブと衛星をまたぐ

# NG: LOD式 + cross-table
"formula": "IIF([表示回数 (pages_master.csv)] > {FIXED : AVG([表示回数 (pages_master.csv)])} * 1.5 ...)"

# NG: 他calc参照
"formula": "COUNTD( IIF([Calculation_xxx]=1, [ページタイトル], NULL) )"
```

## 推奨対応
1. **TWB生成段階では calc 注入しない**（空文字を返す関数にする）
2. publish 通過後、**Tableau Cloud Web Edit で手動追加**
3. Web Edit で動作確認できた calc XMLをコピー → 次回 generator に反映

## Why
- 2026-06-03 サンプル市v9 Phase2 で「到達率 = pages表示回数 / daily表示回数」を generator 注入→ publish 400011
- calc 削除のみで通過 (windows + dashboard 構造は問題なしと切り分け確定)
- リレーションDS の cross-table 計算は Tableau Desktop で対話的に作成した場合のみ正しいXMLが生成される
- 手書き XMLでは `[列名 (csv名)]` のリネーム参照式がパースエラーを誘発する模様（未解明）

## How to apply
- 新規リレーションDS generator では calc_fields_xml() を空文字返却にする
- 質ベースKPI (到達率/直行率/詰まり度) は Cloud Web Edit で追加してXMLを観察 → 学習資産にする
- 関連: [[feedback_twb_relation_xml_structure]] (リネーム形式)、[[feedback_twb_v5_textscan_breaks_web_edit_calc]] (Web Edit calc作成可否)
