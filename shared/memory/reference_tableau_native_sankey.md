---
name: Tableau VizExtension Sankey 利用・XML自動生成手順
description: Tableau Cloud の Sankey は VizExtension (com.tableau.extension.sankey v1.5.0)。Web Edit手動配置だけでなくTWB XMLからも完全再現可能
metadata:
  type: reference
---

Tableau Cloud (2024.2以降) の Sankey は **VizExtension方式** (`com.tableau.extension.sankey` v1.5.0)。
"ネイティブ"と呼ばれているが実体はTableau公式拡張機能。Web Edit手動でもTWB XML直書きでも生成可能。

## 方式A: Web Edit 手動 (5分・確実性★★★)

1. ワークブックを Web Edit (`/authoring/`) で開く
2. 対象worksheet タブに移動 (空でもよい / 既存ビューを置換でもよい)
3. 右側パネル「Show Me」展開 → Sankey アイコン選択
4. **空のキャンバスが表示される** (ここで詰まりやすい)
5. データペインから手動でドラッグ:
   - **Level 棚**: 次元を 2〜5個ドロップ (フローの段階順、左→右)
   - **Link 棚**: メジャー 1個ドロップ (リンク幅 = この値)
6. 自動描画 → 必要ならマークカードのColorで色分け
7. 右上「公開」で上書き保存

### 落とし穴
- Show Me で Sankey を選んだだけでは描画されない (Level/Link 棚への手動ドラッグが必須)
- 既存ヒートマップ等から切り替えた場合、行/列棚にあったフィールドは Sankey 棚に自動マッピングされない
- Level 棚の順序 = サンキーの並び順 (左 → 右)

## 方式B: TWB XML 自動生成 (10分・確実性★★★)

2026-05-25 サンプル市案件で手動配置版をdownloadして構造判明。完全再現可能。

### 必要な3要素

#### ① CSV (シンプル3列)
```
チャネル,着地ページ,セッション
Direct,01. トップ,3500
Organic Search,02. ごみカレンダー,2100
...
```
シグモイドSankey と違い Path複製/RankFrom/RankTo は不要。

#### ② Worksheet本体 XML
```xml
<worksheet name='チャネル→ページ フロー'>
  <table>
    <view>
      <datasources><datasource caption='チャネル→ページ' name='ds_ch2pg' /></datasources>
      <datasource-dependencies datasource='ds_ch2pg'>
        <column-instance column='[チャネル]' derivation='None' name='[none:チャネル:nk]' pivot='key' type='nominal' />
        <column-instance column='[着地ページ]' derivation='None' name='[none:着地ページ:nk]' pivot='key' type='nominal' />
        <column-instance column='[セッション]' derivation='Sum' name='[sum:セッション:qk]' pivot='key' type='quantitative' />
        <column datatype='integer' name='[セッション]' role='measure' type='quantitative' />
        <column datatype='string' name='[チャネル]' role='dimension' type='nominal' />
        <column datatype='string' name='[着地ページ]' role='dimension' type='nominal' />
      </datasource-dependencies>
      <aggregation value='true' />
    </view>
    <panes>
      <pane selection-relaxation-option='selection-relaxation-allow'>
        <view><breakdown value='auto' /></view>
        <_.fcp.VizExtensions.false...mark class='Automatic' />
        <_.fcp.VizExtensions.true...mark class='VizExtension' />
        <mark-sizing mark-sizing-setting='marks-scaling-off' />
        <_.fcp.VizExtensions.true...add-in add-in-id='com.tableau.extension.sankey'
          extension-url='https://extensions.tableauusercontent.com/sandbox/sankey/sankey.html'
          extension-version='1.5.0' instance-id='{NEW-UUID-HEX32}'>
          <instance-settings>
            <setting key='color-map' value='{"チャネル":[["Direct","#4e79a7"],...],"着地ページ":[...]}' />
          </instance-settings>
          <type-settings><worksheet /></type-settings>
        </_.fcp.VizExtensions.true...add-in>
        <encodings>
          <!-- 各Level次元: lod + custom level の2行ペア (encoding-id 同一UUID) -->
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-A}' column='[ds_ch2pg].[none:チャネル:nk]' />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-A}' column='[ds_ch2pg].[none:チャネル:nk]' custom-type-name='level' />
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-B}' column='[ds_ch2pg].[none:着地ページ:nk]' />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-B}' column='[ds_ch2pg].[none:着地ページ:nk]' custom-type-name='level' />
          <!-- Linkメジャー: lod + custom edge の2行ペア -->
          <_.fcp.VizExtensions.false...lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-C}' column='[ds_ch2pg].[sum:セッション:qk]' />
          <_.fcp.VizExtensions.true...custom _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-C}' column='[ds_ch2pg].[sum:セッション:qk]' custom-type-name='edge' />
          <!-- 各次元/メジャーの追加 <lod> 行 (encoding-idは別UUID) -->
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-D}' column='[ds_ch2pg].[none:チャネル:nk]' />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-E}' column='[ds_ch2pg].[none:着地ページ:nk]' />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-F}' column='[ds_ch2pg].[sum:セッション:qk]' />
          <lod _.fcp.VizExtensionsDupEncodingUUID.true...encoding-id='{UUID-G}' column='[ds_ch2pg].[sum:セッション:qk]' />
        </encodings>
        <style>
          <style-rule element='mark'>
            <format attr='mark-labels-show' value='true' />
            <format attr='mark-labels-cull' value='false' />
          </style-rule>
        </style>
      </pane>
    </panes>
    <rows /><cols />
  </table>
  <simple-id uuid='{NEW-UUID}' />
</worksheet>
```

