---
name: Tableau .twb XML直接生成のルール
description: Claude CodeでTableau .twbファイルをXML生成する際の必須要素と注意点。mapsources/object-graph/manifest/dashboardの正しい構造
type: feedback
---

Tableau .twb (XML) をClaude Codeで生成する際の必須ルール。

**Why:** デモ用ワークブック生成実験（2026-04-01）で5回のエラーを経て確立。テリトリーマップ.twbを参照して正しいパターンを特定。

**How to apply:** .twb XML生成時に以下を必ず守る。

## 必須要素

1. **`<mapsources>`**: 地図を使うワークブックでは2箇所に必要
   - ワークブックレベル: `</datasources>` と `<worksheets>` の間
   - マップワークシートの `<view>` 内: `<datasources>` の直後
   ```xml
   <mapsources><mapsource name='Tableau' /></mapsources>
   ```

2. **`<object-graph>`**: 全datasourceに必須（`ObjectModelEncapsulateLegacy` manifest対応）
   - datasource内の `</connection>` の後、`</datasource>` の前
   - 各テーブルを `<object>` として定義（id付き）
   - metadata-recordの `<object-id>` と一致させる

3. **manifest flags**: `<document-format-change-manifest>` に機能フラグが必要
   - `<AutoCreateAndUpdateDSDPhoneLayouts />` → `devicelayout auto-generated='true'` を使うために必須
   - 存在しないフラグに依存する属性を使うとXMLパースエラー

4. **ダッシュボード**: content model順序が厳密
   ```
   style → size → datasources → datasource-dependencies* → zones → devicelayouts → simple-id
   ```
   - `<dashboards />` (空)は不可。要素があるなら1つ以上の `<dashboard>` が必須
   - なければ `<dashboards>` 要素自体を省略

## 参照ファイル
- テリトリーマップ.twb: `マイ Tableau リポジトリ/ワークブック/テリトリーマップ.twb` （実動するマップ+ダッシュボード付きワークブック）
- 生成スクリプト: `scripts/20260401_generate_twb.py`

## 地図表示の条件
- 列に `semantic-role='[Geographical].[Latitude]'` / `[Longitude]` を設定
- `aggregation='Avg'` を設定（Sumだと座標が壊れる）
- `<style-rule element='map'>` でマップスタイル定義

## ダッシュボードXML生成ルール（2026-04-02解決、2026-04-12更新）
以前は500000: Forbiddenで失敗していたが、以下で解決:
1. `<dashboard enable-sort-zone-taborder='true'>` — この属性が必須
2. `<size maxheight='1050' maxwidth='1400' minheight='1050' minwidth='1400' sizing-mode='fixed' />` — **fixed+min/max指定が推奨**（automatic も動作するがCloud表示でゾーン重複する）。旧ルール「automaticのみ」は誤り（2026-04-12訂正）
3. `<devicelayouts><devicelayout auto-generated='true' name='Phone'>` — Phone layoutが**必須**。これがないとpublish 500エラー

### 動作するダッシュボード構成
```xml
<dashboard enable-sort-zone-taborder='true' name='名前'>
  <style />
  <size sizing-mode='automatic' />
  <zones>
    <zone h='100000' id='4' type-v2='layout-basic' w='100000' x='0' y='0'>
      <!-- 2x2グリッド: id=3,5,6,7 各シートのname属性がworksheet名と一致 -->
      <zone h='49006' id='3' name='シート1' w='49501' x='499' y='993'>...</zone>
      <zone h='49006' id='5' name='シート2' w='49501' x='50000' y='993'>...</zone>
      <zone h='49008' id='6' name='シート3' w='49501' x='499' y='49999'>...</zone>
      <zone h='49008' id='7' name='シート4' w='49501' x='50000' y='49999'>...</zone>
    </zone>
  </zones>
  <devicelayouts>
    <devicelayout auto-generated='true' name='Phone'>
      <size maxheight='1200' minheight='1200' sizing-mode='vscroll' />
      <zones><!-- layout-flow(vert)にfixed-size='280'で各シートを配置 --></zones>
    </devicelayout>
  </devicelayouts>
  <simple-id uuid='...' />
</dashboard>
```

### dashboard window要素
```xml
<window class='dashboard' maximized='true' name='ダッシュボード名'>
  <viewpoints>
    <viewpoint name='シート1'><zoom type='entire-view' /></viewpoint>
    ...
  </viewpoints>
  <active id='7' />  <!-- zone idのいずれか。-1は避ける -->
  <simple-id uuid='...' />
</window>
```
- `<device-preview />` は不要（Desktop生成TWBにもない）
- `<active id='-1' />` ではなく実在するzone idを使う

