"""pulse_zone_injector.py — 既存TWBにPulseカード+AI質問ボタン+Web zoneを注入するライブラリ。

5パターン全部入り:
  1. KPI worksheet zone → Pulse zone 置換 (replace_kpi_zones)
  2. dashboard <simple-id uuid> 抽出 (extract_dashboard_uuids)
  3. AI質問ボタン + 隠しWeb zone (add_button_and_web_zone)
  4. KPI アイコン bitmap zone 除去 (remove_kpi_icon_zones)
  5. 親レイアウト fixed-size 拡大 (bump_kpi_row_layout)

元実装: SE提供の参照実装 の output/_template/apply_pulse_template.py
        (515行) を汎用化抽出。
動作確認: 2026-06-09 Phase A で city-trial-monthly_CityTrialMonthly に対し
        KPI zone 置換8件 / アイコン除去8件 / 親レイアウト拡大5件 / AIボタン2件 すべて動作。

主要関数:
  - inject_pulse_full_pipeline(twbx_path, ...): TWBX 入力→TWBX 出力の一気通貫
  - replace_kpi_zones(xml, kpi_specs, ...): 個別利用、KPI zone のみ
  - add_button_and_web_zone(xml, ...): 個別利用、AIボタンのみ

汎用化方針:
  - design.json / publish_result.json には依存しない（呼び出し側で kpi_specs として整形）
  - PULSE_ROOT は引数で渡す（.env 依存なし）
  - 全関数は XML 文字列 in/out（zip 操作は inject_pulse_full_pipeline のみ）

最重要ルール: TWB XML編集はテキスト置換のみ（ElementTree禁止）。本実装は re.sub のみ使用。
関連メモリ: feedback_twb_pulse_integration.md (実装パターン詳細・落とし穴・5パターンXML仕様)
"""
from __future__ import annotations

import re
import urllib.parse
import uuid
import zipfile
from pathlib import Path

# ── 定数 ──────────────────────────────────────────────────────────────────────

PULSE_ZONE_FIXED_SIZE = 200
PULSE_ZONE_H = 23000
PULSE_ROW_FIXED_SIZE = 220    # horz 親 = 子の高さ
PULSE_COL_FIXED_SIZE = 358    # vert 親 = 子の幅（Superstore 参考値）
PULSE_PARENT_H = 25000

DEFAULT_KPI_ICON_FILENAMES = ("wheelbarrow.png", "gold-ingots.png", "offer.png", "low-price.png")

DISCOVER_QUERY_DEFAULT = "前期間と比較すると、先月に何がありましたか?"


# ── 補助: zone block balance 探索 ────────────────────────────────────────────

def find_balanced_zone(xml: str, start_idx: int) -> tuple[int, int]:
    """start_idx で始まる <zone> タグから対応する </zone> までの (start, end) を返す。
    end は </zone> 直後の位置。失敗時 end=-1。"""
    depth = 0
    pos = start_idx
    while pos < len(xml):
        tm = re.search(r"<(/?)zone\b", xml[pos:])
        if not tm:
            break
        ap = pos + tm.start()
        if tm.group(1) == '':
            depth += 1
            pos = xml.find('>', ap) + 1
        else:
            depth -= 1
            pos = xml.find('>', ap) + 1
            if depth == 0:
                return start_idx, pos
    return start_idx, -1


def _ancestors(xml: str, target_idx: int) -> list[tuple[int, int]]:
    """target_idx を含む zone の開始タグ位置リスト（外側から内側順、(start, end_gt) のtuple）。"""
    stack: list[tuple[int, int]] = []
    pos = 0
    while pos < target_idx:
        m = re.search(r"<(/?)zone\b", xml[pos:target_idx])
        if not m:
            break
        ap = pos + m.start()
        end_gt = xml.find('>', ap)
        if m.group(1) == '':
            stack.append((ap, end_gt))
        else:
            if stack:
                stack.pop()
        pos = end_gt + 1
    return stack


# ── パターン1: KPI worksheet zone → Pulse zone 置換 ───────────────────────────

