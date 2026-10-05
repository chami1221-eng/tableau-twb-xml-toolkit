# TWB XML パターンカタログ

80個以上のTableau Public/Cloud Vizの生XMLから抽出した実装パターン集（57パターン / 68早見表エントリ）。
TWB生成時にこのカタログを参照し、要望に応じたパターンを組み合わせる。

## ⚠️ 最重要ルール (2026-05-26追加・違反厳禁)

### datasource構造は必ず pref-demo構造を採用すること

新規TWB生成scriptは **`generate_pref_twb.py` の構造を必ずbase にする**。具体的には以下5要素を全て満たすこと:

1. **`<connection class='federated'>` で wrap** (datasource直下)
2. 内側に `<named-connection>` を置き、その中に `<connection class='textscan'>` を入れる
3. `<columns>` に `character-set='UTF-8' header='yes' locale='ja_JP' separator=','` 属性
4. `<metadata-record class='capability'>` をDS全体に1個必ず入れる (character-set/collation/locale/field-delimiter等の `<attribute>`)
5. `<metadata-record class='column'>` の `<remote-type>` を正しい型コード (integer=20, real=5, string=129) に。string列は `<collation flag='0' name='LJA_RJP' />` も必須

**禁止構造** (`<connection class='textscan'>` を datasource直下に直接配置):
```xml
<datasource name='ds_xxx' version='18.1'>
  <connection class='textscan' directory='...' filename='...'>   ← ❌ Cloud Web Edit Calc validationを破壊
```

**正解構造**:
```xml
<datasource name='federated.ds_xxx' version='18.1'>
  <connection class='federated'>   ← ✅
    <named-connections>
      <named-connection name='textscan.nc_xxx'>
        <connection class='textscan' directory='...' filename='...' />
      </named-connection>
    </named-connections>
    ...
```

**Why**: 2026-05-26 サンプル市demo構築で発覚。v5_3 base script (textscan直接) は publish成功してもCloud Web Editでの **新規Calculated Field作成が LogicException で完全ブロック** される。pref-demo構造 (federated wrap + capability metadata + 型コード+collation) で完全解決済。詳細: `../shared/memory/feedback_twb_v5_textscan_breaks_web_edit_calc.md`

**影響範囲** (v5_3 base継承scriptはすべて pref-demo構造へリライト要):
- `scripts/20260525_generate_city_hp_v*.py`
- `scripts/20260526_generate_city_v6*_twb.py`
- `scripts/20260415_generate_city_usage_twb.py`
- `scripts/20260402_generate_district_twb.py`
- `scripts/20260401_generate_twb*.py`

**正しい参考実装**:
- base template: `scripts/generate_pref_twb.py` (named_conn/capability_meta/col_meta/table_rel/meta_for_table ヘルパー)
- 実証済適用例: `scripts/20260526_generate_city_v7_twb.py` (Web Edit Calc作成OK確認済)

### publish.py呼び出し時は `--name` 必須

`publish.py` の `--name` は必須引数。default依存禁止。2026-05-26に default value だった「別案件デモWB」を意図せず上書き破壊した事故あり。詳細: `../shared/memory/feedback_publish_py_name_required.md`

### publish.py の `csv_dir` は絶対パス必須

`publish.py` 内部の `directory='{csv_dir}'` → `directory='Data'` 文字列置換が、TWB内のハードコード絶対パス (例: `C:/Users/.../masters`) と一致する必要がある。相対パスで渡すと置換が動かず Cloud側で `FAKEPATH directory missing` エラーが datasource数分発生する。2026-05-26 v8で実発生。詳細: `../shared/memory/feedback_publish_py_absolute_csvdir.md`

### dashboard filter/legend zone は dashboard_zone_helpers.py 経由で生成

filter/legend zone XML は **3点セット必須** (1つでも欠けると Cloud描画されない):
1. **`pane-specification-id='0'` 属性**
2. **open/close tag** (`<zone .../>` 自閉じは不可)
3. **`param='[<ds_ref>].[<column-instance>]'` 形式** (シンプルな `[日付]` は無視される)

```xml
<!-- ❌ NG: Cloud描画されない -->
<zone h='3500' id='70' w='24500' x='500' y='7500'
      name='日別セッション推移' param='[日付]' type-v2='filter' />

<!-- ✅ OK -->
<zone h='3500' id='70' w='24500' x='500' y='7500'
      name='日別セッション推移'
      param='[federated.ds_daily].[none:日付:nk]'
      type-v2='filter' pane-specification-id='0'>
  <zone-style>
    <format attr='background-color' value='#ffffff' />
    <format attr='border-color' value='#cccccc' />
  </zone-style>
</zone>
```

**新規TWB生成は `dashboard_zone_helpers.py` の helper関数 (`make_filter_zone`, `make_legend_zone`, `field_ref`, `top_legend_preset`, `right_sidebar_filter_preset`) を経由して生成すること**。3点必須要素を自動充足する。詳細: `../shared/memory/feedback_twb_filter_legend_zone_xml.md`、`../skills/twb-generator/SKILL.md`「Dashboard Zone Helpers」セクション

**legend source worksheet選び**: categorical color encoding を持つworksheetを指定。gradient encoding (`color column='[avg:直帰率:qk]'` 等) を持つworksheetを指定すると gradient凡例になる。

**推奨レイアウト**:
- 上部 full-width 色凡例: y=7500, w=99000, h=4000 (`top_legend_preset`)
- 右サイドバー縦長 filter: x=80000, y=11500, w=19500, h=87000 (`right_sidebar_filter_preset`)
- worksheet zones は w=79000 (x=500-79500) に縮める前提

---

> 学習元Viz一覧: `out/reports/20260405_tableau_public_twb_reference_vizzes.md`
> 個別分析: `out/research/20260405_*_twb_analysis.md`, `20260408_*_twb_analysis.md`
> 追加解析(2026-04-08): Call Center Capacity & Service Analytics, 建設案件スケジュール管理, Melbourne Public Transport Frequency, 勤怠管理Viz, 県有施設マップ（山口県）
> 追加学習(2026-04-08): Insurance Operations Dashboard, Map Layers Visualization Catalogue, テキストマイニングファーストフード, 山口県クマ出没MAP, ODPOダッシュボード
> 追加学習2(2026-04-08): Melbourne Public Transport, Workforce Plan, Narendra Modi Twitter, KPI Viz, 人件費デモ, きよこじまViz, 上竹Viz, せりざわViz, DPC2021, 横浜医療DB, FTAS合祀DB, 沖縄市統計, Iron Viz 2026(Empire/LateNight/Sociable), Pulse-inspired DB, African Languages, KPI Cards VizExt, Customer Analytics
> Cloud学習(2026-04-09): ビジュアル表現, 品質管理_QC7つ道具, 経営層向けダッシュボード, Banking Customer Insights, 工場でのプロセス管理, Key Metrics Dashboard (Tableau Cloud)

---

## 1. アクションパターン

### 1-1. フィルタアクション (tsl-filter)

**簡易版** (同一DS・全フィールド自動マッチ):
```xml
<action caption="散布図→他シートフィルタ" name="[Action1_xxx]">
  <activation auto-clear="true" type="on-select" />
  <source dashboard="DB名" type="sheet" worksheet="ソースシート" />
  <command command="tsc:tsl-filter">
    <param name="exclude" value="ソースシート" />  <!-- 自己フィルタ防止 -->
    <param name="target" value="DB名" />
  </command>
</action>
```

**完全版** (cross-DS field mapping必須・XML注入時はこちら推奨):
```xml
<action caption="ページ→日別セッション" name="[Action1_{32hex-UUID}]">
  <activation auto-clear="true" type="on-select" />
  <source dashboard="DB2 異常検知" type="sheet" worksheet="ハイライト_PV" />
  <link caption="ページ→日別セッション" delimiter="," escape="\"
        expression="tsl:{URL-enc dashboard}?{URL-enc target_col}~s0=&lt;{source_col literal}~na&gt;"
        include-null="true" multi-select="true" url-escape="true" />
  <command command="tsc:tsl-filter">
    <param name="exclude" value="ハイライト_直帰率,ハイライト_滞在秒,ハイライト_PV" />
    <param name="target" value="DB2 異常検知" />
  </command>
</action>
```

**expression構築 (Python例)**:
```python
import urllib.parse, uuid
def make_action_name(n): return f"Action{n}_{uuid.uuid4().hex.upper()}"

def build_expression(dashboard, target_ds, target_field, source_ds, source_field):
    db_enc = urllib.parse.quote(dashboard, safe='')
    target_col_enc = urllib.parse.quote(f"[{target_ds}].[{target_field}]", safe='')
    source_col_raw = f"[{source_ds}].[{source_field}]"
    return f"tsl:{db_enc}?{target_col_enc}~s0=&lt;{source_col_raw}~na&gt;"
```

**`</actions>` 直前に DS dependencies を必須登録**:
```xml
<datasources>
  <datasource caption="月別集計" name="ds_pages" />
  <datasource caption="ページ別日別" name="ds_pages_daily" />
</datasources>
<datasource-dependencies datasource="ds_pages">
  <column datatype="string" name="[ページタイトル]" role="dimension" type="nominal" />
</datasource-dependencies>
<datasource-dependencies datasource="ds_pages_daily">
  <column datatype="string" name="[ページタイトル]" role="dimension" type="nominal" />
</datasource-dependencies>
```

**禁止形式** (Cloud roundtripで剥落):
```xml
<!-- ❌ 旧Desktop形式。publish通るが <target>/<field-instances> がCloud側で消える -->
<action ...>
  <source ... />
  <target dashboard="..." worksheet="..." />
  <field-instances>
    <field-instance source="[ds_a].[field]" target="[ds_b].[field]" />
  </field-instances>
</action>
```

**運用ルール** (XML注入時の必須手順):
1. 必ず最初に1個 Web Edit で manual 作成 → download → XML確認してから自動生成
2. 既存 `<actions>` block を全置換せず **append-only** で追加 (手動作成版を消さない)
3. publish 直後に download し `<link>` と `<command>` が保持されたか確認
4. action name は `[ActionN_{32hex-UUID}]` 形式必須

詳細: `../shared/memory/feedback_twb_action_xml_injection.md`

### 1-2. ハイライトアクション (brush)
```xml
<action caption="ハイライト" name="[Action2_{32hex-UUID}]">
  <activation auto-clear="true" type="on-hover" />
  <source dashboard="DB名" type="sheet" worksheet="ソースシート" />
  <command command="tsc:brush">
    <param name="target" value="DB名" />
  </command>
</action>
```

- **on-hover** は `tsc:brush` 必須 (`tsc:tsl-filter` を on-hover で使うと動かない)
- brush は同一DS内のフィールド名一致で自動ハイライト
- cross-DS でハイライト連動したい場合: 両DSに同名フィールドが必要 (or `<link>` で明示マッピング - filterと同じ書式)

### 1-3. パラメータアクション (edit-parameter-action)
```xml
<edit-parameter-action caption="パラメータ更新" name="[Action3_xxx]">
  <activation type="on-select" />
  <source dashboard="DB名" type="sheet" worksheet="ソースシート" />
  <agg-type type="attr" />
  <clear-option type="do-nothing" value="s:LROOT:" />  <!-- string default -->
  <!-- integer default: value="i:0" -->
  <params>
    <param name="source-field" value="[DS名].[none:フィールド名:nk]" />
    <param name="target-parameter" value="[Parameters].[パラメータ名]" />
  </params>
</edit-parameter-action>
```
- `clear-option`: 選択解除時の挙動。`do-nothing`=維持, `all`=デフォルトに戻す
- `agg-type`: `attr`=属性値, `sum`/`avg`等=集計値

### 1-4. セットアクション (edit-group-action)
```xml
<edit-group-action caption="セット更新" name="[Action4_xxx]">
  <activation type="on-select" />
  <source datasource="DS名" type="datasource" />
  <!-- or: <source dashboard="DB名" type="sheet" worksheet="シート名" /> -->
  <single-select value="true" />  <!-- 単一選択のみ。省略=複数選択可 -->
  <add-or-remove-marks value="assign" />  <!-- assign=置換, add=追加, remove=削除 -->
  <params>
    <param name="selection-clear-set-option" value="exclude-all" />
    <!-- exclude-all=選択解除時にセット空に, keep=維持 -->
    <param name="target-group" value="[DS名].[セット名]" />
  </params>
</edit-group-action>
```

### 1-5. Go-to-sheet ボタン（ダッシュボード間ナビゲーション）
```xml
<zone type-v2="dashboard-object" id="351" h="2304" w="1200">
  <button action='tabdoc:goto-sheet window-id="{遷移先DB-GUID}"' button-type='text'>
    <button-visual-state>
      <caption>ページ名</caption>
      <button-caption-font-style fontcolor='#ffffff' fontname='Tableau Medium' />
      <format attr='background-color' value='#080a44' />
    </button-visual-state>
  </button>
</zone>
```
- `window-id`: 遷移先ダッシュボードのGUID
- ダッシュボードごとに `<simple-id uuid='{GUID}' />` でIDが振られる

---

## 2. セット定義

### 2-1. セット (group) の定義
```xml
<!-- datasource内に定義 -->
<group caption="Category Set" name="[Category Set]" name-style="unqualified"
       user:ui-builder="filter-group">
  <!-- 初期メンバー（空セット） -->
  <groupfilter function="empty-level" member="[Category]"
               user:ui-domain="database" user:ui-enumeration="inclusive"
               user:ui-marker="enumerate" />
</group>

<!-- 初期メンバーあり -->
<group caption="State Set" name="[State Set]" name-style="unqualified"
       user:ui-builder="filter-group">
  <groupfilter function="union" user:ui-domain="database"
               user:ui-enumeration="inclusive" user:ui-marker="enumerate">
    <groupfilter function="member" level="[State]" member="&quot;Texas&quot;" />
    <groupfilter function="member" level="[State]" member="&quot;Colorado&quot;" />
  </groupfilter>
</group>
```

### 2-2. セット参照の計算フィールド
```xml
<!-- セットをBool条件として参照 -->
<column caption="Sub-Category Level" datatype="string" name="[Calc_xxx]"
        role="dimension" type="nominal">
  <calculation class="tableau"
    formula='IF [Category Set]&#10;THEN [Sub-Category]&#10;ELSE &quot;&quot;&#10;END' />
</column>
```

### 2-3. セットのIn/Outエンコーディング
```xml
<encodings>
  <color column="[DS名].[io:Category Set:nk]" />
</encodings>
```
- `io:` prefix = In/Out encoding（セット内=In, 外=Out で色分け）

---

## 3. Dynamic Zone Visibility (DZV)

ゾーンの表示/非表示をBool計算フィールドで条件制御する。

### 3-1. Bool計算フィールド
```xml
<column caption="Show Sales" datatype="boolean" name="[Calc_show_sales]"
        role="measure" type="quantitative">
  <calculation class="tableau"
    formula='[Parameters].[Parameter 1] = &quot;Sales&quot;' />
</column>
```

### 3-2. ダッシュボードゾーンに `hidden-by-user` を設定
```xml
<!-- 初期非表示（DZVで制御されるゾーン） -->
<zone h="89286" hidden-by-user="true" id="24" param="vert"
      type-v2="layout-flow" w="100000" x="0" y="10714">
  <!-- 子ゾーン群 -->
</zone>
```

### 3-3. datagraph セクション（TWB末尾）
```xml
<datagraph>
  <graph>
    <node-execution-subgraphs>
      <pair execution-subgraph-guid="xxx" node-guid="field-node-guid" />
      <pair execution-subgraph-guid="xxx" node-guid="zone-vis-node-guid" />
    </node-execution-subgraphs>
    <nodes>
      <!-- Bool計算フィールド→値出力 -->
      <single-value-field-node
        fieldname="[DS名].[Calc_show_sales]"
        fieldname-input-guid="input-guid"
        node-guid="field-node-guid"
        value-output-guid="output-guid" />
      <!-- ゾーンの表示制御ノード -->
      <dashboard-zone-visibility-node
        dashboard-identifier="{DB-GUID}"
        node-guid="zone-vis-node-guid"
        visibility-input-guid="vis-input-guid"
        zone-id="24" />
    </nodes>
    <edges>
      <!-- 計算フィールドの出力 → ゾーンのvisibility入力 を接続 -->
      <edge from="output-guid" to="vis-input-guid" />
    </edges>
    <pin-values />
  </graph>
</datagraph>
```
- 各GUID はランダム生成（`uuid.uuid4()`）
- 1つのBool計算フィールド → 1つのゾーンの表示制御
- ゾーンに `hidden-by-user="true"` + datagraph edgeの組み合わせで動的制御

---

## 4. Show/Hide Toggle Button

### 4-1. テキストボタン
```xml
<zone fixed-size="220" h="7778" id="24" is-fixed="true"
      type-v2="dashboard-object" w="20833">
  <button action="" button-type="text">
    <toggle-action>tabdoc:toggle-button-click-action
      window-id="{DB-GUID}" zone-id="24"
      zone-ids=[10]</toggle-action>
    <!-- 表示時のスタイル -->
    <button-visual-state>
      <caption>Hide Filters</caption>
      <button-caption-font-style fontcolor="#ffffff" fontname="Tableau Bold"
                                  fontsize="12" />
      <format attr="background-color" value="#080a44" />
    </button-visual-state>
    <!-- 非表示時のスタイル -->
    <button-visual-state>
      <caption>Show Filters</caption>
      <button-caption-font-style fontcolor="#ffffff" fontname="Tableau Bold"
                                  fontsize="12" />
      <format attr="background-color" value="#080a44" />
    </button-visual-state>
  </button>
</zone>
```

### 4-2. 画像ボタン
```xml
<zone type-v2="dashboard-object" id="25" is-fixed="true" fixed-size="30">
  <button action="">
    <toggle-action>tabdoc:toggle-button-click-action
      window-id="{DB-GUID}" zone-id="25"
      zone-ids=[16]</toggle-action>
    <button-visual-state>
      <image-path>Image/bars0.png</image-path>
      <tooltip-text>Hide Order Info</tooltip-text>
    </button-visual-state>
    <button-visual-state>
      <image-path>Image/BarsFull.png</image-path>
      <tooltip-text>Show Order Info</tooltip-text>
    </button-visual-state>
  </button>
</zone>
```
- `zone-ids=[10]`: トグル対象のゾーンID
- 2つの `button-visual-state`: 表示中/非表示中のそれぞれの見た目

---

## 5. Reference Line

```xml
<!-- worksheetのpane内に定義 -->
<reference-line
  axis-column="[DS名].[sum:Sales:qk]"
  enable-instant-analytics="true"
  formula="constant"
  id="refline0"
  label-type="none"
  scope="per-table"
  tooltip-type="none"
  value="0.0"
  value-column="[DS名].[sum:Sales:qk]"
  z-order="1" />

<!-- スタイル定義 -->
<style-rule element="refline">
  <format attr="fill-above" id="refline0" value="#00000000" />
  <format attr="fill-below" id="refline0" value="#00000000" />
  <format attr="stroke-size" id="refline0" value="1" />
  <format attr="stroke-color" id="refline0" value="#898989" />
  <format attr="line-pattern-only" id="refline0" value="dashed" />
  <format attr="line-visibility" id="refline0" value="on" />
</style-rule>
```
- `formula`: `constant`=固定値, `average`=平均, `median`=中央値, `total`=合計
- `scope`: `per-table`=テーブル単位, `per-pane`=ペイン単位, `per-cell`=セル単位

---

## 6. Dual Axis

> ⚠️ `(2)` suffix方式はCloud publishで拒否される。以下の**3ペイン方式**（基準ペイン+id=1/id=2+style-rule+Measure Names color+rows加算）が動作実績あり。
> **2ペイン方式（基準ペイン省略）は上下2ペイン分割になり本物の二重軸にならない**（2026-07-06 サンプル市 WS3実装で確認）。

### 動作実績パターン: 3ペイン方式

