---
name: twb-pulse-5-kpi-zone-ai-uuid
description: 既存TWBダッシュボードに Pulse カード+AI質問ボタン+Web zoneを統合する5パターンの完全実装。dashboard UUID 抽出/KPI worksheet zone→Pulse zone置換/AIボタン+toggle-action/隠しWeb zone追加/KPIアイコン除去/親レイアウト fixed-size 拡大。参照実装 apply_pulse_template.py から抽出
metadata: 
  node_type: memory
  type: feedback
---

既存TWBダッシュボード（KPI 4枚 + Chart 4枚等）に Pulse 統合する5パターンの完全実装。参照実装版 `output/_template/apply_pulse_template.py` (515行) を体系化。私の `.claude/skills/twb-cloud-dl-xml-inject/sqlproxy_rewriter.py` と併用すれば、新規生成TWB の最終段で Pulse 化が完結する。

**Why:**
2026-04-15 city_usage Pulse統合で5回方式転換した経緯（旧メモリ）+ 2026-06-08 参照実装版 apply_pulse_template.py の完成版実装で **5パターン全部入り** が判明。toggle-action 単独メモリだったが、KPI zone置換ロジック・dashboard UUID抽出・親レイアウト fixed-size 非対称仕様まで含めて完全ガイド化。

**How to apply:**

## パターン1: KPI worksheet zone → Pulse zone 置換

### 検出パターン

既存テンプレで KPI を worksheet 化している場合、zone name は `'<title>(カード)'` 形式が多い:
```xml
<zone w='10000' h='5000' id='1234' name='月間アクセス(カード)' ...>
```

### 置換後 (Pulse 拡張 zone)

```xml
<zone fixed-size='200' forceUpdate='true' h='23000' id='9004' is-fixed='true'
      param='[com.tableau.pulse-metric].[0.100.0].[tableau:/pulse/extension-assets/dashboard-metric/index.html]'
      type-v2='dashboard-object' w='9999' x='18148' y='10380'>
  <add-in add-in-id='com.tableau.pulse-metric'
          extension-url='tableau:/pulse/extension-assets/dashboard-metric/index.html'
          extension-version='0.100.0' instance-id='{UUID大文字HEX32字}'>
    <instance-settings>
      <setting key='DATASOURCE_NAME' value='{datasource_name}' />
      <setting key='ENABLE_LINK' value='false' />
      <setting key='MEASURE_FIELD' value='{measure列名}' />
      <setting key='METRIC_DEFINITION_ID' value='{Pulse definition UUID}' />
      <setting key='METRIC_ID' value='{Pulse metric UUID}' />
      <setting key='PULSE_ROOT' value='https://{server}/pulse/site/{site}/' />
      <setting key='SQUARE_CORNERS' value='false' />
      <setting key='SYSTEM_TOOLTIP_TEXT' value='先月' />
      <setting key='TIME_DIMENSION_FIELD' value='{date_column}' />
      <setting key='USE_DASHBOARD_FILTERS' value='true' />
      <setting key='USE_FULL_CARD' value='false' />
      <setting key='has_been_configured' value='true' />
      <setting key='has_been_initialized' value='true' />
    </instance-settings>
    <type-settings><dashboard /></type-settings>
  </add-in>
  <zone-style>
    <format attr='border-color' value='#000000' />
    <format attr='border-style' value='none' />
    <format attr='border-width' value='0' />
    <format attr='margin' value='4' />
  </zone-style>
</zone>
```

### 必須属性

- `param` の左側固定文字列: `[com.tableau.pulse-metric].[0.100.0].[tableau:/pulse/extension-assets/dashboard-metric/index.html]`
- `extension-version` = `'0.100.0'`
- `instance-id` = `uuid.uuid4().hex.upper()` (32字大文字)
- `h='23000'` 以上（見切れ防止）
- `fixed-size='200'` + `is-fixed='true'`

