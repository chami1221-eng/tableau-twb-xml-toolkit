---
name: twb-cloud-desktop
description: generator製/Cloud由来TWBをTableau Desktop 2026.1で開けるようにする確定21項目修正レシピ+button対応+storyboard+nav button仕様。配布先向けv11newで2026-06-16実証
metadata:
  node_type: memory
  type: feedback
---

generator製TWB（`twb-generator`で生成 → REST API で Cloud publish → Cloud DL）と Cloud Web Edit 由来TWB は **Tableau Desktop 2026.1 でD2E8DA72エラー** で開けない。Cloud内部はCloud専用構造をそのまま保存するため、Desktop XSDで全要素拒否される。配布先ユーザー（サンプル市）向け配布で2026-06-15に v9、2026-06-16に v11new で実発生し、累積21項目のレシピ確立。

**Why:** v9配布で「Desktopで開けない」事象発生 → v11newはサンキー/button/storyboard/リレーション含むためさらに複雑。延べ約30回のテキスト置換試行で確立。本セッション（2026-06-16）で第2-4弾累計21項目+デザイン調整+ジャパンデモ参考WB調査によりbutton/storyboard/manifest フラグの完全仕様判明。

**How to apply:** generator製/Cloud編集後TWBをDesktop配布する場合、以下21項目をテキスト置換で適用する。最重要ルール準拠（ElementTree/lxml禁止・テキスト置換のみ）。

## 確定21項目レシピ（順序問わず・該当項目のみ適用）

### 1. manifest を 17要素フルセットに置換（**1ブロックのみ**）

generator製は `<ManifestByVersion />` 1要素のみ。Desktop XSDは以下17要素フラグを読んで「拡張モード」「リレーション論理層モード」「VizExtension対応」を有効化する。

```xml
<document-format-change-manifest>
  <AccessibleZoneTabOrder />
  <AnimationOnByDefault />
  <AutoCreateAndUpdateDSDPhoneLayouts />
  <Extensions />
  <ISO8601DefaultCalendarPref />
  <IntuitiveSorting />
  <IntuitiveSorting_SP2 />
  <MapboxVectorStylesAndLayers />
  <MarkAnimation />
  <ObjectModelEncapsulateLegacy />
  <ObjectModelTableType />
  <SchemaViewerObjectModel />
  <SetMembershipControl />
  <SheetIdentifierTracking />
  <SortTagCleanup />
  <VizExtensions />
  <WindowsPersistSimpleIdentifiers />
</document-format-change-manifest>
```

⚠️ サンキー含む場合は `<Extensions />` + `<VizExtensions />` 必須（17要素）。サンキー無しなら15要素でも可。

### 1.5. button (ナビゲーション) 含む場合は manifest に追加2要素必須

**Cloud Web Edit の button要素 か Desktop ネイティブの go-to-sheet button** を持つ場合、以下を manifest に追加（合計19要素）：

```xml
<BasicButtonObject />
<BasicButtonObjectTextSupport />
```

無いとXSDが `no declaration found for element 'button'` で拒否する（2026-06-16実証）。

### 2. source-build を Desktop publish 値に変更

```xml
<workbook ... source-build='2025.2.0 (20252.25.0707.1658)' ...>
```

完全ビルド番号（`(20252.25.0707.1658)` 部分）が必要。シンプル `2025.2` だとDesktopが古いスキーマで解釈する。

### 3. source-platform 属性削除

```xml
<!-- 元: source-platform='windows' -->
<!-- 修正後: 属性ごと削除 -->
```

### 4. `_.fcp.VizExtensions` プレフィックス全削除

```regex
_\.fcp\.VizExtensions(?:DupEncodingUUID)?\.(?:true|false)\.\.\.
```

3パターン (true/false/DupEncodingUUID.true)。Cloud Web Edit由来のCloud専用prefix。

### 5. layout の `dim-percentage` / `measure-percentage` 属性削除

```xml
<!-- 元: <layout ... dim-percentage='0.5' measure-percentage='0.5' ...> -->
<!-- 修正後: 両属性削除 -->
```

datasource内 layout に付くCloud専用属性。

### 6. `<formatted-text>` ブロック → 削除ではなく **中身保持** が原則

⚠️ **重要訂正（2026-06-16）**: 第1弾レシピでは「formatted-text ブロック全削除」としていたが、これは **誤り**。

正しい対応：
- formatted-text の中身（`<run>...</run>`）を**保持**したまま残す
- 削除すると BAN大文字数字/ヘッダー解説/サイドバーラベル等が全部消える（実害大）
- Desktop XSD的に formatted-text 自体は OK、ただし **zone直下の content model順序は遵守**（先頭、zone-styleより前）

