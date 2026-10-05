"""
twb-generator: dashboard zone helpers (filter / color legend / size legend / shape legend)

Tableau dashboard XMLで filter zone / legend zone を表示するには 3点必須:
  1. pane-specification-id='0' 属性
  2. open/close tag (自閉じ <zone .../> ではなく <zone>...</zone>)
  3. param='[<ds_ref>].[<column-instance>]' 形式 (シンプルな [日付] では Cloud 側で無視される)

参考: shared/memory/feedback_twb_filter_legend_zone_xml.md（リポジトリ直下基準）

Usage:
    from dashboard_zone_helpers import make_filter_zone, make_color_legend_zone, field_ref

    filter_xml = make_filter_zone(
        field=field_ref("daily", "日付"),  # → "[federated.ds_daily].[none:日付:nk]"
        src_sheet="日別セッション推移",
        x=80000, y=11500, w=19500, h=87000,
        zone_id=70,
    )

    legend_xml = make_color_legend_zone(
        field=field_ref("daily", "曜日"),
        src_sheet="曜日別 平均セッション",
        x=500, y=7500, w=99000, h=4000,
        zone_id=80,
    )

    # または生フィールド参照を渡す
    legend_xml = make_color_legend_zone(
        field="[federated.ds_pages].[none:ページタイトル:nk]",
        src_sheet="ページ品質象限",
        x=500, y=7500, w=99000, h=4000,
    )
"""
from typing import Literal


# 型コード → column-instance derivation prefix のマップ
# string列(dimension)→ none:nk / integer,real(measure)→ sum:qk または avg:qk / date(dimension)→ none:nk
DERIVATION_MAP = {
    ("string", "dimension"): ("none", "nk"),
    ("string", "measure"): ("count", "qk"),  # 文字列をCount集約
    ("integer", "dimension"): ("none", "ok"),  # ordinal-key
    ("integer", "measure"): ("sum", "qk"),
    ("real", "dimension"): ("none", "ok"),
    ("real", "measure"): ("sum", "qk"),
    ("date", "dimension"): ("none", "nk"),
    ("date", "measure"): ("none", "nk"),
}


def column_instance(col_name: str, dtype: str = "string", role: str = "dimension",
                    aggregation: str = "") -> str:
    """column-instance ID形式を生成。
    例:  column_instance("日付", "string", "dimension") → "[none:日付:nk]"
         column_instance("セッション", "integer", "measure") → "[sum:セッション:qk]"
         column_instance("直帰率", "real", "measure", aggregation="avg") → "[avg:直帰率:qk]"
    """
    if aggregation:
        # ユーザー指定の集約 (avg, min, max等) を優先
        suffix = "qk"
        return f"[{aggregation.lower()}:{col_name}:{suffix}]"
    prefix, suffix = DERIVATION_MAP.get((dtype, role), ("none", "nk"))
    return f"[{prefix}:{col_name}:{suffix}]"


def field_ref(ds_key: str, col_name: str, dtype: str = "string",
              role: str = "dimension", aggregation: str = "",
              ds_prefix: str = "federated.ds_") -> str:
    """pref-demo構造の field参照を生成。
    例:  field_ref("daily", "日付") → "[federated.ds_daily].[none:日付:nk]"
         field_ref("channel", "セッション", "integer", "measure") → "[federated.ds_channel].[sum:セッション:qk]"

    ds_prefix を変更すれば他の datasource命名規則にも対応可。
    """
    inst = column_instance(col_name, dtype, role, aggregation)
    return f"[{ds_prefix}{ds_key}].{inst}"


def _zone_style(bg: str = "#ffffff", border: str = "#cccccc") -> str:
    return (
        "          <zone-style>\n"
        f"            <format attr='background-color' value='{bg}' />\n"
        f"            <format attr='border-color' value='{border}' />\n"
        "          </zone-style>\n"
    )