```xml
<view>
  <datasource-dependencies datasource="[DS]">
    <!-- Measure Names をcolor encodingに使うので明示 -->
    ...(略)...
  </datasource-dependencies>
  <aggregation value="true" />
</view>
<style>
  <!-- ★軸同期のstyle-rule必須。synchronized='false' で独立軸(推奨) / 'true' で強制同期 -->
  <style-rule element="axis">
    <encoding attr="space" class="0"
      field="[DS].[sum:measure2:qk]" field-type="quantitative"
      fold="true" scope="rows" synchronized="false" type="space" />
  </style-rule>
</style>
<panes>
  <!-- 基準ペイン（Automatic mark、Measure Names color） -->
  <pane selection-relaxation-option="selection-relaxation-allow">
    <view><breakdown value="auto" /></view>
    <mark class="Automatic" />
    <encodings>
      <color column="[DS].[:Measure Names]" />
    </encodings>
  </pane>
  <!-- 左軸ペイン: 線 -->
  <pane id="1" selection-relaxation-option="selection-relaxation-allow"
        y-axis-name="[DS].[sum:measure1:qk]">
    <view><breakdown value="auto" /></view>
    <mark class="Line" />
    <encodings>
      <color column="[DS].[:Measure Names]" />
    </encodings>
  </pane>
  <!-- 右軸ペイン: 棒 -->
  <pane id="2" selection-relaxation-option="selection-relaxation-allow"
        y-axis-name="[DS].[sum:measure2:qk]">
    <view><breakdown value="auto" /></view>
    <mark class="Bar" />
    <encodings>
      <color column="[DS].[:Measure Names]" />
    </encodings>
  </pane>
</panes>
<rows>([DS].[sum:measure1:qk] + [DS].[sum:measure2:qk])</rows>
<cols>[DS].[none:dim:ok]</cols>
```

### 必須4要素（1つでも欠けると上下2ペイン分割になる）
1. **panes構成 = 3ペイン**: 基準ペイン+`<pane id='1' y-axis-name='X'>`+`<pane id='2' y-axis-name='Y'>`
2. **各ペインに `<encodings><color column='[DS].[:Measure Names]'/></encodings>`**（凡例統一・軸識別）
3. **`<style><style-rule element='axis'><encoding attr='space' scope='rows' synchronized='false' .../></style-rule></style>`**（軸同期指定。false=独立軸、true=強制同期）
4. **`<rows>([DS].[sum:X:qk] + [DS].[sum:Y:qk])</rows>`**（加算式で二重軸を明示）

### 動作実績・参考実装
- **2026-07-06 サンプル市ハンズオン WS3**: 受入件数×受入金額(億円)の14年推移で Cloud描画成功
- **参照実装元**: `体験会用サンプルワークブック.twb` row720-740（Superstoreの売上×利益 二重軸）
- **参考コード**: `scripts/20260705_generate_dualaxis_twb_v3.py` の `ws_dualaxis_generic()` ヘルパー関数

### 演出オプション
- 右軸ペインに `<mark-sizing mark-sizing-setting='marks-scaling-off'/>` でBar幅固定
- 右軸ペインstyleに `<format attr='mark-transparency' value='128'/>` でBar半透明化
- `synchronized='true'` は同一単位の系列（例: 予算vs実績）で使用、それ以外は`false`推奨

### 「何を重ねるか」の意思決定
- 二重軸で重ねる2メジャーの選定は**机上検討でなく実装比較で決める**（複数パターンをpublishして描画を目視選定）
- 「軸スケールが2桁以上非対称になる組み合わせ」が最も刺さる（例: サンプル市 受入1.10億 vs 流出46.6億の10倍差 → 視覚的に「非対称性」が説明不要）

---

## 7. Spatial / 地図パターン

### 7-1. 空間関数
```
BUFFER([geometry], [distance_param], 'km')    -- バッファ生成
INTERSECTS([point], [polygon])                -- 空間交差判定
MAKEPOINT([lat], [lon])                       -- ポイント生成
MAKELINE([point1], [point2])                  -- ライン生成
SHAPETYPE([geometry])                         -- 形状タイプ判定
AREA([geometry])                              -- 面積計算
```

### 7-2. Geometry encoding
```xml
<encodings>
  <geometry column="[DS名].[clct:Geometry:nk]" />
  <lod column="[DS名].[none:Name:nk]" />
</encodings>
```

---

## 8. カスタムカラーパレット

```xml
<preferences>
  <color-palette name="Custom Palette" type="ordered-sequential">
    <color>#5d5d75</color>
    <color>#7b7b91</color>
    <color>#9999ad</color>
    <!-- ... -->
  </color-palette>
</preferences>
```
- `type`: `regular`=カテゴリ, `ordered-sequential`=連続, `ordered-diverging`=発散

---

## 9. ダッシュボードレイアウトパターン

### 9-1. 基本構造
```
layout-basic [100000x100000]       -- ルート（常にこのサイズ）
  layout-flow param='vert'         -- 縦配置コンテナ
    title                          -- ダッシュボードタイトル
    layout-flow param='horz'       -- 横配置コンテナ
      worksheet 'シート名'          -- ワークシート
      layout-flow param='vert'     -- サイドバー
        filter                     -- フィルタコントロール
        paramctrl                  -- パラメータコントロール
        color                      -- 凡例
```

### 9-2. KPIグリッド（Kevin Flerlage パターン）
```
layout-flow param='horz'           -- KPI行
  layout-flow param='vert'         -- KPIカード1
    worksheet 'BAN'                -- Big Ass Number
    worksheet 'Sparkline'          -- スパークライン
  layout-flow param='vert'         -- KPIカード2
    ...
```

### 9-3. サイドバーフィルタパネル
```
layout-flow param='vert'           -- サイドバー
  filter param='[none:Region:nk]'  -- フィルタ1
  filter param='[none:Category:nk]' -- フィルタ2
  paramctrl param='[Parameters].[P1]' -- パラメータ1
  color                            -- 凡例
```

### 9-4. ナビゲーション付き複数DB（ServiceDesk パターン）
各ダッシュボードに共通フィルタ+go-to-sheetボタンを配置。
フィルタ状態は同一DSの同一フィールドを各DBに配置することで共有。

---

## 10. パラメータ定義パターン

### 10-1. リスト型（ドロップダウン）
```xml
<column caption="表示モード" datatype="string" name="[Parameter 1]"
        param-domain-type="list" role="measure" type="nominal"
        value="&quot;デフォルト値&quot;">
  <members>
    <member alias="表示名1" value="&quot;値1&quot;" />
    <member alias="表示名2" value="&quot;値2&quot;" />
  </members>
</column>
```

### 10-2. 範囲型（スライダー）
```xml
<column caption="Top N" datatype="integer" name="[Parameter 2]"
        param-domain-type="range" role="measure" type="quantitative"
        value="10">
  <range granularity="1" max="50" min="1" />
</column>
```

### 10-3. 任意入力型
```xml
<column caption="Search" datatype="string" name="[Parameter 3]"
        param-domain-type="any" role="measure" type="nominal"
        value="&quot;&quot;">
</column>
```

### 10-4. 日付型範囲パラメータ
```xml
<column caption="日付From" datatype="date" name="[Parameter 10]"
        param-domain-type="range" role="measure" type="quantitative"
        value="#2026-03-01#">
  <calculation class="tableau" formula="#2026-03-01#"/>
  <range granularity="1" max="#2026-03-31#" min="#2026-03-01#"/>
</column>
```
**ポイント:** date型でも `value` 属性は `#YYYY-MM-DD#`(シャープ括弧)形式。range要素も同形式。From/Toペアでスライダー2個並べると期間絞り込みUIになる。

---

## 10A. クロスDS パラメータ連動パターン

複数の独立した published datasource を持つworkbookで、全シートを **1つのパラメータ操作で連動させる** パターン。
Web Edit の relationships UI は同一federated DS内のテーブル間でしか繋げないため、独立DS間連動の唯一の正攻法。

学習元: サンプル市HPアクセス分析v5.3 demo (2026-05-26 city_actions_test)

### 10A-1. 適用条件

- 連動させたい全DSが **同名・同型のkey列** (例: `[日付]` date型) を持つ
- key列を持たないDS (集計済データなど) は **連動対象外として割り切る** ことが前提
- 完全1DS統合 (Prep Flowでwide table化) する余裕が無い場合の現実解

### 10A-2. 構造4点セット

**A. Parameters DS に範囲型パラメータをペアで追加**
```xml
<datasource hasconnection="false" inline="true" name="Parameters" version="18.1">
  <aliases enabled="yes"/>
  <column caption="日付From" datatype="date" name="[Parameter 10]"
          param-domain-type="range" role="measure" type="quantitative"
          value="#2026-03-01#">
    <calculation class="tableau" formula="#2026-03-01#"/>
    <range granularity="1" max="#2026-03-31#" min="#2026-03-01#"/>
  </column>
  <column caption="日付To" datatype="date" name="[Parameter 11]"
          param-domain-type="range" role="measure" type="quantitative"
          value="#2026-03-31#">
    <calculation class="tableau" formula="#2026-03-31#"/>
    <range granularity="1" max="#2026-03-31#" min="#2026-03-01#"/>
  </column>
  <layout dim-ordering="alphabetic" dim-percentage="0.5" measure-ordering="alphabetic" measure-percentage="0.5" show-structure="true"/>
</datasource>
```

**B. 各対象DSに boolean計算フィールド注入** (Parameters への参照を含む)
```xml
<!-- ds_daily, ds_device_daily, ds_pages_daily 等 全てに同じ計算を注入 -->
<column caption="Filter_DateInRange" datatype="boolean" name="[Calc_DateRange]"
        role="dimension" type="ordinal">
  <calculation class="tableau"
    formula="[日付] &gt;= [Parameters].[Parameter 10] AND [日付] &lt;= [Parameters].[Parameter 11]"/>
</column>
```
配置位置: `<datasource>` 直下、`<layout>` 要素の **前** に挿入。

**C. 対象worksheet全部に TRUE-only filter追加 + dep登録**
```xml
<worksheet name="...">
  <table>
    <view>
      <datasources>
        <datasource caption="..." name="ds_xxx"/>
      </datasources>
      <datasource-dependencies datasource="ds_xxx">
        <!-- 既存のcolumn-instance等の後に追加 -->
        <column caption="Filter_DateInRange" datatype="boolean" name="[Calc_DateRange]"
                role="dimension" type="ordinal">
          <calculation class="tableau" formula="[日付] &gt;= [Parameters].[Parameter 10] AND [日付] &lt;= [Parameters].[Parameter 11]"/>
        </column>
      </datasource-dependencies>
      <!-- aggregation の前に filter を挿入 -->
      <filter class="categorical" column="[ds_xxx].[Calc_DateRange]">
        <groupfilter function="member" level="[Calc_DateRange]" member="true"/>
      </filter>
      <aggregation value="true"/>
      ...
```
**重要:** `member="true"` は文字列 (booleanのリテラルではない)。

**D. Dashboard サイドバーに paramctrl zone を配置**
```xml
<dashboard name="...">
  <datasources>
    <!-- Parameters DSへの参照を必ず宣言 -->
    <datasource caption="Parameters" name="Parameters"/>
    <!-- 他の参照DSもここに列挙 -->
  </datasources>
  <zones>
    <zone h="100000" id="3" type-v2="layout-basic" w="100000" x="0" y="0">
      <zone h="100000" id="110" param="horz" type-v2="layout-flow" w="100000" x="0" y="0">
        <zone h="100000" id="111" type-v2="layout-basic" w="88571" x="0" y="0">
          <!-- 既存のchart zone群 -->
        </zone>
        <zone fixed-size="160" h="100000" id="112" is-fixed="true" param="vert"
              type-v2="layout-flow" w="11429" x="88571" y="0">
          <zone h="3500" id="113" name="Parameter 10"
                param="[Parameters].[Parameter 10]"
                type-v2="paramctrl" values="range"
                w="11429" x="88571" y="0">
            <zone-style>
              <format attr="border-color" value="#000000"/>
              <format attr="border-style" value="none"/>
              <format attr="border-width" value="0"/>
              <format attr="margin" value="4"/>
            </zone-style>
          </zone>
          <zone h="3500" id="114" name="Parameter 11"
                param="[Parameters].[Parameter 11]"
                type-v2="paramctrl" values="range"
                w="11429" x="88571" y="3500">
            <zone-style>...</zone-style>
          </zone>
        </zone>
      </zone>
    </zone>
  </zones>
</dashboard>
```

### 10A-3. Cloud roundtrip 検証 (必須)

publish直後にdownloadして全要素 (A/B/C/D) 残存をXMLレベルで確認:
```bash
grep "Parameter 10" downloaded.twb              # A残存
grep "Calc_DateRange" downloaded.twb            # B/C残存
grep "type-v2=\"paramctrl\"" downloaded.twb     # D残存
grep "Parameters.*caption=\"Parameters\"" downloaded.twb  # D dashboard refs
```
2026-05-26 サンプル市demoでは A/B/C/D 全項目が Cloud roundtrip 後も完全保持。
`feedback_twb_action_xml_injection.md` の `<command>` 剥落のような問題は発生しない。

### 10A-4. 落とし穴

1. **パラメータの value形式**: date型でも `#YYYY-MM-DD#` (シャープ括弧)。クォート不要
2. **boolean filter の member値**: `"true"` (string)。boolean trueリテラルではない
3. **dashboard datasources参照忘れ**: paramctrl zoneが表示されない
4. **既存filter zoneとの併存**: UX重複するので統一推奨。`feedback_twb_action_xml_injection.md` の action filter とは併存可
5. **粒度違いDS**: ds_pages_daily(372行) と ds_daily(32行) のように粒度が違うDSは完全統合 (full outer join) すると行が12倍に膨張。**それぞれにCalc_DateRange注入する方式が正解** (=本パターン)

### 10A-5. 参考実装

- 注入script: `scripts/20260526_city_inject_parameter_filter.py` (8 worksheets / 3 dashboards 一括処理 / 約230行)
- publish: `scripts/20260526_city_publish_unified.py` (TWBX preserve方式)
- 検証: `scripts/20260526_city_verify_unified.py`
- 参考TWB: `data/sample_city_hp_demo/city_test_unified.twb`

### 10A-6. 適用判断フローチャート

```
Q1: 連動先のDSが同名key列を持つか?
  YES → Q2へ
  NO → このパターン適用不可 (CSV側で再設計が必要)

Q2: DSのレコード粒度が一致するか?
  YES → 完全統合DS (Prep Flow) も検討可
  NO → このパターン (10A) を採用

Q3: Tableau Prep Flow経由でwide table化する余裕があるか?
  YES → Flowで統合 (中長期メンテ性◎)
  NO → このパターン (10A) を採用

Q4: ユーザーUXは「filter zone」 vs 「parameter slider」 どちら?
  filter zone → 各DSにfilter zone並べる (見た目重複)
  parameter slider → このパターン (10A) を採用 ★推奨
```

---

## 11. ガントチャート

### 11-1. 基本構造（mark class = Automatic）

cols に continuous date を配置し、size に日数を入れると Tableau が自動で Gantt Bar を選択する。

```xml
<panes>
  <pane selection-relaxation-option="selection-relaxation-allow">
    <view><breakdown value="auto" /></view>
    <mark class="Automatic" />
    <encodings>
      <color column="[DS名].[none:{{COLOR_FIELD}}:nk]" />
      <size column="[DS名].[sum:{{DURATION_FIELD}}:qk]" />
      <text column="[DS名].[sum:{{DURATION_FIELD}}:qk]" />
      <lod column="[DS名].[tdy:{{END_DATE}}:qk]" />
    </encodings>
    <style>
      <style-rule element="mark">
        <format attr="mark-labels-show" value="true" />
        <format attr="mark-labels-cull" value="true" />
        <format attr="mark-transparency" value="255" />
        <format attr="has-stroke" value="true" />
        <format attr="stroke-color" value="#898989" />
      </style-rule>
    </style>
  </pane>
</panes>
<!-- 行: 階層で分類。/ は階層区切り -->
<rows>([DS名].[none:グループ:nk] / ([DS名].[none:カテゴリ:nk] / [DS名].[none:タスク名:nk]))</rows>
<!-- 列: 開始日を continuous (Day-Trunc + quantitative) で配置 -->
<cols>[DS名].[tdy:開始日:qk]</cols>
```

**必須条件**:
- 開始日の column-instance: `derivation='Day-Trunc'` + `pivot='key' type='quantitative'`（`:qk`）
- 日数フィールドを size encoding に配置 → バーの長さを制御
- 終了日は encodings の `<lod>` に入れるだけ（cols には配置しない）

### 11-2. 参照バンド（ペア参照線でハイライト帯を表示）

2本の reference-line を `paired-id` で紐づけ → reference band（帯）として表示。
パラメータと連動させることで、基準日範囲や今日の日付帯を動的に表示できる。

```xml
<!-- pane内に配置 -->
<reference-line axis-column="[DS名].[tdy:開始日:qk]"
  enable-instant-analytics="true" formula="min" id="refline0"
  label-type="none" paired-id="refline1" scope="per-table"
  symmetric="false" value-column="[Parameters].[基準日開始]" z-order="1" />
<reference-line axis-column="[DS名].[tdy:開始日:qk]"
  enable-instant-analytics="true" formula="max" id="refline1"
  label-type="none" paired-id="refline0" scope="per-table"
  symmetric="false" value-column="[Parameters].[基準日終了]" z-order="2" />

<!-- style section内 -->
<style-rule element="refband">
  <format attr="fill-color" id="refline0" value="#9bbcc5" />
  <format attr="stroke-color" id="refline0" value="#6d8abd" />
  <format attr="line-visibility" id="refline0" value="on" />
  <format attr="line-pattern-only" id="refline0" value="dashed" />
</style-rule>
```

### 11-3. 条件付き色分け（範囲内/範囲外でフェーズ色を切替）

パラメータの基準日範囲と工期を比較し、範囲外のバーをグレーアウトするパターン。

**計算フィールド1: 工期かぶり判定**
```
IF DATETRUNC('day', { FIXED [タスク名]: MIN([開始日]) }) <= [Parameters].[基準日開始]
AND DATETRUNC('day', { FIXED [タスク名]: MAX([終了日]) }) >= [Parameters].[基準日開始]
THEN 'YES'
ELSEIF DATETRUNC('day', { FIXED [タスク名]: MIN([開始日]) }) >= [Parameters].[基準日開始]
AND DATETRUNC('day', { FIXED [タスク名]: MIN([開始日]) }) <= [Parameters].[基準日終了]
THEN 'YES'
ELSE 'NO'
END
```

**計算フィールド2: 条件付きフェーズ色**
```
IF [工期かぶり] = 'YES' THEN [フェーズ] ELSE '範囲外' END
```

**色エンコーディング（信号機パターン）**:
```xml
<encoding attr="color" field="[none:条件付きフェーズ:nk]"
          palette="traffic_light_10_0" type="palette">
  <map to="#e03531"><bucket>"PQ"</bucket></map>
  <map to="#f0bd27"><bucket>"入札"</bucket></map>
  <map to="#51b364"><bucket>"工期"</bucket></map>
  <map to="#898989"><bucket>"範囲外"</bucket></map>
</encoding>
```

### 11-4. Viz in Tooltip（ガントバーホバーでサブシート表示）

```xml
<customized-tooltip>
  <formatted-text>
    <run fontcolor="#787878">フィールド名:&#9;</run>
    <run bold="true"><![CDATA[<[DS名].[none:フィールド:nk]>]]></run>
    <run>&#10;</run>
    <!-- Viz in Tooltip -->
    <run bold="true" underline="true">セクション名</run>
    <run>&#10;</run>
    <run bold="true"><![CDATA[<Sheet name="サブシート名"
      maxwidth="300" maxheight="300"
      filter="<[DS名].[none:タスク名:nk]>">]]></run>
  </formatted-text>
</customized-tooltip>
```

---

## 12. BANカード（Big Ass Numbers / KPIサマリ）

3ペイン構成で不可視マーク+ラベルのみ表示する手法。左=タイトル、右=KPI値。
学習元: Call Center Capacity & Service Analytics (phData, 12K views)

### 12-1. 基本構造

