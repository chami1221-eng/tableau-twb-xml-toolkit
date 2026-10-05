---
name: twb-publish-error-codes
description: TWB publish時のエラーコード(400011/500000/403132/401002)早見表。真因と即対処、関連feedbackへのリンク
metadata: 
  node_type: memory
  type: reference
---

# TWB Publish エラーコード辞典

`publish.py` 経由で Tableau Cloud に TWB をアップロードする際の代表的エラー4種の早見表。
**メッセージ文言と真因が乖離しているケース多数**（特に 500000）。本表で即時診断する。

## 一覧

| code | メッセージ表面 | **真因** | 即対処 | 参照 |
|------|--------------|---------|--------|------|
| **401002** | `Sign-in failed` / `Authentication failed` | **PAT競合**（同じPATを別プロセスで連続sign-in→相互無効化） | 30〜120秒待機後再実行。MCP接続とREST sign-inを直前直後に混在させない | - |
| **400011** | `Tableau encountered an error while parsing the workbook` | **XML構造parse失敗**。リレーションDS内のcross-table calc注入（`SUM([列名 (csv名)])`）/ 不正LOD式 / 他calc参照 | calc削除でpublish通過確認 → Cloud Web Editで手動追加 | [[twb-relation-calc-limitation]] |
| **400011 (FAKEPATH変種)** | `The directory is missing or has been moved: .../temp/.../FAKEPATH-xxx`（複数行・DS数ぶん） | **publish.py の csv_dir 相対パス渡し**。publish.py は TWB内 `directory='{csv_dir}'` を `directory='Data'` に文字列置換するが、generatorのCSV_DIRが**絶対パス**なのに csv_dir を**相対**で渡すと置換no-op→絶対Windowsパスが残存→Cloudが各CSVを解決できずFAKEPATH。**スパチャルcalc/XML構造を疑う前にコレ**（2026-07-07 別案件で3publish浪費）| **csv_dir を TWBの `directory=` と一致する絶対パスで渡す**（例 `publish.py x.twb "C:/Users/.../data/dir" --name ...`）| [[twb-map-marks-layer]] |
| **403132** | `Failed to establish a connection to the database` | **publish.pyのdirectory rewrite**（CSV相対パス不整合）。TWBに `directory=''` を出力すると `'Data'` に書き換わるが対応CSVが配置されていない | generator側で `directory='Data'` を直接出力、csv_dir引数を絶対パスで指定 | [[publish-py-absolute-csvdir]] |
| **500000** | `Forbidden` / `User does not have permission` | **誤マップ。実体は XML parse失敗**。`<window>` 自己閉じタグ（cards+simple-id欠落）/ ManifestByVersion残存 / 旧action XML形式残存 / **filter zone追加attribute（mode/values/show-domain/show-null-ctrls）** / **WS削除・追加時の`<viewpoint>`未同期**（dashboard windowの`<viewpoints>`にmain zoneと不一致のWS名が残存/欠落） 等 | 1. `<window>` に `<cards>` + `<simple-id uuid='...'/>` を追加 2. ManifestByVersion削除 3. action XML を新形式に 4. **filter zoneは `pane-specification-id='0'` + `name` + `param` のシンプル3属性のみに削減** 5. **WS増減時は zone / devicelayouts / `<viewpoint>` の3箇所すべて同期**（削除WSのviewpoint削除・追加WSのviewpoint追加） | [[twb-window-cards-required]] [[twb-action-xml-injection]] [[twb-desktop-compat]] [[twb-filter-param-zone-patterns]] |

## 診断フロー

```
publish失敗
   │
   ├─ 401002 → PAT競合。30〜120秒待機して再実行
   │
   ├─ 400011 → XML parse失敗
   │     ├─ メッセージが `FAKEPATH-xxx directory missing`（DS数ぶん複数行）→ **publish.py csv_dir が相対パス**。絶対パスで渡し直す（スパチャル/XML構造より先に確認）
   │     └─ リレーションDS内cross-table calc を疑う → calc削除して再試行
   │           └─ 通過したら Cloud Web Edit で手動calc追加
   │
   ├─ 403132 → CSV配置パス不整合
   │     └─ csv_dir引数を絶対パスで指定し直す
   │     └─ generatorの directory 値が空ならpublish.pyのrewriteと衝突
   │
   └─ 500000 → 「権限」と読まず XML 構造を疑う（最重要ルール）
         ├─ dashboard publish時 → <window> cards+simple-id 欠落？
         ├─ Desktop互換問題 → ManifestByVersion等10項目チェック
         ├─ action注入時 → 旧field-instances形式残存？
         ├─ filter zone 追加attribute → mode/values/show-domain/show-null-ctrls を削除（generator経由ではシンプル3属性のみ通る。Cloud DLしたWBには入っているが新規publishでは reject）
         └─ WS削除・追加した？ → dashboard windowの `<viewpoints>` を確認。main zoneのWSとviewpointのWS名が不一致だと reject（2026-06-14 サンプル市v11new: DB1にWS6削除残骸 / DB2にWS12追加欠落の両方で500000）。zone/devicelayouts/viewpoint の3点セット同期が鉄則
```