## マークラベル表示（mark-labels-show）
- `<style>` を **pane内** に配置（table levelでは効かない）
- **シンプルなラベル表示**（dimension名をそのまま表示）: `<text column>` + `mark-labels-show` だけでOK。`customized-label` は不要
  ```xml
  <pane>
    <mark class='Circle' />
    <encodings>
      <text column='[DS].[none:city_name:nk]' />
    </encodings>
    <style>
      <style-rule element='mark'>
        <format attr='mark-labels-show' value='true' />
        <format attr='mark-labels-cull' value='true' />
      </style-rule>
    </style>
  </pane>
  ```
- **カスタムフォーマットラベル**（複数フィールドを組み合わせ）: `customized-label` + `&lt;&gt;` デリミタが必要
- **Line chartの末尾ラベル**: `<format attr='mark-labels-mode' value='most-recent' />` で最終ポイントのみ表示
- `mark-labels-cull='true'` で重なりを自動カリング、`'false'` で全ラベル強制表示

## 数値フォーマット（default-format）
- `default-format='n1'` は**NG**（値が文字通り1になる）
- 正しい構文: `default-format='n#,##0.0'`（小数1桁）
- `n` プレフィックス + Excel形式フォーマット文字列

## melted CSV（縦持ち変換）パターン
- stacked bar / highlight table にはmelted CSVが最も安定
- 元データ(横持ち) → city_name, type, value の3列に変換
- ソート用にtype名に "01_", "02_" プレフィックス + aliases で表示名変換

## 空間ファイル接続（2026-04-02追加）
- TWB XMLで `class='geojson'` や `class='spatial_file'` は**Tableauバージョン依存で失敗する**
- **Polygon CSV方式が最も安全**: shapefile→CSV変換（path_id, point_order, lat, lon）→ `mark class='Polygon'`
- Polygon CSVの構造:
  ```
  chocho_code, chocho_name, jinko, path_id, point_order, lat, lon
  ```
- encodings: `<color>` で塗り分け、`<path column='[point_order]'>` で頂点順序、`<lod>` で地区単位集約
- Shapefile ZIPはTableau Desktop GUIから手動接続する方式なら確実に動く（ユーザー確認済み）

## ダッシュボードwindow要素（2026-04-02修正、2026-04-15追記）
- content model: `(viewpoints, active, simple-id)` — device-previewは不要
- `<active id='N' />` のNは実在するzone id（-1は避ける）
- **`<cards>` 要素はworksheet windowのみ。dashboard windowに入れるとCloud publish 500エラー**（2026-04-15確定）

## object-graph構造ルール（2026-04-15追記）
- `<object-graph>` 直下に `<objects>` ラッパーが**必須**
- object内部は `<properties context=''>` + 完全な `<relation>` 構造
- `<bindings>` 方式は不可（Cloud非互換）
```xml
<object-graph>
  <objects>
    <object caption='file.csv' id='obj_id'>
      <properties context=''>
        <relation connection='nc_id' name='file.csv' table='[file#csv]' type='table'>
          <columns ...>...</columns>
        </relation>
      </properties>
    </object>
  </objects>
</object-graph>
```

## Parameters DS XML構造（2026-04-05追加）
Parameters DSは特殊構造。以下を守らないとTableau Cloudパブリッシュ時に500000エラー:

1. **`<datasource>`タグに`caption`属性を付けない** — `hasconnection='false' inline='true' name='Parameters'` のみ
2. **parameter columnに`<calculation class='tableau' formula='デフォルト値' />`が必須**
3. `<member>`にalias属性は不要（value属性のみでOK）

```xml
<datasource hasconnection='false' inline='true' name='Parameters' version='18.1'>
  <aliases enabled='yes' />
  <column caption='表示名' datatype='string' name='[ParamName]'
          param-domain-type='list' role='measure' type='nominal'
          value='&quot;デフォルト値&quot;'>
    <calculation class='tableau' formula='&quot;デフォルト値&quot;' />
    <members>
      <member value='&quot;値1&quot;' />
      <member value='&quot;値2&quot;' />
    </members>
  </column>
</datasource>
```

## textscan connection属性（2026-04-08追加）
- `password=''` と `server=''` を**付けない** — Cloud publish時に403エラーの原因
- 正しい構文: `<connection class='textscan' directory='...' filename='...' />`
- publish.pyがdirectoryを'Data'に書き換えるので、生成時のdirectoryは任意

## text-align属性（2026-04-08追加）
- `<format attr='text-align' value='left' />` — 値は**文字列**（left/right/center）
- 数値（0/1/2）は無効（Tableauに無視される）
- Text markの左寄せには `<style-rule element='cell'>` 内で使用

## BIN計算フィールド制約（2026-04-08追加）
- `<calculation class='bin'>` はcalculated fieldを参照できない（Cloud publish時エラー）
- 代替: `<calculation class='tableau'>` でIF/THEN式を使う
- 例: `IF [Calc_field] < 5 THEN "0-5" ELSEIF ... END`