### 既存zoneからの引き継ぎ
- `x`, `y` はそのまま継承（位置維持）
- `w` も基本そのまま、`h` だけ最大化（`max(h, 23000)`）
- 既存 `fixed-size` 属性があれば値を 200 で上書き

### 実装 (regex で zone block balance 探索)

```python
# 後ろから処理して位置ズレ回避
matches = list(re.finditer(r"<zone\s+([^>]*?)\sname='([^']+\(カード\)[^']*)'([^>]*)>", xml))
matches.sort(key=lambda m: -m.start())
for m in matches:
    zone_name = m.group(2).rstrip()  # 末尾スペース除去
    title = zone_name.removesuffix("(カード)").rstrip()
    # title → KPI title → metric_id 解決
    # _find_balanced_zone(xml, m.start()) で対応 </zone> を探して全置換
```

`_find_balanced_zone` は `<zone>`/`</zone>` のネスト数を数えて対応 close を返す関数（要実装）。

## パターン2: dashboard `<simple-id uuid>` 抽出

### 必要性

toggle-action の `window-id` は **dashboard window の `<simple-id uuid>` と一致必須**（既存メモリ通り）。これを取得する関数。

### 実装

```python
def _extract_dashboard_uuids(xml: str) -> list[str]:
    """<window class='dashboard' ...> 内の <simple-id uuid='{...}'/> を順に返す。"""
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
```

dashboards 複数あれば順番に並ぶ。Phone layout 用は2番目以降（無ければ1番目を流用）。

## パターン3: AI質問ボタン + 隠しWeb zone

### toggle-action 構造 (既存メモリと同じ)

```xml
<zone h='6473' id='9101' type-v2='dashboard-object' w='3939' x='4121' y='42634'>
  <button action='' active-visual-state-index='1'>
    <toggle-action>tabdoc:toggle-button-click-action
      window-id=&quot;{DASHBOARD_UUID}&quot;
      zone-id=&quot;9101&quot;
      zone-ids=[9100]</toggle-action>
    <button-visual-state><image-path>Image/agent.png</image-path></button-visual-state>
    <button-visual-state><image-path>Image/agent.png</image-path></button-visual-state>
  </button>
</zone>
```

### 隠しWeb zone

```xml
<zone forceUpdate='' h='99776' hidden-by-user='true' id='9100'
      param='{PULSE_DISCOVER_URL}' type-v2='web' w='36364' x='13152' y='112'>
  <zone-style>...</zone-style>
</zone>
```

### Pulse Discover URL の組み立て

```python
import urllib.parse
PULSE_ROOT = f"{server_url}/pulse/site/{site}/"
encoded_prefix = urllib.parse.quote(datasource_name, safe="")
metric_ids_qs = "&amp;".join(f"metric_ids={mid}" for mid in all_metric_ids)
discover_url = (
    PULSE_ROOT + "discover"
    f"?{metric_ids_qs}"
    f"&amp;discover_query={urllib.parse.quote('前期間と比較すると、先月に何がありましたか?')}"
    f"&amp;entry_point=homepage_hook"
    f"&amp;prefix={encoded_prefix}"
)
```

`&amp;` (HTML エンコード) で結合する点に注意（XML 属性内になるため）。

### 挿入位置

dashboard と device-layout (Phone) の両方の `</zones>` 直前に挿入。Phone 用も別 zone_id で同じ window-id を使う。

## パターン4: KPI アイコン除去

### 検出パターン

generate_icons.py で自動生成された KPI ミニアイコン bitmap zone:
```xml
<zone w='3000' h='3000' id='1111' param='Image/wheelbarrow.png' type-v2='bitmap' ...>
```

Pulse カード化後はミニアイコンが視覚ノイズ → zone ごと削除。

### 削除対象固定リスト

```python
KPI_ICON_FILENAMES = ("wheelbarrow.png", "gold-ingots.png", "offer.png", "low-price.png")
```

### 実装

