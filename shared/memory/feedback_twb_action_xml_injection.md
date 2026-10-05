---
name: TWB action XML 注入は tsc:tsl-filter + link expression 形式必須
description: TWB に filter action を XML注入する場合、旧 field-instances 形式は Cloud roundtrip で剥落する。新 tsc:tsl-filter + URL-encoded link expression が必須
metadata:
  type: feedback
---

TWB に filter/highlight action を XML編集で注入する場合、Tableau Cloud 2024+ では
**新フォーマット (`tsc:tsl-filter` command + URL-encoded `<link expression>`)** が必須。
旧 Tableau Desktop 形式 (`<field-instances source='...' target='...' />`) は
publish 時には通るが、Cloud roundtrip で **`<link>` と `<command>` が剥落** されて
`<source>` だけ残った骸骨状態になり、Web Edit からは "(生成済み)" として認識されず
runtime でも一切フィルターしない。

**Why:**
2026-05-25 サンプル市v5.3 案件で、DB2/DB3/DB4 のアクション6個を XML一括注入した際、
旧 `<field-instances>` 形式で publish → Cloud に保存はされるが Web Edit ダイアログには表示されず
何もフィルターしない事故。3回 republish して原因不明で時間浪費。
ユーザーが Web Edit で手動作成した1個を download → XML逆解析して新フォーマット判明。

**How to apply:**

### 動く正解 (filter action, on-select)
```xml
<actions>
  <action caption='ページ→日別' name='[Action1_<32hex-UUID>]'>
    <activation auto-clear='true' type='on-select' />
    <source dashboard='DB2 異常検知' type='sheet' worksheet='ハイライト_PV' />
    <link caption='ページ→日別' delimiter=',' escape='\' 
          expression='tsl:{URL-encoded dashboard}?{URL-encoded target_col}~s0=&lt;{source_col literal}~na&gt;' 
          include-null='true' multi-select='true' url-escape='true' />
    <command command='tsc:tsl-filter'>
      <param name='exclude' value='同一DB内の他ソースシート,カンマ区切り' />
      <param name='target' value='DB2 異常検知' />
    </command>
  </action>
  <!-- ...他actions... -->
  <datasources>
    <datasource caption='月別集計' name='ds_pages' />
    <datasource caption='ページ別日別' name='ds_pages_daily' />
  </datasources>
  <datasource-dependencies datasource='ds_pages'>
    <column datatype='string' name='[ページタイトル]' role='dimension' type='nominal' />
  </datasource-dependencies>
  <datasource-dependencies datasource='ds_pages_daily'>
    <column datatype='string' name='[ページタイトル]' role='dimension' type='nominal' />
  </datasource-dependencies>
</actions>
```

### expression の構築
```python
import urllib.parse, uuid
def make_action_name(n): return f'Action{n}_{uuid.uuid4().hex.upper()}'

def build_expression(dashboard, target_ds, target_field, source_ds, source_field):
    db_enc = urllib.parse.quote(dashboard, safe='')
    target_col_enc = urllib.parse.quote(f"[{target_ds}].[{target_field}]", safe='')
    source_col_raw = f"[{source_ds}].[{source_field}]"
    return f"tsl:{db_enc}?{target_col_enc}~s0=&lt;{source_col_raw}~na&gt;"
```

### 死ぬパターン (旧形式 — Cloud で剥落)
```xml
<!-- これは publish 通るが Cloud roundtrip で <target> と <field-instances> が消える -->
<action ...>
  <source ... />
  <target dashboard='...' worksheet='...' />
  <field-instances>
    <field-instance source='[ds_a].[field]' target='[ds_b].[field]' />
  </field-instances>
</action>
```

### ハイライトアクション (on-hover) は別形式必須
filter action と同じ `tsc:tsl-filter` でなく **`tsc:brush`** を使う:
```xml
<action caption='hover ハイライト' name='[Action_xxx]'>
  <activation auto-clear='true' type='on-hover' />
  <source dashboard='...' type='sheet' worksheet='...' />
  <command command='tsc:brush'>
    <param name='target' value='ダッシュボード名' />
  </command>
</action>
```
2026-05-25時点で DB3 Sankey hover を `tsc:tsl-filter` + on-hover で実装→動かず。
twb-patterns.md にも `tsc:brush` 形式が記載されている。

### 必須運用ルール
1. **XML注入アクションは必ず最初に1個 manual 作成 → download → XML確認**してから自動生成すること
2. **既存 actions block を全置換せず append-only** で追加（ユーザー手動作成版を消さない）
3. **publish 直後に必ず download → `<link>` と `<command>` の保持確認**
4. **DS と field の `<datasource-dependencies>` 登録**を `</actions>` 直前に必須

### ⚠️ `<actions>` は workbook root level (2026-06-03 サンプル市v10で実発見)

action XMLは **dashboard内ではなく workbook root直下** に置く。dashboard内に置くと publish OK でも runtime で完全に無視される。

```xml
<workbook>
  <datasources>...</datasources>
  <actions>                               ← ★ここに置く
    <action ... />
    <action ... />
  </actions>
  <worksheets>...</worksheets>
  <dashboards>...</dashboards>
</workbook>
```

ユーザーがWeb Editで Use as Filter (漏斗) を設定して Save した場合も、上記workbook root位置に書き出される (caption='フィルター N (生成済み)')。

**最小pattern (special-fields='all' でも実動作OK・2026-06-03 サンプル市v10で確認)**:
```xml
<action caption='フィルター 1 (生成済み)' name='[Action1_{32hex-UUID大文字}]'>
  <activation auto-clear='true' type='on-select' />
  <source dashboard='DB1_xxx' type='sheet' worksheet='WS3_xxx' />
  <command command='tsc:tsl-filter'>
    <param name='special-fields' value='all' />
    <param name='target' value='DB1_xxx' />
  </command>
</action>
```

`<link expression>` が無くても **workbook root配置+special-fields='all'** なら動く。複雑な field path 不要。

### ⚠️ Web Edit手動Save後の剥落 (2026-06-03 サンプル市v10で実発生)

ユーザーが Web Edit でworksheet配置やshow me変更 (e.g. Sankey作成) を行い **Save** すると、
**dashboard XML が Tableau Web Editによって再書き出され、`<actions>` ブロックが全削除される**。

| 操作 | actions XMLへの影響 |
|------|---------------------|
| WB のDL → 編集 → publish | OK (剥落なし) |
| Web Edit でworksheet変更 → **Save** | **`<actions>` 完全削除** |
| Web Edit でフィルタ追加 → Save | actions 残る (worksheet配置触らないので) |

**対策**:
- ユーザーのWeb Edit Save **後** に actions を再注入する運用が必要
- またはユーザーに「Save後はクリック連動が消えるので再注入が必要」と事前告知
- 既存 actions block を削除してから再注入する `gen_actions_xml()` ヘルパーを ready で持つ
- ws抽出 regex: `<zone[^/]+name='(WS[^']+)'[^/]*/>` で `type-v2='filter'` `paramctrl` 除外

関連:
- 参考TWB: `data/sample_city_hp_demo/city_v3.twb`
- 参考 script: `scripts/20260525_city_inject_actions_v3.py`
- [[reference_tableau_native_sankey]] — Sankey VizExtension の TWB自動生成
- [[feedback_twb_use_generic_publish_script]] — generic publish.py 使用必須