## TWBX作成ルール（2026-04-05追加）
- **publish.pyの`create_twbx()`を必ず使う** — CSVパスを`Data/`に書き換える処理が必須
- 手動でZIP作成する場合も `directory='CSV_DIR'` → `directory='Data'` の置換を忘れないこと
- パス未変換のまま publish すると 403132（接続失敗）エラー

## paramctrlゾーン定義（2026-04-05追加）
- `type-v2='paramctrl'` ゾーンに `name` 属性を**付けない**
- filter/colorゾーンの `name` はソースワークシート参照だが、paramctrlにはこの概念がない
- `name` を付けると色凡例として誤レンダリングされる
- 正しい構文: `<zone id='N' type-v2='paramctrl' w='...' h='...' x='...' y='...' param='[Parameters].[パラメータ名]'>`

## customized-labelのフィールド参照（2026-04-05追加）
- `<customized-label>` 内でフィールド値を表示するには `&lt;` `&gt;` デリミタが**必須**
- デリミタなしの `<run>[DS].[field]</run>` はリテラル文字列として表示される
- 正しい構文: `<run>&lt;</run><run>[DS].[sum:field:qk]</run><run>&gt;</run>`
- 集計関数を含む文字列計算フィールド（`STR(SUM(...))` 等）は TWB XML では不安定。個別メジャーを text encoding に並べて customized-label でフォーマットする方式が安定

## Dual Axis XML構文（2026-04-05解決）
Cloud publishで動作する正しいDual Axis構文:

1. **rows/colsで2メジャーを`+`結合**: `([DS].[avg:measure1:qk] + [DS].[sum:measure2:qk])`
2. **1番目のpane**: y-axis-name不要（デフォルトで1番目のメジャー軸に紐づく）
3. **2番目のpane**: `y-axis-name='[DS].[sum:measure2:qk]'` で2番目の軸に紐づける（`(2)` suffixは不要）
4. **mark-sizing**: `<mark-sizing mark-sizing-setting='marks-scaling-off' />` でBar幅固定
5. **透明度**: `<format attr='mark-transparency' value='128' />` でBarを半透明に

```xml
<panes>
  <pane selection-relaxation-option='selection-relaxation-allow'>
    <mark class='Line' />
    <encodings><color column='[DS].[none:dim:nk]' /></encodings>
  </pane>
  <pane selection-relaxation-option='selection-relaxation-allow' y-axis-name='[DS].[sum:measure2:qk]'>
    <mark class='Bar' />
    <mark-sizing mark-sizing-setting='marks-scaling-off' />
  </pane>
</panes>
<rows>([DS].[avg:measure1:qk] + [DS].[sum:measure2:qk])</rows>
```
- 以前の `(2)` suffix方式は**使わない**。Tableau Public実VizのXMLでは `y-axis-name` でメジャーを直接指定する方式が安定

## dashboard zoneのis-fixed挙動（2026-04-08追加）
- `is-fixed='true'` + `fixed-size='N'` はhorz flowで**幅をピクセル固定**する
- **両方のchildに付けると高さ方向にも影響**し、レイアウトが崩れる（上段が巨大化して下段が消える）
- 推奨: 片方のchildのみにis-fixedを付け、もう片方は残りスペースを自動取得させる
- `w='N'` のみ（is-fixedなし）はTableauが**コンテンツ幅で自動配分**するため、指定値が無視されることがある

## 連続色凡例/フィルターの最小幅制約（2026-04-08追加、2026-04-12更新）
- `layout-flow`コンテナ内では、連続メジャーの色凡例（`type-v2='color'`）やフィルター（`type-v2='filter'`）に**Tableauが最小幅を強制**する → サイドバーやKPI行に配置すると幅指定が無視され余白が発生
- **回避策: `layout-basic`（絶対座標）のルートzone直下にフィルター/色凡例を直接配置する** → 最小幅制約が効かず `w='7000'` 等の指定がそのまま反映される（pref TWB 2DB化で実証、2026-04-12）
- `layout-flow`入れ子サイドバーは避け、フラット絶対座標で配置するのが安全
- paramctrlゾーンには`name`属性を付けない（既知ルール）

## ダッシュボード内シートタイトル非表示（2026-04-08追加）
- `<window>` の `<cards><edge name='top'>` から `<card type='title' />` のstripを除去すると、ダッシュボード内のシートタイトルが非表示になる
- `show-title='false'` をzone属性に付けても効かない
- `<title><formatted-text><run /></formatted-text></title>` をworksheetに追加しても効かない
- **window cards方式が唯一の確実な方法**

## REST APIでTWBXダウンロード（2026-04-08追加）
- Tableau REST API認証はXML形式（`Content-Type: application/xml`）が必要。JSON形式は失敗する
- ダウンロードURL: `/api/3.24/sites/{siteId}/workbooks/{wbId}/content`
- .mcp.jsonからPAT_NAME/PAT_VALUE/SERVER/SITE_NAMEを取得して認証