def make_filter_zone(field: str, src_sheet: str, x: int, y: int, w: int, h: int,
                     zone_id: int = 70, bg_color: str = "#ffffff",
                     border_color: str = "#cccccc") -> str:
    """Quick filter zone XML を生成 (3点必須要素を満たす)。

    Args:
        field: '[<ds_ref>].[<column-instance>]' 形式の field参照 (field_ref() で生成推奨)
        src_sheet: 対象 worksheet名 (実worksheet名と完全一致必須・括弧含む全角文字含む)
        x, y, w, h: zone座標 (1000分率, 0-100000)
        zone_id: zone XML id (dashboard内ユニーク。慣例: filter=70台、legend=80台)
        bg_color, border_color: zone-style背景/枠色

    Returns:
        XMLスニペット (改行含む文字列)
    """
    return (
        f"        <zone h='{h}' id='{zone_id}' w='{w}' x='{x}' y='{y}' "
        f"name='{src_sheet}' param='{field}' type-v2='filter' "
        f"pane-specification-id='0'>\n"
        f"{_zone_style(bg_color, border_color)}"
        f"        </zone>\n"
    )


def make_legend_zone(field: str, src_sheet: str, x: int, y: int, w: int, h: int,
                     ltype: Literal["color", "size", "shape"] = "color",
                     zone_id: int = 80, bg_color: str = "#ffffff",
                     border_color: str = "#cccccc") -> str:
    """Legend zone XML を生成 (color/size/shape 凡例)。

    NOTE: legend zoneの source worksheet は **categorical encoding** を持つworksheetを指定。
          gradient encoding (例: color column='[avg:直帰率:qk]') を持つworksheetを指定すると
          gradient凡例になり期待と異なる表示になる。

    Args:
        field: '[<ds_ref>].[<column-instance>]' 形式の field参照
        src_sheet: 対象 worksheet名
        x, y, w, h: zone座標 (1000分率)
        ltype: 'color' | 'size' | 'shape'
        zone_id: zone XML id
    """
    return (
        f"        <zone h='{h}' id='{zone_id}' w='{w}' x='{x}' y='{y}' "
        f"name='{src_sheet}' param='{field}' type-v2='{ltype}' "
        f"pane-specification-id='0'>\n"
        f"{_zone_style(bg_color, border_color)}"
        f"        </zone>\n"
    )


# 互換用エイリアス
make_color_legend_zone = lambda field, src_sheet, x, y, w, h, zone_id=80, **kw: \
    make_legend_zone(field, src_sheet, x, y, w, h, "color", zone_id, **kw)
make_size_legend_zone = lambda field, src_sheet, x, y, w, h, zone_id=81, **kw: \
    make_legend_zone(field, src_sheet, x, y, w, h, "size", zone_id, **kw)
make_shape_legend_zone = lambda field, src_sheet, x, y, w, h, zone_id=82, **kw: \
    make_legend_zone(field, src_sheet, x, y, w, h, "shape", zone_id, **kw)


# ============================================================
# 推奨レイアウト プリセット
# ============================================================
# 1400x900 dashboard (sizing-mode='fixed') 前提

LAYOUT_TOP_FULLWIDTH_LEGEND = {
    "title":    {"y": 0,     "h": 5000},   # title bar
    "subtitle": {"y": 5000,  "h": 2500},   # 操作ガイド短文 (extra_text_zones経由)
    "legend":   {"x": 500, "y": 7500, "w": 99000, "h": 4000},  # 上部 full-width 色凡例
    "worksheets_y_start": 11500,
}

LAYOUT_RIGHT_SIDEBAR_FILTER = {
    "filter":   {"x": 80000, "y": 11500, "w": 19500, "h": 87000},  # 右サイドバー縦長
    "worksheets_x_max_width": 79000,  # x=500 → x+w=79500 まで利用可能
}


def top_legend_preset(field: str, src_sheet: str, ltype: str = "color") -> str:
    """上部 full-width legend のショートカット。
    Args:
        field: '[<ds_ref>].[<column-instance>]' field参照
        src_sheet: source worksheet名
        ltype: 'color' | 'size' | 'shape'
    """
    p = LAYOUT_TOP_FULLWIDTH_LEGEND["legend"]
    return make_legend_zone(field, src_sheet, p["x"], p["y"], p["w"], p["h"], ltype=ltype)


def right_sidebar_filter_preset(field: str, src_sheet: str) -> str:
    """右サイドバー縦長 filter のショートカット。
    worksheet zones は x=500-79500 (w=79000) に縮める前提。
    """
    p = LAYOUT_RIGHT_SIDEBAR_FILTER["filter"]
    return make_filter_zone(field, src_sheet, p["x"], p["y"], p["w"], p["h"])