```python
for icon in KPI_ICON_FILENAMES:
    pat = re.compile(rf"<zone\b[^>]*param='Image/{re.escape(icon)}'[^>]*type-v2='bitmap'[^>]*>")
    matches = list(pat.finditer(xml))
    for m in reversed(matches):
        _, end = _find_balanced_zone(xml, m.start())
        if end > 0:
            xml = xml[:m.start()] + xml[end:]
```

dashboard と device-layout (Phone) の両方から消える（zone は両方の `<zones>` 配下に複製されている）。

## パターン5: 親レイアウト fixed-size 拡大（**横/縦で意味が逆**）

### 非対称仕様 (最重要)

Tableau の `<zone type-v2='layout-flow' param='horz|vert'>` の `fixed-size` 属性は **horz/vert で意味が逆**:

| 親 layout の param | fixed-size の意味 | Pulse カード推奨値 |
|---|---|---|
| `param='horz'` (KPI 行) | **子の高さ (px)** | `220` (Pulse カード高さ) |
| `param='vert'` (KPI 列) | **子の幅 (px)** | `358` (Superstore 参考値、これ未満で文字見切れ) |

### Pulse zone の祖先layout-flow/layout-basic を辿って拡大

```python
PULSE_ROW_FIXED_SIZE = 220   # horz 親
PULSE_COL_FIXED_SIZE = 358   # vert 親
PULSE_PARENT_H = 25000

def _bump_kpi_row_layout(xml: str) -> tuple[str, int]:
    # Pulse zone の位置を列挙
    pulse_positions = [m.start() for m in re.finditer(
        r"<zone\b[^>]*param='\[com\.tableau\.pulse-metric\]", xml
    )]
    seen = set()
    bump_targets = []
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
            if cur_h >= PULSE_PARENT_H:
                continue
            bump_targets.append((s, e))

    # 後ろから書き換え（位置ズレ回避）
    for s, e in sorted(bump_targets, key=lambda x: -x[0]):
        attrs = xml[s:e + 1]
        new_attrs = re.sub(r"\bh='\d+'", f"h='{PULSE_PARENT_H}'", attrs)
        is_vert = "param='vert'" in attrs
        target_fs = PULSE_COL_FIXED_SIZE if is_vert else PULSE_ROW_FIXED_SIZE
        if re.search(r"\bfixed-size='\d+'", new_attrs):
            new_attrs = re.sub(r"\bfixed-size='\d+'", f"fixed-size='{target_fs}'", new_attrs)
        elif is_vert:
            # 末尾の > 直前に fixed-size + is-fixed 追加
            new_attrs = new_attrs[:-1].rstrip() + (
                f" fixed-size='{target_fs}' is-fixed='true'" + new_attrs[-1]
            )
        xml = xml[:s] + new_attrs + xml[e + 1:]
```

`_ancestors(xml, idx)` は target_idx を含む全 zone 開始タグ位置を外側から内側順に返す関数（zone stack 走査）。

## 全体実行順序

1. `_replace_kpi_zones(xml, design, publish_result, datasource_name)`
2. `_remove_kpi_icon_zones(xml)`
3. `_bump_kpi_row_layout(xml)`
4. `_add_button_and_web_zone(xml, all_metric_ids, datasource_name)`

各ステップで「置換件数」を return → ログ出力で検証。

## TWBX 同梱要件

- `Image/agent.png` を TWBX に同梱する（参照実装版は `pipeline/templates/pulse_template.twbx` から copy）
- 既存 KPI アイコン4種 (`wheelbarrow.png` 等) は zone 削除後も TWBX に残してOK（読み込み不発で害なし）

## 既存スキル/メモリへの取り込み先

- ✅ `.claude/skills/twb-cloud-dl-xml-inject/pulse_zone_injector.py` として配備（2026-06-09実装）
- 関連: `sqlproxy_rewriter.py` (新規TWB→Cloud DS参照) と組み合わせて
  「生成TWB → sqlproxy書換 → Pulse zone注入 → final.twbx」の3段パイプラインに