#### ③ Workbook root の Extension Registration
worksheets ブロックと同階層 (workbook末尾近く) に追加:
```xml
<_.fcp.VizExtensions.true...referenced-extension>
  <manifest manifest-version='0.1'>
    <worksheet-extension extension-version='1.5.0' id='com.tableau.extension.sankey'>
      <default-locale>en_US</default-locale>
      <name resource-id='name' />
      <description>Sankeys show before-and-after states and relationships between two or more categories.</description>
      <author email='github@tableau.com' name='Tableau' organization='Tableau' website='https://www.tableau.com/support' />
      <min-api-version>1.12</min-api-version>
      <source-location>
        <url>https://extensions.tableauusercontent.com/sandbox/sankey/sankey.html</url>
      </source-location>
      <icon />
      <context-menu><configure-context-menu-item /></context-menu>
      <encoding id='level'>
        <display-name resource-id='level-encoding'>Level</display-name>
        <role-spec>
          <role-type>discrete-dimension</role-type>
          <role-type>discrete-measure</role-type>
        </role-spec>
        <fields max-count='5' />
        <encoding-icon token='level' />
        <tooltip resource-id='level-tooltip'>Sankey Level - Drag up to five dimensions here.</tooltip>
      </encoding>
      <encoding id='edge'>
        <display-name resource-id='edge-encoding'>Link</display-name>
        <role-spec>
          <role-type>continuous-dimension</role-type>
          <role-type>continuous-measure</role-type>
        </role-spec>
        <fields max-count='1' />
        <encoding-icon token='edge' />
        <tooltip resource-id='edge-tooltip'>Link - Drag a measure here.</tooltip>
      </encoding>
    </worksheet-extension>
  </manifest>
</_.fcp.VizExtensions.true...referenced-extension>
```

### XML生成の要点

- 全UUID は `uuid.uuid4()` でhex32 (instance-id) または波カッコ付きhex36 (encoding-id) 形式で生成
- Level次元の `encoding-id` は **lod行とcustom行で同一UUID** (ペア)、別の次元/メジャーごとに別UUID
- 追加 `<lod>` 行 (`_.fcp.VizExtensions` プレフィックスなし) も必要 — 各次元1行+メジャー2行
- `custom-type-name='level'` の順序 = Sankeyの左→右の段階順
- `color-map` JSON は省略可 (Tableauデフォルトカラーで描画)
- `<rows />` `<cols />` は **空タグ必須** (棚に何もない宣言)

## 方式比較

| アプローチ | 工数 | 確実性 | 用途 |
|---|---|---|---|
| Web Edit 手動 | 5分 | ★★★ | 単発・1案件 |
| **VizExtension XML自動生成** | 10分 | ★★★ | テンプレ化・横展開・PDCA |
| シグモイドSankey XML直書き (Self-Union+Curve計算) | 30-60分 | ★ (Cloud Curve/LOD不整合で空白頻発) | 非推奨 |

## 関連
- [[feedback_twb_use_generic_publish_script]]
- 実装パターン: `.claude/skills/twb-generator/` に `sankey_worksheet()` ヘルパー追加検討中 (Task #7)
- 参考TWB: `data/sample_city_hp_demo/city_current.twb` の `<worksheet name='チャネル→ページ フロー'>`