```xml
<worksheet name="{{KPI_NAME}}">
  <table>
    <view>
      <datasource-dependencies datasource="{{DS_NAME}}">
        <!-- 空白dimension（1行固定） -->
        <column caption="&quot; &quot;" datatype="string" name="[calc_spacer]"
                role="dimension" type="nominal">
          <calculation class="tableau" formula="&quot; &quot;" />
        </column>
        <!-- 左軸: MIN(0.0) -->
        <column caption="MIN(0.0)" datatype="real" name="[calc_min0]"
                role="measure" type="quantitative">
          <calculation class="tableau" formula="MIN(0.0)" />
        </column>
        <!-- 右軸: MIN(1.0) -->
        <column caption="MIN(1.0)" datatype="real" name="[calc_min1]"
                role="measure" type="quantitative">
          <calculation class="tableau" formula="MIN(1.0)" />
        </column>
        <!-- メインKPI値 -->
        <column caption="{{KPI_CAPTION}}" datatype="real"
                default-format="{{KPI_FORMAT}}" name="[{{KPI_FIELD}}]"
                role="measure" type="quantitative">
          <calculation class="tableau" formula="{{KPI_FORMULA}}" />
        </column>
      </datasource-dependencies>
    </view>
    <panes>
      <!-- Pane 0: タイトルラベル（Bar、不可視マーク+ラベル） -->
      <pane selection-relaxation-option="selection-relaxation-disallow"
            x-axis-name="[{{DS_NAME}}].[usr:calc_min0:qk]">
        <mark class="Bar" />
        <mark-sizing mark-sizing-setting="marks-scaling-off" />
        <customized-label>
          <formatted-text>
            <run fontcolor="#4f4a41" fontname="Tableau Light" fontsize="15">{{KPI_TITLE}}</run>
          </formatted-text>
        </customized-label>
        <style>
          <style-rule element="cell">
            <format attr="text-align" value="left" />
          </style-rule>
          <style-rule element="mark">
            <format attr="mark-labels-show" value="true" />
            <format attr="mark-labels-cull" value="false" />
            <format attr="has-stroke" value="false" />
            <format attr="mark-color" value="#ffffff" />
            <format attr="mark-transparency" value="0" />
          </style-rule>
        </style>
      </pane>
      <!-- Pane 1: メインKPI値（GanttBar、不可視マーク+ラベル） -->
      <pane id="1" selection-relaxation-option="selection-relaxation-disallow"
            x-axis-name="[{{DS_NAME}}].[usr:calc_min1:qk]">
        <mark class="GanttBar" />
        <mark-sizing mark-sizing-setting="marks-scaling-off" />
        <encodings>
          <text column="[{{DS_NAME}}].[usr:{{KPI_FIELD}}:qk]" />
        </encodings>
        <customized-label>
          <formatted-text>
            <run fontname="Tableau Light" fontsize="15">&lt;[{{DS_NAME}}].[usr:{{KPI_FIELD}}:qk]&gt;</run>
          </formatted-text>
        </customized-label>
        <style>
          <style-rule element="cell">
            <format attr="text-align" value="right" />
          </style-rule>
          <style-rule element="datalabel">
            <format attr="color-mode" value="user" />
            <format attr="color" value="#4f4a41" />
          </style-rule>
          <style-rule element="mark">
            <format attr="mark-labels-show" value="true" />
            <format attr="has-stroke" value="false" />
            <format attr="mark-color" value="#ffffff" />
            <format attr="mark-transparency" value="0" />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows>[{{DS_NAME}}].[none:calc_spacer:nk]</rows>
    <cols>([{{DS_NAME}}].[usr:calc_min0:qk] + [{{DS_NAME}}].[usr:calc_min1:qk])</cols>
  </table>
</worksheet>
```

**設計ポイント**:
- `mark-color=#ffffff` + `mark-transparency=0` でマーク完全不可視（ラベルのみ表示）
- rows=`" "` (空白文字列dimension) で1行固定
- cols=`MIN(0.0) + MIN(1.0)` の2軸で左=タイトル、右=値
- fontsize=15(メイン) / fontsize=8(サブ) でフォントサイズ差
- 改行: `&#xC6;&#10;` でメイン値と差分値を2行表示

### 12-2. Favorable/Unfavorable 色分けパターン

KPIの値が目標を達成しているかで色を切り替える汎用パターン。

```
-- 2値パターン（最も多用）
IF [{{VARIANCE}}] >= 0 THEN 'Favorable' ELSE 'Unfavorable' END

-- Hit/Missパターン（SL等）
IF [{{VARIANCE}}] >= 0 THEN 'Hit'
ELSEIF [{{VARIANCE}}] < 0 THEN 'Miss'
ELSE '' END

-- 4段階閾値パターン（Occupancy等）
IF [{{VARIANCE}}] <= -0.05 THEN 'Low'
ELSEIF [{{VARIANCE}}] <= 0 THEN 'Close-Low'
ELSEIF [{{VARIANCE}}] <= 0.03 THEN 'Close-High'
ELSE 'High' END
```

### 12-3. 2x4 KPIグリッドレイアウト

```xml
<!-- ダッシュボード: 2列 x 4行のKPIグリッド -->
<zone type-v2="layout-flow" param="vert">
  <zone type-v2="layout-flow" param="horz">
    <zone type-v2="layout-flow" param="vert">
      <!-- 左列: KPI1カード + スパークライン + KPI2カード + スパークライン -->
      <zone name="KPI1" fixed="true" />
      <zone name="KPI1 Trend" />
      <zone type-v2="empty" fixed="true" />
      <zone name="KPI2" fixed="true" />
      <zone name="KPI2 Trend" />
    </zone>
    <zone type-v2="layout-flow" param="vert">
      <!-- 右列: 同構造 -->
    </zone>
  </zone>
</zone>
```

### 12-4. Cloud互換BAN実装（2026-04-11 実証済み2方式）

**方式A: Square mark（パターンショーケースv2で実証）**
```xml
<mark class='Square' />
<mark-sizing mark-sizing-setting='marks-scaling-off' />
<encodings>
  <size column='[DS].[sum:calc_value:qk]' />
  <text column='[DS].[sum:calc_value:qk]' />
</encodings>
<customized-label>
  <formatted-text>
    <run bold='true' fontcolor='#ffffff' fontsize='11'>タイトル</run>
    <run>&#xC6;&#10;</run>
    <run fontcolor='#ffffff' fontsize='28'>&lt;[DS].[sum:calc_value:qk]&gt;</run>
  </formatted-text>
</customized-label>
<!-- background-color = mark-color で統一塗り -->
<style-rule element='table'><format attr='background-color' value='#2c5f7c' /></style-rule>
<style-rule element='mark'><format attr='mark-color' value='#2c5f7c' /></style-rule>
<rows /><cols />
```
- **注意**: 計算フィールドは行レベル式（SUM()含めない）+ derivation='Sum'
- `SUM(IF ... THEN [金額] END)` はCloud空白。`IF ... THEN [金額] END` + derivation='Sum' が正解

**方式B: Bar mark（city_twb.pyで実証、ゾーン全体塗り推奨）**
```xml
<mark class='Bar' />
<encodings>
  <color column='[DS].[none:category:nk]' />
  <text column='[DS].[sum:value:qk]' />
  <text column='[DS].[none:category:nk]' />
</encodings>
<customized-label>
  <formatted-text>
    <run fontcolor='#ffffff' fontsize='11'>&lt;[DS].[none:category:nk]&gt;</run>
    <run>&#xC6;&#10;</run>
    <run bold='true' fontcolor='#ffffff' fontsize='28'>&lt;[DS].[sum:value:qk]&gt;</run>
  </formatted-text>
</customized-label>
<rows>[DS].[sum:value:qk]</rows>
<cols>[DS].[none:category:nk]</cols>
```
- Bar markはrowsにメジャーを入れることでゾーン全体を塗りつぶす
- Square markはサイズ固定でゾーン高さに追従しない（上部空白が残る場合あり）

### 12-5. Cloud互換性チェックリスト（BAN全般）

| 項目 | 状態 | 備考 |
|------|------|------|
| Square mark + customized-label | ✅ | size/textに同一calcを入れる |
| Bar mark + customized-label | ✅ | rows=メジャーでゾーン塗り |
| 行レベル計算 + derivation='Sum' | ✅ | SUM()含む計算は空白になる |
| background-color + mark-color 統一 | ✅ | 色の隙間を消す |
| x-axis-name dual-axis | ⚠️ | 12-1方式。Cloud動作未検証 |
| customized-labelで2フィールド参照 | ✅ | 両方encodingsに入れること |

---

## 13. ウォーターフォールチャート

GanttBarのサイズを差分値にすることで浮動バーを実現する。
学習元: Call Center Capacity & Service Analytics

### 13-1. 基本構造

```xml
<worksheet name="{{WATERFALL_NAME}}">
  <table>
    <rows>
      ([{{DS}}].[sum:{{START_VALUE}}:qk] + [{{DS}}].[usr:{{CHANGE_VALUE}}:qk])
    </rows>
    <cols>
      [{{DS}}].[attr:{{STEP_NAME}}:nk]
    </cols>
    <panes>
      <!-- 差分バー（GanttBar） -->
      <pane>
        <mark class="GanttBar" />
        <encodings>
          <color column="[{{DS}}].[none:{{WATERFALL_COLOR}}:nk]" />
          <size column="[{{DS}}].[usr:{{CHANGE_VALUE}}:qk]" />
        </encodings>
      </pane>
    </panes>
  </table>
</worksheet>
```

**Waterfall色分け**:
```
IF [Value Type] = 'Pillar' THEN 'Pillar'      -- 灰色（基準柱）
ELSEIF [Value] <= 0 THEN 'Favorable'           -- 緑（改善）
ELSE 'Unfavorable'                              -- 赤（悪化）
END
```

### 13-2. KPI目標線（パラメータ連動）

```xml
<reference-line
  axis-column="[{{DS}}].[usr:{{ACTUAL_METRIC}}:qk]"
  formula="total"
  label="{{LABEL}}: &lt;Value&gt;"
  label-type="custom"
  scope="per-pane"
  value-column="[{{DS}}].[usr:{{TARGET_METRIC}}:qk]"
  z-order="{{Z_ORDER}}" />
```

### 13-3. Current Date マーカー

```xml
<reference-line
  axis-column="[{{DS}}].[none:{{DATE_FIELD}}:qk]"
  formula="min"
  label-type="none"
  scope="per-table"
  tooltip="Current Date: &lt;Value&gt;"
  tooltip-type="custom"
  value-column="[Parameters].[{{CURRENT_DATE_PARAM}}]"
  z-order="1" />
```

---

## 14. ドットデンシティマップ

mark class="Shape" + :filled/square でポイント密度を表現する。大量データ向け。
学習元: Melbourne Public Transport Frequency (1.8M行)

### 14-1. 座標の丸め（パフォーマンス最適化）

```xml
<column aggregation="Avg" caption="Round Latitude" datatype="real"
  name="[calc_round_lat]" role="measure"
  semantic-role="[Geographical].[Latitude]" type="quantitative">
  <calculation class="tableau" formula="ROUND([{{Y_COORD}}], {{PRECISION}})" />
</column>
<column aggregation="Avg" caption="Round Longitude" datatype="real"
  name="[calc_round_lon]" role="measure"
  semantic-role="[Geographical].[Longitude]" type="quantitative">
  <calculation class="tableau" formula="ROUND([{{X_COORD}}], {{PRECISION}})" />
</column>
```
- `ROUND(,2)` ≒ 1.1kmグリッド。180万行を実質ビンニングして描画負荷低減

### 14-2. マーク設定

```xml
<pane>
  <mark class="Shape" />
  <mark-sizing mark-sizing-setting="marks-scaling-off" />
  <encodings>
    <color column="[{{DS}}].[usr:{{CATEGORY_FIELD}}:nk]" />
    <size column="[{{DS}}].[cnt:Number of Records:qk]" />
  </encodings>
  <style>
    <style-rule element="mark">
      <format attr="shape" value=":filled/square" />
      <format attr="has-halo" value="false" />
      <format attr="mark-transparency" value="229" />
      <format attr="mark-labels-show" value="false" />
    </style-rule>
  </style>
</pane>
<rows>[{{DS}}].[none:calc_round_lat:qk]</rows>
<cols>[{{DS}}].[none:calc_round_lon:qk]</cols>
```

**設計ポイント**:
- `marks-scaling-off`: ズームしてもマークサイズ不変
- `mark-transparency=229` (90%不透明): 重なりを許容しつつ視認性確保
- `has-halo=false`: ハロー効果なし（ドット密集時にノイズになるため）

---

## 15. ダークマップスタイル / 地図詳細制御

### 15-1. ダークマップ

```xml
<style-rule element="map">
  <format attr="washout" value="0" />
  <format attr="map-style" value="dark" />
</style-rule>
```
- `map-style`: `normal`(デフォルト), `dark`, `light`
- `washout`: 0.0(完全な色)〜1.0(完全に薄い)

### 15-2. 座標軸非表示 + tooltip除外

```xml
<style-rule element="axis">
  <format attr="display" class="0"
    field="[{{DS}}].[none:{{LAT_FIELD}}:qk]"
    scope="rows" value="false" />
  <format attr="display" class="0"
    field="[{{DS}}].[none:{{LON_FIELD}}:qk]"
    scope="cols" value="false" />
</style-rule>
<style-rule element="worksheet">
  <format attr="in-tooltip"
    field="[{{DS}}].[none:{{LON_FIELD}}:qk]" value="false" />
  <format attr="in-tooltip"
    field="[{{DS}}].[none:{{LAT_FIELD}}:qk]" value="false" />
</style-rule>
```

### 15-3. マップレイヤー制御

```xml
<style-rule element="map-layer">
  <format attr="enabled" id="admin-2-boundaries" value="true" />
  <format attr="enabled" id="admin-2-label" value="true" />
  <!-- demographicレイヤーは全無効化 -->
  <format attr="enabled" id="dp05_0001e" value="false" />
</style-rule>
```

### 15-4. マップviewpoint

```xml
<viewpoint>
  <zoom type="entire-view" />
  <map-scale-visibility value="0" />
  <default-map-tool-selection tool="2" />
  <map-navigation value="1" />
</viewpoint>
```

---

## 16. パラメータ連動リージョンフィルタ

1つのパラメータから地図+チャート両方の表示を制御するパターン。
学習元: Melbourne Public Transport Frequency

### 16-1. (All)対応のフィルタ計算フィールド

```
-- MapFilter: (All)選択時は全表示、特定値選択時はフィルタ
IF [Parameters].[{{REGION_PARAM}}]="(All)" THEN 'True'
ELSEIF [{{REGION_FIELD}}]=[Parameters].[{{REGION_PARAM}}] THEN 'True'
ELSE 'False'
END
```

### 16-2. パラメータ定義（リスト + (All)先頭）

```xml
<column caption="{{PARAM_CAPTION}}" datatype="string"
  param-domain-type="list" role="measure" type="nominal"
  value="&quot;(All)&quot;">
  <calculation class="tableau" formula="&quot;(All)&quot;" />
  <members>
    <member value="&quot;(All)&quot;" />
    <member value="&quot;{{REGION1}}&quot;" />
    <member value="&quot;{{REGION2}}&quot;" />
  </members>
</column>
```

---

## 17. カスタムカラーパレット（科学的配色）

### 17-1. Plasma（連続・高コントラスト）

```xml
<color-palette custom="true" name="plasma" type="ordered-sequential">
  <color>#f0f622</color><color>#f3de31</color><color>#f4c63d</color>
  <color>#f2b048</color><color>#ed9852</color><color>#e6805d</color>
  <color>#dd6967</color><color>#d15273</color><color>#bd3f82</color>
  <color>#a1328e</color><color>#832894</color><color>#642094</color>
  <color>#411a90</color><color>#0d1687</color>
</color-palette>
```

### 17-2. CB_RdBu（発散型・赤青）

```xml
<color-palette custom="true" name="CB_RdBu" type="ordered-diverging">
  <color>#67001f</color><color>#b2182b</color><color>#d6604d</color>
  <color>#f4a582</color><color>#fddbc7</color><color>#f7f7f7</color>
  <color>#d1e5f0</color><color>#92c5de</color><color>#4393c3</color>
  <color>#2166ac</color><color>#053061</color>
</color-palette>
```

### 17-3. 例外色付きカテゴリマッピング

順序パレットの中で特定カテゴリだけグレーにする手法:
```xml
<encoding attr="color" field="[{{COLOR_FIELD}}]" palette="plasma" type="palette">
  <map to="#0d1687"><bucket>"&gt; 60"</bucket></map>
  <map to="#acb0b1"><bucket>"No Services"</bucket></map>  <!-- 例外色=グレー -->
  <map to="#f3c23e"><bucket>"&lt; 3"</bucket></map>
</encoding>
```

---

## 18. ナビゲーションアクション

ダッシュボード間のページ遷移ボタン。
学習元: Call Center Capacity & Service Analytics

```xml
<nav-action caption="{{NAV_CAPTION}}" name="[{{ACTION_ID}}]">
  <activation type="on-select" />
  <source dashboard="{{SOURCE_DB}}" type="sheet" worksheet="{{NAV_BUTTON_SHEET}}" />
  <params>
    <param name="sheet" value="{{TARGET_DB}}" />
  </params>
</nav-action>
```

**パラメータアクション + 選択解除 + ナビゲーション の3点セット**:
ボタンクリック時に (1) パラメータ更新 (2) 選択解除 (3) 画面遷移 を同時実行。

---

## 19. 閾値ベース条件付き色分け (Threshold Color Encoding)

メジャーの値を複数閾値で区分し、カテゴリ色マッピングで色分けするパターン。
学習元: 勤怠管理Viz (残業時間 30h/45h 閾値)

```xml
<!-- 計算フィールド: 3段階閾値判定 -->
<column caption='Range' datatype='string' name='[Calculation_Range]' role='measure' type='nominal'>
  <calculation class='tableau' formula='IF AVG([{{measure_field}}]) > {{upper_threshold}} then "{{upper_label}}"
ELSEIF AVG([{{measure_field}}]) > {{lower_threshold}} then "{{middle_label}}"
ELSE "{{lower_label}}"
END' />
</column>

<!-- 色マッピング (datasource > style > style-rule element='mark' 内) -->
<encoding attr='color' field='[usr:Calculation_Range:nk]' type='palette'>
  <map to='{{safe_color}}'>    <!-- e.g. #bce4d8 ミントグリーン -->
    <bucket>"{{lower_label}}"</bucket>
  </map>
  <map to='{{warning_color}'>  <!-- e.g. #ffda66 黄 -->
    <bucket>"{{middle_label}}"</bucket>
  </map>
  <map to='{{danger_color}}'>  <!-- e.g. #ee7422 オレンジ -->
    <bucket>"{{upper_label}}"</bucket>
  </map>
</encoding>
```

**推奨カラーセット**: 安全=#bce4d8, 注意=#ffda66, 超過=#ee7422 (勤怠管理の実績色)

---

## 20. Beeswarm (ドットプロット)

カテゴリごとにドットを垂直分散させ、個別値の分布を一覧表示するパターン。
学習元: 勤怠管理Viz (月別個人残業分布)

```xml
<!-- 計算フィールド: ドット位置分散 (テーブル計算) -->
<column caption='dot_position' datatype='integer' name='[Calculation_DotPos]'
        role='measure' type='quantitative'>
  <calculation class='tableau' formula='INDEX()%{{num_rows}}'>
    <table-calc ordering-type='Rows' />
  </calculation>
</column>

<!-- column-instance: ordering-fieldを指定してアドレス解決 -->
<column-instance column='[Calculation_DotPos]' derivation='User'
  name='[usr:Calculation_DotPos:qk]' pivot='key' type='quantitative'>
  <table-calc ordering-field='[{{datasource}}].[{{sort_field}}]' ordering-type='Field' />
</column-instance>

<!-- rows/cols構成 -->
<rows>([{{datasource}}].[none:{{category_field}}:nk] * [{{datasource}}].[usr:Calculation_DotPos:qk])</rows>
<cols>[{{datasource}}].[avg:{{measure_field}}:qk]</cols>

<!-- ペイン設定 -->
<pane>
  <mark class='Circle' />
  <mark-sizing mark-sizing-setting='marks-scaling-off' />
  <encodings>
    <color column='[{{datasource}}].[usr:Calculation_Range:nk]' />  <!-- Pattern 19と組合せ -->
    <text column='[{{datasource}}].[none:{{label_field}}:nk]' />
  </encodings>
  <style>
    <style-rule element='mark'>
      <format attr='mark-labels-show' value='true' />
      <format attr='mark-labels-cull' value='false' />
      <format attr='mark-labels-mode' value='range' />  <!-- 重なり時に端のみ表示 -->
      <format attr='has-stroke' value='false' />
    </style-rule>
    <style-rule element='pane'>
      <format attr='minwidth' value='{{width}}' />   <!-- e.g. 428 -->
      <format attr='maxwidth' value='{{width}}' />
      <format attr='minheight' value='{{height}}' />  <!-- e.g. 61 -->
      <format attr='maxheight' value='{{height}}' />
    </style-rule>
  </style>
</pane>
```

