---
name: tableau-pulse-rest-api-409-sibling-connected-app-jwt
description: Pulse definition/metric の POST/PATCH/GET フロー、definition 409の名前一致再利用、default metric PATCH 409時の sibling 採用 or POST 作成、Connected App JWT 認証、必須payload (allowed_dimensions/comparisons/insights_options) を1本にまとめた実装パターン
metadata: 
  node_type: memory
  type: feedback
---

Pulse メトリクスを REST API で作る正攻法。参照実装 `pipeline/publisher.py` の `create_pulse_metrics` (L521〜) と `_get_connected_app_token` (L76〜) が完成版で、私の `tableau-pulse-*` 系メモリ群の **実装側まで含めた裏取り** になっている。

**Why:**
2026-06-08 SE経由で入手した 参照実装を解析。私は既に `[[tableau-pulse-metric-409-use-sibling]]` `[[tableau-pulse-api]]` 等で挙動メモは持っていたが、**実装コード**は持っていなかった。参照実装は409対応・JWT認証・必須payload構造まで全部入りで実装している。今後 Pulse 連携系スキルを作る時はこれを下敷きにする。

**How to apply:**

### エンドポイント階層

```
POST  /api/-/pulse/definitions                          # 定義作成
GET   /api/-/pulse/definitions?page_size=200            # 409時の名前一致用
PATCH /api/-/pulse/definitions/{def_id}                 # 既存定義更新
DELETE /api/-/pulse/definitions/{def_id}                # 削除

GET   /api/-/pulse/definitions/{def_id}/metrics         # default metric取得
POST  /api/-/pulse/metrics                              # sibling作成 (定義紐付け)
PATCH /api/-/pulse/metrics/{metric_id}                  # measurement_period更新
DELETE /api/-/pulse/metrics/{metric_id}                 # 削除
```

### 認証2系統

| 用途 | 認証 | scope |
|---|---|---|
| Pulse **読み取り** (GET) | PAT (server.auth_token) | 自動 |
| Pulse **書き込み** (POST/PATCH/DELETE) | **Connected App JWT 推奨**。PAT で 403 になる環境多数 | `tableau:insight_definitions:create/update/delete/read` `tableau:insight_metrics:create/update/delete/read` `tableau:insight_definitions_metrics:read` `tableau:insights:read` `tableau:metric_subscriptions:create/delete/read` `tableau:datasources:read` `tableau:content:read` |

Connected App JWT 生成 → `/api/3.28/auth/signin` で Tableau 認証トークンに交換。実装は publisher.py `_get_connected_app_token` をそのまま使う。

```python
import jwt as pyjwt, datetime, uuid, requests
payload = {
  "iss": ca_client_id,
  "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5),
  "jti": str(uuid.uuid4()),
  "aud": "tableau",
  "sub": ca_user,
  "scp": [...上記scope全部...],
}
jwt_token = pyjwt.encode(payload, ca_secret_value, algorithm="HS256",
                         headers={"kid": ca_secret_id, "iss": ca_client_id})
# /auth/signin で交換 → x-tableau-auth ヘッダーに使う
```

### definition POST 必須payload (省略すると 400706/400922)

