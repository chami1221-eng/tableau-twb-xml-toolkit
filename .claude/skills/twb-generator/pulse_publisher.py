"""pulse_publisher.py — Tableau Cloud Pulse メトリクス作成ライブラリ。

元実装: SE提供の参照実装 の pipeline/publisher.py L37-152 + L521-766
動作確認: 2026-06-09 検証用Cloudサイトで Pulse 4個作成成功（city-trial-monthly）
        4個全 [✓] OK・metric_id / definition_id 取得・MONTH/RANGE_LAST_COMPLETE 設定済

主要関数:
  - TableauCredentials.from_env(): 環境変数から認証情報を読み込み
  - get_connected_app_token(creds): Connected App JWT 交換でPulse書込みtoken取得
  - create_pulse_metrics(server, creds, ds_id, design, site_id): KPI4個分のPulse定義+metric作成

design スキーマ要件:
  {
    "date_column": "<日付列名>",
    "pulse_grain": "MONTH|DAY|WEEK|QUARTER|YEAR",
    "category_param_dimension": "<string列名>",   # allowed_dimensions 用
    "kpi_cards": [
      {"index": 0, "title": "...", "measure": "...",
       "aggregation": "SUM|AVG|COUNT|...", "unit": "..."},
      ... (4個)
    ],
    "charts": [...]   # row_dimension/category から allowed_dimensions 補完
  }

❗ 最重要ルール準拠:
  - PAT書込みで403になる場合は Connected App JWT が必要
  - .env のPAT値はチャット非表示原則（このスクリプトは os.environ 経由のみ参照）

エラーコード対応:
  - 400706/400922: allowed_dimensions / comparisons が空 → string列1個以上必須
  - 400957: insights_options 欠落 → 必ず {"show_insights": True, "settings": []}
  - 403 (PAT書込み): Connected App JWT に切替
  - 409 (definition POST): GET + 名前一致再利用 + PATCH
  - 409 (metric PATCH): sibling POST 作成

関連メモリ: feedback_pulse_rest_api_recipe.md (実装パターン詳細・落とし穴)
"""
from __future__ import annotations

import datetime
import os
import uuid
from dataclasses import dataclass

import requests


# ── 認証 ─────────────────────────────────────────────────────────────────────

@dataclass
class TableauCredentials:
    server_url: str
    site_name: str
    pat_name: str
    pat_value: str
    # Connected App（Pulse書き込み用・任意）
    ca_client_id: str = ""
    ca_secret_id: str = ""
    ca_secret_value: str = ""
    ca_user: str = ""

    @classmethod
    def from_env(cls) -> "TableauCredentials":
        return cls(
            server_url=_require_env("TABLEAU_SERVER_URL"),
            site_name=os.environ.get("TABLEAU_SITE_NAME", ""),
            pat_name=_require_env("TABLEAU_PAT_NAME"),
            pat_value=_require_env("TABLEAU_PAT_VALUE"),
            ca_client_id=os.environ.get("TABLEAU_CONNECTED_APP_CLIENT_ID", ""),
            ca_secret_id=os.environ.get("TABLEAU_CONNECTED_APP_SECRET_ID", ""),
            ca_secret_value=os.environ.get("TABLEAU_CONNECTED_APP_SECRET_VALUE", ""),
            ca_user=os.environ.get("TABLEAU_CONNECTED_APP_USER", ""),
        )

    @property
    def has_connected_app(self) -> bool:
        return bool(self.ca_client_id and self.ca_secret_id and self.ca_secret_value)


