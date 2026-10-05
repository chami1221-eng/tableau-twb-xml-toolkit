---
name: v5_3 base script (textscan直接接続) はWeb Edit Calc作成と非互換
description: <connection class='textscan'> 直接接続のTWBはpublishできるがCloud Web Edit新規Calc field作成でLogicException。pref-demo相当のfederated wrap必須
metadata:
  type: feedback
---

`generate_city_hp_v5_3_twb.py` 系の **`<connection class='textscan'>` を datasource直下に置く** TWB構造は、publishは成功してもCloud Web Editでの **新規Calculated Field作成が LogicException で完全ブロック** される。

**Why:**
2026-05-26 サンプル市demo再構築で発覚。
- testWB(v5_3 base) → 新規Calc作成 NG
- v6 (v5_3 base、Parameters DS削除、master CSV化) → 新規Calc作成 NG
- v6b (calcs全削除) → 新規Calc作成 NG  ← calcs定義は無罪
- **pref-demo(動作実績 `class='federated'` wrap)** → 新規Calc作成 OK

→ Parameters DS XML注入が原因という以前の判定 は **誤り**。
真因は **v5_3 のdatasource XML構造 (textscan直接接続) 自体がCloud Web Edit Calc creation backend validationを破壊** している。

**How to apply:**

### 症状判定
- publish: 成功 (200 OK)
- Cloud roundtrip検証: 全要素保持OK
- Worksheet描画: OK
- 既存Calc使用: OK
- Worksheet drag&drop追加: OK
- **新規Calculated Field作成 (右クリック → Create Calculated Field): LogicException「内部エラー」**

### NG構造 (v5_3 base)
```xml
<datasource caption='daily' inline='true' name='ds_daily' version='18.1'>
  <connection class='textscan' directory='...' filename='daily.csv'>   ← 直接textscan
    <named-connections>
      <named-connection caption='daily.csv' name='nc_daily'>
        <connection class='textscan' directory='...' filename='daily.csv' />
      </named-connection>
    </named-connections>
    <relation connection='nc_daily' name='daily.csv' table='[daily#csv]' type='table'>
      <columns header='yes' />   ← 簡易columns
    </relation>
    <metadata-records>
      <metadata-record class='column'>
        <remote-name>日付</remote-name>
        <remote-type>0</remote-type>   ← 全列 type=0
        ...
      </metadata-record>
    </metadata-records>
  </connection>
  <column datatype='date' name='[日付]' role='dimension' type='ordinal' />
  <object-graph>...</object-graph>
</datasource>
```

### OK構造 (pref-demo `generate_pref_twb.py` base)
```xml
<datasource caption='daily' inline='true' name='federated.ds_daily' version='18.1'>
  <connection class='federated'>   ← federated wrap が必須
    <named-connections>
      <named-connection caption='daily' name='textscan.nc_daily'>
        <connection class='textscan' directory='...' filename='daily.csv' />
      </named-connection>
    </named-connections>
    <relation connection='textscan.nc_daily' name='daily.csv' table='[daily#csv]' type='table'>
      <columns character-set='UTF-8' header='yes' locale='ja_JP' separator=','>   ← 詳細属性
        <column datatype="integer" name="日付" ordinal="0" />
        ...
      </columns>
    </relation>
    <metadata-records>
      <metadata-record class='capability'>   ← capability metadataが必須
        <attributes>
          <attribute datatype='string' name='character-set'>&quot;UTF-8&quot;</attribute>
          <attribute datatype='string' name='collation'>&quot;ja&quot;</attribute>
          <attribute datatype='string' name='locale'>&quot;ja_JP&quot;</attribute>
          ...
        </attributes>
      </metadata-record>
      <metadata-record class='column'>
        <remote-name>日付</remote-name>
        <remote-type>20</remote-type>   ← 型コード20(int)/5(real)/129(string) を正しく
        <local-type>date</local-type>
        <aggregation>Sum</aggregation>
        <collation flag='0' name='LJA_RJP' />   ← string列はcollation必須
        ...
      </metadata-record>
    </metadata-records>
  </connection>
  ...
</datasource>
```

### 必須修正点 (5点)
1. `<connection class='federated'>` で wrap (datasource直下)
2. 内側に `<named-connection>` を置き、その中に `<connection class='textscan'>` を入れる
3. `<columns>` に `character-set='UTF-8' header='yes' locale='ja_JP' separator=','` 属性を付ける
4. `<metadata-record class='capability'>` をDS全体に1個必ず入れる (character-set/collation/locale/field-delimiter等の<attribute>)
5. `<metadata-record class='column'>` の `<remote-type>` を正しい型コード (integer=20, real=5, string=129) にする。string列は `<collation flag='0' name='LJA_RJP' />` も必須

### 影響範囲
以下の generator script はすべてv5_3 base継承 → **同じ問題を抱える**:
- `scripts/20260525_generate_city_hp_v5_3_twb.py` (元凶)
- `scripts/20260526_generate_city_v6_twb.py`
- `scripts/20260526_generate_city_v6b_nocalcs_twb.py`
- `scripts/20260525_generate_city_hp_v5_2_twb.py`
- `scripts/20260525_generate_city_hp_v4_twb.py`
- `scripts/20260525_generate_city_hp_v3_twb.py`
- `scripts/20260525_generate_city_hp_v2_twb.py`
- `scripts/20260501_generate_city_hp_twb.py`
- `scripts/20260415_generate_city_usage_twb.py`
- `scripts/20260402_generate_district_twb.py`
- `scripts/20260401_generate_twb.py` / `_v5.py`

これら **すべて pref-demo構造 (`generate_pref_twb.py` の named_conn/capability_meta/col_meta/table_rel/meta_for_table) を採用したリライト** が必要。

### 推奨アクション
1. 新規 TWB 生成scriptは必ず `generate_pref_twb.py` を base に書く
2. v5_3 base scriptで生成済のWBは「既存Calcのみ使用」「drag&drop worksheet追加のみ」で運用 (新規Calc作成NG前提)
3. 配布先ユーザー向けサンプル市v6は **pref-demo構造で再生成** が必須 (現状の v6 は描画OKだが Calc追加不可)

関連:
- [[feedback_twb_cross_ds_parameter_pattern]] — 前回「Parameters注入が原因」と誤判定。本memo新規化で訂正
- [[feedback_twb_cloud_compat]] — TWB Cloud互換性。pref-demo流用ルール
- [[feedback_twb_use_generic_publish_script]] — publish.py generic必須
- [[reference_publish_py_path]] — publish.py path

