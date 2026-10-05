---
name: twb-ban-kpi-card-pattern
description: Tableau Cloud描画でBAN(Big Ass Number) KPIカードのフォント拡大が効く唯一の XML pattern。customized-label + run fontsize
metadata:
  type: reference
---

# TWB BAN (KPI カード) XML パターン

Cloud描画で巨大数値表示するための **正解 XML pattern**。worksheet-level / pane-level の `<style-rule element='mark-labels'>` は **効かない**。

## なぜこのドキュメントが必要か

サンプル市v10 で BAN×5 のフォント拡大を試みた際、以下が **全て効かなかった**:
- worksheet `<style>` 内 `<style-rule element='mark-labels'>` + `font-size`
- pane `<style>` 内 `<style-rule element='mark-labels'>` + `font-size`

Sub-agent並列でCOO/KeyMetrics/HR-Dashboard.twb から「Total Revenue」「NPS Text」「COGS Label」等の単一数値WS XML構造を解析した結果、**`<customized-label>` + `<formatted-text>` + `<run fontsize='N'>` パターンのみが Cloud描画で効く**ことが判明。

## 正解パターン (Cloud 2024+ で動作確認済)

```xml
<worksheet name='WS1a_BAN_到達率'>
  <table>
    <view>
      <datasources>
        <datasource caption='サンプル市HP統合ハブ' name='federated.city_hub' />
      </datasources>
      <datasource-dependencies datasource='federated.city_hub'>
        <column caption='表示回数' datatype='integer' name='[表示回数 (pages_master.csv)]' role='measure' type='quantitative' />
        <column-instance column='[表示回数 (pages_master.csv)]' derivation='Sum' name='[sum:表示回数_pages:qk]' pivot='key' type='quantitative' />
      </datasource-dependencies>
      <aggregation value='true' />
    </view>
    <style />
    <panes>
      <pane selection-relaxation-option='selection-relaxation-disallow'>
        <mark class='Text' />
        <encodings>
          <text column='[federated.city_hub].[sum:表示回数_pages:qk]' />
        </encodings>
        <customized-label>                                              <!-- ★ここから -->
          <formatted-text>
            <run bold='true' fontcolor='#4E79A7' fontsize='11'>到達率 (主要ページPV)
</run>
            <run bold='true' fontcolor='#1B2A4A' fontsize='22'><![CDATA[<[federated.city_hub].[sum:表示回数_pages:qk]>]]></run>
          </formatted-text>
        </customized-label>                                              <!-- ★ここまで -->
        <style>
          <style-rule element='cell'>
            <format attr='text-align' value='center' />
          </style-rule>
          <style-rule element='mark'>
            <format attr='mark-labels-show' value='true' />               <!-- ★必須 -->
            <format attr='mark-labels-cull' value='true' />               <!-- ★必須 -->
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows></rows>
    <cols></cols>
  </table>
</worksheet>
```

## 必須要素

| 要素 | 説明 |
|------|------|
| `<mark class='Text' />` | Text mark 必須 (Automatic でも可) |
| `<encodings><text column='...' /></encodings>` | 数値フィールドのtext encoding |
| `<customized-label>` | これがフォント拡大の核心 |
| `<formatted-text>` | label内容を formatted-textで定義 |
| `<run ... fontsize='N'>` | **これでサイズ指定**。N=11〜22 推奨 (24以上は桁オーバーフロー「####」になりやすい) |
| `<![CDATA[<[ds].[instance]>]]>` | 数値参照は CDATA で包む |
| `<style-rule element='mark'>` + `mark-labels-show='true'` / `mark-labels-cull='true'` | pane styleに必須 |
| `<rows></rows> <cols></cols>` | 完全空 (rows/cols 棚なし) |

## fontsize目安 (zone width=15800 基準)

| 数値桁 | 推奨 fontsize | 注意 |
|--------|---------------|------|
| 1-3桁 (例: 12) | 36 | 余裕あり |
| 4-7桁 (例: 537,884) | 22 | 22超えると「########」化 |
| 8桁+ (例: 823,981) | 18-22 | カンマ区切り想定 |
| ラベル | 11-13 | 数値の3-5割 |

## 段組デザイン (上=ラベル 下=数値)

`<run>` の末尾に改行 `\n` (XML上は `&#10;` or 実改行) を入れることで上下段組:

```xml
<run fontsize='11'>到達率 (主要ページPV)
</run>
<run fontsize='22'><![CDATA[<...>]]></run>
```

## 配色推奨 (NAVY 基調・SF Tableau パブリックセクター標準)

- ラベル: `fontcolor='#4E79A7'` (副NAVY)
- 数値: `fontcolor='#1B2A4A'` (主NAVY) + `bold='true'`
- 中央揃え: `<style-rule element='cell'><format attr='text-align' value='center' /></style-rule>`

## やってはいけない (Cloud描画で効かない)

```xml
<!-- ❌ worksheet level style-rule -->
<worksheet>
  <table>
    <view>...</view>
    <style>
      <style-rule element='mark-labels'>     <!-- 効かない -->
        <format attr='font-size' value='36' />
      </style-rule>
    </style>
    ...
  </table>
</worksheet>

<!-- ❌ pane level style-rule element='mark-labels' -->
<pane>
  <mark class='Text' />
  <encodings><text column='...' /></encodings>
  <style>
    <style-rule element='mark-labels'>       <!-- 効かない -->
      <format attr='font-size' value='36' />
    </style-rule>
  </style>
</pane>
```

## format-string トラップ

`default-format='p1'` (percentage 1 decimal) は 1.0以上の値で 1 と表示される罠あり (2026-06-03 サンプル市v10で実発生)。
詳細: [[twb-cloud-xml-normalization]] に記載。

代替: `<column ... default-format='c"##,###"'>` (currency-style number) や、formatをWeb Edit手動で `Number Format → Custom` 設定する方が安全。

## Why (なぜこのpatternが必要か)

- 2026-06-03 サンプル市v10 BAN×5実装で worksheet/pane の style-rule が全て効かず Loop 4 round浪費
- 並列sub-agent (Explore) でCOO/KeyMetrics/HR-Dashboard 計4WSのXML構造解析 → `<customized-label>` pattern判明
- 適用1発でBAN×5巨大数値表示成功 → 「Cloud描画でフォント効くXML pattern」として確定

## How to apply

- TWB generator でBAN/KPIカード worksheet生成時、**必ず本patternを使う**
- gen_ws_ban_template 関数で `label_text` + `column_instance` を引数に取り、上記テンプレを返す形が再利用しやすい
- 関連: [[twb-filter-param-zone-patterns]] (dashboard zone XML), [[twb-publish-error-codes]] (publish エラー早見表), [[twb-cloud-xml-normalization]] (Cloud正規化罠)