**ポイント**:
- `INDEX()%N` で N行にドットを分散 (N=5が実績値)
- `mark-labels-mode='range'` で密集部は端ラベルのみ表示
- Pattern 19 (閾値色分け) と組み合わせて使うのが定番

---

## 21. フィルタボタン (Circleマーク流用)

パラメータやドロップダウンの代わりにCircleマーク+ダッシュボードアクションでフィルタUI実装。
学習元: 勤怠管理Viz (役職選択/月選択/班選択)

```xml
<!-- フィルタボタン用ワークシート -->
<worksheet name='{{selector_name}}'>
  <table>
    <style>
      <style-rule element='cell'>
        <format attr='cell-w' value='120' />  <!-- ボタン幅 -->
        <format attr='cell-h' value='40' />   <!-- ボタン高さ -->
      </style-rule>
      <style-rule element='label'>
        <format attr='display' field='[{{datasource}}].[none:{{field}}:nk]' value='false' />
      </style-rule>
      <style-rule element='table'>
        <format attr='background-color' value='{{bg_color}}' />  <!-- e.g. #555555 -->
      </style-rule>
      <style-rule element='worksheet'>
        <format attr='display-field-labels' scope='cols' value='false' />
      </style-rule>
    </style>
    <panes>
      <pane selection-relaxation-option='selection-relaxation-disallow'>  <!-- 単一選択 -->
        <mark class='Circle' />
        <mark-sizing mark-sizing-setting='marks-scaling-off' />
        <encodings>
          <text column='[{{datasource}}].[none:{{field}}:nk]' />
        </encodings>
        <style>
          <style-rule element='datalabel'>
            <format attr='color-mode' value='user' />
            <format attr='font-size' value='9' />
            <format attr='color' value='#000000' />
          </style-rule>
          <style-rule element='mark'>
            <format attr='mark-labels-show' value='true' />
            <format attr='size' value='2.5' />          <!-- 大きいCircle -->
            <format attr='mark-color' value='#e6e6e6' />
            <format attr='has-stroke' value='true' />
            <format attr='stroke-color' value='#ffffff' />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows />
    <cols>[{{datasource}}].[none:{{field}}:nk]</cols>
    <tooltip-style tooltip-mode='none' />
  </table>
</worksheet>

<!-- ダッシュボードアクション -->
<action caption='{{filter_caption}}' name='[{{action_id}}]'>
  <activation auto-clear='true' type='on-select' />
  <source dashboard='{{dashboard_name}}' type='sheet' worksheet='{{selector_name}}' />
  <command command='tsc:tsl-filter'>
    <param name='exclude' value='title,{{selector_name}}' />
    <param name='special-fields' value='all' />
    <param name='target' value='{{dashboard_name}}' />
  </command>
</action>
```

**ポイント**:
- `selection-relaxation-disallow`: 複数マーク同時選択不可
- `auto-clear='true'`: 再クリックで選択解除→フィルタリセット
- `exclude` にソースシート自身を含めて自己フィルタ防止
- 手動ソートで表示順制御可能

---

## 22. ドーナツチャート (二重Pie)

ダミーメジャーで2段Pieを作り、ドーナツ効果を実現するパターン。
学習元: 勤怠管理Viz (残業時間帯別人数)

```xml
<!-- ダミーメジャー (1固定) -->
<column caption='dummy' datatype='integer' name='[Calculation_Dummy]'
        role='measure' type='quantitative'>
  <calculation class='tableau' formula='1' />
</column>

<!-- rows: (dummy + dummy) で2段Pie -->
<rows>([{{datasource}}].[none:Calculation_Dummy:qk] + [{{datasource}}].[none:Calculation_Dummy:qk])</rows>
<cols onLeft='true' total='true' />

<!-- Pane 0: テキストのみ (中心の上部に総計表示) -->
<pane selection-relaxation-option='selection-relaxation-allow'>
  <mark class='Pie' />
  <encodings>
    <text column='[{{datasource}}].[ctd:{{id_field}}:qk]' />
  </encodings>
</pane>

<!-- Pane 1: 実データPie (カテゴリ色+ウェッジサイズ) -->
<pane id='1' y-axis-name='[{{datasource}}].[none:Calculation_Dummy:qk]'>
  <mark class='Pie' />
  <mark-sizing mark-sizing-setting='marks-scaling-off' />
  <encodings>
    <color column='[{{datasource}}].[none:{{category_bin}}:ok]' />
    <wedge-size column='[{{datasource}}].[ctd:{{id_field}}:qk]' />
    <text column='[{{datasource}}].[none:{{category_bin}}:ok]' />
    <text column='[{{datasource}}].[ctd:{{id_field}}:qk]' />
  </encodings>
  <style>
    <style-rule element='mark'>
      <format attr='size' value='1.4' />
      <format attr='mark-labels-show' value='true' />
      <format attr='mark-labels-cull' value='false' />
    </style-rule>
  </style>
</pane>

<!-- Pane 2: 中心ラベル (背景色Pieで穴を表現) -->
<pane id='2' y-axis-name='[{{datasource}}].[none:Calculation_Dummy:qk]' y-index='1'>
  <mark class='Pie' />
  <encodings>
    <text column='[{{datasource}}].[ctd:{{id_field}}:qk]' />
  </encodings>
  <customized-label>
    <formatted-text>
      <run>合計&#10;&lt;[{{datasource}}].[ctd:{{id_field}}:qk]&gt;</run>
    </formatted-text>
  </customized-label>
  <style>
    <style-rule element='mark'>
      <format attr='mark-color' value='#666666' />  <!-- 背景色マッチ -->
      <format attr='mark-labels-show' value='true' />
    </style-rule>
  </style>
</pane>
```

**ポイント**:
- 3ペイン構成: テキスト | 外側Pie | 中心(穴)
- 中心Paneのmark-colorをダッシュボード背景色に合わせると自然な「穴」になる
- ビンのエイリアスで表示ラベルをカスタマイズ

---

## 23. LODベース動的月検出

パラメータなしで「データが存在する直近月」を自動検出するパターン。
学習元: 勤怠管理Viz (直近月の自動検出)

```xml
<!-- isnull判定 (メジャーの存在チェック) -->
<column caption='isnull' datatype='boolean' name='[Calc_IsNull]'
        role='dimension' type='nominal'>
  <calculation class='tableau' formula='ISNULL([{{measure_field}}])' />
</column>

<!-- 直近月 (EXCLUDE LOD) -->
<column aggregation='Attribute' caption='latest_period' datatype='date'
        name='[Calc_LatestPeriod]' role='measure' type='ordinal'>
  <calculation class='tableau' formula='{ EXCLUDE [{{date_field}}]:
MAX(IF not [Calc_IsNull] then [{{date_field}}] END)}' />
</column>

<!-- 当期メジャー (直近月のみ値を返す) -->
<column aggregation='Avg' caption='current_value' datatype='integer'
        name='[Calc_CurrentValue]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='IF [{{date_field}}] = [Calc_LatestPeriod]
then [{{measure_field}}]
END' />
</column>

<!-- 月ラベル -->
<column aggregation='Attribute' caption='period_label' datatype='integer'
        name='[Calc_PeriodLabel]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='DATEPART("month", [Calc_LatestPeriod])' />
</column>
```

**ポイント**:
- EXCLUDE LOD で日付軸から独立した「最新月」を算出
- ISNULLチェックで未入力月を除外
- パラメータ不要で自動更新 → 月次レポートの自動化に最適

---

## 24. 動的タイトル (計算フィールドテキスト)

計算フィールドでタイトルテキストを動的生成し、専用シートで表示するパターン。
学習元: 勤怠管理Viz ("X月度 残業管理ダッシュボード")

```xml
<!-- タイトル計算フィールド -->
<column aggregation='Attribute' caption='Title' datatype='string'
        name='[Calc_Title]' role='measure' type='nominal'>
  <calculation class='tableau' formula='STR([Calc_PeriodLabel]) + "{{suffix_text}}"' />
  <!-- e.g. suffix_text = "月度　残業管理ダッシュボード" -->
</column>

<!-- titleシート -->
<worksheet name='title'>
  <table>
    <style>
      <style-rule element='table'>
        <format attr='background-color' value='#00000000' />  <!-- 透明 -->
      </style-rule>
      <style-rule element='worksheet'>
        <format attr='font-size' value='14' />
        <format attr='font-weight' value='bold' />
      </style-rule>
    </style>
    <panes>
      <pane selection-relaxation-option='selection-relaxation-allow'>
        <mark class='Automatic' />
        <encodings>
          <text column='[{{datasource}}].[attr:Calc_Title:nk]' />
        </encodings>
        <style>
          <style-rule element='mark'>
            <format attr='mark-labels-show' value='true' />
            <format attr='mark-labels-cull' value='true' />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows />
    <cols />
  </table>
</worksheet>
```

---

## 25. ダークテーマ基本設定

ワークブックレベルのグローバルスタイル設定。
学習元: 勤怠管理Viz (ダークグレー背景+白文字)

```xml
<!-- workbook直下のstyle -->
<style>
  <style-rule element='axis'>
    <format attr='stroke-color' value='#d4d4d4' />
  </style-rule>
  <style-rule element='gridline'>
    <format attr='stroke-color' value='#898989' />
  </style-rule>
  <style-rule element='title'>
    <format attr='font-size' value='12' />
    <format attr='font-weight' value='normal' />
    <format attr='color' value='#ffffff' />
  </style-rule>
  <style-rule element='tooltip'>
    <format attr='color' value='#000000' />  <!-- ツールチップは黒文字維持 -->
  </style-rule>
  <style-rule element='all'>
    <format attr='color' value='#ffffff' />
    <format attr='font-family' value='{{font_name}}' />  <!-- e.g. メイリオ -->
  </style-rule>
</style>

<!-- ダッシュボード背景 -->
<dashboard>
  <style>
    <style-rule element='table'>
      <format attr='background-color' value='#555555' />
    </style-rule>
  </style>
</dashboard>

<!-- 各ワークシートの背景 (ダッシュボードと同色) -->
<style-rule element='table'>
  <format attr='background-color' value='#555555' />
</style-rule>
```

---

## 26. 期間スライダー（相対日付フィルタ群）

パラメータで期間（7日/30日/60日/90日等）を切替え、対応するbooleanフィルタを適用するパターン。
KPIダッシュボードの「期間切替」をフィルタアクションなしで実装できる。
学習元: Insurance Operations Dashboard (Stephanie N. Anyama)

### 26-1. 相対日付boolean計算フィールド
```xml
<!-- 現在期間: 直近N日 -->
<column caption="7 Days" datatype="boolean" name="[calc_7d]"
        role="dimension" type="nominal">
  <calculation class="tableau"
    formula="DATETRUNC('day', [{{DATE_FIELD}}]) &gt;= DATEADD('day', -7, DATETRUNC('day', { MAX([{{DATE_FIELD}}])}))" />
</column>
<!-- 同パターンで 30/60/90/All Time を作成 -->

<!-- 比較期間: Prior N日（前の同期間） -->
<column caption="Prior 7 Days" datatype="boolean" name="[calc_prior_7d]"
        role="dimension" type="nominal">
  <calculation class="tableau"
    formula="DATETRUNC('week', [{{DATE_FIELD}}]) &gt;= DATEADD('week', -2, DATETRUNC('week', { MAX([{{DATE_FIELD}}])} + 2))
AND DATETRUNC('week', [{{DATE_FIELD}}]) &lt; DATEADD('week', -1, DATETRUNC('week', { MAX([{{DATE_FIELD}}])} + 1))" />
</column>
```

### 26-2. 期間選択CASE切替
```xml
<column caption="Selected Time Period" datatype="boolean" name="[calc_selected_period]"
        role="dimension" type="nominal">
  <calculation class="tableau"
    formula="CASE [Parameters].[{{PARAM_NAME}}]
  WHEN '7 Days' THEN [calc_7d]
  WHEN '30 Days' THEN [calc_30d]
  WHEN '60 Days' THEN [calc_60d]
  WHEN '90 Days' THEN [calc_90d]
  ELSE TRUE
END" />
</column>
```

- `{ MAX([date]) }` でデータの最新日を自動検出（FIXED LOD不要）
- Prior期間は同じ長さの直前期間を取る（7日→前週、30日→前月等）
- フィルタシェルフに `Selected Time Period = TRUE` を設定して使用

---

## 27. テーブルソート（パラメータ制御）

テーブル（GanttBar疑似テーブル含む）のヘッダクリックでソート列・方向を切替えるパターン。
3つのパラメータ（ソート列名・ソート方向・ASCII変換値）を連携させる。
学習元: Insurance Operations Dashboard (Stephanie N. Anyama)

### 27-1. ソートフィールド計算
```xml
<!-- ソート列に応じた値を返す -->
<column caption="Sort Field" datatype="real" name="[calc_sort_field]"
        role="measure" type="quantitative">
  <calculation class="tableau"
    formula="CASE [Parameters].[{{SORT_COLUMN_PARAM}}]
  WHEN '{{COL_A}}' THEN MIN(INT([calc_ascii_a]))
  WHEN '{{COL_B}}' THEN MIN(INT([calc_ascii_b]))
  WHEN '{{COL_C}}' THEN MIN([{{MEASURE_FIELD}}])
END * [Parameters].[{{SORT_DIR_PARAM}}]" />
</column>

<!-- ソート方向: 1=ASC, -1=DESC -->
<column caption="Sort Direction" datatype="integer" name="[{{SORT_DIR_PARAM}}]"
        param-domain-type="list" role="measure" type="quantitative" value="1">
  <calculation class="tableau" formula="1" />
  <members>
    <member value="1" />
    <member value="-1" />
  </members>
</column>
```

### 27-2. ソート記号表示
```xml
<!-- ヘッダに▼▲を表示 -->
<column caption="Sort Symbol" datatype="string" name="[calc_sort_symbol]"
        role="dimension" type="nominal">
  <calculation class="tableau"
    formula="IIF([Parameters].[{{SORT_COLUMN_PARAM}}]=[calc_header_label],
  IIF([Parameters].[{{SORT_DIR_PARAM}}]=1,'&#x25BC;','&#x25B2;'),'')" />
</column>
```

- パラメータアクション(1-3)でヘッダクリック→Sort Column/Directionを更新
- Sort Fieldをrows/colsのソートに使用（continuous → sort by field）
- ASCII変換: 文字列ソートは `STR(ASCII(UPPER(MID(str,1)))) + STR(ASCII(...,2))...` で数値化

---

## 28. KPI差分フォーマット（矢印記号付き）

`default-format` 属性でカスタム数値書式を設定し、正負で異なる記号を自動表示するパターン。
学習元: Insurance Operations Dashboard (Stephanie N. Anyama)

```xml
<!-- パーセント差分: 上昇↗/下降↘ -->
<column caption="% Change" datatype="real"
        default-format="*&#x2934; 0.0%;&#x2935; 0.0%"
        name="[calc_pct_change]" role="measure" type="quantitative">
  <calculation class="tableau"
    formula="([{{CURRENT_MEASURE}}] / [{{PRIOR_MEASURE}}]) - 1" />
</column>

<!-- 絶対値差分: +/-記号付き -->
<column caption="Diff" datatype="integer"
        default-format="*+#,##0;-#,##0"
        name="[calc_diff]" role="measure" type="quantitative">
  <calculation class="tableau"
    formula="[{{CURRENT_MEASURE}}] - [{{PRIOR_MEASURE}}]" />
</column>
```

- `default-format` の `*` はリテラル文字の開始を示す
- セミコロン区切り: `正の書式;負の書式`
- Unicode文字: `&#x2934;`=↴, `&#x2935;`=↵, `&#x25B2;`=▲, `&#x25BC;`=▼
- BANカード(12-1)と組合せてKPIの前期比表示に使用

---

## 29. ワードクラウド（Text mark）

mark=Textで単語をサイズ・色で重み付け表示するパターン。
rows/colsを空にして自動配置させる。
学習元: テキストマイニングをしたファーストフード店のアンケート分析 (Tetsu Yamanaka, 12K views)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows />   <!-- 空: 自動配置 -->
    <cols />
    <pane>
      <mark class="Text" />
      <encodings>
        <size column="[{{DS_NAME}}].[sum:{{FREQ_MEASURE}}:qk]" />
        <color column="[{{DS_NAME}}].[none:{{CATEGORY_FIELD}}:nk]" />
        <text column="[{{DS_NAME}}].[none:{{WORD_FIELD}}:nk]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- `size`: 出現頻度などの数値メジャー
- `color`: ポジティブ/ネガティブ等のカテゴリ分類
- `text`: 単語そのもの（ディメンション）
- フィルタアクション(1-1)と組合せてクリック→他シート連動

---

## 30. 人口ピラミッド（Butterfly Chart）

左右反転軸で2つのカテゴリを対比表示するパターン。
年齢×性別の人口分布だけでなく、任意の対比に応用可能。
学習元: テキストマイニングをしたファーストフード店のアンケート分析 (Tetsu Yamanaka)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]</rows>
    <cols>[{{DS_NAME}}].[sum:{{LEFT_MEASURE}}:qk]
      + [{{DS_NAME}}].[sum:{{RIGHT_MEASURE}}:qk]</cols>
    <pane id='0'>
      <view>
        <axis type='x'>
          <reversed value='true' />  <!-- 左側を反転 -->
        </axis>
      </view>
      <mark class="Bar" />
    </pane>
    <pane id='1'>
      <mark class="Bar" />
      <!-- 右側は通常方向 -->
    </pane>
  </table>
</worksheet>
```

- `cols`に`+`で2メジャーを並べ、Dual Axis的に左右配置
- 左ペインの`<reversed value='true'/>` で左向きバーを実現
- `{{LEFT_MEASURE}}`: 例 `-1 * SUM([男性人口])` のように負値にする方法もあり
- 色分け: 各ペインで固定色を設定

---

## 31. ヒートマップ（Square mark）

mark=Squareでクロス集計の値を色の濃淡で表示するパターン。
学習元: テキストマイニングをしたファーストフード店のアンケート分析 (Tetsu Yamanaka)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[none:{{ROW_DIM}}:nk]</rows>
    <cols>[{{DS_NAME}}].[none:{{COL_DIM}}:nk]</cols>
    <pane>
      <mark class="Square" />
      <encodings>
        <color column="[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]" />
        <text column="[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- `color`: 連続値 → 自動でグラデーション（sequential palette推奨）
- `text`: セル内に数値を表示
- `mark class="Square"` でセル間に隙間ができ、マトリクス感が出る（`"Automatic"` だとBar等になる）
- カスタムパレット(8/17)と組合せて色調整可能

---

## 32. 円グラフ（Pie Chart）

mark=Pieで構成比を扇形で表示するパターン。wedge-sizeが角度、colorがカテゴリ分け。
パターン22（ドーナツ）は二重Pieだが、これは基本的な単一Pieチャート。
学習元: 人件費パーセント Viz (sableau), FTAS合祀ダッシュボード (sama.shibuya)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows />
    <cols />
    <pane>
      <view>
        <breakdown value="auto" />
      </view>
      <mark class="Pie" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <encodings>
        <color column="[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]" />
        <wedge-size column="[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]" />
        <text column="[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]" />
        <text column="[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- `wedge-size`: 扇形の角度を決めるメジャー（構成比の元データ）
- `color`: カテゴリディメンションで色分け
- `text`: ラベル表示（カテゴリ名+値の両方可）
- `mark-sizing-setting="marks-scaling-off"`: Pieサイズを固定（ダッシュボード内でサイズ変動させない）
- rows/cols空でPie表示。セット(11)と組合せて内側/外側のフィルタリングも可能

---

## 33. エリアチャート（Area mark）

mark=Areaで時系列データを面グラフとして表示するパターン。
スパークライン（KPIカード内ミニグラフ）としてもよく使われる。
学習元: Insurance Operations Dashboard (Neto Anyama), Pulse-inspired Dashboard (yoshitaka6076)

### 33-1. 基本エリアチャート
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]</rows>
    <cols>[{{DS_NAME}}].[none:{{DATE_FIELD}}:qk]</cols>
    <pane>
      <view>
        <breakdown value="auto" />
      </view>
      <mark class="Area" />
      <encodings>
        <color column="[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]" />
      </encodings>
      <style>
        <style-rule element="mark">
          <format attr="mark-transparency" value="29" />
        </style-rule>
      </style>
    </pane>
  </table>
</worksheet>
```