def build_pulse_zone(
    *, zone_id: str, x: int, y: int, w: int, h: int,
    datasource_name: str, measure: str, time_dim: str,
    metric_id: str, definition_id: str, instance_id: str,
    pulse_root: str,
    fixed_size: int | None = None,
) -> str:
    """Pulse 拡張 zone の XML 文字列を組み立てる。"""
    fixed_attr = f"fixed-size='{fixed_size}' " if fixed_size is not None else ""
    is_fixed_attr = "is-fixed='true' " if fixed_size is not None else ""
    return (
        f"<zone {fixed_attr}forceUpdate='true' h='{h}' id='{zone_id}' {is_fixed_attr}"
        f"param='[com.tableau.pulse-metric].[0.100.0].[tableau:/pulse/extension-assets/dashboard-metric/index.html]' "
        f"type-v2='dashboard-object' w='{w}' x='{x}' y='{y}'>"
        f"<add-in add-in-id='com.tableau.pulse-metric' "
        f"extension-url='tableau:/pulse/extension-assets/dashboard-metric/index.html' "
        f"extension-version='0.100.0' instance-id='{instance_id}'>"
        f"<instance-settings>"
        f"<setting key='DATASOURCE_NAME' value='{datasource_name}' />"
        f"<setting key='ENABLE_LINK' value='false' />"
        f"<setting key='MEASURE_FIELD' value='{measure}' />"
        f"<setting key='METRIC_DEFINITION_ID' value='{definition_id}' />"
        f"<setting key='METRIC_ID' value='{metric_id}' />"
        f"<setting key='PULSE_ROOT' value='{pulse_root}' />"
        f"<setting key='SQUARE_CORNERS' value='false' />"
        f"<setting key='SYSTEM_TOOLTIP_TEXT' value='先月' />"
        f"<setting key='TIME_DIMENSION_FIELD' value='{time_dim}' />"
        f"<setting key='USE_DASHBOARD_FILTERS' value='true' />"
        f"<setting key='USE_FULL_CARD' value='false' />"
        f"<setting key='has_been_configured' value='true' />"
        f"<setting key='has_been_initialized' value='true' />"
        f"</instance-settings>"
        f"<type-settings><dashboard /></type-settings>"
        f"</add-in>"
        f"<zone-style>"
        f"<format attr='border-color' value='#000000' />"
        f"<format attr='border-style' value='none' />"
        f"<format attr='border-width' value='0' />"
        f"<format attr='margin' value='4' />"
        f"</zone-style>"
        f"</zone>"
    )


def replace_kpi_zones(
    xml: str,
    kpi_specs: list[dict],
    datasource_name: str,
    pulse_root: str,
    *,
    starting_zone_id: int = 9000,
    zone_name_suffix: str = "(カード)",
) -> tuple[str, int]:
    """name='<title>{suffix}' の KPI zone を Pulse zone に置換。

    kpi_specs: [{"title": str, "measure": str, "time_dim": str,
                 "metric_id": str, "definition_id": str}, ...]
    """
    title_to_spec = {spec["title"]: spec for spec in kpi_specs}
    n_patched = 0
    next_id = starting_zone_id

    # 後ろから処理して位置ズレを避ける
    suffix_escaped = re.escape(zone_name_suffix)
    pattern = rf"<zone\s+([^>]*?)\sname='([^']+{suffix_escaped}[^']*)'([^>]*)>"
    matches = list(re.finditer(pattern, xml))
    matches.sort(key=lambda m: -m.start())

    for m in matches:
        zone_name = m.group(2).rstrip()
        title = zone_name.removesuffix(zone_name_suffix).rstrip()
        spec = title_to_spec.get(title)
        if not spec:
            continue

        attrs = m.group(1) + " " + (m.group(3) or "")
        x_m = re.search(r"\bx='(\d+)'", attrs)
        y_m = re.search(r"\by='(\d+)'", attrs)
        w_m = re.search(r"\bw='(\d+)'", attrs)
        h_m = re.search(r"\bh='(\d+)'", attrs)
        if not (x_m and y_m and w_m and h_m):
            continue
        x = int(x_m.group(1))
        y = int(y_m.group(1))
        w = int(w_m.group(1))
        h = int(h_m.group(1))

        zone_start = m.start()
        _, zone_end = find_balanced_zone(xml, zone_start)
        if zone_end < 0:
            continue

        new_h = max(h, PULSE_ZONE_H)
        next_id += 1
        instance_id = uuid.uuid4().hex.upper()
        new_zone = build_pulse_zone(
            zone_id=str(next_id), x=x, y=y, w=w, h=new_h,
            datasource_name=datasource_name,
            measure=spec["measure"],
            time_dim=spec.get("time_dim", ""),
            metric_id=spec["metric_id"],
            definition_id=spec["definition_id"],
            instance_id=instance_id,
            pulse_root=pulse_root,
            fixed_size=PULSE_ZONE_FIXED_SIZE,
        )
        xml = xml[:zone_start] + new_zone + xml[zone_end:]
        n_patched += 1

    return xml, n_patched