```python
{
  "name": "{KPI title}",
  "specification": {
    "datasource": {"id": "{datasource_uuid}"},
    "basic_specification": {
      "measure": {"field": "{column_name}", "aggregation": "AGGREGATION_SUM"},
      "time_dimension": {"field": "{date_column}"},
      "filters": [],
    },
    "is_running_total": False,
  },
  "extension_options": {
    "allowed_dimensions": ["{dim1}", "{dim2}", ...],  # ←空だと400
    "allowed_granularities": [
      "GRANULARITY_BY_DAY", "GRANULARITY_BY_WEEK",
      "GRANULARITY_BY_MONTH", "GRANULARITY_BY_QUARTER", "GRANULARITY_BY_YEAR",
    ],
    "offset_from_today": 0,
    "correlation_candidate_definition_ids": [],
    "use_dynamic_offset": False,
  },
  "representation_options": {
    "type": "NUMBER_FORMAT_TYPE_NUMBER",
    "number_units": {"singular_noun": "{unit}", "plural_noun": "{unit}"},
    "sentiment_type": "SENTIMENT_TYPE_NONE",
  },
  "insights_options": {"show_insights": True, "settings": []},  # ←必須(400957回避)
  "comparisons": {
    "comparisons": [
      {"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD"}, "index": 0},
      {"compare_config": {"comparison": "TIME_COMPARISON_YEAR_AGO_PERIOD"}, "index": 1},
    ],  # ←空だと400922
  },
  "datasource_goals": [],
  "related_links": [],
  "certification": {"is_certified": False},
}
```

`aggregation` の値マッピング: `SUM→AGGREGATION_SUM` `AVG→AGGREGATION_AVERAGE` `MEDIAN→AGGREGATION_MEDIAN` `COUNT→AGGREGATION_COUNT` `COUNTD→AGGREGATION_COUNT_DISTINCT` `MIN→AGGREGATION_MIN` `MAX→AGGREGATION_MAX`

### 409 Conflict 対応 (definition)

同名定義が既存 → POST が 409 を返す:

```python
if def_resp.status_code == 409:
    list_resp = requests.get(def_url, headers=headers, params={"page_size": 200})
    for d in list_resp.json().get("definitions", []):
        md = d.get("metadata", {})
        if md.get("name") == title:
            definition_id = md.get("id", "")
            break
    # 設定変更を反映するため PATCH で更新
    requests.patch(f"{base_url}/api/-/pulse/definitions/{definition_id}",
                   json=definition_payload, headers=headers)
```

### default metric の取得と PATCH

definition 作成時に default metric が自動生成される。これを取得して `measurement_period` を完了期間ベースに変更する (デフォルトは `RANGE_CURRENT_PARTIAL` で「現在の期間データなし」になる):

```python
# GET で取得
metric_resp = requests.get(f"{base_url}/api/-/pulse/definitions/{definition_id}/metrics", ...)
metrics = metric_resp.json().get("metrics", [])

# design.pulse_grain と一致する non-default metric があれば優先 (sibling採用)
target_gran = f"GRANULARITY_BY_{grain}"   # MONTH/DAY/WEEK/QUARTER/YEAR
match_metric = next(
    (m for m in metrics
     if m["specification"]["measurement_period"]["granularity"] == target_gran
     and m["specification"]["measurement_period"]["range"] == "RANGE_LAST_COMPLETE"),
    None,
)
default_metric = next((m for m in metrics if m.get("is_default")), metrics[0] if metrics else None)
chosen_metric = match_metric or default_metric
```

### default metric PATCH 409 → sibling POST フォールバック

default metric は **schema_version 上の楽観ロック** で PATCH 不可になることがある (409)。その場合は **同 granularity の新 metric を POST で作成**:

```python
patch_payload = {
  "specification": {
    "filters": [],
    "measurement_period": {
      "granularity": f"GRANULARITY_BY_{grain}",
      "range": "RANGE_LAST_COMPLETE",   # ← CURRENT_PARTIAL だと値出ない
    },
    "comparison": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD"},
  },
}
patch_resp = requests.patch(f"{base_url}/api/-/pulse/metrics/{metric_id}",
                            json=patch_payload, headers=headers)

if patch_resp.status_code not in (200, 201):
    # sibling 作成
    post_payload = {"definition_id": definition_id, **patch_payload}
    post_resp = requests.post(f"{base_url}/api/-/pulse/metrics",
                              json=post_payload, headers=headers)
    if post_resp.status_code in (200, 201):
        metric_id = post_resp.json().get("metric", post_resp.json()).get("id", metric_id)
```

