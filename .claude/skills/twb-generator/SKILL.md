---
name: twb-generator
description: >
  CSV群からTableau .twbワークブックをXML直接生成するスキル。
  データソース定義・リレーション・ワークシート・マップを含む.twbを自動生成する。
  「twb作って」「ワークブック生成」「Tableauファイル作って」でトリガー。
---

# twb-generator — Tableau .twb XML生成

## トリガー
- `twb-generator {CSV群のパス} {出力先}`
- 「twb作って」「ワークブック生成」「Tableauファイル作って」

## 前提
- Tableau Desktop 2025.2+ で開ける .twb (version 18.1) を生成
- CSVファイルが手元に存在すること
- 生成後の微調整はDesktop or Tableau Agentで行う想定

## ⚠️ 必須遵守事項 (違反厳禁)

1. **datasource構造は pref-demo構造 (`<connection class='federated'>` wrap + capability metadata + 型コード20/5/129 + collation) を必ず採用**。`<connection class='textscan'>` 直接配置はCloud Web Edit Calc作成を破壊する。詳細: `docs/twb-patterns.md` 冒頭の最重要ルール
2. **datasource は federated wrap 構造で書く**（named_conn/capability_meta/col_meta/table_rel/meta_for_table の各ヘルパー相当）。手本＝`.claude/skills/freetext-to-tableau/template/freetext_dashboard.twb` の `<datasource>`
3. **publish.py呼び出しは `--name "<wb_name>"` を必ず明示**。default依存禁止 (別案件WB上書き事故防止)
4. **publish.py の csv_dir 引数は必ず絶対パス**。相対パスだとTWB内ハードコード絶対パスと directory置換マッチせず FAKEPATHエラー発生 (shared/memory/feedback_publish_py_absolute_csvdir.md)
5. **dashboard filter/legend zone は `dashboard_zone_helpers.py` の helper関数経由で生成**。`pane-specification-id='0'` + open/close tag + `param='[<ds_ref>].[<column-instance>]'` の3点が揃わないと Cloud描画されない (shared/memory/feedback_twb_filter_legend_zone_xml.md)

## 実行手順

### Step 0: 参照Viz探索（設計インプット・推奨）

手元に「お手本にする参照ダッシュボード」が無い場合は、**設計に入る前に Tableau Public で参考Vizを探す**。

1. `../tableau-public-reference-finder/` でテーマ/キーワードから参考Vizを探す（要 `pip install pyyaml`）:
   ```bash
   cd ../tableau-public-reference-finder
   python .claude/skills/tableau-public-reference-finder/recommend.py --themes "{テーマ}" --keywords "{キーワード}"   # ネットがあれば --dynamic も
   ```
2. 良さそうな Viz の URL を `../tableau-public-twb-analyzer/` で解析し、シート構成・calc・レイアウトを把握:
   ```bash
   cd ../tableau-public-twb-analyzer
   python .claude/skills/tableau-public-twb-analyzer/analyze.py "{Viz URL}"
   ```
3. 得た構造を下の Step 1〜3 の設計インプットにする。

### Step 1: CSV分析
1. 対象CSVのヘッダーを `head -2` で確認
2. 各CSVの列名・データ型・行数を把握
3. 結合キー（共通カラム）を特定

### Step 2: データソース設計
ユーザーに確認:
- **結合方式**: どのCSVをどのキーでJOINするか
- **スタンドアロン**: JOINしないCSVはあるか（例: メッシュデータ）
- **ワークシート構成**: 何枚のシートをどのVizタイプで作るか

### Step 3: .twb生成スクリプト作成・実行
`scripts/YYYYMMDD_generate_twb.py` としてPythonスクリプトを作成。

### Step 4: Desktop検証（オプション）
ユーザーにDesktopで開いてもらい、エラーがあれば修正ループ。

### Step 5: Tableau Cloudパブリッシュ
`tools/publish.py` を使って .twb→.twbx変換→Cloudパブリッシュ。

```bash
python tools/publish.py \
  "path/to/workbook.twb" \
  "path/to/csv_dir" \
  --project "Default" \
  --name "ワークブック名"
```