# ── パターン2: dashboard <simple-id uuid> 抽出 ────────────────────────────────

def extract_dashboard_uuids(xml: str) -> list[str]:
    """<window class='dashboard' ...> 内の <simple-id uuid='{...}'/> を順に返す。
    toggle-action の window-id はこの uuid と一致必須。"""
    uuids: list[str] = []
    for m in re.finditer(r"<window\s+class='dashboard'[^>]*>", xml):
        pos = m.end()
        depth = 1
        while depth > 0 and pos < len(xml):
            nm = re.search(r"<(/?)window\b", xml[pos:])
            if not nm:
                break
            ap = pos + nm.start()
            if nm.group(1) == '':
                depth += 1
            else:
                depth -= 1
            pos = xml.find('>', ap) + 1
        inner = xml[m.start():pos]
        sm = re.search(r"<simple-id\s+uuid='\{([0-9A-F-]+)\}'\s*/>", inner)
        if sm:
            uuids.append(sm.group(1))
    return uuids


# ── パターン3: AI質問ボタン + 隠しWeb zone ────────────────────────────────────

def build_web_zone(
    *, zone_id: str, discover_url: str, x: int, y: int, w: int, h: int,
    fixed_size: int | None, hidden: bool,
) -> str:
    fixed_attr = f"fixed-size='{fixed_size}' " if fixed_size is not None else ""
    is_fixed_attr = "is-fixed='true' " if fixed_size is not None else ""
    hidden_attr = "hidden-by-user='true' " if hidden else ""
    return (
        f"<zone {fixed_attr}forceUpdate='' h='{h}' {hidden_attr}id='{zone_id}' {is_fixed_attr}"
        f"param='{discover_url}' type-v2='web' w='{w}' x='{x}' y='{y}'>"
        f"<zone-style>"
        f"<format attr='border-color' value='#000000' />"
        f"<format attr='border-style' value='none' />"
        f"<format attr='border-width' value='0' />"
        f"<format attr='margin' value='4' />"
        f"</zone-style>"
        f"</zone>"
    )


def build_button_zone(
    *, zone_id: str, target_zone_id: str, window_id: str,
    x: int, y: int, w: int, h: int,
    image_path: str = "Image/agent.png",
) -> str:
    """agent.png ボタン zone。クリックで target_zone_id (Web zone) を toggle 表示。"""
    toggle = (
        f"tabdoc:toggle-button-click-action "
        f"window-id=&quot;{{{window_id}}}&quot; "
        f"zone-id=&quot;{zone_id}&quot; zone-ids=[{target_zone_id}]"
    )
    return (
        f"<zone h='{h}' id='{zone_id}' type-v2='dashboard-object' w='{w}' x='{x}' y='{y}'>"
        f"<button action='' active-visual-state-index='1'>"
        f"<toggle-action>{toggle}</toggle-action>"
        f"<button-visual-state><image-path>{image_path}</image-path></button-visual-state>"
        f"<button-visual-state><image-path>{image_path}</image-path></button-visual-state>"
        f"</button>"
        f"</zone>"
    )