### 削除順 (publisher.py `delete_all` L771〜)

1. Pulse metrics (DELETE `/api/-/pulse/metrics/{metric_id}`)
2. Pulse definitions (DELETE `/api/-/pulse/definitions/{def_id}`)
3. Workbook (TSC)
4. Datasource (TSC)
5. Project (空なら、TSC)

逆順だと「definition がまだ metric を持つ」エラー / 「project にコンテンツ残存」エラーで詰まる。

### Hyper 単票生成 (Pulse 必須仕様)

Pulse は **schema=Extract, table=Extract の単一テーブル** しか受け付けない。星型を fact + master JOIN で非正規化して `tableauhyperapi` で生成する。実装は publisher.py `build_pulse_hyper` (L373〜) を流用。同名衝突は `{col_name}_{master_name}` 形式でリネーム。

### 既知エラーコード一覧 (API系)

| HTTP / コード | 原因 | 対処 |
|---|---|---|
| 400706 / 400922 | `allowed_dimensions=[]` / `comparisons=[]` | 上記payload通り埋める |
| 400957 | `insights_options` 欠落 | `{"show_insights": True, "settings": []}` |
| 403 (PAT書込み) | PAT では Pulse 書込権限なし | Connected App JWT に切替 |
| 403045 (project作成) | サイト管理権限なし | 既存プロジェクト指定（Sandbox 等） |
| 403132 (workbook publish) | sqlproxy 書換漏れ | [[feedback_twb_sqlproxy_rewrite_pattern]] 適用 |
| 409 (definition POST) | 同名定義既存 | 名前一致再利用 + PATCH |
| 409 (metric PATCH) | default metric 楽観ロック | sibling POST 作成 |

### Pulse 表示・運用系問題（API成功してから表示崩れるパターン）

| 症状 | 原因 | 対処 |
|---|---|---|
| Pulse カード「現在の期間のデータはまだありません」 | grain ≠ データ粒度 / `RANGE_CURRENT_PARTIAL` のまま | grain 整合 + `RANGE_LAST_COMPLETE`（PATCH既定済） |
| 全カード "-" + 「現在の期間のデータはまだありません」（編集保存でも解消しない） | grain 単位の直近 period にデータが無い (例: DAY 指定で昨日が土日 0 行) | Phase 1.5 grain整合ガード で事前検出（[[feedback_skill_design_pattern]] パターン4） → WEEK/MONTH へ切替 |
| Pulse 初期表示で「-」 | Cloud キャッシュの既知挙動 | 編集モードに入れば値が出る。再 publish しても無駄 |
| Pulse カードが `4.0万` / `100M` のように省略表記される | Pulse 仕様 (API で抑制不可) | ソース側で `百万円`/`万円` 単位への事前丸めをしない（[[feedback_pulse_kpi_unit_rules]]）|
| Pulse カード値が全部 0 | ダミー行が「先月」に位置 + 数値全カラム 0 | ダミー値を 1つ前の月の値コピーに変更 or pulse_grainを変える（2026-06-09Phase A実発生） |
| Pulse「比較データなし」「一昨年起点」 | 月次/年次で 12ヶ月以下しか無く前年同月不在 | 24ヶ月以上に伸ばすか末尾に年跨ぎダミー1行追加 |
| line chart x 軸起点が古すぎる (例: 24ヶ月データなのに `2023/4` から始まる) | 不要な年跨ぎダミー1行が start より前に入っている | 24ヶ月以上のデータならダミーを書き込まない |
| line chart の x 軸が「2/1, 8/1...」 | テンプレ Day-Trunc 固定 | `design.pulse_grain` から `date_granularity` を派生 → Year-Trunc に切替 |
| ダッシュボード初期表示で全 worksheet 空 | テンプレ TWB の当月絞り込み (`member='YYYYMM'`) | [[feedback_twb_template_residue_patterns]] パターン3 で level-members 置換 |
| Pulse カード見切れ | vert 親の `fixed-size` が小さい | [[feedback_twb_pulse_integration]] パターン5: PULSE_COL_FIXED_SIZE=358 |
| Agent ボタン無反応 | toggle-action の window-id が dashboard simple-id 不一致 | [[feedback_twb_pulse_integration]] パターン2-3: dashboard UUID 抽出+流用 |
| KPI ミニアイコン残留 | `generate_icons.py` 由来の wheelbarrow.png 等 | [[feedback_twb_pulse_integration]] パターン4: `remove_kpi_icon_zones()` |
| チャート空 | テンプレ内部名 `[受入量_t]` 残骸 / `DATEADD('day',-3,...)` | [[feedback_twb_template_residue_patterns]] パターン1-2 |
| TDSX に列名ミスマッチ | `(master_X.csv)` 接尾辞 | チャート row_dimension は fact に非正規化（[[feedback_pulse_hyper_denorm_pattern]]）|
| Pulse フィルター UI エラー | 時系列非連続 / 日付列 type=ordinal | TDSX 再ビルドで連続日付＋type=nominal |
| ワークブック URL が開けない | UUID 直指定 | `wb_item.content_url` を使う |