**前提**: `.env.tableau`（キット直下） にPAT情報がセットされていること。

**Monitor Tool活用**: ユーザーが並行作業を指示している場合、tools/publish.py をMonitorでバックグラウンド実行し、`Published successfully` 行の検知で次ステップに進む。未指示の場合は従来の直列実行。

### Step 6: publish後の描画確認（脱MCP）
パブリッシュ後、`python tools/tableau_rest.py view-image --workbook "{WB名}" --out ./verify` で各シートのview画像をPNG取得して目視確認（MCPサーバ不要・TSC/RESTで取得）。

## PAT管理

認証情報は `.env.tableau`（キット直下） で管理（チャット履歴に露出させない）。

```
TABLEAU_PAT_NAME=your_pat_name
TABLEAU_PAT_SECRET=your_pat_secret
TABLEAU_SERVER=https://<your-pod>.online.tableau.com
TABLEAU_SITE_ID=<your-site-id>
```

- PATはTableau Cloud → 設定 → Personal Access Tokensで発行
- **チャットに直接PAT値を入力しない**。必ず.envファイル経由で読み込む
- ローテーション時は `.env.tableau` の値を更新するだけでOK

## .twb XML必須ルール

### manifest
```xml
<document-format-change-manifest>
  <ManifestByVersion />
</document-format-change-manifest>
```
> **Note (2026-04):** `ManifestByVersion` は8個の個別フラグ（AnimationOnByDefault等）を1行に置換。
> Tableau 2026.1 XSD公式対応。旧8フラグ形式も引き続き動作する。

### datasource構造
各datasource内に以下が必須:
1. `<named-connections>` — CSV接続定義
2. `<relation>` — テーブル or JOINリレーション
3. `<metadata-records>` — 列メタデータ（`<object-id>` 付き）
4. `<column>` 定義 — role/type/semantic-role
5. **`<object-graph>`** — `ObjectModelEncapsulateLegacy` 対応。各テーブルを `<object>` として定義

```xml
<object-graph>
  <objects>
    <object caption='テーブル名' id='テーブル名_GUID'>
      <properties context=''>
        <relation connection='named_conn_id' name='file.csv' table='[file#csv]' type='table'>
          <columns>...</columns>
        </relation>
      </properties>
    </object>
  </objects>
</object-graph>
```

### mapsources（地図使用時）
2箇所に必要:
1. **ワークブックレベル**: `</datasources>` と `<worksheets>` の間
2. **マップワークシートの `<view>` 内**: `<datasources>` の直後

```xml
<mapsources>
  <mapsource name='Tableau' />
</mapsources>
```

### 地理カラム設定
```xml
<column aggregation='Avg' caption='緯度' datatype='real' name='[lat]'
        role='measure' semantic-role='[Geographical].[Latitude]' type='quantitative' />
```
- `aggregation='Avg'`（Sumだと座標が壊れる）
- `semantic-role='[Geographical].[Latitude]'` or `[Longitude]`

### マップワークシート
```xml
<style>
  <style-rule element='map'>
    <format attr='washout' value='0.0' />
  </style-rule>
</style>
```
- `<lod>` エンコーディングでメッシュ単位の詳細度を指定

### ダッシュボード
**注意**: XML直接生成のダッシュボードは内部エラーが出やすい。Desktop上で手動作成を推奨。
生成する場合のcontent model順序:
```
style → size → datasources → datasource-dependencies* → zones → devicelayouts → simple-id
```
- `<dashboards />` (空) は不可。要素があるなら1つ以上の `<dashboard>` 必須
- なければ `<dashboards>` 要素自体を省略

### JOIN定義
```xml
<relation join='left' type='join'>
  <clause type='join'>
    <expression op='='>
      <expression op='[table1.csv].[key_col]' />
      <expression op='[table2.csv].[key_col]' />
    </expression>
  </clause>
  <relation connection='nc_id1' name='table1.csv' table='[table1#csv]' type='table'>
    <columns>...</columns>
  </relation>
  <relation connection='nc_id2' name='table2.csv' table='[table2#csv]' type='table'>
    <columns>...</columns>
  </relation>
</relation>
```
多テーブルJOINはネスト: `((A JOIN B) JOIN C) JOIN D`