例: BAN customized-label
```xml
<customized-label>
  <formatted-text>
    <run bold='true' fontcolor='#4A5878' fontsize='14'>PV
</run>
    <run bold='true' fontcolor='#1F2A44' fontsize='28'><![CDATA[<[federated.ds_hub].[sum:pageview:qk]>]]></run>
  </formatted-text>
</customized-label>
```

Cloud→Desktop ラウンドトリップで Tableau Desktop が空 formatted-text を自動クリーンアップする ので、復元は SAFE_P12 (元のCloud版TWB) から再注入する。

### 6.5. zone内 zone-style→formatted-text 順序を入替（content model順守）

zone content model: `(formatted-text, layout-cache?, zone, flipboard, (add-in?), zone-style?)`

→ formatted-text は **zone-styleより前** 必須。元のCloud生成順では `zone-style → formatted-text` の場合があるため入替必要。

### 7. `<devicelayouts>` ブロック全削除

```regex
\s*<devicelayouts>.*?</devicelayouts>
```

Phone自動レイアウトは Desktop で再生成可能なので削除が安全。zone要素の `x/y/w` 必須属性欠如で大量エラー。

### 8. 各 worksheet 末尾に `<simple-id uuid='...'/>` 追加（不足分のみ）

worksheet content model `((layout-options?)|(repository-location?)), table, simple-id` で simple-id 必須。 generator製は一部 worksheet にsimple-id を生成しない。

```python
import re, uuid
def add_sid_if_missing(m):
    block = m.group(0)
    if '<simple-id' in block: return block
    new_uuid = '{' + str(uuid.uuid4()).upper() + '}'
    sid = f"      <simple-id uuid='{new_uuid}' />\n    "
    return re.sub(r'(</table>\s*)(</worksheet>)', r'\1' + sid + r'\2', block, count=1)
content = re.sub(r"<worksheet name='[^']+'.*?</worksheet>", add_sid_if_missing, content, flags=re.DOTALL)
```

### 9. v11new固有: `<slices>`/`<aggregation>` 順序入替

worksheet view content model: `(filter, sort, perspectives, slices?, aggregation)` で slicesがaggregationの**前**。

```python
pat = re.compile(r"(\s*)<aggregation value='([^']*)' />(\s*)(<slices>.*?</slices>)", re.DOTALL)
content = pat.sub(lambda m: f"{m.group(1)}{m.group(4)}{m.group(3)}<aggregation value='{m.group(2)}' />", content)
```

### 10. encoding 内 `<detail column='...'/>` 削除

content model `((color|size|text|shape|wedge-size|lod|geometry|image|tooltip|path|level|edge|custom))` に detail なし。

### 11. `<reference-lines>` ブロック全削除

worksheet pane content modelで `reference-line` (単数) のみ許容、`reference-lines` (複数) は無効。

### 12. `<style-rule element='X'>` で X が 'rows-axis-tick-labels' / 'mark-labels' のもの削除

```python
content, n = re.subn(r"\s*<style-rule element='(?:rows-axis-tick-labels|mark-labels)'>.*?</style-rule>", "", content, flags=re.DOTALL)
```

format-attribute enumeration外。format行ではなく **style-rule要素まるごと**削除が正しい。

### 13. button × N zone内ブロック削除（manifest BasicButtonObject 追加が選択肢）

button要素はXSD非対応 → 削除 OR manifest にBasicButtonObject フラグ追加で有効化（**項目1.5参照**）。Desktop互換 button XML 仕様：

```xml
<zone fixed-size='270' h='6032' id='229' is-fixed='true' type-v2='dashboard-object' w='32183' x='1755' y='9891'>
  <button action='tabdoc:goto-sheet window-id="{UUID}"' button-type='text'>
    <button-visual-state>
      <caption>DB1 戦略層</caption>
      <button-caption-font-style bold='true' fontcolor='#FFFFFF' fontname='Tableau Bold' fontsize='10' />
      <format attr='background-color' value='#1F2A44' />
      <format attr='border-style' value='solid' />
      <format attr='border-width' value='1' />
      <format attr='border-color' value='#1F2A44' />
    </button-visual-state>
  </button>
  <zone-style>
    <format attr='border-style' value='none' />
    <format attr='margin' value='2' />
  </zone-style>
</zone>
```

`window-id` には遷移先 dashboard window の simple-id uuid を指定（{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX} 形式）。

### 14. encoding-id 属性削除（lod/custom 要素から）

```regex
 encoding-id='[^']*'
```