### 33-2. KPIスパークラインエリア（Dual Axis: Area + Circle）
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]
      + [{{DS_NAME}}].[usr:{{VALUE_MEASURE}}:qk]</rows>
    <cols>[{{DS_NAME}}].[none:{{DATE_CALC}}:qk]</cols>
    <pane id='0'>
      <mark class="Area" />
      <style>
        <style-rule element="mark">
          <format attr="mark-color" value="#3a3a45" />
          <format attr="mark-transparency" value="29" />
        </style-rule>
      </style>
    </pane>
    <pane id='1'>
      <mark class="Circle" />
      <!-- 最新値のみCircleで強調 -->
    </pane>
  </table>
</worksheet>
```

- `mark-transparency`: 面の透過度（0=不透明、255=完全透明）。29程度で背景が透ける
- スパークライン: rows/colsにメジャー+日付計算、サイズ固定でKPIカード内に配置
- Dual Axis (12) と組合せ: Area (背景面) + Circle (最新ポイント) で強調表示
- Stacked Area: colorにカテゴリを入れると積上げ面グラフ

---

## 34. ツリーマップ（Treemap）

mark=Automatic（内部的にSquare）でsize+color+textを組合せ、階層的な構成比を面積で表示。
rows/colsを空にしてsize encodingで面積配分を決定する。
学習元: Late-night Snacks Iron Viz 2026 (Shreya Arya)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows />
    <cols />
    <pane>
      <view>
        <breakdown value="auto" />
      </view>
      <mark class="Automatic" />
      <encodings>
        <color column="[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]" />
        <size column="[{{DS_NAME}}].[usr:{{VALUE_MEASURE}}:qk]" />
        <text column="[{{DS_NAME}}].[none:{{LABEL_DIM}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{DETAIL_DIM}}:nk]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- rows/cols空 + size encoding → Tableauが自動でツリーマップレイアウトを生成
- `lod`: Level of Detail（詳細レベル）。sizeの粒度を決める追加ディメンション
- `color`: カテゴリ（親階層）で色分け、`text`: ラベル表示
- 階層構造: lod + color で親→子の入れ子表現
- mark="Automatic"でTableauが最適配置。明示的に"Square"でも可

---

## 35. 予測バンド（MODEL_QUANTILE / Pulse-inspired）

Tableauの予測モデル関数MODEL_QUANTILEを使い、信頼区間付きの予測バンドを表示するパターン。
Tableau Pulse風ダッシュボードのコア技術。
学習元: Pulse-inspired Dashboard (yoshitaka6076)

### 35-1. 予測モデル計算フィールド
```xml
<!-- 上限バンド (75%) -->
<column caption="{{FIELD_CAPTION}}" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="MODEL_QUANTILE(&#13;&#10;    &quot;model=gp&quot;&#13;&#10;    , 0.75&#13;&#10;    , SUM([{{MEASURE_FIELD}}])&#13;&#10;    , ATTR([{{DATE_FIELD}}])&#13;&#10;    , ATTR(STR(DATEPART('weekday', [{{DATE_FIELD}}])))&#13;&#10;) - [{{LOWER_BOUND_CALC}}]">
    <table-calc ordering-type="Rows" />
  </calculation>
</column>

<!-- 下限バンド (25%) -->
<column caption="{{FIELD_CAPTION}}" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="MODEL_QUANTILE(&#13;&#10;    &quot;model=gp&quot;&#13;&#10;    , 0.25&#13;&#10;    , SUM([{{MEASURE_FIELD}}])&#13;&#10;    , ATTR([{{DATE_FIELD}}])&#13;&#10;    , ATTR(STR(DATEPART('weekday', [{{DATE_FIELD}}])))&#13;&#10;)">
    <table-calc ordering-type="Rows" />
  </calculation>
</column>
```

### 35-2. MtD/MoM比較計算セット
```xml
<!-- 当月MTD -->
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]" role="dimension" type="nominal">
  <calculation class="tableau" formula="DATEDIFF('month', [{{DATE_FIELD}}], [Parameters].[{{PARAM_NAME}}]) = 0&#13;&#10;AND&#13;&#10;[{{DATE_FIELD}}] &lt;= [Parameters].[{{PARAM_NAME}}]" />
</column>

<!-- 前月同期 -->
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]" role="dimension" type="nominal">
  <calculation class="tableau" formula="DATEDIFF('month', [{{DATE_FIELD}}], [Parameters].[{{PARAM_NAME}}]) = 1&#13;&#10;AND&#13;&#10;[{{DATE_FIELD}}] &lt;= DATEADD('month', -1, [Parameters].[{{PARAM_NAME}}])" />
</column>

<!-- MTD差分 -->
<column caption="{{FIELD_CAPTION}}" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="SUM([{{MTD_CALC}}]) - SUM([{{MTD_PRIOR_CALC}}])" />
</column>
```

- `MODEL_QUANTILE("model=gp", quantile, measure, ...)`: ガウス過程(GP)回帰による予測
- `quantile`: 0.25/0.75で50%信頼区間、0.1/0.9で80%信頼区間
- `table-calc ordering-type="Rows"`: テーブル計算として実行（行方向）
- MtD/MoM: 当月累計と前月同期を比較するPulse標準パターン
- エリアチャート(33-1)と組合せ: 予測バンドをAreaで表示、実績値をLineで重ねる

---

## 36. ロリポップチャート（Lollipop Chart）

Dual Axisで細いBar（棒）+ Circle（点）を重ね、ロリポップ型のチャートを構成するパターン。
バーチャートより視覚的に軽く、カテゴリ間の比較がしやすい。
学習元: Customer Behavioral Analytics & Segmentation (Constantin Dumitriu)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]</rows>
    <cols>[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]
      + [{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]</cols>
    <pane id='0'>
      <mark class="Bar" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <style>
        <style-rule element="mark">
          <format attr="size" value="0.186" />
          <format attr="has-stroke" value="false" />
        </style-rule>
      </style>
    </pane>
    <pane id='1'>
      <mark class="Circle" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <encodings>
        <text column="[{{DS_NAME}}].[sum:{{VALUE_MEASURE}}:qk]" />
      </encodings>
      <style>
        <style-rule element="mark">
          <format attr="size" value="1.945" />
          <format attr="has-stroke" value="true" />
        </style-rule>
      </style>
    </pane>
  </table>
</worksheet>
```

- `size="0.186"`: Barを極細に設定（棒部分）
- `size="1.945"`: Circleを大きめに設定（先端の点）
- `marks-scaling-off`: ダッシュボードサイズ変更時にマークサイズを固定
- `has-stroke="false"`: Bar部分の枠線を消す
- Dual Axis (12) を使い、同じメジャーを2回colsに配置して重ねる

---

## 37. 動的ゾーン表示（Dynamic Zone Visibility / DZV）

Boolean計算フィールドの値でダッシュボードゾーンの表示/非表示を制御するパターン。
フィルタパネルの開閉、詳細ペインの切替、ページナビゲーションに使用。
学習元: Late-night Snacks Iron Viz 2026 (Shreya Arya), DPC2021 (Takashi Nishi)

### 37-1. DZVブール計算フィールド
```xml
<!-- 表示条件: パラメータが特定値のとき表示 -->
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="[Parameters].[{{PARAM_NAME}}] = &quot;{{TARGET_VALUE}}&quot;" />
</column>

<!-- 非表示条件: パラメータが特定値でないとき表示 -->
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="[Parameters].[{{PARAM_NAME}}] != &quot;{{EXCLUDE_VALUE}}&quot;" />
</column>
```

### 37-2. トグルボタン（ゾーン切替）
```xml
<zone id="{{ZONE_ID}}" type-v2="layout-basic">
  <zone-style>
    <format attr="border-color" value="#000000" />
    <format attr="border-style" value="none" />
    <format attr="border-width" value="0" />
    <format attr="margin" value="0" />
  </zone-style>
  <button type="toggle">
    <toggle-action action-name="tabdoc:toggle-button-click-action" />
    <button-visual-state state-index="0">
      <format attr="text" value="&#x25B6; 表示" />
    </button-visual-state>
    <button-visual-state state-index="1">
      <format attr="text" value="&#x25BC; 閉じる" />
    </button-visual-state>
  </button>
</zone>
```

- DZVはBoolean計算フィールドをゾーンの`visibility`に紐付ける
- パラメータアクション(7)と組合せ: クリック→パラメータ更新→DZV計算→ゾーン切替
- トグルボタン: `tabdoc:toggle-button-click-action`で2状態切替
- フィルタパネル開閉(4)の発展版として、ゾーン単位でより細かい制御が可能

---

## 38. 100%積上げバー（Stacked Percent-of-Total）

`pcto:`（percent-of-total）エンコーディングで構成比を積上げバーとして表示するパターン。
市場シェア、カテゴリ構成比、回答割合の比較に最適。
学習元: Melbourne Public Transport Frequency (Transport for Victoria)

```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[none:{{ROW_DIM}}:nk]</rows>
    <cols>[{{DS_NAME}}].[pcto:cnt:{{VALUE_FIELD}}:qk:2]</cols>
    <pane>
      <view>
        <breakdown value="auto" />
      </view>
      <mark class="Bar" />
      <encodings>
        <color column="[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]" />
        <text column="[{{DS_NAME}}].[pcto:cnt:{{VALUE_FIELD}}:qk:2]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- `pcto:cnt:` プレフィックス: カウントの割合を自動計算（0.0〜1.0）
- `pcto:sum:` も使用可能（合計値の割合）
- 軸を0〜1.0（or 0%〜100%）に固定して比較しやすくする
- colorにカテゴリディメンションを入れることで自動的に積上げ構成比バーになる
- テーブル計算(17)の`PERCENT_OF_TOTAL()`と同等だが、XML上はエンコーディングで完結

---

## 39. バレットチャート（Bullet Chart / Target vs Actual）

実績バーに目標線（Reference Line）を重ね、達成/未達をBoolean色分けするパターン。
KPIダッシュボードの目標管理、予算vs実績比較に最適。
学習元: Viz 7 KPI (Yoshihito Kimura)

### 39-1. 達成判定ブール計算
```xml
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="SUM([{{ACTUAL_MEASURE}}])&gt;=SUM([{{TARGET_MEASURE}}])" />
</column>
```

### 39-2. 達成率計算
```xml
<column caption="{{FIELD_CAPTION}}" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="SUM([{{ACTUAL_MEASURE}}])/SUM([{{TARGET_MEASURE}}])" />
</column>
```

### 39-3. バレットバー構成（3ペイン）
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>[{{DS_NAME}}].[none:{{CATEGORY_DIM}}:nk]</rows>
    <cols>[{{DS_NAME}}].[sum:{{ACTUAL_MEASURE}}:qk]</cols>
    <!-- Pane 0: 背景バー（予算/目標の全体範囲） -->
    <pane id='0'>
      <mark class="Bar" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <reference-line axis-column="[{{DS_NAME}}].[sum:{{ACTUAL_MEASURE}}:qk]"
        formula="sum" id="refline0" label-type="none" scope="per-cell"
        value-column="[{{DS_NAME}}].[sum:{{TARGET_MEASURE}}:qk]" z-order="1" />
      <style>
        <style-rule element="mark">
          <format attr="mark-transparency" value="139" />
        </style-rule>
      </style>
    </pane>
    <!-- Pane 1: 実績バー（達成色分け） -->
    <pane id='1'>
      <mark class="Bar" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <encodings>
        <color column="[{{DS_NAME}}].[usr:{{ACHIEVED_BOOL}}:nk]" />
        <text column="[{{DS_NAME}}].[usr:{{ACHIEVEMENT_RATE}}:qk]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- 3ペイン構成: 背景(目標全体) + 実績(色分け) で視覚的にBullet Chartを構成
- `reference-line`: 目標値を黒線として重ねる（fill-above/below は透明 `#00000000`）
- 達成判定Boolean(39-1) → True/Falseで色が自動切替（達成=青/緑, 未達=赤/オレンジ）
- 達成率(39-2) → テキストラベルに%表示
- Dual Axis (6) と組合せ可: 同じメジャーを2回配置して背景+実績を重ねる

---

## 40. パラメータ切替（Dimension Swap / Measure Switcher）

CASE文でパラメータの値に応じて表示するディメンションやメジャーを動的に切替えるパターン。
1つのシートで複数の切り口を提供する際に使用。
学習元: Bottoms Up 5 Year Workforce Plan (Scott Reida)

### 40-1. ディメンション切替計算
```xml
<column caption="{{FIELD_CAPTION}}" datatype="string" name="[{{CALC_NAME}}]" role="dimension" type="nominal">
  <calculation class="tableau" formula="CASE [Parameters].[{{PARAM_NAME}}]&#13;&#10;WHEN &quot;{{OPTION_A}}&quot; THEN [{{FIELD_A}}]&#13;&#10;WHEN &quot;{{OPTION_B}}&quot; THEN [{{FIELD_B}}]&#13;&#10;WHEN &quot;{{OPTION_C}}&quot; THEN [{{FIELD_C}}]&#13;&#10;END" />
</column>
```

### 40-2. 切替用リストパラメータ
```xml
<column caption="{{PARAM_CAPTION}}" datatype="string" name="[{{PARAM_NAME}}]" param-domain-type="list" role="measure" type="nominal" value="&quot;{{DEFAULT_VALUE}}&quot;">
  <calculation class="tableau" formula="&quot;{{DEFAULT_VALUE}}&quot;" />
  <members>
    <member value="&quot;{{OPTION_A}}&quot;" />
    <member value="&quot;{{OPTION_B}}&quot;" />
    <member value="&quot;{{OPTION_C}}&quot;" />
  </members>
</column>
```

- `CASE [Parameters].[param]`: パラメータ値に応じて異なるフィールドを返す
- ディメンション切替: rowsまたはcolsに計算フィールドを配置→パラメータ変更でドリルパス変更
- メジャー切替: `CASE ... WHEN "売上" THEN SUM([売上]) WHEN "利益" THEN SUM([利益]) END` でも同様
- 複数段: Dive 1 / Dive 2 の2段切替で2軸の組合せを自由に変更可能
- パラメータコントロール(10)と組合せ: ダッシュボード上でドロップダウン切替UI

---

## 41. URLアクション（外部リンク / URL Action）

クリック時にフィールド値を埋め込んだURLで外部サービスを開くパターン。
Google Maps経路案内、外部Webサイトへの遷移に使用。
学習元: 沖縄市統計Viz (.4721156007)

### 41-1. URLアクション（ダッシュボードゾーン内表示）
```xml
<action caption="{{ACTION_CAPTION}}" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" />
  <link caption="" expression="https://maps.google.com/maps?q=&lt;AVG([{{LAT_FIELD}}])&gt;,&lt;AVG([{{LON_FIELD}}])&gt;&amp;z=13">
    <url-action-type>specific-zone</url-action-type>
    <url-action-target>{{ZONE_ID}}</url-action-target>
  </link>
</action>
```

### 41-2. URLアクション（新しいタブで開く）
```xml
<action caption="{{ACTION_CAPTION}}" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{WS_NAME}}" />
  <link caption="" expression="{{BASE_URL}}?param=&lt;[{{DS_NAME}}].[none:{{FIELD_NAME}}:nk]&gt;" />
</action>
```

- `expression`: URL文字列内に `&lt;field_reference&gt;` でフィールド値を埋め込む
- `<url-action-type>specific-zone</url-action-type>`: ダッシュボード内のWebページゾーンに表示
- `<url-action-target>{{ZONE_ID}}</url-action-target>`: 表示先のゾーンID
- target省略時: 新しいブラウザタブで開く（デフォルト動作）
- `&amp;` でURLパラメータを連結（XMLエスケープ必須）
- Google Maps例: 緯度経度フィールドからストリートビューやルート案内を開く

---

## 42. 空間距離フィルタ（Spatial Distance / Buffer）

パラメータで指定した地点からの距離を計算し、範囲内のポイントをセットアクションで選択するパターン。
不動産検索、施設周辺分析、商圏分析に使用。
学習元: 不動産会社向け土地仕入検討マップ (Kiyo Kojima)

### 42-1. 基準点（パラメータ座標→MAKEPOINT）
```xml
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="MAKEPOINT([Parameters].[{{LAT_PARAM}}],[Parameters].[{{LON_PARAM}}])" />
</column>
```

### 42-2. 距離計算
```xml
<column caption="{{FIELD_CAPTION}}" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="DISTANCE([{{REFERENCE_POINT_CALC}}], MAKEPOINT([{{LAT_FIELD}}],[{{LON_FIELD}}]), 'km')" />
</column>
```

### 42-3. 範囲内判定（セット用）
```xml
<column caption="{{FIELD_CAPTION}}" datatype="integer" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="IF [{{IN_SET_BOOL_CALC}}]&#13;&#10;THEN 1&#13;&#10;ELSE 0&#13;&#10;END" />
</column>
```

### 42-4. セットアクション（追加/削除ペア）
```xml
<!-- セット追加 -->
<edit-group-action caption="{{ADD_CAPTION}}" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{WS_NAME}}" />
  <add-or-remove-marks value="add" />
  <params>
    <param name="selection-clear-set-option" value="do-nothing" />
    <param name="target-group" value="[{{DS_NAME}}].[{{SET_NAME}}]" />
  </params>
</edit-group-action>

<!-- セット削除 -->
<edit-group-action caption="{{REMOVE_CAPTION}}" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{REMOVE_WS}}" />
  <add-or-remove-marks value="remove" />
  <params>
    <param name="selection-clear-set-option" value="do-nothing" />
    <param name="target-group" value="[{{DS_NAME}}].[{{SET_NAME}}]" />
  </params>
</edit-group-action>
```

- `MAKEPOINT` + `DISTANCE`: 空間関数で2点間距離をkm単位で計算
- パラメータアクション(1-3)で地図クリック→基準点座標を更新→距離再計算
- セットアクション(1-4): add/remove ペアで選択リストを管理（追加ワークシートと削除ワークシートを分離）
- `selection-clear-set-option="do-nothing"`: 選択解除時にセットを維持
- FIXED LOD式で重複排除: `{ FIXED [住所]: MAX([連番]) }` でユニーク化

---

## 43. 共起ネットワーク（Co-occurrence Network Graph）

X/Y座標の散布図にDual Axisで Line（エッジ）+ Circle（ノード）を重ね、ネットワークグラフを描画するパターン。
テキスト分析の共起関係、組織関係図、ソーシャルネットワーク可視化に使用。
学習元: ふるさと納税DaB (Naoki Namihira)

