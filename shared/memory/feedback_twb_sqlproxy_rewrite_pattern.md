---
name: twb-embedded-csv-sqlproxy-published-datasource
description: 埋め込みCSV接続のfederated datasourceを、publish済DSへのsqlproxy参照に正規表現だけで完全変換するレシピ。UUID→base36命名規則・object-graph除去・Parameters除外まで含む実装パターン
metadata: 
  node_type: memory
  type: feedback
---

ローカル CSV を埋め込んだ TWB を「先に TDSX として publish したデータソース」を参照する形に書き換えると、TWBX を Cloud に publish した時に **CSV ファイルを同梱せず、Server 側 datasource を参照する形** で動作する。Web Edit でも正しく Data pane が表示される。参照実装版 `pipeline/publisher.py` の `_patch_twb_datasource` を取り込むのが正解。

**Why:**
2026-06-08 SE経由で入手した 参照実装を解析して判明。私の既存 `twb-cloud-dl-xml-inject` は既存 Cloud WB の XML 編集が主で、**新規 TWB を「Cloud datasource参照」に書き換える正攻法コード**は持っていなかった。参照実装は regex 4本だけで完全変換を実装している（XML parser 不使用 = `feedback_twb_xml_parser_forbidden` 準拠）。

**How to apply:**

### 適用シーン

- ローカル CSV embed の TWB を生成 → CSV は別途 TDSX として publish 済 → TWBX は CSV 同梱せずに sqlproxy 参照したい
- `403132 publish error` (sqlproxy 書換漏れ) の根本対処
- Web Edit で Data pane に独立した published DS として現れて欲しい

### 変換前後（datasource ブロック）

**Before (federated.xxx + embedded textscan)**
```xml
<datasource caption='daily' inline='true' name='federated.0abc123...' version='18.1'>
  <connection class='federated'>
    <named-connections>
      <named-connection caption='daily.csv' name='textscan.0abc'>
        <connection class='textscan' directory='...' filename='daily.csv'/>
      </named-connection>
    </named-connections>
    <relation .../>
    <metadata-records>...</metadata-records>
  </connection>
  <object-graph>...</object-graph>
  <column .../>
  ...
</datasource>
```

**After (sqlproxy → published DS 参照)**
```xml
<datasource caption='daily' inline='true' name='sqlproxy.{base36(uuid)}' version='18.1'>
  <repository-location derived-from='http://localhost'
    id='{ds_item.content_url}' path='/t/{site}/datasources'
    revision='1.0' site='{site}'/>
  <connection channel='https' class='sqlproxy' dbname='{ds_item.content_url}'
    directory='dataserver' port='443'
    server='{server_host}' username='' workgroup-auth-mode='prompt'>
    <relation type='collection'>
      <relation name='sqlproxy' table='[sqlproxy]' type='table'/>
    </relation>
  </connection>
  <!-- 元の <column .../> 定義はそのまま保持 -->
  <column .../>
  ...
</datasource>
```

### 必須6ステップ

1. **古い federated.xxx ID を抽出** — `<datasource ... inline='true' name='(federated\.[^']+)'>` から取得。後段でワークシート参照を一括置換するキー
2. **sqlproxy 名生成** — `sqlproxy.{base36(uuid26文字)}` 形式。UUID hex → int → base36 → 26字 zfill
   ```python
   def _uuid_to_base36(u: str) -> str:
       n = int(u.replace("-", ""), 16)
       chars = "0123456789abcdefghijklmnopqrstuvwxyz"
       result = ""
       while n:
           result = chars[n % 36] + result
           n //= 36
       return result.zfill(26)
   ```
3. **federated ブロック全体を sqlproxy ブロックに丸ごと置換** — `<datasource ... inline='true' name='federated.xxx'>...</datasource>` 全体に対する re.sub。**`<column>` 等のメタ定義は保持** (inner 抽出後に再注入)
4. **除外条件3つ** — 以下は触らない:
   - `name='Parameters'` (これを触ると WB全体壊れる: [[feedback_twb_cross_ds_parameter_pattern]] 訂正分参照)
   - `hasconnection='false'` (Parameters は基本これ)
   - そもそも `federated.` を含まないブロック