## 高度なダッシュボード機能

以下のパターンは `docs/twb-patterns.md` に完全なXMLスニペットと組合せ方法を記載。

| 機能 | XMLパターン | 難易度 |
|------|-------------|--------|
| フィルタアクション | `tsc:tsl-filter` + `exclude-sheet` | 実装済み |
| ハイライト | `tsc:brush` | 実装済み |
| パラメータアクション | `edit-parameter-action` | 実装済み |
| セットアクション | `edit-group-action` + `<group>` | 中 |
| Dynamic Zone Visibility | `datagraph` + `dashboard-zone-visibility-node` | 高 |
| Show/Hide Toggle | `<button>` + `<toggle-action>` | 中 |
| Go-to-sheet | `tabdoc:goto-sheet window-id="{GUID}"` | 低 |
| Reference Line | `<reference-line>` + `<style-rule element='refline'>` | 低 |
| Dual Axis | rows `+` 結合 + 2nd pane `y-axis-name` 直接指定 | 中 |
| カスタムカラー | `<color-palette>` in `<preferences>` | 低 |
| 空間関数 | BUFFER/INTERSECTS/MAKEPOINT/MAKELINE | 中 |

## ⚠️ TWB XML生成前に必ず読むファイル
- **`shared/memory/feedback_twb_xml_generation.md`** — 過去のパブリッシュ失敗から学んだ必須ルール集。Dual Axis/paramctrl/customized-label/mark-labels等のCloud publish対応構文

## Correction記録（TWB生成時に必ず参照）

過去のpublish失敗・描画異常から抽出したルール。TWB生成前にこのリストを事前チェックすること。

### C-001: publish 403はXML構造を疑う（PATではない）
- **発生**: PAT再発行を繰り返して解決せず、実際はXML非互換
- **ルール**: 動作実績TWBをテンプレートにする。PATを先に疑わない
- **参照**: feedback_twb_cloud_compat.md

### C-002: ElementTree禁止
- **発生**: ETラウンドトリップでuser:名前空間・属性順序が破壊→Cloud 403
- **ルール**: TWB XMLの**編集**はテキスト置換のみ。ElementTree/lxml禁止
- **例外**: **読み取り専用**の検証（XSD validation, XPath検索）はlxml使用OK
- **参照**: feedback_twb_no_elementtree.md

### C-003: デザインルール強制適用しない
- **発生**: XMLにフォント・色を埋め込むとTableauデフォルトより悪化
- **ルール**: `<style />`空のまま。Tableauに任せる
- **参照**: feedback_twb_no_forced_styling.md

### C-004: ダッシュボードはlayout-basic絶対配置
- **発生**: layout-flowでデータ多WSが他を圧縮
- **ルール**: layout-basicで全zone絶対配置
- **参照**: feedback_twb_dashboard_layout_basic.md

### C-005: BANカードは行レベル計算
- **発生**: SUM()+derivation='Sum'=二重集計で空白
- **ルール**: Square mark + 行レベル式。集約関数をencodingに含めない
- **参照**: feedback_twb_ban_text_only.md

### C-006: フィルター/凡例はソースチャート横配置
- **発生**: ダッシュボード上部に全フィルタ集約→使いにくい
- **ルール**: フィルターは対象WSの横、2DB両方に凡例必須、paramctrl復元チェック
- **参照**: feedback_twb_dashboard_ux.md

### C-007: customized-label/tooltipのフィールド参照スコープ
- **発生**: datasource-dependenciesにフィールドを定義したがlabelに表示されない
- **ルール**: encodings内のフィールドのみ参照可能
- **参照**: feedback_twb_customized_label_scope.md

## XSD Schema Validation (optional)

Tableau公式XSD (2026-02公開) でTWB構造を検証する。`schemas/` にローカル保存済み。

```bash
# XSD検証のみ（publish不要）
python tools/publish_test.py path/to/file.twb --xsd

# XSD + パブリッシュテスト
python tools/publish_test.py path/to/file.twb csv_dir/ --xsd

# XSD再ダウンロード（更新時）
python tools/publish_test.py --download-xsd
```