### 43-1. ネットワークグラフ構成（Line + Circle Dual-Axis）
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <rows>([{{DS_NAME}}].[avg:{{Y_FIELD}}:qk] + [{{DS_NAME}}].[avg:{{Y_FIELD}}:qk])</rows>
    <cols>[{{DS_NAME}}].[avg:{{X_FIELD}}:qk]</cols>
    <!-- Pane 0: ベース（LODでノードグループ） -->
    <pane id='0'>
      <mark class="Automatic" />
      <encodings>
        <lod column="[{{DS_NAME}}].[none:{{NODE_ID}}:nk]" />
      </encodings>
    </pane>
    <!-- Pane 1: エッジ（Line mark, 細い灰色線） -->
    <pane id='1'>
      <mark class="Line" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <encodings>
        <lod column="[{{DS_NAME}}].[none:{{SOURCE_FIELD}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{TARGET_FIELD}}:nk]" />
      </encodings>
      <style>
        <style-rule element="mark">
          <format attr="mark-color" value="#b0b0b0" />
          <format attr="size" value="0.34" />
        </style-rule>
      </style>
    </pane>
    <!-- Pane 2: ノード（Circle mark, サイズ=出現数, ラベル付き） -->
    <pane id='2'>
      <mark class="Circle" />
      <mark-sizing mark-sizing-setting="marks-scaling-off" />
      <encodings>
        <size column="[{{DS_NAME}}].[usr:{{COUNT_MEASURE}}:qk]" />
        <text column="[{{DS_NAME}}].[none:{{LABEL_DIM}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{NODE_ID}}:nk]" />
      </encodings>
      <style>
        <style-rule element="mark">
          <format attr="mark-labels-show" value="true" />
          <format attr="mark-labels-cull" value="true" />
          <format attr="size" value="1.13" />
        </style-rule>
      </style>
    </pane>
  </table>
</worksheet>
```

### 43-2. 軸非表示設定
```xml
<style-rule element="axis">
  <encoding attr="space" class="1" field="[{{DS_NAME}}].[avg:{{Y_FIELD}}:qk]"
    field-type="quantitative" fold="true" scope="rows" synchronized="true" type="space" />
  <format attr="display" class="1" field="[{{DS_NAME}}].[avg:{{Y_FIELD}}:qk]" scope="rows" value="false" />
  <format attr="display" class="0" field="[{{DS_NAME}}].[avg:{{Y_FIELD}}:qk]" scope="rows" value="false" />
  <format attr="display" class="0" field="[{{DS_NAME}}].[avg:{{X_FIELD}}:qk]" scope="cols" value="false" />
</style-rule>
```

- 前提: CSVにsource/target/X/Yの座標列が必要（Pythonのnetworkx等で事前レイアウト計算）
- Dual Axis (6): Y軸を2回配置し、Line (エッジ) と Circle (ノード) を重ねる
- `fold="true" synchronized="true"`: 2つのY軸スケールを同期
- ノードサイズ: 出現数(size encoding)で重要度を表現
- エッジ色: 灰色 `#b0b0b0` + 細い線 `size=0.34` で控えめに
- 軸非表示: `display="false"` でX/Y軸ラベルを消し、ネットワーク図に見せる

---

## 44. PDFエクスポートボタン

ダッシュボード内にPDFエクスポートボタンを配置するパターン。
ユーザーがワンクリックで現在のダッシュボード状態をPDF出力できる。
学習元: 不動産会社向け土地仕入検討マップ (Kiyo Kojima)

```xml
<zone type-v2="dashboard-object" id="{{ZONE_ID}}">
  <button action="" button-click-action-metadata="pdf" button-type="text">
    <export-button-action>tabdoc:abstract-dashboard-button-export-wrapper dashboard-button-export-type="pdf" dashboarddoc-id="{{{DB_GUID}}}"</export-button-action>
    <button-visual-state>
      <caption>PDF出力</caption>
      <button-caption-font-style fontcolor="#ffffff" fontname="Tableau Bold" fontsize="12" />
      <format attr="background-color" value="{{BUTTON_BG_COLOR}}" />
    </button-visual-state>
  </button>
</zone>
```

- `button-click-action-metadata="pdf"`: PDFエクスポートアクション
- `dashboard-button-export-type`: `pdf` / `image` / `crosstab` / `powerpoint` から選択
- `dashboarddoc-id`: 対象ダッシュボードのGUID
- go-to-sheetボタン(1-5)と同じzone構造だが、action属性が異なる
- Tableau Server/Cloud環境でのみ動作（Tableau Public/Desktopでは無効）

---

## 45. 空間バッファ（Spatial Buffer / 同心円描画）

地図上のクリック地点を中心にBUFFER関数で同心円を描画するパターン。
パターン42（距離計算）の視覚表現版。商圏分析、施設到達圏、避難圏の可視化に使用。
学習元: 指定した地点を中心に円を描く (川崎BIS / kawasakibis)

### 45-1. 座標キャプチャ（パラメータアクション×2）
```xml
<!-- 経度キャプチャ -->
<edit-parameter-action caption="select_経度" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{WS_NAME}}" />
  <agg-type type="attr" />
  <clear-option type="do-nothing" value="r:1:0:1" />
  <params>
    <param name="source-field" value="[{{DS_NAME}}].[Longitude (generated)]" />
    <param name="target-parameter" value="[Parameters].[{{LON_PARAM}}]" />
  </params>
</edit-parameter-action>

<!-- 緯度キャプチャ -->
<edit-parameter-action caption="select_緯度" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{WS_NAME}}" />
  <agg-type type="attr" />
  <clear-option type="do-nothing" value="r:::1" />
  <params>
    <param name="source-field" value="[{{DS_NAME}}].[Latitude (generated)]" />
    <param name="target-parameter" value="[Parameters].[{{LAT_PARAM}}]" />
  </params>
</edit-parameter-action>
```

### 45-2. BUFFER計算（同心円ポリゴン）
```xml
<!-- 基準点 -->
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="MAKEPOINT([Parameters].[{{LAT_PARAM}}],[Parameters].[{{LON_PARAM}}])" />
</column>

<!-- バッファ円1（内円） -->
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="BUFFER([{{REFERENCE_POINT_CALC}}],[Parameters].[{{RADIUS_PARAM_1}}],&quot;km&quot;)" />
</column>

<!-- バッファ円2（外円） -->
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="BUFFER([{{REFERENCE_POINT_CALC}}],[Parameters].[{{RADIUS_PARAM_2}}],&quot;km&quot;)" />
</column>
```

### 45-3. バッファ円のマップ表示（Multipolygonレイヤー）
```xml
<pane generated-title="{{FIELD_CAPTION}}" id="{{PANE_ID}}" inert="true">
  <mark class="Multipolygon" />
  <encodings>
    <lod column="[{{DS_NAME}}].[none:{{GROUP_DIM}}:nk]" />
    <geometry column="[{{DS_NAME}}].[Geometry (generated)]" />
  </encodings>
  <style>
    <style-rule element="mark">
      <format attr="mark-color" value="#d4d4d4" />
      <format attr="mark-transparency" value="114" />
    </style-rule>
  </style>
</pane>
```

- `BUFFER(point, distance, unit)`: 空間ポイントから指定距離の円ポリゴンを生成
- `inert="true"`: バッファ円レイヤーをクリック不可にし、背面に固定
- 複数バッファ: パラメータを変えた複数BUFFER計算で同心円を重ねる（500m/1km等）
- ラベル位置: `MAKEPOINT([lat]+0.0045, [lon])` で円の縁にラベル用ポイントを配置
- パターン42(距離計算)+45(バッファ描画)の組合せで完全な商圏分析ダッシュボードが構成可能

---

## 46. トレンドライン（Trendline / 回帰線）

散布図や折れ線グラフにトレンドライン（回帰線）を重ねるパターン。
相関分析、予測傾向の可視化、外れ値検出に使用。
学習元: 人件費デモ Viz (.16316142004130)

### 46-1. トレンドライン基本構成
```xml
<pane selection-relaxation-option="selection-relaxation-allow"
  x-axis-name="[{{DS_NAME}}].[sum:{{X_MEASURE}}:qk]"
  y-axis-name="[{{DS_NAME}}].[sum:{{Y_MEASURE}}:qk]">
  <view>
    <breakdown value="auto" />
  </view>
  <mark class="Circle" />
  <encodings>
    <color column="[{{DS_NAME}}].[none:{{COLOR_DIM}}:nk]" />
    <lod column="[{{DS_NAME}}].[none:{{DETAIL_DIM}}:nk]" />
  </encodings>
  <trendline enable-confidence-bands="false" enable-instant-analytics="true"
    enabled="true" exclude-color="false" exclude-intercept="false" fit="linear">
    <excluded-factors>
      <column>[{{DS_NAME}}].[none:{{EXCLUDE_DIM}}:nk]</column>
    </excluded-factors>
  </trendline>
</pane>
```

- `fit`: `linear` / `logarithmic` / `exponential` / `polynomial` / `power` から選択
- `enable-confidence-bands="true"`: 95%信頼区間バンドを表示
- `exclude-color="true"`: 色分けしたカテゴリごとに個別トレンドラインを引かない（全体1本）
- `exclude-intercept="true"`: 切片を0に固定（原点通過の回帰線）
- `<excluded-factors>`: 特定ディメンションをトレンドライン計算から除外
- Dual Axis (6) と組合せ: 片方のペインのみにトレンドラインを付けることが可能

---

## 47. Viz Extension（外部拡張ビジュアル）

Tableau Viz Extensionsを使い、サードパーティの可視化コンポーネントをワークシート内に埋め込むパターン。
KPIカード、ドリルダウンツリー、カスタムチャートに使用。
学習元: Can You Create KPI Cards with Viz Extensions? (Kyle Yetter)

### 47-1. Viz Extension ペイン構成
```xml
<pane selection-relaxation-option="selection-relaxation-allow">
  <view>
    <breakdown value="auto" />
  </view>
  <_.fcp.VizExtensions.false...mark class="Automatic" />
  <_.fcp.VizExtensions.true...mark class="VizExtension" />
  <_.fcp.VizExtensions.true...add-in add-in-id="{{EXTENSION_ID}}"
    extension-url="{{EXTENSION_URL}}" extension-version="{{VERSION}}"
    instance-id="{{GUID}}">
    <instance-settings>
      <setting key="vizConfig" value="{{JSON_CONFIG_ESCAPED}}" />
    </instance-settings>
    <type-settings>
      <worksheet />
    </type-settings>
  </_.fcp.VizExtensions.true...add-in>
  <encodings>
    <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{{GUID}}}"
      column="[{{DS_NAME}}].[none:{{FIELD_NAME}}:nk]" />
  </encodings>
</pane>
```

### 47-2. 代表的なExtension ID一覧
```
com.ladataviz.extension.bang        — KPI Bang Cards（KPI表示+スパークライン）
com.ladataviz.extension.drilldowndev — Drill Down Tree（階層ツリーフィルタ）
com.tableau.extension.bubbleChart   — Bubble Chart（カスタムバブル）
com.tableau.extension.sankey        — Sankey Chart（フロー図・2024.2+ native Sankey）
```

- `_.fcp.VizExtensions.false...mark` + `_.fcp.VizExtensions.true...mark`: 後方互換性のためのフォールバックペア
- `extension-url`: Tableau Exchange CDN上のURL（`partner-extensions.tableauusercontent.com`）
- `instance-settings`: Extension固有のJSON設定（HTMLエスケープ済み: `&quot;` / `&amp;`）
- `encoding-id`: VizExtensions固有のLODエンコーディングUUID
- Tableau Public/Desktop: 一部Extensionのみ利用可。Cloud/Server: フル対応

---

## 48. 複数選択パラメータ（Multi-Select String Parameter）

文字列パラメータに複数選択値をカンマ区切りで蓄積し、CONTAINS()で判定するパターン。
セットアクションの代替として、カスタムのトグル選択UIを実現。
学習元: From Empire To Identity Iron Viz 2026 (Rob Taylor), DPC2021 (.DPC2021)

### 48-1. リスト型文字列パラメータ
```xml
<column caption="{{PARAM_CAPTION}}" datatype="string" name="[{{PARAM_NAME}}]"
  param-domain-type="list" role="measure" type="nominal"
  value="&quot;{{DEFAULT_VALUE}}&quot;">
  <calculation class="tableau" formula="&quot;{{DEFAULT_VALUE}}&quot;" />
  <members>
    <member value="&quot;{{OPTION_A}}&quot;" />
    <member value="&quot;{{OPTION_B}}&quot;" />
    <member value="&quot;{{OPTION_C}}&quot;" />
  </members>
</column>
```

### 48-2. トグル選択計算（CONTAINS/REPLACE）
```xml
<column caption="{{FIELD_CAPTION}}" datatype="string" name="[{{CALC_NAME}}]"
  role="dimension" type="nominal">
  <calculation class="tableau" formula="IF CONTAINS([Parameters].[{{PARAM_NAME}}], [{{FIELD_NAME}}])&#13;&#10;THEN REPLACE([Parameters].[{{PARAM_NAME}}], [{{FIELD_NAME}}] + &quot;,&quot;, &quot;&quot;)&#13;&#10;ELSE [Parameters].[{{PARAM_NAME}}] + [{{FIELD_NAME}}] + &quot;,&quot;&#13;&#10;END" />
</column>
```

### 48-3. 選択状態判定（ハイライト/フィルタ用）
```xml
<column caption="{{FIELD_CAPTION}}" datatype="boolean" name="[{{CALC_NAME}}]"
  role="measure" type="nominal">
  <calculation class="tableau" formula="CONTAINS([Parameters].[{{PARAM_NAME}}], [{{FIELD_NAME}}])" />
</column>
```

### 48-4. パラメータアクション（トグル更新）
```xml
<edit-parameter-action caption="{{ACTION_CAPTION}}" name="[{{ACTION_NAME}}]">
  <activation type="on-select" />
  <source dashboard="{{DB_NAME}}" type="sheet" worksheet="{{WS_NAME}}" />
  <agg-type type="attr" />
  <clear-option type="do-nothing" value="s:" />
  <params>
    <param name="source-field" value="[{{DS_NAME}}].[usr:{{TOGGLE_CALC}}:nk]" />
    <param name="target-parameter" value="[Parameters].[{{PARAM_NAME}}]" />
  </params>
</edit-parameter-action>
```

- カンマ区切り蓄積: クリックで値を追加、再クリックで削除（トグル動作）
- `param-domain-type="list"`: 定義済みリストの値のみ許可（`range`はスライダー用）
- 48-3のBoolean判定でcolor encodingに使用→選択中アイテムをハイライト色、非選択をグレー
- セットアクション(1-4)との違い: パラメータは選択解除時に値を保持できる
- 数値パラメータも同様: `param-domain-type="range"` + `<range min="..." max="..." granularity="..." />`

---

## 49. Sankeyダイアグラム（Sankey Diagram / Flow Chart）

> **⚠️ Cloud非推奨**: MAKEPOINT+ベジェ曲線方式は Cloud で Curve計算/LOD不整合により空白描画頻発。
> **新規実装は Section 49B (VizExtension Sankey)** を使用すること。本セクションは学習用に保持。

MAKEPOINT + ベジェ曲線計算でフロー（サンキー）図を描画するパターン。
カテゴリ間の遷移、プロセスフロー、予算配分の可視化に使用。
学習元: From Empire To Identity Iron Viz 2026 (Rob Taylor)

### 49-1. データ構造（前提）
```
必須列: sourceId, targetId, value, type (node/link), path, x, y, t
- type='node': ノード描画用レコード（1ノード=1行）
- type='link': エッジ描画用レコード（1リンク=N行、t=0〜1のステップ）
- x, y: ノード/リンクの座標（事前レイアウト計算済み）
- path: ベジェ曲線のパスインデックス（1, 2, ...）
```

### 49-2. 正規化座標計算
```xml
<!-- X正規化 -->
<column caption="X Normalized" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="[x]/ {MAX([x])}" />
</column>

<!-- Y正規化 -->
<column caption="Y Normalized" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="[y]/ {MAX([y])}" />
</column>

<!-- T パラメータ（ベジェ曲線補間） -->
<column caption="T" datatype="real" name="[{{CALC_NAME}}]" role="measure" type="quantitative">
  <calculation class="tableau" formula="([{{PATH_FIELD}}]-1)/{MAX([{{PATH_FIELD}}])-1}" />
</column>
```

### 49-3. ノード・リンク MAKEPOINT
```xml
<!-- ノード用 MAKEPOINT -->
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="IF [type]= 'node'&#13;&#10;THEN MAKEPOINT([{{Y_NORM_CALC}}], -[{{X_NORM_CALC}}])&#13;&#10;END" />
</column>

<!-- リンク用 MAKEPOINT -->
<column caption="{{FIELD_CAPTION}}" datatype="spatial" name="[{{CALC_NAME}}]" role="measure" type="nominal">
  <calculation class="tableau" formula="IF [type]= 'link' AND [{{PATH_FIELD}}] &gt; 0&#13;&#10;THEN MAKEPOINT([{{Y_NORM_CALC}}], -[{{X_NORM_CALC}}])&#13;&#10;END" />
</column>
```

### 49-4. マップ構成（Mark Layer）
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <!-- リンクレイヤー: Lineマークで曲線エッジ -->
    <pane id="0">
      <mark class="Line" />
      <encodings>
        <color column="[{{DS_NAME}}].[usr:{{HIGHLIGHT_CALC}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{SOURCE_ID}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{TARGET_ID}}:nk]" />
        <geometry column="[{{DS_NAME}}].[usr:{{LINK_MAKEPOINT}}:ok]" />
      </encodings>
      <style>
        <style-rule element="mark">
          <format attr="mark-transparency" value="140" />
        </style-rule>
      </style>
    </pane>
    <!-- ノードレイヤー: Circleマークで頂点 -->
    <pane id="1">
      <mark class="Circle" />
      <encodings>
        <size column="[{{DS_NAME}}].[sum:{{VALUE_FIELD}}:qk]" />
        <text column="[{{DS_NAME}}].[none:{{LABEL_DIM}}:nk]" />
        <lod column="[{{DS_NAME}}].[none:{{NODE_ID}}:nk]" />
        <geometry column="[{{DS_NAME}}].[usr:{{NODE_MAKEPOINT}}:ok]" />
      </encodings>
    </pane>
  </table>