def add_button_and_web_zone(
    xml: str,
    all_metric_ids: list[str],
    datasource_name: str,
    pulse_root: str,
    *,
    discover_query: str = DISCOVER_QUERY_DEFAULT,
    starting_id: int = 9100,
    button_image_path: str = "Image/agent.png",
    # Pulse zone デフォルト位置（必要に応じてオーバーライド）
    web_zone_pos: tuple[int, int, int, int] = (13152, 112, 36364, 99776),
    button_zone_pos: tuple[int, int, int, int] = (4121, 42634, 3939, 6473),
) -> tuple[str, int]:
    """ダッシュボード末尾と device-layout 末尾に AI 質問ボタンと隠し Web zone を追加。"""
    encoded_prefix = urllib.parse.quote(datasource_name, safe="")
    encoded_query = urllib.parse.quote(discover_query)
    metric_ids_qs = "&amp;".join(f"metric_ids={mid}" for mid in all_metric_ids)
    discover_url = (
        pulse_root.rstrip("/") + "/discover"
        f"?{metric_ids_qs}"
        f"&amp;discover_query={encoded_query}"
        f"&amp;entry_point=homepage_hook"
        f"&amp;prefix={encoded_prefix}"
    )

    dashboard_uuids = extract_dashboard_uuids(xml)
    if not dashboard_uuids:
        return xml, 0

    next_id = starting_id
    n_added = 0
    insertions: list[tuple[int, str]] = []

    dashboard_zones_close = [m.start() for m in re.finditer(r"</zones>", xml)]
    if not dashboard_zones_close:
        return xml, 0

    web_x, web_y, web_w, web_h = web_zone_pos
    btn_x, btn_y, btn_w, btn_h = button_zone_pos

    # dashboard 用 (最初の </zones>)
    dashboard_window_id = dashboard_uuids[0]
    web_id = next_id; next_id += 1
    btn_id = next_id; next_id += 1
    web_zone = build_web_zone(
        zone_id=str(web_id), discover_url=discover_url,
        x=web_x, y=web_y, w=web_w, h=web_h, fixed_size=None, hidden=True,
    )
    button_zone = build_button_zone(
        zone_id=str(btn_id), target_zone_id=str(web_id),
        window_id=dashboard_window_id, x=btn_x, y=btn_y, w=btn_w, h=btn_h,
        image_path=button_image_path,
    )
    insertions.append((dashboard_zones_close[0], web_zone + button_zone))
    n_added += 1

    # device-layout (Phone) 用 (2番目の </zones> があれば)
    if len(dashboard_zones_close) >= 2:
        phone_window_id = dashboard_uuids[1] if len(dashboard_uuids) >= 2 else dashboard_window_id
        web_id2 = next_id; next_id += 1
        btn_id2 = next_id; next_id += 1
        web_zone2 = build_web_zone(
            zone_id=str(web_id2), discover_url=discover_url,
            x=web_x, y=web_y, w=web_w, h=web_h, fixed_size=280, hidden=True,
        )
        button_zone2 = build_button_zone(
            zone_id=str(btn_id2), target_zone_id=str(web_id2),
            window_id=phone_window_id, x=btn_x, y=btn_y, w=btn_w, h=btn_h,
            image_path=button_image_path,
        )
        insertions.append((dashboard_zones_close[1], web_zone2 + button_zone2))
        n_added += 1

    # 後ろから挿入してずれを防ぐ
    for pos, snippet in reversed(insertions):
        xml = xml[:pos] + snippet + xml[pos:]

    return xml, n_added


# ── パターン4: KPI アイコン除去 ──────────────────────────────────────────────

def remove_kpi_icon_zones(
    xml: str,
    icon_filenames: tuple[str, ...] = DEFAULT_KPI_ICON_FILENAMES,
) -> tuple[str, int]:
    """指定 KPI アイコン bitmap zone を削除。dashboard / device-layout 両方から消える。"""
    n = 0
    for icon in icon_filenames:
        pat = re.compile(
            rf"<zone\b[^>]*param='Image/{re.escape(icon)}'[^>]*type-v2='bitmap'[^>]*>"
        )
        matches = list(pat.finditer(xml))
        for m in reversed(matches):
            _, end = find_balanced_zone(xml, m.start())
            if end < 0:
                continue
            xml = xml[:m.start()] + xml[end:]
            n += 1
    return xml, n


# ── パターン5: 親レイアウト fixed-size 拡大 ──────────────────────────────────