Cloud内部識別子、Desktop は認識しない。

### 15. pane に `<view>` 要素追加（欠落分のみ）

worksheet pane content model: `(view, mark, mark-sizing?, add-in?, encodings?, ...)` で view 必須。

⚠️ **重要訂正（2026-06-16）**: v9 で「pane内view追加禁止」と書いた前回の memory は誤り。**generator製の一部paneでview欠落**があるので、**view持たないpaneだけ追加**が正しい。

```python
def add_view_if_missing(m):
    block = m.group(0)
    inside_start = block.find('>') + 1
    head = block[:inside_start]
    rest = block[inside_start:]
    if rest.lstrip().startswith('<view>') or rest.lstrip().startswith('<view '):
        return block
    return head + "\n            <view>\n              <breakdown value='auto' />\n            </view>" + rest
```

### 16. `<referenced-views>` 中身（referenced-view要素）追加

`<referenced-extension>` content model `(manifest, referenced-views)` で referenced-views必須、かつ中身も必要：

```xml
<referenced-extensions>
  <referenced-extension>
    <manifest manifest-version='0.1'>...</manifest>
    <referenced-views>
      <referenced-view instances='1' viewId='WS12_詳細セッション_サンキー' />
    </referenced-views>
  </referenced-extension>
</referenced-extensions>
```

空 `<referenced-views />` は `content model '(referenced-view)'` で違反。

### 17. workbook 末尾 `<actions>` ブロック削除

workbook content model: `actions?` は worksheets の **前** に来る。末尾にあるのは違反。

```python
ws_pos = content.find('<worksheets>')
if ws_pos > 0:
    before, after = content[:ws_pos], content[ws_pos:]
    after, n = re.subn(r"\s*<actions>.*?</actions>", "", after, flags=re.DOTALL)
    content = before + after
```

### 18. datasource 直下 column順序入替

datasource content model: `column, column-instance, ...` で column → column-instance の順序。

generator製は **column-instance → column (calc field)** の順序違反がある。

```python
# 例: ds_ch2pg datasource内
pat = re.compile(r"(<column-instance column='\[月\]'[^/]*name='\[none:月:ok\]'[^/]*/>)(\s*)(<column caption='fltr_月'[^>]*>.*?</column>)", re.DOTALL)
content = pat.sub(lambda m: f"{m.group(3)}{m.group(2)}{m.group(1)}", content)
```

### 19. サンキーWS の重複 mark 削除

Cloud Web Edit でVizExtension Sankey作ると `<mark class='Automatic' />` と `<mark class='VizExtension' />` の両方が出る。Desktop XSD は mark 1個のみ許容。

```python
content, n = re.subn(r"<mark class='Automatic' />\s*(<mark class='VizExtension' />)", r"\1", content)
```

### 20. Tableau Story (storyboard) 構造仕様

Tableau Desktop の**ストーリー**機能は dashboard + storyboard type で実装：

```xml
<dashboard name='ストーリー' type='storyboard'>
  <style>
    <style-rule element='story-point-caption'>
      <format attr='background-color' value='#1F2A44' />
      <format attr='color' value='#FFFFFF' />
      <format attr='width' value='200' />
    </style-rule>
  </style>
  <zones>
    <zone h='100000' id='2' type-v2='layout-basic' w='100000' x='0' y='0'>
      <zone h='98172' id='1' param='vert' removable='false' type-v2='layout-flow' w='99034' x='483' y='914'>
        <zone h='4800' id='3' type-v2='title' w='99034' x='483' y='914' />
        <zone fixed-size='80' h='9143' id='4' is-fixed='true' paired-zone-id='5' removable='false' type-v2='flipboard-nav' w='99034' x='483' y='5714' />
        <zone h='84229' id='5' paired-zone-id='4' removable='false' type-v2='flipboard' w='99034' x='483' y='14857'>
          <flipboard active-id='1' nav-type='caption' show-nav-arrows='true'>
            <story-points>
              <story-point caption='DB1 戦略層' captured-sheet='DB1_Strategic_到達状況' id='1' />
              <story-point caption='DB2 原課' captured-sheet='DB2_Operational_原課ページ' id='2' />
              <story-point caption='DB3 EBPM深掘' captured-sheet='DB3_Analytical_EBPM深掘' id='3' />
            </story-points>
          </flipboard>
        </zone>
      </zone>
    </zone>
  </zones>
  <simple-id uuid='{STORY_UUID}' />
</dashboard>
```

対応する window セクション entry：
```xml
<window class='dashboard' maximized='true' name='ストーリー'>
  <viewpoints />
  <active id='-1' />
  <simple-id uuid='{WIN_UUID}' />
</window>
```