</worksheet>
```

- **前処理必須**: CSVにx/y座標・type・pathを含むデータが必要（Python networkx/d3-sankey等で生成）
- T パラメータ: ベジェ曲線の補間値（0〜1）。リンク上の各点の位置を制御
- `{MAX([x])}`: LOD式（FIXED）で全レコードのMAXを取得→正規化
- ハイライト: パターン48(Multi-Select Parameter)と組合せ→クリックでフロー経路をハイライト
- 地図空間モデル: MAKEPOINT+Geometry encodingでマップビュー上に描画（軸非表示で図に見せる）
- パターン43(共起ネットワーク)の発展版: ネットワークは無向グラフ、Sankeyは有向フロー

---

## 49B. Sankey VizExtension（Tableau 2024.2+ ネイティブSankey・推奨）

`com.tableau.extension.sankey` v1.5.0 を使った新方式。Cloud で完全動作する。
CSVは3列 (level1, level2, measure) でOK。Path複製・RankFrom/RankTo・ベジェ計算すべて不要。

学習元: サンプル市HPアクセス分析v5.3 (2026-05-25 実装)

### 49B-1. データ構造（CSV）
```
チャネル,着地ページ,セッション
Direct,01. トップ,3500
Organic Search,02. ごみカレンダー,2100
Paid,03. 職員採用,800
...
```

### 49B-2. Worksheet本体 XML
```xml
<worksheet name="{{WS_NAME}}">
  <table>
    <view>
      <datasources><datasource caption="{{DS_CAPTION}}" name="{{DS_NAME}}" /></datasources>
      <datasource-dependencies datasource="{{DS_NAME}}">
        <column-instance column="[{{LEVEL1}}]" derivation="None" name="[none:{{LEVEL1}}:nk]" pivot="key" type="nominal" />
        <column-instance column="[{{LEVEL2}}]" derivation="None" name="[none:{{LEVEL2}}:nk]" pivot="key" type="nominal" />
        <column-instance column="[{{MEASURE}}]" derivation="Sum" name="[sum:{{MEASURE}}:qk]" pivot="key" type="quantitative" />
        <column datatype="integer" name="[{{MEASURE}}]" role="measure" type="quantitative" />
        <column datatype="string" name="[{{LEVEL1}}]" role="dimension" type="nominal" />
        <column datatype="string" name="[{{LEVEL2}}]" role="dimension" type="nominal" />
      </datasource-dependencies>
      <aggregation value="true" />
    </view>
    <panes>
      <pane selection-relaxation-option="selection-relaxation-allow">
        <view><breakdown value="auto" /></view>
        <_.fcp.VizExtensions.false...mark class="Automatic" />
        <_.fcp.VizExtensions.true...mark class="VizExtension" />
        <mark-sizing mark-sizing-setting="marks-scaling-off" />
        <_.fcp.VizExtensions.true...add-in add-in-id="com.tableau.extension.sankey"
          extension-url="https://extensions.tableauusercontent.com/sandbox/sankey/sankey.html"
          extension-version="1.5.0" instance-id="{{INSTANCE_GUID_32HEX}}">
          <instance-settings>
            <setting key="color-map" value="{{COLOR_MAP_JSON_ESCAPED}}" />
          </instance-settings>
          <type-settings><worksheet /></type-settings>
        </_.fcp.VizExtensions.true...add-in>
        <encodings>
          <!-- 各Level次元: lod + custom level の2行ペア (encoding-id同一UUID) -->
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_A}}" column="[{{DS_NAME}}].[none:{{LEVEL1}}:nk]" />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_A}}" column="[{{DS_NAME}}].[none:{{LEVEL1}}:nk]" custom-type-name="level" />
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_B}}" column="[{{DS_NAME}}].[none:{{LEVEL2}}:nk]" />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_B}}" column="[{{DS_NAME}}].[none:{{LEVEL2}}:nk]" custom-type-name="level" />
          <!-- Linkメジャー: lod + custom edge の2行ペア -->
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_C}}" column="[{{DS_NAME}}].[sum:{{MEASURE}}:qk]" />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_C}}" column="[{{DS_NAME}}].[sum:{{MEASURE}}:qk]" custom-type-name="edge" />
          <!-- 各次元/メジャーの追加 <lod> 行 (encoding-idは別UUID) -->
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_D}}" column="[{{DS_NAME}}].[none:{{LEVEL1}}:nk]" />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_E}}" column="[{{DS_NAME}}].[none:{{LEVEL2}}:nk]" />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_F}}" column="[{{DS_NAME}}].[sum:{{MEASURE}}:qk]" />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id="{{UUID_G}}" column="[{{DS_NAME}}].[sum:{{MEASURE}}:qk]" />
        </encodings>
        <style>
          <style-rule element="mark">
            <format attr="mark-labels-show" value="true" />
            <format attr="mark-labels-cull" value="false" />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows /><cols />
  </table>
  <simple-id uuid="{{WS_UUID}}" />
</worksheet>
```

### 49B-3. Workbook root の Extension Registration
TWB末尾 `</workbook>` 直前に追加:
```xml
<_.fcp.VizExtensions.true...referenced-extensions>
  <_.fcp.VizExtensions.true...referenced-extension>
    <manifest manifest-version="0.1">
      <worksheet-extension extension-version="1.5.0" id="com.tableau.extension.sankey">
        <default-locale>en_US</default-locale>
        <name resource-id="name" />
        <description>Sankeys show before-and-after states and relationships between two or more categories.</description>
        <author email="github@tableau.com" name="Tableau" organization="Tableau" website="https://www.tableau.com/support" />
        <min-api-version>1.12</min-api-version>
        <source-location>
          <url>https://extensions.tableauusercontent.com/sandbox/sankey/sankey.html</url>
        </source-location>
        <icon />
        <context-menu><configure-context-menu-item /></context-menu>
        <encoding id="level">
          <display-name resource-id="level-encoding">Level</display-name>
          <role-spec>
            <role-type>discrete-dimension</role-type>
            <role-type>discrete-measure</role-type>
          </role-spec>
          <fields max-count="5" />
          <encoding-icon token="level" />
          <tooltip resource-id="level-tooltip">Sankey Level - Drag up to five dimensions here.</tooltip>
        </encoding>
        <encoding id="edge">
          <display-name resource-id="edge-encoding">Link</display-name>
          <role-spec>
            <role-type>continuous-dimension</role-type>
            <role-type>continuous-measure</role-type>
          </role-spec>
          <fields max-count="1" />
          <encoding-icon token="edge" />
          <tooltip resource-id="edge-tooltip">Link - Drag a measure here.</tooltip>
        </encoding>
      </worksheet-extension>
    </manifest>
    <referenced-views>
      <referenced-view instances="1" viewId="{{WS_NAME}}" />
    </referenced-views>
  </_.fcp.VizExtensions.true...referenced-extension>
</_.fcp.VizExtensions.true...referenced-extensions>
```

### 49B-4. UUID/エンコーディング ルール

- 全 `instance-id` は `uuid.uuid4().hex.upper()` (32文字hex)
- 全 `encoding-id` は `"{" + str(uuid.uuid4()).upper() + "}"` (中括弧付き36文字)
- **Level/edge ペア**: lod行とcustom行で同一UUID必須 (2行で1encoding)
- **追加 `<lod>` 行**: 各次元1行+メジャー2行、それぞれ別UUID
- `custom-type-name="level"` の順序 = サンキーの左→右の段階順
- `color-map` JSON は省略可 (省略するとTableauデフォルトカラー)

### 49B-5. Web Edit 手動配置との比較

| アプローチ | 工数 | 確実性 | 用途 |
|---|---|---|---|
| Web Edit 手動 (Show Me → Sankey → Level/Link棚へドラッグ) | 5分 | ★★★ | 単発・1案件 |
| **VizExtension XML自動生成 (本パターン)** | 10分 | ★★★ | テンプレ化・横展開・PDCA |
| Section 49 (シグモイドSankey) | 30-60分 | ★ (Cloud空白頻発) | 非推奨 |

詳細: `../shared/memory/reference_tableau_native_sankey.md`

---

## 50. パレート図（Pareto Chart / 80-20 Analysis）

Dual Axisで棒グラフ（個別値）と折れ線（累積%）を重ね、80/20ラインをReference Lineで表示するパターン。
品質管理（QC7つ道具）、不良分析、コスト分析に使用。
学習元: 品質管理_QC7つ道具 (Tableau Cloud)

### 50-1. 累積割合の計算フィールド（テーブル計算）
```xml
<!-- datasource内で定義 -->
<column-instance column='[{{MEASURE_FIELD}}]' derivation='Sum' name='[pcto:cum:sum:{{MEASURE_FIELD}}:qk]' pivot='key' type='quantitative'>
  <table-calc aggregation='Sum' ordering-field='[{{DS_NAME}}].[{{DIM_FIELD}}]' ordering-type='Field' type='CumTotal' />
  <table-calc ordering-field='[{{DS_NAME}}].[{{DIM_FIELD}}]' ordering-type='Field' type='PctTotal' />
</column-instance>
```

### 50-2. Dual Axis構成（棒+累積線）
```xml
<panes>
  <!-- Pane 1: 棒グラフ（個別値） -->
  <pane id='3'>
    <mark class='Bar' />
    <mark-sizing mark-sizing-setting='marks-scaling-off' />
    <encodings>
      <color column='[{{DS_NAME}}].[:Measure Names]' />
      <lod column='[{{DS_NAME}}].[none:{{DIM_FIELD}}:ok]' />
    </encodings>
    <!-- 80%ライン（累積軸） -->
    <reference-line axis-column='[{{DS_NAME}}].[pcto:cum:sum:{{MEASURE_FIELD}}:qk]'
      formula='constant' id='refline1' label-type='automatic'
      scope='per-table' value='0.80000000000000004'
      value-column='[{{DS_NAME}}].[pcto:cum:sum:{{MEASURE_FIELD}}:qk]' z-order='2' />
    <!-- 20%ライン（項目軸） -->
    <reference-line axis-column='[{{DS_NAME}}].[usr:{{PCTINDEX_CALC}}:qk:2]'
      formula='constant' id='refline0' label-type='automatic'
      scope='per-table' value='0.20000000000000001'
      value-column='[{{DS_NAME}}].[usr:{{PCTINDEX_CALC}}:qk:2]' z-order='1' />
  </pane>
  <!-- Pane 2: 折れ線（累積%） -->
  <pane id='4' y-axis-name='[{{DS_NAME}}].[pcto:cum:sum:{{MEASURE_FIELD}}:qk]'>
    <mark class='Line' />
    <encodings>
      <color column='[{{DS_NAME}}].[:Measure Names]' />
      <lod column='[{{DS_NAME}}].[none:{{DIM_FIELD}}:ok]' />
    </encodings>
  </pane>
</panes>
<!-- Dual Axis: rows に2つのメジャーを + で結合 -->
<rows>([{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk] + [{{DS_NAME}}].[pcto:cum:sum:{{MEASURE_FIELD}}:qk])</rows>
<cols>[{{DS_NAME}}].[usr:{{PCTINDEX_CALC}}:qk:2]</cols>
```

### 50-3. ソート（降順）+ INDEX%計算
```xml
<!-- 降順ソート -->
<computed-sort column='[{{DS_NAME}}].[none:{{DIM_FIELD}}:ok]' direction='DESC'
  using='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' />

<!-- INDEX()/SIZE() で項目位置の割合を算出（X軸用） -->
<column caption='% of items' datatype='real' name='[{{CALC_NAME}}]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='INDEX()/SIZE()'>
    <table-calc ordering-type='Rows' />
  </calculation>
</column>
```

- テーブル計算の連鎖: `CumTotal` → `PctTotal` の順で適用し、累積割合を算出
- Reference Line: `value='0.80000000000000004'` は80%、`value='0.20000000000000001'` は20%
- INDEX()/SIZE(): 各カテゴリの位置を0〜1にマッピング（20%ラインとの交点表示用）
- `refline`のスタイル: `text-format='p0%'` で%表示
- `fold='true'`: Dual Axis時に軸を同期する場合に使用

### 50-4. Cloud実証済み簡易パレート（city_twb.py方式, 2026-04-11）

テーブル計算を使わず、CSV前処理で累積%を算出する安全方式。

```xml
<!-- CSVで事前計算: cumulative_pct列をMAX()で取得 -->
<pane id='3'><mark class='Bar' /></pane>
<pane id='4' y-axis-name='[DS].[max:cumulative_pct:qk]'>
  <mark class='Line' />
</pane>
<computed-sort column='[DS].[none:subject:nk]' direction='DESC'
  using='[DS].[sum:count:qk]' />
<rows>([DS].[sum:count:qk] + [DS].[max:cumulative_pct:qk])</rows>
<cols>[DS].[none:subject:nk]</cols>
```

**Cloud互換の注意点:**
- `y-axis-name` による dual-axis: Bar+Line は Cloud で動作実績あり（Pie dual-axisはNG）
- `groupfilter end='top'` による Top N フィルタは Cloud で不安定 → **CSV前処理でTop Nを絞るのが確実**
- `computed-sort` は Cloud 互換 ✅

---

## 51. 管理図（Control Chart / Xbar-R / 6σ）

UCL/LCL（管理限界）+ CL（中心線）をReference Line/Bandで描画し、
管理限界外のデータポイントを条件付き色分けで強調するパターン。2方式あり。
学習元: 品質管理_QC7つ道具 + 工場でのプロセス管理 (Tableau Cloud)

### 51-1. 方式A: 計算フィールドによるUCL/LCL（パラメータ係数制御）
```xml
<!-- パラメータ: σ係数 -->
<column caption='係数' datatype='real' name='[{{PARAM_NAME}}]' param-domain-type='range'
  role='measure' type='quantitative' value='2.0'>
  <calculation class='tableau' formula='2.0' />
  <range granularity='0.10000000000000001' max='5.0' min='0.0' />
</column>

<!-- UCL = WINDOW_AVG + WINDOW_STDEV * 係数 -->
<column caption='UCL' datatype='real' name='[{{CALC_UCL}}]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='WINDOW_AVG(SUM([{{MEASURE_FIELD}}])) + WINDOW_STDEV(SUM([{{MEASURE_FIELD}}]))*[Parameters].[{{PARAM_NAME}}]'>
    <table-calc ordering-type='Rows' />
  </calculation>
</column>

<!-- LCL = WINDOW_AVG - WINDOW_STDEV * 係数 -->
<column caption='LCL' datatype='real' name='[{{CALC_LCL}}]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='WINDOW_AVG(SUM([{{MEASURE_FIELD}}])) - WINDOW_STDEV(SUM([{{MEASURE_FIELD}}]))*[Parameters].[{{PARAM_NAME}}]'>
    <table-calc ordering-type='Rows' />
  </calculation>
</column>

<!-- 管理限界内/外の判定 -->
<column caption='管理限界内/外' datatype='boolean' name='[{{CALC_OUTLIER}}]' role='measure' type='nominal'>
  <calculation class='tableau' formula='SUM([{{MEASURE_FIELD}}])>=[{{CALC_UCL}}]&#13;&#10;or&#13;&#10;SUM([{{MEASURE_FIELD}}])&lt;=[{{CALC_LCL}}]'>
    <table-calc ordering-type='Rows' />
  </calculation>
</column>
```

### 51-2. 方式A: ワークシート構成（Dual Axis + 色分け）
```xml
<panes>
  <!-- Pane 0: Reference Lines (UCL/LCL/CL) -->
  <pane>
    <mark class='Automatic' />
    <reference-line axis-column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]'
      formula='average' id='refline0' label-type='none' scope='per-table'
      value-column='[{{DS_NAME}}].[usr:{{CALC_UCL}}:qk]' z-order='1' />
    <reference-line axis-column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]'
      formula='average' id='refline1' label-type='none' scope='per-pane'
      value-column='[{{DS_NAME}}].[usr:{{CALC_LCL}}:qk]' z-order='2' />
    <reference-line axis-column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]'
      formula='average' id='refline2' label-type='value' scope='per-table'
      value-column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' z-order='3' />
  </pane>
  <!-- Pane 1: LOD for UCL/LCL lines -->
  <pane id='1' y-axis-name='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]'>
    <mark class='Automatic' />
    <encodings>
      <lod column='[{{DS_NAME}}].[usr:{{CALC_LCL}}:qk]' />
      <lod column='[{{DS_NAME}}].[usr:{{CALC_UCL}}:qk]' />
    </encodings>
  </pane>
  <!-- Pane 2: Circle mark with outlier color -->
  <pane id='2' y-axis-name='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' y-index='1'>
    <mark class='Circle' />
    <encodings>
      <color column='[{{DS_NAME}}].[usr:{{CALC_OUTLIER}}:nk:1]' />
    </encodings>
  </pane>