def bump_kpi_row_layout(
    xml: str,
    *,
    parent_h: int = PULSE_PARENT_H,
    row_fixed_size: int = PULSE_ROW_FIXED_SIZE,
    col_fixed_size: int = PULSE_COL_FIXED_SIZE,
) -> tuple[str, int]:
    """Pulse zone を含む親階層 (KPI 行/列) の h と fixed-size を拡大して見切れを防ぐ。

    horz 親 (KPI 行) は子の高さを決める → row_fixed_size
    vert 親 (KPI 列) は子の幅を決める → col_fixed_size
    """
    pulse_positions = [
        m.start() for m in re.finditer(r"<zone\b[^>]*param='\[com\.tableau\.pulse-metric\]", xml)
    ]
    seen: set[int] = set()
    bump_targets: list[tuple[int, int]] = []

    for p in pulse_positions:
        for s, e in _ancestors(xml, p):
            if s in seen:
                continue
            seen.add(s)
            attrs = xml[s:e + 1]
            if not re.search(r"type-v2='(layout-flow|layout-basic)'", attrs):
                continue
            h_m = re.search(r"\bh='(\d+)'", attrs)
            if not h_m:
                continue
            cur_h = int(h_m.group(1))
            if cur_h >= parent_h:
                continue
            bump_targets.append((s, e))

    # 後ろから書き換え
    bump_targets.sort(key=lambda x: -x[0])
    n = 0
    for s, e in bump_targets:
        attrs = xml[s:e + 1]
        new_attrs = re.sub(r"\bh='\d+'", f"h='{parent_h}'", attrs)
        is_vert_column = "param='vert'" in attrs
        target_fs = col_fixed_size if is_vert_column else row_fixed_size
        if re.search(r"\bfixed-size='\d+'", new_attrs):
            new_attrs = re.sub(r"\bfixed-size='\d+'", f"fixed-size='{target_fs}'", new_attrs)
        elif is_vert_column:
            new_attrs = new_attrs[:-1].rstrip() + (
                f" fixed-size='{target_fs}' is-fixed='true'" + new_attrs[-1]
            )
        xml = xml[:s] + new_attrs + xml[e + 1:]
        n += 1

    return xml, n


# ── 一気通貫: TWBX → TWBX ────────────────────────────────────────────────────

def inject_pulse_full_pipeline(
    src_twbx: Path,
    dst_twbx: Path,
    *,
    kpi_specs: list[dict],
    all_metric_ids: list[str],
    datasource_name: str,
    pulse_root: str,
    extra_assets: dict[str, bytes] | None = None,
    icon_filenames: tuple[str, ...] = DEFAULT_KPI_ICON_FILENAMES,
    zone_name_suffix: str = "(カード)",
    discover_query: str = DISCOVER_QUERY_DEFAULT,
) -> dict:
    """src_twbx を読み込み 5パターン適用して dst_twbx に出力。
    extra_assets で Image/agent.png 等を同梱可能（{arcname: bytes}）。

    Returns: {"kpi_replaced": int, "icon_removed": int, "layout_bumped": int, "button_added": int}
    """
    with zipfile.ZipFile(src_twbx, "r") as zin:
        names = zin.namelist()
        twb_name = next(n for n in names if n.endswith(".twb"))
        twb_xml = zin.read(twb_name).decode("utf-8")
        other_files = {n: zin.read(n) for n in names if n != twb_name}

    if extra_assets:
        for arcname, data in extra_assets.items():
            if arcname not in other_files:
                other_files[arcname] = data

    twb_xml, n_kpi = replace_kpi_zones(
        twb_xml, kpi_specs, datasource_name, pulse_root,
        zone_name_suffix=zone_name_suffix,
    )
    twb_xml, n_icon = remove_kpi_icon_zones(twb_xml, icon_filenames)
    twb_xml, n_layout = bump_kpi_row_layout(twb_xml)
    twb_xml, n_btn = add_button_and_web_zone(
        twb_xml, all_metric_ids, datasource_name, pulse_root,
        discover_query=discover_query,
    )

    dst_twbx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst_twbx, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr(twb_name, twb_xml.encode("utf-8"))
        for n, data in other_files.items():
            zout.writestr(n, data)

    return {
        "kpi_replaced": n_kpi,
        "icon_removed": n_icon,
        "layout_bumped": n_layout,
        "button_added": n_btn,
    }
