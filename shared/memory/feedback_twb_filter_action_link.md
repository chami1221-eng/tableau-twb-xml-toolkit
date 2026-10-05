---
name: feedback-twb-filter-action-link
description: クリック連動（フィルターアクション）は「選択したフィールド」型＝<link> で書く。special-fields=all＋受け口の形は Desktop で開けず、縦積みデータでは0件になりやすい
metadata:
  type: feedback
---

**クリック連動は、クリック元のシートごとに1本の action を作り、`<link>` で渡す列を1つに絞って書く。**

```xml
<actions>
  <action caption='語をクリック → 原文を見る' name='[Action1_固定の名前]'>
    <activation type='on-select' />
    <source dashboard='{ダッシュボード名}' type='sheet' worksheet='{クリック元のシート}' />
    <link caption='…' delimiter=',' escape='\' expression='tsl:{ダッシュボード名をURLエンコード}?{[ds].[列]をURLエンコード}~s0=&lt;[ds].[列]~na&gt;'
          include-null='true' multi-select='true' url-escape='true' />
    <command command='tsc:tsl-filter'>
      <param name='exclude' value='{絞らないシート,カンマ区切り}' />
      <param name='target' value='{ダッシュボード名}' />
    </command>
  </action>
  <!-- 最後の action の後に、link が参照する列を宣言する -->
  <datasources><datasource caption='…' name='{ds}' /></datasources>
  <datasource-dependencies datasource='{ds}'>
    <column datatype='string' name='[列]' role='dimension' type='nominal' />
  </datasource-dependencies>
</actions>
```

- `<actions>` は `<worksheets>` より**前**に置く（後ろに置くと消える）
- link 型のとき `<command>` に `special-fields` を書かない
- `~s0=` の右辺は URL エンコードしない（XML エンティティのまま）
- ターゲットのシートは、その列を `<slices>` に宣言しておく（行に置かなくても絞れる）
- 上のグラフ同士は `exclude` に入れる。入れないと押した瞬間に他のグラフが1本に痩せる

**Why:** `special-fields='all'`（ソースの全次元を渡す）＋ターゲット側の受け口（`group user:auto-column='sheet_link'`）の形は Cloud では動くが、
①Desktop の内容モデルでは1 action に source 1つ・link 必須なので開けない ②縦積みUNIONのデータでは、ソースが持つ埋め草の値（エッジIDなど）まで渡って**0件になる**。
link 型ならどちらも起きない。

**How to apply:** 新しく書くときは最初から link 型。既存の special-fields 型は `twb-public-export` の検査で見つかる。手本＝`.claude/skills/freetext-to-tableau/template/freetext_dashboard.twb`。