5. **inner から削除する要素3種** — `<connection class='federated'>...</connection>` / `<object-graph>...</object-graph>` / `<connection class='textscan'>...</connection>` (残存対応) を re.sub で除去
6. **ワークシート参照を全置換** — 旧 federated.xxx ID を sqlproxy.{base36} に `xml_str.replace()` で一括置換。worksheet の `<datasource-dependencies>` や filter の `[federated.xxx].[fieldname]` 表記まで全て切り替わる

### 実装コード（移植元: 参照実装 publisher.py L223〜348）

移植時は `_patch_twb_datasource` + `_uuid_to_base36` + `_rewrite_twbx_to_published_datasource` の3関数セット（参照実装 `pipeline/publisher.py` 由来）。

### Cloud roundtrip 検証チェック

publish後すぐ download:
```bash
grep "class='sqlproxy'" downloaded.twb           # sqlproxy connection残存
grep "sqlproxy\." downloaded.twb                 # 命名規則
grep -c "federated\." downloaded.twb             # 0 (旧IDが全て置換されてること)
grep "<object-graph>" downloaded.twb             # 0 (除去されてること)
```

### 落とし穴

- **Parameters DS を除外しないと WB が壊れる**: `name='Parameters'` の datasource は `hasconnection='false'` で別系統。federated 置換ロジックを通すと paramctrl 等が全部死ぬ
- **base36 命名規則ミス**: 26字パディング忘れ / hex→int変換時のハイフン残しで sqlproxy 名不正 → Cloud が DS 解決失敗
- **content_url を取り違える**: `ds_item.content_url` (例 `_12345678901234`) を使う。`ds_item.id` (UUID) ではない
- **server_host 取り出し**: `https://` プレフィックスを strip しないと sqlproxy connection の server 属性が壊れる
- **<column> 定義の消失**: federated inner を丸ごと消すと型定義まで失われる → `<connection>` と `<object-graph>` だけピンポイント除去

### 私の既存スキル/メモリへの取り込み先（2026-06-09実装完了）

- ✅ `.claude/skills/twb-cloud-dl-xml-inject/sqlproxy_rewriter.py` に配備済
  - 関数: `rewrite_twbx_to_sqlproxy(twbx_path, ds_id, ds_content_url, ds_name, server_url, site_name, out_path)`
  - 補助: `patch_twb_to_sqlproxy()` (XMLレベル直叩き) + `_uuid_to_base36()` (命名規則)
  - CLI モード対応 (`python sqlproxy_rewriter.py input.twbx --ds-id ... -o output.twbx`)
- ✅ `.claude/skills/twb-cloud-dl-xml-inject/SKILL.md` に「派生用途: 新規TWBをCloud DS参照化」セクション追記
- ⏳ `tools/publish.py` の前処理組み込みは未着手 (`--with-sqlproxy` 等の追加が将来オプション)
- 動作検証: 2026-06-09 検証用サイト/Sandbox/city-trial-monthly_CityTrialMonthly で実証
  (federated/object-graph/textscan 全0、sqlproxy 1個、base36 26字命名OK)

関連:
- [[feedback_twb_v5_textscan_breaks_web_edit_calc]] — embedded textscan 直接接続が Web Edit Calc 作成を破壊する問題。本パターンで「Cloud DS参照に切り替え」すれば回避可
- [[feedback_twb_cloud_compat]] — TWB Cloud互換性。pref-demo流用ルール
- [[feedback_twb_cross_ds_parameter_pattern]] — Parameters DS 除外の必要性（訂正注記）
- [[feedback_twb_use_generic_publish_script]] — publish.py generic必須
- [[reference_twb_publish_error_codes]] — 403132 (sqlproxy書換漏れ) の対処
- [[feedback_pulse_rest_api_recipe]] — sqlproxy 書換後の TDSX publish と Pulse 定義は同じ publisher.py に同居している
