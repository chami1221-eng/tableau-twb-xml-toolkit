---
name: feedback-twb-dual-axis-xml
description: 二重軸（棒＋折れ線、線＋丸を1枚に重ねる）の TWB XML。y-index ではなく axis の fold='true'
metadata:
  type: feedback
---

**二重軸は `y-index` では作れない。軸の `fold='true'` で作る。**（Tableau が書き出した実物から採取）

```xml
<!-- rows に2つの測度を + でつなぐ -->
<rows>([ds].[sum:測度A:qk] + [ds].[sum:測度B:qk])</rows>

<!-- worksheet の <style> に、第2の測度を第1軸へ畳む宣言 -->
<style>
  <style-rule element='axis'>
    <encoding attr='space' class='0' field='[ds].[sum:測度B:qk]' field-type='quantitative'
              fold='true' scope='rows' type='space' />
  </style-rule>
</style>

<!-- pane は測度ごと（y-axis-name で対応づけ）。mark を pane ごとに変えられる -->
<pane id='1' y-axis-name='[ds].[sum:測度A:qk]'> … <mark class='Bar' /> … </pane>
<pane id='2' y-axis-name='[ds].[sum:測度B:qk]'> … <mark class='Line' /> … </pane>
```

- 全 pane に `<color column='[ds].[:Measure Names]' />` を置くと色が測度名で分かれる（Tableau の既定）。各 pane が自前の色を持つなら不要
- **2つの測度が同じ値（座標など）を重ねるときは、両方の軸レンジを固定する**
  （`<encoding attr='space' … range-type='fixed' min='…' max='…' />` を両方に）。固定しないとレイヤーがずれる
- 例: リレーションマップの「線レイヤ＋丸レイヤ」（→ `feedback_twb_relation_map.md`）
