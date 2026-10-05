---
name: twb-filter-legend-zone-xml
description: dashboard filter/legend zone XML は pane-specification-id='0' + open/close tag + param='[<ds_ref>].[<column-instance>]' の3点必須。シンプル形式は Cloud で無視される
metadata:
  type: feedback
---

Tableau dashboard XMLで filter zone / legend zone を表示するには **3点セット必須**。1つでも欠けると Cloud描画で zone自体が描画されない。

## NG (Cloud側で無視される)
```xml
<zone h='3500' id='70' w='24500' x='500' y='7500'
      name='日別セッション推移' param='[日付]' type-v2='filter' />
```
- 自閉じタグ
- `pane-specification-id` なし
- `param` が `[日付]` (column-instance ID形式でない)

## OK (Cloud描画成功)
```xml
<zone h='3500' id='70' w='24500' x='500' y='7500'
      name='日別セッション推移'
      param='[federated.ds_daily].[none:日付:nk]'
      type-v2='filter'
      pane-specification-id='0'>
  <zone-style>
    <format attr='background-color' value='#ffffff' />
    <format attr='border-color' value='#cccccc' />
  </zone-style>
</zone>
```

### 3点必須要素
1. **`pane-specification-id='0'`**: zone定義の必須属性 (Tableau内部のpane参照)
2. **open/close tag**: `<zone-style>` を子要素として持つため自閉じ不可
3. **`param='[<ds_ref>].[<column-instance>]'`**: 
   - `ds_ref` = pref-demo構造なら `federated.ds_<key>`
   - `column-instance` = 列タイプ別フォーマット:
     - 文字列 dimension: `[none:<col>:nk]` (none-derivation, nominal-key)
     - 数値 measure: `[sum:<col>:qk]` or `[avg:<col>:qk]`
     - 日付 dimension: `[none:<col>:nk]` (date型でも nk が動く)

## Why
2026-05-26 サンプル市v8 Phase 1で実発生。初回 `param='[日付]'` で publish → Cloud視認で filter/legend zone が完全に空白で描画されず。`generate_city_twb_4chart.py:813` の例を参考に3点修正→Cloud描画成功。

## How to apply
- **type-v2 タイプ別**:
  - `type-v2='filter'` — Quick filter (チェックボックスリスト等)
  - `type-v2='color'` — Color凡例
  - `type-v2='size'` — Size凡例
  - `type-v2='shape'` — Shape凡例
- **legend source worksheet選び**: categorical color encoding を持つworksheet を指定。gradient encoding (`color column='[avg:直帰率:qk]'` 等) を持つworksheet を指定すると gradient凡例になり意図しない表示になる
- 表示崩れる場合: width拡張 (w=99000 full-width) or 右サイドバー縦長配置 (x=80000-99500, h=87000)
- twb-generator skill の gen_dashboard 関数で実装済 (v8 generator参照)

## 関連
- [[reference_tableau_native_sankey]] — Sankey VizExtension XML
- [[feedback_twb_v5_textscan_breaks_web_edit_calc]] — pref-demo構造 (datasource側)
- [[feedback_publish_py_absolute_csvdir]] — publish.py csv_dir絶対パス
- 参考TWB: `scripts/generate_city_twb_4chart.py:813` (filter/legend zone正規実装例)
- 参考TWB: `scripts/20260526_generate_city_v8_twb.py:gen_dashboard` (helperで実装済)