⚠️ `class='story'` は無効。**`class='dashboard'`** + `<viewpoints />` + `<active id='-1' />` 構造が正しい（2026-06-16実証）。

### 21. dashboard 内 zone座標は dashboard全体に対する絶対値（要検証）

dashboard 内 zone のy/x座標は **dashboard全体100000基準** か **parent layout-basic 内relative** か、Tableau Desktopの解釈に依存。BAN ラベル zone追加でずれ発生（2026-06-16）。

**未確定**：layout-flow vert で「ラベル+数字」を縦並べに包む構造に変更すれば自動配置で揃う可能性。次セッション課題。

## デザイン調整ベストプラクティス

### BAN font-size 適正値
- BAN数字: 20pt 太字 #1F2A44 (dashboard 1500幅、zone w=17013 で 9文字までfits)
- BAN ラベル: 12pt 太字 #4A5878 (混雑回避)
- BAN zone はTableau Desktop保存時に `show-title='false'` 適用後 x/w が **再配置**される (例: x=500→0, w=15800→17013)。XML編集前に実機座標確認必須。

### show-title='false' で worksheet zone タイトル非表示
```xml
<zone ... id='10' name='WS1a_BAN_PV' show-title='false' w='17013' x='0' y='11800' />
```

### Show Mark Labels (mark内テキスト表示) XML
```xml
<style>
  <style-rule element='mark'>
    <format attr='mark-labels-show' value='true' />
    <format attr='mark-labels-cull' value='true' />
  </style-rule>
</style>
```

## 重要ハマりどころ（試行錯誤の知見）

### A. pane 内 view は **必要なら追加**（v9 memoryは誤り）
generator製は pane に view 持つものと持たないものがあり、欠落分のみ追加必須（項目15参照）。

### B. v11new固有問題 → 解決済み（21項目+α）
- add-in (VizExtension Sankey) ×2 + referenced-extensions ×4 → 項目1+16
- button (goto-sheet) ×9 → 項目1.5+13
- slices ×20 → 項目9
- object-graph ×5 → manifest 17要素フラグで許容
- 重複mark → 項目19
- column順序 → 項目18

### C. Tableau Desktop 保存後の TWBX は zone構造が変わる
Tableau Desktop で開いて Save した TWBX は：
- 空 formatted-text を自動クリーンアップ
- show-title='false' 適用後の BAN zone を x/w 再計算
- zone id が 再採番されることがある (DB3 ヘッダー id=9→1)

→ XML編集スクリプトは **実機保存後の構造を読み直して動的に対応**する設計が必要。

### D. Cloud-Desktop ラウンドトリップ判定
| 元WB | Cloud DL | Desktop互換 |
|------|---------|------------|
| Desktop publish済（例: Desktopネイティブ作成のWB） | OK | OK |
| generator製 (twb-generator + REST publish) | OK | **NG** (21項目+α 修正必要) |
| Cloud Web Edit 編集後 | OK | **NG** (同上) |

### E. Tableau Public WBはダウンロード可能
公式DL URL: `https://public.tableau.com/workbooks/{contentUrl}.twb` または `.twbx`
`.claude/skills/tableau-public-twb-analyzer/analyze.py {viz URL}` でDL+XML解析自動化。

### F. button vs storyboard の選択
- **button (navigation)**: 各dashboard内に「他DBへ遷移」リンク。サイドバー下部などに常駐表示。BasicButtonObject manifest必須。
- **storyboard**: 1つの「ストーリー」シートで複数dashboardを切替表示。flipboardベース。

両方使うことも可能だが、UI複雑化するので片方推奨。配布先向けv11newでは button方式採用（2026-06-16）。

## 実証実績

- 2026-06-16: サンプル市 v11new (city_hp_ga4_full_v11 系) で適用 → 21項目+α 全 XSDエラー潰し成功
- 2026-06-16: 検証用サイト「サンキーダイアグラム」(Cloud DL) で manifest 17要素レシピ実証
- 2026-06-16: 観光統計デモWB (Desktop 2026.1ネイティブ) からBasicButtonObject manifest+nav button XML仕様発見
- 2026-06-16: 公開観光統計WB (Tableau Public) から storyboard/flipboard XML仕様発見

## 関連
- [[feedback_twb_desktop_compat]] — 2024.3ダウングレード（古いDesktop向け）
- [[feedback_twb_manifest_by_version_silent_injection]] — ManifestByVersion混入問題
- [[feedback_twbx_export_dual_use]] — TWBX化2系統
