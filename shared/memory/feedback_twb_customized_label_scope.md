---
name: customized-label/tooltipはencodings内フィールドのみ参照可能
description: TWB XMLのcustomized-label/customized-tooltipで参照できるフィールドはencodingsに含まれるもののみ。datasource-dependenciesだけでは不足
type: feedback
---

TWBのcustomized-label / customized-tooltip で `<[DS].[field]>` 形式で参照できるフィールドは、
**そのpaneのencodings内（color/size/text/lod/wedge-size等）に含まれるフィールドのみ**。

**Why:** Tableau Cloudは、encodingsに含まれないフィールドのデータをmark（描画単位）に持ち込まない。
datasource-dependenciesに宣言しても、encodings外なら参照結果は空文字になる（2026-04-11実証）。

**How to apply:**
- customized-labelで新フィールドを参照したい場合、`<text>` か `<tooltip>` エンコーディングに追加する
- `<text>` エンコーディングに入れれば確実にmark dataに含まれる
- ツリーマップの例: `<text column='[DS].[sum:calc_okuyen:qk]' />` で億円calcを参照可能にし、customized-labelで `<区分5名> <億円値>億円` を表示
- 複数textフィールドを使う場合は `<text column='field1' /><text column='field2' />` で記述可能