**検証範囲**: 要素順序・必須属性・属性値パターン・manifest構造
**検証外**: 接続属性・計算式・フィールド名参照整合性・TWBX・セマンティック正当性

**既知のwarning（非ブロッキング）**: fontstyle属性、sort/computed-sort順序、trendline順序、missing trailing elements

**C-002との関係**: XSD検証はlxml読み取り専用→C-002（ラウンドトリップ編集禁止）に抵触しない。

## Dashboard Zone Helpers (filter/legend zone生成)

`dashboard_zone_helpers.py` に filter/legend zone XML helper関数を提供。Cloud描画の3点必須仕様 (`pane-specification-id='0'` + open/close tag + `param='[<ds_ref>].[<column-instance>]'`) を自動で満たす。

### 使用例

```python
import sys
sys.path.insert(0, '.claude/skills/twb-generator')  # リポジトリ直下から実行する
from dashboard_zone_helpers import (
    make_filter_zone, make_legend_zone, field_ref,
    top_legend_preset, right_sidebar_filter_preset,
)

# field参照を生成 (pref-demo構造 federated.ds_<key>.<column-instance>)
field = field_ref("daily", "曜日")              # → "[federated.ds_daily].[none:曜日:nk]"
field = field_ref("channel", "セッション",
                  dtype="integer", role="measure")  # → "[federated.ds_channel].[sum:セッション:qk]"

# 上部 full-width legend (推奨レイアウトプリセット)
legend_xml = top_legend_preset(field_ref("daily", "曜日"), "曜日別 平均セッション")

# 右サイドバー縦長 filter (推奨レイアウトプリセット)
filter_xml = right_sidebar_filter_preset(field_ref("channel", "チャネル"), "サンキー")

# カスタム座標で生成
custom_filter = make_filter_zone(
    field=field_ref("ku_centers", "区"),
    src_sheet="サンプル市5区 バブルマップ",
    x=80000, y=11500, w=19500, h=87000,
    zone_id=70,
)
```

### Helper関数一覧

| 関数 | 用途 |
|------|------|
| `field_ref(ds_key, col, dtype, role)` | pref-demo構造の field参照を生成 |
| `column_instance(col, dtype, role)` | column-instance ID (`[none:col:nk]`等) を生成 |
| `make_filter_zone(field, src, x, y, w, h)` | Quick filter zone XML |
| `make_legend_zone(field, src, x, y, w, h, ltype)` | color/size/shape凡例 zone XML |
| `top_legend_preset(field, src, ltype)` | 上部 full-width legend ショートカット (y=7500, w=99000, h=4000) |
| `right_sidebar_filter_preset(field, src)` | 右サイドバー縦長 filter ショートカット (x=80000, w=19500, h=87000) |

### 落とし穴
- **field参照の column-instance形式**: `[日付]` のようなシンプル形式は Cloud で無視される。必ず `column_instance()` または `field_ref()` 経由で `[none:日付:nk]` 等を生成
- **legend source worksheet選び**: categorical color encoding を持つworksheetを指定。gradient encoding (`color column='[avg:直帰率:qk]'` 等) を持つworksheetを指定すると gradient凡例になる
- **worksheet名は完全一致**: dashboard zone定義の `src_sheet` は実worksheet名と括弧含む全文字列完全一致必須
- 右サイドバー filter採用時は worksheet zones を w=79000 (x=500-79500) に縮める必要あり

詳細パターン: `docs/twb-patterns.md` Section 5.5 (Dashboard Filter/Legend Zones)
実例: `scripts/20260526_generate_city_v8_twb.py` (gen_dashboard内で本helperを参考に実装)

## 派生用途: Tableau Pulse メトリクス自動作成 (pulse_publisher.py)

公開済データソース (TDSX) に対して、KPI 4枚分の Pulse メトリクス definition + metric を REST API で
一括作成する単体ライブラリ。twb生成パイプラインの最終段 or 別 publish スキルから呼び出し可能。