## 再利用パターン: Top-N categorical filter（worksheet内部フィルタ）

実WB（executive_dashboard.twb / REAL_workbooks rel4）から抽出した検証済みskeleton。`<aggregation value='true'/>` の直前、他filterの後に挿入する。

```xml
<filter class='categorical' column='[federated.DSNAME].[none:DIM:nk]'>
  <groupfilter count='5' end='top' function='end' units='records' user:ui-marker='end' user:ui-top-by-field='true'>
    <groupfilter direction='DESC' expression='ORDER_EXPR' function='order' user:ui-marker='order'>
      <groupfilter function='level-members' level='[none:DIM:nk]' user:ui-enumeration='all' user:ui-marker='enumerate' />
    </groupfilter>
  </groupfilter>
</filter>
```

- `count` = 上位N / `direction='DESC'`+`end='top'` = 上位（BOTTOMなら`end='bottom'`）
- **ORDER_EXPR の書き方**: 単一メジャーは `SUM([base_field])`（参照WBの形式）。**比率の集約calc（例 直帰率=SUM(bounce)/SUM(session)）は SUM で包めない → calc名を直接参照 `[Calculation_BR01]`**（federated接頭辞・SUM 不要。2026-06-14 サンプル市v11new WS3 詰まりTop5=直帰率順で動作実証）
- action sourceのworksheetに付けても special-fields=all のactionは上位N marksで正常動作（action XML側に値参照が無いため）

## 最重要ルール 鉄則（再掲）

- **TWB publish 500/403 はPATでなく XML構造を疑う**
- 真因 → メッセージ文言の対応は腐っているので、コードで分類して上記表を参照する
- 経験上8回中7回はXML側。PAT/権限が真因なのは1回程度

## Why

- 2026-06-03 サンプル市v9で **計8回の publish 試行 / 4エラー種別** に直面し、毎回手動で原因切り分け
- 切り分け工数: 約4時間（理由: メッセージ文言が真因と乖離・既知feedbackが分散している）
- 本リファレンス集約後の想定工数: 0分（即診断）

## 切り分けの実体験ログ（参考）

| 回 | エラー | 何を疑った | 真因 | 工数 |
|---|---|---|---|---|
| 1 | 401002 | PAT期限切れ → 再発行検討 | 直前のMCP sign-in競合 | 20分 |
| 2 | 401002 | 同上 | 同上 | 15分 |
| 3 | 401002 | 同上 | 同上 | 10分 |
| 4 | 403132 | CSV欠落 → ファイル確認 | publish.py の directory rewrite衝突 | 30分 |
| 5 | 500000 | PAT権限 → site admin確認 | `<window>` 自己閉じタグ（cards欠落） | 80分 |
| 6 | 400011 | XML構文ミス → エディタ確認 | リレーションDS cross-table calc | 60分 |
| 7 | 500000 | XML構造 → 切り分け | dashboard `<window>` simple-id欠落 | 30分 |
| 8 | 500000 | （即診断成功） | 同上 | 5分 |
| 9-16 | 500000×8 | filter zone追加attribute切り分け (v10 generator) | mode/values/show-domain/show-null-ctrls → 全部 reject | 60分（2026-06-03 サンプル市v10）|

## How to apply

- publish失敗時、**即この表を参照** → メッセージ文言でなく code で判定
- 真因が表に無いパターンに遭遇したら、本reference に追記して**次回の手戻りを潰す**
- 関連: [[twb-cloud-compat]] (Public Desktop互換), [[twb-cloud-rendering]] (Cloud描画), [[twb-window-cards-required]], [[twb-relation-calc-limitation]], [[twb-relation-xml-structure]], [[twb-action-xml-injection]], [[twb-v5-textscan-breaks-web-edit-calc]]