## 動作確認

2026-06-09 Phase A で実証 (city-trial-monthly_CityTrialMonthly):
- KPI zone 置換: 8件（dashboard 4 + Phone 4）
- KPI アイコン除去: 8件
- 親レイアウト拡大: 5件
- AIボタン+Web zone追加: 2件（dashboard + Phone）
- 全パターン動作 ✓

## 落とし穴

1. **zone の name 属性末尾スペース**: `'月間アクセス(カード) '` 等末尾空白あり → `.rstrip()` してから title 抽出
2. **zone block balance 探索**: 単純な `</zone>` までだとネスト時に誤検出。必ず depth counter 使う
3. **toggle-action window-id**: `{...}` の中括弧で囲む（regex は `\{...\}` で照合）
4. **後ろから処理**: regex で複数置換するときは `reversed(matches)` か `sort key=-m.start()` で位置ズレ回避
5. **&amp; HTML エンコード**: URL内の `&` は `&amp;` にする（XML 属性内）
6. **Phone layout の window-id**: 同じ dashboard window の UUID を流用（別 UUID 生成しない）
7. ⚠️ **window-id は dashboard simple-id 必須・worksheet simple-id では toggle 全く動作しない**: 2026-06-16 v11new_A市 で worksheet `<simple-id uuid='{8E4B529D...}'/>` を誤って window-id に指定してしまい、AIアイコンクリックでチャット展開ゼロ。dashboard simple-id `{35835320...}` に修正したら即動作。**取得手段**: `<window class='dashboard' name='...'>` 配下の `<simple-id uuid='...'/>` を grep。または同 dashboard 内に既に存在する `tabdoc:goto-sheet window-id="{UUID}"` ボタン（タブ移動ボタン）から正しい UUID をコピー。**worksheet `<simple-id>` を間違って取ると見た目正常に publish 成功するが click イベント無反応で原因特定が長引く**
8. **layout-flow vert (サイドバー) 内 button 配置も toggle 動作する**: city-trial-monthly は絶対座標方式 (`x=4121 y=42634`) だが、サイドバー layout-flow vert 内に `<zone fixed-size='60' is-fixed='true' w='16000'>` で button を置いても toggle-action は機能（2026-06-16 v11new_A市 で実証）。サイドバー組込みの方が UI 整合性は高い。Web zone は最外 `<zones>` 直下に残してOK（同じ親要件は不要、window-id 一致だけ満たせばよい）
9. **複数 dashboard (DB1/DB2/DB3) への複製パターン**: 同じPulse機能を複数 dashboard に展開する場合、 (a) 各 dashboard 固有の window-id を埋め込む / (b) button/Web zone id は dashboard ごとに被らせない（DB1=9100/9002, DB2=9110/9012, DB3=9120/9022 のように prefix で分離）/ (c) Pulse Discover URL は dashboard 間で共有可能（同じmetric_ids群）。テキスト置換で安全に複製できる
10. **WS が単一色になったら Cache ではなく XML/データ問題を疑う**: 新規 別名 WB に publish して同症状か確認すれば即切り分け可能。`get-view-image` の結果は real-time 描画でキャッシュ無し（2026-06-16 v11new_A市 task_type 単一色問題で TEST WB 検証パターン確立）。詳細は別 feedback [[feedback_twb_join_dimension_paramcaption_collision]] 参照

### 関連
- 原典: SE提供の参照実装 の `output/_template/apply_pulse_template.py` 全515行
- 姉妹: [[feedback_pulse_rest_api_recipe]] (metric_id / definition_id 取得側、本パターンの入力)
- 姉妹: [[feedback_twb_sqlproxy_rewrite_pattern]] (TWB を Cloud DS 参照化、本パターンと併用)
- 姉妹: [[feedback_pulse_kpi_unit_rules]] (KPI 設計の formula_suffix/unit 絶対ルール)