### 用途
- 既存TDSX(publish済)に Pulse カードを後付け
- pref-demo / 任意CSV パイプラインへの「Pulse 4枚追加」機能拡張
- 顧客デモで「KPIカードが先月比 / 前年同期付きで見える」状態を1関数で

### 使い方

```python
import tableauserverclient as TSC
from pulse_publisher import TableauCredentials, create_pulse_metrics

creds = TableauCredentials.from_env()
auth = TSC.PersonalAccessTokenAuth(creds.pat_name, creds.pat_value, site_id=creds.site_name)
server = TSC.Server(creds.server_url, use_server_version=True)

with server.auth.sign_in(auth):
    results = create_pulse_metrics(
        server=server,
        creds=creds,
        datasource_id="<TDSX publish後の UUID>",
        design={
            "date_column": "Month",
            "pulse_grain": "MONTH",
            "category_param_dimension": "Quarter",   # ← string列1個以上必須(400706回避)
            "kpi_cards": [
                {"index": 0, "title": "月間アクセス", "measure": "Impressions",
                 "aggregation": "SUM", "unit": "件"},
                # ... 4個
            ],
            "charts": [...],
            "tables": [...],
        },
        site_id=server.site_id,
    )
# results = [{"title": "...", "definition_id": "...", "id": "...", "status": "ok"}, ...]
```

### 重要な落とし穴 (Phase A検証で踏んだもの)

1. **allowed_dimensions に string 列が1個以上必須** — 全列が date/numeric だと 400 Bad Request
   - design.json で `category_param_dimension` を string列に設定する
   - もしくは prepare_csv 段階で Quarter 等の派生 string 列を追加
2. **PAT書込みで403になる環境あり** — Connected App JWT に切替 (`TABLEAU_CONNECTED_APP_*` 環境変数4つ設定)
3. **default metric は CURRENT_PARTIAL** — 「現在の期間データなし」回避のため必ず PATCH/sibling POST で `RANGE_LAST_COMPLETE` に
4. **同名 definition は 409** — GET + 名前一致 + PATCH 自動再利用ロジック内蔵
5. **pulse_grain は date列の最終データに整合** — 先月にデータないと値が `-` or 0 になる

### エラーコード対応表

| HTTP | 原因 | 対処 |
|---|---|---|
| 400706 | allowed_dimensions が空 | string列1個以上を `category_param_dimension` に設定 |
| 400922 | comparisons が空 | payload内蔵デフォルトで対応済 |
| 400957 | insights_options 欠落 | payload内蔵デフォルトで対応済 |
| 403 | PAT書込み権限なし | Connected App JWT に切替 |
| 409 (def) | 同名既存 | GET + PATCH 再利用 (内蔵) |
| 409 (metric) | default 楽観ロック | sibling POST 作成 (内蔵) |

### 動作確認
2026-06-09 検証用Cloudサイトで Pulse 4個作成成功（city-trial-monthly_CityTrialMonthly）:
- 4個全 [✓] OK
- metric_id / definition_id 取得済
- MONTH/RANGE_LAST_COMPLETE 設定済

### 関連
- 実装パターン詳細・落とし穴: `shared/memory/feedback_pulse_rest_api_recipe.md`
- 原典: SE提供の参照実装 の `pipeline/publisher.py` L37-152 + L521-766
- 姉妹: `../twb-cloud-dl-xml-inject/sqlproxy_rewriter.py` (TWBX を Cloud DS 参照化)

## 参照ファイル
- **docs/twb-patterns.md** — XML実装パターンカタログ（11 Viz分析から抽出）
- **dashboard_zone_helpers.py** — filter/legend zone XML helper (本セクション参照)
- **pulse_publisher.py** — Pulse REST API 完全レシピ (本セクション参照)
- テリトリーマップ.twb: `マイ Tableau リポジトリ/ワークブック/テリトリーマップ.twb` — 実動リファレンス
- pref-demo生成スクリプト: `scripts/generate_pref_twb.py` — Dual Axis+paramctrl+mark-labels実装例
- pref-demo検証スクリプト: `scripts/verify_pref.py` — 生成→パブリッシュ→全ビュー画像検証