</panes>
<!-- Dual Axis -->
<rows>([{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk] + [{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk])</rows>
<cols>[{{DS_NAME}}].[tmn:{{DATE_FIELD}}:qk]</cols>
```

### 51-3. 方式B: Reference Line stdev方式（シンプル）
```xml
<!-- formula='stdev' + factor で±3σバンドを自動描画 -->
<reference-line axis-column='[{{DS_NAME}}].[avg:{{MEASURE_FIELD}}:qk]'
  enable-instant-analytics='false' fill-above='false' fill-below='false'
  formula='stdev' id='refline0' label-type='automatic'
  scope='per-pane' symmetric='false' type='sample'
  value-column='[{{DS_NAME}}].[avg:{{MEASURE_FIELD}}:qk]' z-order='1'>
  <reference-line-value factor='-3' />
  <reference-line-value factor='3' />
</reference-line>
```

### 51-4. Reference Lineスタイル設定
```xml
<style-rule element='refline'>
  <format attr='fill-above' id='refline0' value='#00000000' />
  <format attr='fill-below' id='refline0' value='#00000000' />
  <format attr='line-pattern-only' id='refline0' value='dotted' />
  <format attr='stroke-color' id='refline0' value='#b40f1e' />
  <format attr='line-visibility' id='refline0' value='on' />
</style-rule>
```

- **方式A**: パラメータで係数を動的制御。Dual Axis + Circle markで異常値を色分け。高カスタマイズ
- **方式B**: `formula='stdev'` + `<reference-line-value factor='N' />` で自動計算。設定がシンプル
- 方式Bの`type='sample'`: 標本標準偏差（N-1で割る）。`type='population'`は母標準偏差
- WE（Western Electric）ルール: 連続7点上昇/下降等の追加判定は計算フィールドで実装

---

## 52. プログレスバー（Progress Bar / 達成率バー）

横棒グラフで0〜100%の範囲を固定し、達成率やOverdue率を視覚的に表示するパターン。
KPIダッシュボードでのBAN補助表示に最適。
学習元: 経営層向けダッシュボード (Tableau Cloud)

### 52-1. %メジャーの計算フィールド
```xml
<column caption='{{CAPTION}}' datatype='real' default-format='p0%'
  name='[{{CALC_NAME}}]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='(IF ATTR([{{CATEGORY_FIELD}}]= &quot;{{TARGET_VALUE}}&quot;)&#13;&#10;THEN COUNTD([{{ID_FIELD}}])&#13;&#10;END)&#13;&#10;/&#13;&#10;ATTR({ EXCLUDE [{{CATEGORY_FIELD}}]:&#13;&#10;COUNTD([{{ID_FIELD}}])})' />
</column>
```

### 52-2. ワークシート構成
```xml
<style>
  <style-rule element='axis'>
    <!-- 軸を非表示にして0〜1固定 -->
    <format attr='display' class='0' field='[{{DS_NAME}}].[pcto:ctd:{{ID_FIELD}}:qk]'
      scope='cols' value='false' />
    <encoding attr='space' class='0'
      field='[{{DS_NAME}}].[pcto:ctd:{{ID_FIELD}}:qk]' field-type='quantitative'
      max='1.01' min='-0.01' range-type='fixed' scope='cols' type='space' />
    <format attr='line-visibility' value='off' />
  </style-rule>
  <style-rule element='gridline'>
    <format attr='line-visibility' value='off' />
  </style-rule>
  <style-rule element='zeroline'>
    <format attr='line-visibility' value='off' />
  </style-rule>
</style>
<panes>
  <pane id='1'>
    <mark class='Bar' />
    <mark-sizing mark-sizing-setting='marks-scaling-off' />
    <encodings>
      <color column='[{{DS_NAME}}].[none:{{CATEGORY_FIELD}}:nk]' />
      <text column='[{{DS_NAME}}].[pcto:ctd:{{ID_FIELD}}:qk]' />
    </encodings>
    <style>
      <style-rule element='mark'>
        <format attr='size' value='1.1204420328140259' />
        <format attr='mark-color' value='#c0c0c0' />
      </style-rule>
    </style>
  </pane>
</panes>
<rows />
<cols>[{{DS_NAME}}].[pcto:ctd:{{ID_FIELD}}:qk]</cols>
```

- `range-type='fixed'` + `min='-0.01'` + `max='1.01'`: 0〜100%で軸を固定
- `display='false'`: 軸ラベルを非表示
- `rows`が空: 横一本の棒として描画
- カテゴリ色分け: Overdue/Non Overdue等で棒の色を分ける
- タイトルに動的値を埋め込む: `<run><![CDATA[<[DS].[usr:calc:qk]>]]></run>`

---

## 53. Small Multiples / トレリス（Trellis Chart）

行列にディメンションを配置し、各セルに独立した散布図・折れ線等を描画するパターン。
カテゴリ間比較、層別分析に使用。
学習元: 品質管理_QC7つ道具 (Tableau Cloud)

### 53-1. ワークシート構成
```xml
<panes>
  <pane>
    <mark class='Automatic' />
    <encodings>
      <color column='[{{DS_NAME}}].[none:{{COLOR_DIM}}:nk]' />
      <lod column='[{{DS_NAME}}].[none:{{DETAIL_DIM}}:nk]' />
    </encodings>
    <trendline enable-confidence-bands='true' enable-instant-analytics='true'
      enabled='true' exclude-color='false' exclude-intercept='false' fit='linear' />
  </pane>
</panes>
<!-- rows: (ディメンション * メジャー) → 行方向にグリッド分割 -->
<rows>([{{DS_NAME}}].[none:{{ROW_DIM}}:nk] * [{{DS_NAME}}].[sum:{{ROW_MEASURE}}:qk])</rows>
<!-- cols: (ディメンション * メジャー) → 列方向にグリッド分割 -->
<cols>([{{DS_NAME}}].[none:{{COL_DIM}}:nk] * [{{DS_NAME}}].[sum:{{COL_MEASURE}}:qk])</cols>
```

- **核心**: `(none:Dim:nk * sum:Measure:qk)` の `*` でディメンションとメジャーを掛ける
- 行に `(カテゴリ * 利益)`, 列に `(顧客区分 * 数量)` → カテゴリ×顧客区分のグリッド散布図
- 各パネルは独立した軸スケール（デフォルト）。`fold='true'`で軸同期も可能
- `trendline`: 各パネルに回帰線を追加可能（パターン46と組合せ）
- 応用: 時系列のSmall Multiples → 列にYEAR, 行にメジャー

---

## 54. スロープチャート（Slope Chart）

2つの状態・期間の値を線で結び、変化の方向と大きさを比較するパターン。
順位変動、前後比較、指標間ギャップの可視化に使用。
学習元: ビジュアル表現 (Tableau Cloud)

### 54-1. ワークシート構成
```xml
<!-- 2メジャーをMeasure Namesとして表示 -->
<filter class='categorical' column='[{{DS_NAME}}].[:Measure Names]'>
  <groupfilter function='union' user:op='manual'>
    <groupfilter function='member' level='[:Measure Names]'
      member='&quot;[{{DS_NAME}}].[sum:{{MEASURE_A}}:qk]&quot;' />
    <groupfilter function='member' level='[:Measure Names]'
      member='&quot;[{{DS_NAME}}].[sum:{{MEASURE_B}}:qk]&quot;' />
  </groupfilter>
</filter>
<!-- Measure Namesの表示順を手動ソート -->
<manual-sort column='[{{DS_NAME}}].[:Measure Names]' direction='ASC'>
  <dictionary>
    <bucket>&quot;[{{DS_NAME}}].[sum:{{MEASURE_A}}:qk]&quot;</bucket>
    <bucket>&quot;[{{DS_NAME}}].[sum:{{MEASURE_B}}:qk]&quot;</bucket>
  </dictionary>
</manual-sort>
```

### 54-2. Mark設定
```xml
<panes>
  <pane>
    <mark class='Line' />
    <mark-sizing mark-sizing-setting='marks-scaling-off' />
    <encodings>
      <!-- 色: 計算フィールドで傾きの正負を判定 -->
      <color column='[{{DS_NAME}}].[none:{{SLOPE_COLOR_CALC}}:nk]' />
      <!-- LOD: エンティティごとに1本の線 -->
      <lod column='[{{DS_NAME}}].[none:{{ENTITY_DIM}}:nk]' />
    </encodings>
    <style>
      <style-rule element='mark'>
        <format attr='size' value='0.0099999997764825821' />
        <format attr='mark-markers-mode' value='all' />
      </style-rule>
    </style>
  </pane>
</panes>
<!-- cols: Measure Names（2列）, rows: Multiple Values -->
<rows>[{{DS_NAME}}].[Multiple Values]</rows>
<cols>[{{DS_NAME}}].[:Measure Names]</cols>
```

### 54-3. 傾き方向の色分け計算フィールド
```xml
<column caption='Color' datatype='boolean' name='[{{CALC_NAME}}]' role='dimension' type='nominal'>
  <calculation class='tableau' formula='[{{MEASURE_A}}]>[{{MEASURE_B}}]' />
</column>
```

- `mark-markers-mode='all'`: 線の両端にドット（マーカー）を表示
- `size='0.01'`: 極細線で各エンティティの傾きを表現
- `[:Measure Names]` + `[Multiple Values]`: Tableauの特殊フィールドで複数メジャーを1軸に
- 色分け: `Measure_A > Measure_B` の真偽で2色に分ける（上昇/下降）
- フィールドラベル非表示: `display-field-labels='false'`

---

## 55. ファンチャート（Fan Chart / 予測バンド）

Tableauの組み込みForecast機能で信頼区間バンドを扇状に表示するパターン。
時系列の将来予測表示に使用。パターン35(MODEL_QUANTILE)と違い、コードレス。
学習元: ビジュアル表現 (Tableau Cloud)

### 55-1. ワークシート構成（Forecast有効化）
```xml
<panes>
  <pane>
    <mark class='Automatic' />
    <style>
      <style-rule element='mark'>
        <format attr='mark-transparency' value='255' />
        <format attr='has-stroke' value='false' />
        <format attr='mark-color' value='#268031' />
      </style-rule>
    </style>
  </pane>
</panes>
<!-- forecast-column-type='forecast-value' の列インスタンスを使用 -->
<rows>[{{DS_NAME}}].[fVal:avg:{{MEASURE_FIELD}}:qk]</rows>
<cols>[{{DS_NAME}}].[twk:{{DATE_FIELD}}:qk]</cols>
<!-- 予測範囲の日付全体を表示 -->
<show-full-range>
  <column>[{{DS_NAME}}].[{{DATE_FIELD}}]</column>
</show-full-range>
<!-- Forecast設定 -->
<forecast-specification auto-forecast-agg='true' band-confidence-level='95.000000'
  enabled='true' fill-type='fill-missing' ignore-last='1'
  model-type='custom' range-type='auto'
  season-type='ets-multiplicative' show-prediction-bands='true'
  trend-type='ets-additive' />
```

### 55-2. Forecast列インスタンス
```xml
<column-instance column='[{{MEASURE_FIELD}}]' derivation='Avg'
  forecast-column-base='[avg:{{MEASURE_FIELD}}:qk]'
  forecast-column-type='forecast-value'
  name='[fVal:avg:{{MEASURE_FIELD}}:qk]' pivot='key' type='quantitative' />
```

- `forecast-specification`: XML内で予測モデルを完全に制御
- `model-type='custom'`: カスタムモデル。`'automatic'`で自動選択
- `trend-type`: `ets-additive`(加法的), `ets-multiplicative`(乗法的), `ets-none`(トレンドなし)
- `season-type`: `ets-multiplicative`(乗法的季節性), `ets-additive`(加法的), `ets-none`(なし)
- `band-confidence-level='95.000000'`: 95%信頼区間バンド
- `ignore-last='1'`: 最後の1期間を無視（テスト用）
- `show-prediction-bands='true'`: ファン状のバンド表示
- パターン35(MODEL_QUANTILE)との違い: 35は計算フィールドで手動実装、55は組み込み機能

---

## 56. カレンダーヒートマップ（Calendar Heatmap）

YEAR × MONTH のマトリクスにSquareマークで値を色エンコーディングするパターン。
季節パターン、曜日別傾向の可視化に使用。パターン31(ヒートマップ)の日付特化版。
学習元: ビジュアル表現 (Tableau Cloud)

### 56-1. ワークシート構成
```xml
<datasource-dependencies datasource='{{DS_NAME}}'>
  <!-- MONTH: ordinal型で月名表示 -->
  <column-instance column='[{{DATE_FIELD}}]' derivation='Month'
    name='[mn:{{DATE_FIELD}}:ok]' pivot='key' type='ordinal' />
  <!-- YEAR: ordinal型で年表示 -->
  <column-instance column='[{{DATE_FIELD}}]' derivation='Year'
    name='[yr:{{DATE_FIELD}}:ok]' pivot='key' type='ordinal' />
  <!-- メジャー -->
  <column-instance column='[{{MEASURE_FIELD}}]' derivation='Sum'
    name='[sum:{{MEASURE_FIELD}}:qk]' pivot='key' type='quantitative' />
</datasource-dependencies>
```

### 56-2. スタイルとMark設定
```xml
<style>
  <style-rule element='header'>
    <format attr='width' field='[{{DS_NAME}}].[mn:{{DATE_FIELD}}:ok]' value='36' />
  </style-rule>
  <style-rule element='label'>
    <!-- 月名を短縮形で表示 -->
    <format attr='text-format' field='[{{DS_NAME}}].[mn:{{DATE_FIELD}}:ok]' value='iLLL' />
  </style-rule>
  <style-rule element='mark'>
    <encoding attr='color' field='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]'
      reverse='true' type='custom-interpolated'>
      <color-palette custom='true' name='' type='ordered-diverging'>
        <color>#268031</color>
        <color>#6fac77</color>
        <color>#d9d9d9</color>
        <color>#e1e8ed</color>
        <color>#f5f8fa</color>
      </color-palette>
    </encoding>
  </style-rule>
  <style-rule element='worksheet'>
    <format attr='display-field-labels' scope='cols' value='false' />
    <format attr='display-field-labels' scope='rows' value='false' />
  </style-rule>
  <style-rule element='zeroline'>
    <format attr='line-visibility' value='off' />
  </style-rule>
  <style-rule element='table-div'>
    <format attr='line-visibility' scope='rows' value='off' />
  </style-rule>
</style>
<panes>
  <pane>
    <mark class='Automatic' />
    <encodings>
      <color column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' />
    </encodings>
    <style>
      <style-rule element='mark'>
        <!-- セル境界線 -->
        <format attr='has-stroke' value='true' />
        <format attr='stroke-color' value='#f5f5f5' />
      </style-rule>
    </style>
  </pane>
</panes>
<rows>[{{DS_NAME}}].[mn:{{DATE_FIELD}}:ok]</rows>
<cols>[{{DS_NAME}}].[yr:{{DATE_FIELD}}:ok]</cols>
```

- `derivation='Month'`(ok) + `derivation='Year'`(ok): ordinal型で離散的な行列を構成
- `iLLL`: ICU形式の月名短縮（Jan, Feb...）。日本語環境では1月, 2月...
- `ordered-diverging`パレット: 中心値を境に2色グラデーション
- `has-stroke='true'` + `stroke-color='#f5f5f5'`: セル間に薄い境界線
- 応用: WEEKDAY × WEEK で曜日×週のカレンダー表示も可能（`derivation='Weekday'`）
- パターン31との違い: 31は任意ディメンション、56は日付特化でDATEPART使用

---

## 57. アイコン付きBANカード（Icon BAN Card）

カスタムShapeアイコン + Square mark KPI数値を組み合わせたBANカード。
パターン12の発展版。背景色付きのリッチなKPIカードを構成。
学習元: Banking Customer Insights (Tableau Cloud)

### 57-1. アイコンワークシート（Shape mark）
```xml
<worksheet name='{{ICON_WS_NAME}}'>
  <table>
    <style>
      <style-rule element='table'>
        <format attr='background-color' value='#4e79a7' />
      </style-rule>
    </style>
    <panes>
      <pane>
        <mark class='Shape' />
        <mark-sizing mark-sizing-setting='marks-scaling-off' />
        <encodings>
          <text column='[{{DS_NAME}}].[none:{{FILTER_DIM}}:ok]' />
        </encodings>
        <customized-tooltip>
          <formatted-text><run>&#xC6; </run></formatted-text>
        </customized-tooltip>
        <customized-label>
          <formatted-text />
        </customized-label>
        <style>
          <style-rule element='mark'>
            <!-- カスタムシェイプ画像 -->
            <format attr='shape' value='Custom/{{ICON_FILENAME}}' />
            <format attr='size' value='2.6850829124450684' />
            <format attr='mark-labels-show' value='true' />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows />
    <cols />
  </table>
</worksheet>
```

### 57-2. KPI数値ワークシート（Square mark + customized-label）
```xml
<worksheet name='{{KPI_WS_NAME}}'>
  <table>
    <style>
      <style-rule element='table'>
        <format attr='background-color' value='#00000000' />
      </style-rule>
    </style>
    <panes>
      <pane>
        <mark class='Square' />
        <mark-sizing mark-sizing-setting='marks-scaling-off' />
        <encodings>
          <size column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' />
          <text column='[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]' />
        </encodings>
        <customized-label>
          <formatted-text>
            <run bold='true' fontsize='12'>{{KPI_TITLE}}</run>
            <run>&#xC6;&#10;</run>
            <run fontsize='12'><![CDATA[ <[{{DS_NAME}}].[sum:{{MEASURE_FIELD}}:qk]>]]></run>
          </formatted-text>
        </customized-label>
        <style>
          <style-rule element='mark'>
            <format attr='size' value='5.0694117546081543' />
            <format attr='mark-labels-show' value='true' />
            <format attr='mark-color' value='#4e79a7' />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows />
    <cols />
  </table>
</worksheet>
```

- **2シート構成**: Icon(Shape mark) + KPI(Square mark) をダッシュボード上で重ねて配置
- `shape='Custom/{{ICON_FILENAME}}'`: Shapes フォルダ内の画像ファイルを参照
- `background-color='#4e79a7'`: テーブル背景色で統一感のあるカード
- `customized-label`: `<run bold='true' fontsize='12'>タイトル</run>` + 改行 + 数値
- `&#xC6;&#10;`: Tableau特殊改行コード（Ae + newline）
- `rows`と`cols`が空: 単一セルのBANカード表示
- 複数KPIの統一感: 同じbackground-color + mark-colorで4枚のカードを横並び

---

## パターン組合せ早見表

| 要望 | 組合せるパターン |
|------|-----------------|
| クリックでフィルタ連動 | 1-1 (tsl-filter) + exclude-sheet |
| ホバーでハイライト | 1-2 (brush) |
| ドリルダウン（単一値） | 1-3 (edit-parameter-action) + 10-3 (any param) + 計算フィールド |
| ドリルダウン（複数選択） | 1-4 (edit-group-action) + 2-1 (set定義) + 2-2 (IF [Set] THEN) |
| 表示/非表示切替 | 3 (DZV) or 4 (toggle-button) |
| ページ遷移 | 1-5 (go-to-sheet) or 18 (nav-action) |
| KPIカード（BANカード） | 12-1 (不可視マーク+ラベル) + 12-2 (Favorable色分け) |
| KPIグリッド | 12-3 (2x4グリッド) + 12-1 × N枚 |
| 目標線 | 5 (Reference Line) or 13-2 (KPI目標線) |
| 今日マーカー | 13-3 (Current Date) + 10-3 (日付パラメータ) |
| フィルタパネル | 4 (Show/Hide) + 9-3 (サイドバー) |
| 地図ポイント+ポリゴン | 7-1 (MAKEPOINT) + 7-2 (Geometry encoding) |
| ドットデンシティマップ | 14-1 (座標丸め) + 14-2 (Shape mark) + 15-1 (ダークマップ) |
| ダークマップ | 15-1 + 15-2 (軸非表示) + 15-3 (レイヤー制御) |
| カスタム配色 | 8 or 17-1 (Plasma) or 17-2 (CB_RdBu) |
| 例外色付き配色 | 17-3 (グレー例外) |
| リージョン切替 | 16-1 (MapFilter) + 16-2 ((All)パラメータ) |
| ガントチャート | 11-1 (基本) + 11-3 (条件付き色分け) + 11-2 (参照バンド) |
| ガント+Tooltip詳細 | 11-1 + 11-4 (Viz in Tooltip) |
| 工期ハイライト帯 | 11-2 (参照バンド) + 10-3 (日付パラメータ) |
| フェーズ信号機色 | 11-3 (条件付き色分け) + 手動ソート |
| ウォーターフォール | 13-1 (GanttBar差分) + 12-2 (Favorable色分け) |
| ダッシュボード間ナビ | 18 (nav-action) + 1-3 (パラメータ更新) + 選択解除 |
| 閾値ベース色分け | 19 (Threshold Color) + カスタム色マッピング |
| ドット分布図 | 20 (Beeswarm) + 19 (閾値色分け) + 5 (Reference Line) |
| フィルタボタンUI | 21 (フィルタボタン) + 1-1 (tsl-filter) |
| ドーナツチャート | 22 (二重Pie) + ビン + エイリアス |
| 動的タイトル+自動月検出 | 23 (LOD動的月) + 24 (動的タイトル) |
| ダークテーマDB | 25 (ダークテーマ) + 21 (フィルタボタン) + 4 (Toggle) |
| 勤怠管理ダッシュボード | 19+20+21+22+23+24+25 (全パターン組合せ) |
| 施設ポイントマップ | 7-2 (lat/lon→Circle mark) + 9-3 (サイドバーフィルタ) + 色分け凡例 |
| KPI期間切替（7日/30日/90日） | 26 (期間スライダー) + 12-1 (BANカード) + 28 (差分フォーマット) |
| テーブルヘッダソート | 27 (テーブルソート) + 1-3 (パラメータアクション) |
| KPI前期比表示（▲▼付き） | 28 (KPI差分フォーマット) + 26-2 (期間CASE切替) |
| テキスト分析ワードクラウド | 29 (ワードクラウド) + 1-1 (フィルタ連動) |
| 人口ピラミッド・対比バー | 30 (Butterfly Chart) + 6 (Dual Axis) |
| クロス集計ヒートマップ | 31 (ヒートマップ) + 17 (カスタム配色) |
| 保険オペレーションDB | 26+27+28+12-1+12-2+3+4+16 (全パターン組合せ) |
| 構成比の円グラフ | 32 (Pie Chart) + 14 (カスタム配色) |
| 時系列エリアグラフ | 33-1 (Area Chart) + 5 (Date Filter) |
| KPIスパークライン（面+点） | 33-2 (Sparkline Area) + 12 (Dual Axis) |
| 階層ツリーマップ | 34 (Treemap) + 14 (カスタム配色) |
| Pulse風予測バンド | 35-1 (MODEL_QUANTILE) + 33-1 (Area) + 35-2 (MtD/MoM) |
| MTD前月比ダッシュボード | 35-2 (MtD/MoM) + 28 (KPI差分) + 12-1 (BANカード) |
| ロリポップチャート | 36 (Lollipop) + 12 (Dual Axis) |
| 開閉パネル（DZV） | 37-1 (DZVブール) + 37-2 (トグルボタン) + 7 (パラメータアクション) |
| 構成比100%積上げ | 38 (Stacked 100%) + 14 (カスタム配色) |
| アプリ風ナビゲーション | 37 (DZV) + 18 (nav-action) + 7 (パラメータアクション) |
| 目標vs実績ダッシュボード | 39 (Bullet Chart) + 12-1 (BANカード) + 5 (Reference Line) |
| 軸切替インタラクティブ | 40 (Dimension Swap) + 10-3 (パラメータコントロール) |
| メジャー切替チャート | 40 (Measure Switcher) + 1-3 (パラメータアクション) |
| 地図→外部サービス連携 | 41 (URL Action) + 7-1 (MAKEPOINT) |
| 商圏分析・施設検索 | 42 (Spatial Distance) + 1-4 (Set Action) + 7-1 (MAKEPOINT) |
| テキスト分析ダッシュボード | 43 (共起ネットワーク) + 29 (ワードクラウド) + 30 (Butterfly) |
| レポート出力付きDB | 44 (PDF Export) + 1-5 (Go-to-sheet) |
| 商圏分析（円+距離） | 45 (Spatial Buffer) + 42 (Distance) + 1-3 (パラメータアクション) |
| 散布図+回帰線 | 46 (Trendline) + 6 (Dual Axis) + 19 (閾値色分け) |
| カスタムKPIカード（Extension） | 47 (Viz Extension) + 12-1 (BANカード) |
| トグル選択ハイライト | 48 (Multi-Select Param) + 1-3 (パラメータアクション) + 色分け |
| Sankeyフロー図 | 49 (Sankey) + 48 (Multi-Select) + 7-1 (MAKEPOINT) |
| パレート分析（80/20） | 50 (パレート図) + 6 (Dual Axis) + 5 (Reference Line) |
| QC管理図（計算フィールド方式） | 51-1/51-2 (Control Chart 方式A) + 19 (閾値色分け) + 10 (パラメータ) |
| QC管理図（シンプル方式） | 51-3 (Control Chart 方式B stdev) |
| KPI達成率プログレスバー | 52 (プログレスバー) + 12-1 (BANカード) |
| カテゴリ×属性の層別分析 | 53 (Small Multiples) + 46 (トレンドライン) |
| 2期間比較スロープ | 54 (スロープチャート) + 19 (閾値色分け) |
| 時系列予測ファンチャート | 55 (ファンチャート) + 33-1 (エリアチャート) |
| 季節パターン分析 | 56 (カレンダーヒートマップ) + 17 (カスタム配色) |
| リッチKPIカード（アイコン付き） | 57 (アイコン付きBAN) + 12-1 (BANカード) + 9 (レイアウト) |
