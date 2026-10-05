---
name: TWB生成にデザインルールを強制適用しない
description: XML直接生成のTWBにフォント・色・スタイルを強制するとTableauデフォルトより見栄えが悪くなる。スキルへの組込みも不要
type: feedback
---

TWB生成時、デジタル庁ガイドブック等のデザインルールをXMLに直接埋め込まない。

**Why:** Tableauのデフォルトスタイリングは十分洗練されており、XMLで強制すると逆に見栄えが悪化した（2026-04-03実証）。カラーパレット定義・フォント指定・軸色変更を全ワークシートに適用→ユーザーが「初めのほうが良かった」と即却下。

**How to apply:**
- generate_pref_twb.py等のTWB生成スクリプトに `<style>` でフォント・色を埋め込まない
- `<style />` （空）のままにしてTableauデフォルトに任せる
- design-guide.mdのようなデザインルールファイルをtwb-generatorスキルに組み込まない
- デザイン改善はDesktop上での手動調整 or Tableau Agentに任せる