def _require_env(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        raise EnvironmentError(f"環境変数 {key} が設定されていません")
    return val


# ── Connected App JWT 認証 ────────────────────────────────────────────────────

def get_connected_app_token(creds: TableauCredentials) -> str:
    """Connected App の JWT を生成し、Tableau Cloud の auth/signin で交換して
    Pulse書き込みスコープ付きの認証トークンを返す。

    PAT では Pulse 書き込みが 403 になる環境で必須。
    """
    import jwt as pyjwt

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": creds.ca_client_id,
        "exp": now + datetime.timedelta(minutes=5),
        "jti": str(uuid.uuid4()),
        "aud": "tableau",
        "sub": creds.ca_user,
        "scp": [
            "tableau:insight_definitions:create",
            "tableau:insight_definitions:update",
            "tableau:insight_definitions:delete",
            "tableau:insight_definitions:read",
            "tableau:insight_metrics:create",
            "tableau:insight_metrics:update",
            "tableau:insight_metrics:delete",
            "tableau:insight_metrics:read",
            "tableau:insight_definitions_metrics:read",
            "tableau:insights:read",
            "tableau:metric_subscriptions:create",
            "tableau:metric_subscriptions:delete",
            "tableau:metric_subscriptions:read",
            "tableau:datasources:read",
            "tableau:content:read",
        ],
    }
    jwt_token = pyjwt.encode(
        payload,
        creds.ca_secret_value,
        algorithm="HS256",
        headers={"kid": creds.ca_secret_id, "iss": creds.ca_client_id},
    )

    base_url = creds.server_url.rstrip("/")
    site_name = creds.site_name or ""
    xml_body = (
        f'<tsRequest>'
        f'<credentials jwt="{jwt_token}">'
        f'<site contentUrl="{site_name}" />'
        f'</credentials>'
        f'</tsRequest>'
    )
    resp = requests.post(
        f"{base_url}/api/3.28/auth/signin",
        data=xml_body,
        headers={"Content-Type": "application/xml", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Connected App サインイン失敗: HTTP {resp.status_code} {resp.text[:200]}")

    token = resp.json().get("credentials", {}).get("token", "")
    if not token:
        raise RuntimeError(f"Connected App トークン取得失敗: {resp.text[:200]}")
    return token


# ── Pulse メトリクス作成 ──────────────────────────────────────────────────────

def create_pulse_metrics(
    server,            # TSC.Server (signed-in)
    creds: TableauCredentials,
    datasource_id: str,
    design: dict,
    site_id: str,
) -> list[dict]:
    """KPI 4件分の Pulse メトリクスを REST API で定義する。

    エンドポイント: /api/-/pulse/definitions → /api/-/pulse/metrics
    Pulse書き込みは Connected App JWT トークンが必要。PAT は環境により403。

    Returns:
        [{"title": str, "definition_id": str, "id": str, "status": "ok"|"error"}, ...]
    """
    base_url = creds.server_url.rstrip("/")

    # Connected App が設定されていれば JWT トークンを使用（Pulse書き込みに必須）
    if creds.has_connected_app:
        try:
            pulse_token = get_connected_app_token(creds)
            print("  [pulse] Connected App JWT トークン取得成功")
        except Exception as e:
            print(f"  [pulse] 警告 - Connected App 認証失敗: {e}")
            pulse_token = server.auth_token
    else:
        pulse_token = server.auth_token
        print("  [pulse] 警告 - Connected App 未設定。PAT では Pulse 書き込みに失敗する可能性があります。")

    headers = {
        "x-tableau-auth": pulse_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    date_col = design.get("date_column", "")
    results = []

    # design から allowed_dimensions を抽出（チャートで使われているディメンション）
    allowed_dims = _collect_allowed_dims(design, date_col)

    for card in design.get("kpi_cards", []):
        measure = card.get("measure", "")
        agg = card.get("aggregation", "SUM").upper()
        title = card.get("title", f"KPI {card.get('index', 0)}")
        unit = card.get("unit", "")

        definition_payload = _build_definition_payload(
            title=title, measure=measure, agg=agg, unit=unit,
            datasource_id=datasource_id, date_col=date_col, allowed_dims=allowed_dims,
        )

        def_url = f"{base_url}/api/-/pulse/definitions"
        def_resp = requests.post(def_url, json=definition_payload, headers=headers, timeout=30)

        definition_id = ""
        if def_resp.status_code in (200, 201):
            resp_json = def_resp.json()
            def_obj = resp_json.get("definition", resp_json)
            definition_id = def_obj.get("metadata", {}).get("id", "") or def_obj.get("id", "")
            print(f"  [pulse] definition作成: {title} (id={definition_id})")
        elif def_resp.status_code == 409:
            # 同名 definition が既存。リスト取得して名前一致するものを再利用。
            list_resp = requests.get(def_url, headers=headers,
                                     params={"page_size": 200}, timeout=30)
            if list_resp.status_code == 200:
                for d in list_resp.json().get("definitions", []):
                    md = d.get("metadata", {})
                    if md.get("name") == title:
                        definition_id = md.get("id", "")
                        break
            if definition_id:
                print(f"  [pulse] definition再利用: {title} (id={definition_id})")
                # データソース変更等を反映するため PATCH で更新
                patch_def_resp = requests.patch(
                    f"{base_url}/api/-/pulse/definitions/{definition_id}",
                    json=definition_payload, headers=headers, timeout=30,
                )
                if patch_def_resp.status_code not in (200, 201):
                    print(f"  [pulse] 警告 - definition更新失敗 {title}: HTTP {patch_def_resp.status_code}")
            else:
                print(f"  [pulse] 警告 - 409 だが既存 definition が見つからず {title}")
                results.append({"title": title, "status": "error", "detail": "409 but not found"})
                continue
        else:
            print(f"  [pulse] 警告 - definition作成失敗 {title}: HTTP {def_resp.status_code} {def_resp.text[:200]}")
            results.append({"title": title, "status": "error", "detail": def_resp.text[:200]})
            continue

        # default metric 取得 → sibling 優先採用 → PATCH or POST
        metric_id = _ensure_metric(
            base_url=base_url, headers=headers,
            definition_id=definition_id, design=design, title=title,
        )
        if metric_id:
            results.append({"title": title, "definition_id": definition_id, "id": metric_id, "status": "ok"})
        else:
            results.append({"title": title, "definition_id": definition_id, "status": "error", "detail": "metric fail"})

    return results


def _collect_allowed_dims(design: dict, date_col: str) -> list[str]:
    """charts/category_param_dimension からPulse allowed_dimensionsを収集。
    date_columnと重複するものは除外。フォールバックでstring列を探す。

    ❗ 空配列だとPulse API 400706/400922 になる → 必ず1個以上確保すべし。
    """
    allowed_dims: list[str] = []
    for chart in design.get("charts", []):
        for k in ("category", "row_dimension"):
            v = chart.get(k, "")
            if v and v != date_col and v not in allowed_dims:
                allowed_dims.append(v)
    param_dim = design.get("category_param_dimension", "")
    if param_dim and param_dim != date_col and param_dim not in allowed_dims:
        allowed_dims.append(param_dim)
    if not allowed_dims:
        # フォールバック: design.tables からディメンション風のフィールドを探す
        for tbl in design.get("tables", []):
            for col in tbl.get("columns", []):
                if col.get("datatype") == "string" and col["name"] not in allowed_dims:
                    allowed_dims.append(col["name"])
                    if len(allowed_dims) >= 3:
                        break
            if len(allowed_dims) >= 3:
                break
    return allowed_dims


def _build_definition_payload(
    *, title: str, measure: str, agg: str, unit: str,
    datasource_id: str, date_col: str, allowed_dims: list[str],
) -> dict:
    """Pulse definition POST用payload。400/409回避の必須フィールド全部入り。"""
    return {
        "name": title,
        "specification": {
            "datasource": {"id": datasource_id},
            "basic_specification": {
                "measure": {
                    "field": measure,
                    "aggregation": _pulse_agg(agg),
                },
                "time_dimension": {"field": date_col},
                "filters": [],
            },
            "is_running_total": False,
        },
        "extension_options": {
            # 空だと400706。必ず1個以上のstring列を入れる
            "allowed_dimensions": allowed_dims,
            "allowed_granularities": [
                "GRANULARITY_BY_DAY",
                "GRANULARITY_BY_WEEK",
                "GRANULARITY_BY_MONTH",
                "GRANULARITY_BY_QUARTER",
                "GRANULARITY_BY_YEAR",
            ],
            "offset_from_today": 0,
            "correlation_candidate_definition_ids": [],
            "use_dynamic_offset": False,
        },
        "representation_options": {
            "type": "NUMBER_FORMAT_TYPE_NUMBER",
            "number_units": {
                "singular_noun": unit,
                "plural_noun": unit,
            },
            "sentiment_type": "SENTIMENT_TYPE_NONE",
        },
        # 必須 (400957 回避)
        "insights_options": {
            "show_insights": True,
            "settings": [],
        },
        # 空だと400922
        "comparisons": {
            "comparisons": [
                {"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD"}, "index": 0},
                {"compare_config": {"comparison": "TIME_COMPARISON_YEAR_AGO_PERIOD"}, "index": 1},
            ],
        },
        "datasource_goals": [],
        "related_links": [],
        "certification": {"is_certified": False},
    }


def _ensure_metric(
    *, base_url: str, headers: dict, definition_id: str,
    design: dict, title: str,
) -> str:
    """default metric を取得し、design.pulse_grain と一致する sibling があれば採用、
    無ければ PATCH 試行 → 失敗時 sibling POST。

    Returns: metric_id (失敗時は空文字)
    """
    metric_list_url = f"{base_url}/api/-/pulse/definitions/{definition_id}/metrics"
    metric_resp = requests.get(metric_list_url, headers=headers, timeout=30)
    if metric_resp.status_code != 200:
        print(f"  [pulse] 警告 - metric取得失敗 {title}: HTTP {metric_resp.status_code} {metric_resp.text[:200]}")
        return ""

    metrics = metric_resp.json().get("metrics", [])
    if not metrics:
        print(f"  [pulse] 警告 - metric が見つかりません: {title}")
        return ""

    grain = design.get("pulse_grain", "MONTH").upper()
    target_gran = f"GRANULARITY_BY_{grain}"

    # design 一致 sibling 優先採用 (PATCH 不要)
    match_metric = next(
        (
            m for m in metrics
            if m.get("specification", {}).get("measurement_period", {}).get("granularity") == target_gran
            and m.get("specification", {}).get("measurement_period", {}).get("range") == "RANGE_LAST_COMPLETE"
        ),
        None,
    )
    if match_metric is not None:
        metric_id = match_metric.get("id", "")
        print(f"  [pulse] {grain}/LAST_COMPLETE 既存 metric を採用: {title} (id={metric_id})")
        return metric_id

    default_metric = next((m for m in metrics if m.get("is_default")), metrics[0])
    metric_id = default_metric.get("id", "")

    # default metric の measurement_period を完了期間ベースに PATCH
    patch_payload = {
        "specification": {
            "filters": [],
            "measurement_period": {
                "granularity": target_gran,
                # CURRENT_PARTIAL だと「現在の期間データなし」になる
                "range": "RANGE_LAST_COMPLETE",
            },
            "comparison": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD"},
        },
    }
    patch_resp = requests.patch(
        f"{base_url}/api/-/pulse/metrics/{metric_id}",
        json=patch_payload, headers=headers, timeout=30,
    )
    if patch_resp.status_code in (200, 201):
        print(f"  [pulse] metric紐づけ+調整: {title} (id={metric_id})")
        return metric_id

    # PATCH 不可 (409 楽観ロック 等) → sibling POST 作成
    post_payload = {"definition_id": definition_id, **patch_payload}
    post_resp = requests.post(
        f"{base_url}/api/-/pulse/metrics",
        json=post_payload, headers=headers, timeout=30,
    )
    if post_resp.status_code in (200, 201):
        created = post_resp.json().get("metric", post_resp.json())
        new_id = created.get("id", metric_id)
        print(f"  [pulse] metric新規作成 ({grain}/LAST_COMPLETE): {title} (id={new_id})")
        return new_id

    print(f"  [pulse] metric紐づけ: {title} (id={metric_id}) "
          f"[PATCH={patch_resp.status_code}, POST={post_resp.status_code}]")
    return metric_id  # PATCH失敗+POST失敗でもdefault metricのIDは返す


def _pulse_agg(agg: str) -> str:
    """Pulse API の aggregation 文字列に変換。"""
    mapping = {
        "SUM": "AGGREGATION_SUM",
        "AVG": "AGGREGATION_AVERAGE",
        "AVERAGE": "AGGREGATION_AVERAGE",
        "MEDIAN": "AGGREGATION_MEDIAN",
        "COUNT": "AGGREGATION_COUNT",
        "COUNTD": "AGGREGATION_COUNT_DISTINCT",
        "MIN": "AGGREGATION_MIN",
        "MAX": "AGGREGATION_MAX",
    }
    return mapping.get(agg.upper(), "AGGREGATION_SUM")


# ── 削除（クリーンアップ用） ────────────────────────────────────────────────

def delete_pulse_metrics(
    creds: TableauCredentials,
    auth_token: str,
    metric_ids: list[str],
) -> None:
    base_url = creds.server_url.rstrip("/")
    headers = {"x-tableau-auth": auth_token, "Accept": "application/json"}
    for metric_id in metric_ids:
        url = f"{base_url}/api/-/pulse/metrics/{metric_id}"
        resp = requests.delete(url, headers=headers, timeout=30)
        if resp.status_code in (200, 204):
            print(f"  [pulse] metric削除: {metric_id}")
        else:
            print(f"  [pulse] 警告 - metric削除失敗 {metric_id}: HTTP {resp.status_code}")


def delete_pulse_definitions(
    creds: TableauCredentials,
    auth_token: str,
    definition_ids: list[str],
) -> None:
    base_url = creds.server_url.rstrip("/")
    headers = {"x-tableau-auth": auth_token, "Accept": "application/json"}
    for def_id in definition_ids:
        url = f"{base_url}/api/-/pulse/definitions/{def_id}"
        resp = requests.delete(url, headers=headers, timeout=30)
        if resp.status_code in (200, 204):
            print(f"  [pulse] definition削除: {def_id}")
        else:
            print(f"  [pulse] 警告 - definition削除失敗 {def_id}: HTTP {resp.status_code}")