### 私の既存スキル/メモリへの取り込み先（2026-06-09実装完了）

- ✅ `.claude/skills/twb-generator/pulse_publisher.py` に配備済
  - クラス: `TableauCredentials.from_env()` (PAT + Connected App 8環境変数読込)
  - 関数: `get_connected_app_token(creds)` (JWT交換)
  - 関数: `create_pulse_metrics(server, creds, datasource_id, design, site_id)` (KPI4個一括作成)
  - 関数: `delete_pulse_metrics()` / `delete_pulse_definitions()` (クリーンアップ)
  - 内部ヘルパー: `_collect_allowed_dims` `_build_definition_payload` `_ensure_metric` `_pulse_agg`
- ✅ `.claude/skills/twb-generator/SKILL.md` に「派生用途: Tableau Pulse メトリクス自動作成」セクション追記
- 動作検証: 2026-06-09 検証用サイト/city-trial-monthly_CityTrialMonthly で Pulse 4個作成成功
  - 4個全 [✓] OK、metric_id/definition_id取得済、MONTH/RANGE_LAST_COMPLETE設定済
  - 1点踏んだ落とし穴: allowed_dimensions が空配列だと 400 Bad Request → string列必須が実証
- ⏳ 新規スキル `tableau-pulse-builder` は保留 (twb-generator配下で十分な可能性高、pref-demoに統合する案も含めて Phase A再評価で判断)
- 既存メモリ統合: 本feedbackが [[tableau-pulse-api]] [[tableau-pulse-metric-409-use-sibling]] [[tableau-pulse-grain-match-data]] の **実装側まとめ**

関連:
- [[tableau-pulse-api]] — Pulse 定義 POST の必須フィールド一覧（要点版）
- [[tableau-pulse-metric-409-use-sibling]] — default metric PATCH 不可時の sibling 採用（挙動メモ）
- [[tableau-pulse-grain-match-data]] — `pulse_grain` をデータ粒度に揃える
- [[tableau-pulse-grain-period-must-be-complete]] — 「直近の閉じたperiod」が無いと "-" になる
- [[tableau-pulse-monthly-yearly-dummy]] — 月次データの1行ダミー
- [[tableau-pulse-source-no-pre-rounding]] — Pulse 表示で二重省略を避ける
- [[tableau-pulse-initial-render-dash]] — 初期表示「-」は編集モードで解消
- [[tableau-pulse-layout-fixed-size]] — Pulse zone の親レイアウト fixed-size 非対称仕様
- [[feedback_twb_sqlproxy_rewrite_pattern]] — 同じ publisher.py に同居する TDSX publish + sqlproxy 書換パターン
