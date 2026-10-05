---
name: twb-paramctrl-layout-nesting
description: paramctrl zone は layout-basic直下では Cloud描画されない。3段ネスト（layout-basic → horz layout-flow → [左 layout-basic + 右 vert layout-flow]）必須
metadata:
  type: feedback
---

# Tableau dashboard paramctrl zone は3段ネスト必須

dashboard に `<zone type-v2='paramctrl'>` を絶対座標で配置しても **Cloud で描画されない**。
**正解は3段ネスト構造**で、paramctrl は最深層の vertical layout-flow 内に置く必要がある。

**Why:**
2026-06-12 サンプル市v11new TWB の stage3 で Month パラメータ切替 UI として paramctrl zone を実装したが、Cloud で右ペインに表示されない問題が発生。
- Iter1: layout-basic 直下に `<zone paramctrl id=999 x=84000 y=9500 w=16000 h=6000>` を絶対座標配置 → 描画されず
- Iter1 改修: layout-flow vert ラッパー (id=9998) で1段ラップ → 描画されず
- 原因: 参考TWB (city_test_unified) と構造比較した結果、paramctrl は **3段ネスト**で配置されている

### 正解構造（参考TWB）

```xml
<zones>
  <zone id="3" type-v2="layout-basic" x="0" y="0" w="100000" h="100000">  <!-- 最上位 -->
    <zone id="113" type-v2="layout-flow" param="horz" x="0" y="0" w="100000" h="100000">  <!-- 横並び親 -->
      <zone id="111" type-v2="layout-basic" x="0" y="0" w="88571" h="100000">  <!-- 左サイド -->
        <!-- 既存 worksheet zones 全部 -->
        <zone id="10" type-v2="worksheet" .../>
        ...
      </zone>
      <zone id="112" type-v2="layout-flow" param="vert" is-fixed="true" fixed-size="160"
            x="88571" y="0" w="11429" h="100000">  <!-- 右サイドバー（固定幅）-->
        <zone id="117" type-v2="paramctrl" param="[Parameters].[Parameter 10]"
              x="88571" y="10000" w="11429" h="3500"/>
        <zone id="118" type-v2="paramctrl" .../>
      </zone>
    </zone>
  </zone>
</zones>
```

### 必須要素

1. 最上位 `layout-basic` (id=3 等) は残す
2. その**中**に `layout-flow param='horz'` を1個追加 (w=100000 h=100000)
3. horz の中に2つの zone を horizontal 配置:
   - **左**: `layout-basic` (w≈85000、既存 worksheet zones を全部包含)
   - **右**: `layout-flow param='vert' is-fixed='true' fixed-size='160'` (w≈15000、サイドバー)
4. **右の vert 内に paramctrl** を配置
5. dashboard 直下に `<datasources><datasource caption='Parameters' name='Parameters'/></datasources>` 参照も必須（これ無いと paramctrl source 解決失敗）。**datasource-dependencies は Parameters には不要**（お手本 city_test_after_unified で実証。データDSの filter zone がある場合のみそのDSの dependencies が要る）

### paramctrl の mode 属性（重要・2026-06-13追記）

- **list型パラメータ（ドロップダウン）= `mode='compact'`**。`values='list'` ではない
- range型（スライダー）= `values='range'`、`mode='slider'`
- 文字入力 = `mode='type_in'`
- list paramctrl 例: `<zone h='4000' id='203' mode='compact' param='[Parameters].[p_月]' type-v2='paramctrl' w='16000' x='84000' y='0'><zone-style>...</zone-style></zone>`
- 全twb横断grepで mode='compact'(6) / values='range'(6) / mode='slider'(5) を確認して決定

### NG構造（描画されない）

- ❌ layout-basic 直下に paramctrl 絶対配置
- ❌ layout-basic 直下に layout-flow vert (paramctrl 含む) を絶対配置（1段ラップ）
- ❌ paramctrl を tiled（auto-layout）にして空きスペースに置こうとする

### 実装上の注意

3段ネスト実装は既存 worksheet zone 10個前後を**新しい親 layout-basic に移動**する大改造になる。
[[feedback_twb_lxml_write_forbidden]] により lxml の全体 write は使えないため、テキスト置換ベースでの構造変換は実装難易度高い。

### 代替策

- **A: filter zone 方式**: paramctrl 諦めて `<zone type-v2='filter'>` を layout-basic直下に絶対配置（1段で描画される）。Parameter 廃止→各WSの dimension filter を show する方式。詳細: A3-full アプローチ
- **B: Web Edit 手動補完**: Cloud Web Edit で Parameter右クリ→Show → サイドバーに paramctrl が自動配置（公式UI経由が最も確実、5分で完了）。ただしWeb Edit Saveは別問題（action剥落リスク）に注意
- **C: 3段ネスト手書き**: 全体構造を文字列レベルで構築。**2026-06-13に実証成功（高難度だが再現可能）**

### C実証手順（2026-06-13 v11new_city 月paramctrl化で成功）

3段ネストをテキスト置換で安全に実装する確立手順:
1. **dashboard単位でblock slice**（`<dashboard ...name='X'>`〜`</dashboard>`）してから置換。アンカー（`<size/>` `</zone>\n</zones>` 等）は全dashboard同一文字列なので盲目置換厳禁
2. 旧filter zone（self-closing `type-v2='filter'`）を regex で削除
3. `<size/>` 直後に `<datasources><datasource caption='Parameters' name='Parameters'/></datasources>` 注入
4. top zone開始直後に horz flow open + 左 layout-basic(w=84000) open を挿入
5. top zone close（`        </zone>\n      </zones>` = 8sp+6sp が desktop zones の唯一マーカー。phone は indent違いで安全）の直前に: 左close + 右vert flow(`fixed-size='224' w='16000' x='84000'`、fixed-size=w/100000*maxwidth) + paramctrl(mode='compact') + vert close + horz close を挿入
6. **zone開閉count検証必須**: `(<zone 数 − /> 数) == </zone> 数` をwrite前にassert。一致しなければabort
7. id採番は200番台（DB1=200系/DB2=210系/DB3=220系）で既存と非衝突
8. publish後 download → structure-diff で action/zone/calc/parameter の only_in_a=0 確認（Cloud は属性順を正規化するので grep は属性順非依存で。zone総数一致が確実な判定）

実装例: `scripts/20260613_p3_dashboard_paramctrl.py`

関連:
- [[feedback_twb_cross_ds_parameter_pattern]] — Parameter+Calc bool filter 構造（paramctrl前提）
- [[feedback_twb_lxml_write_forbidden]] — lxml 全体 write 禁止（3段ネスト実装の制約）
- [[feedback_twb_action_xml_injection]] — filter-action XML注入剥落対応（同様にCloud描画問題）
