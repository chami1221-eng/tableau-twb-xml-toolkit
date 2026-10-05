---
name: feedback-twb-slices-required
description: ダッシュボードのフィルターの選択肢が1つしか出ない／クリック連動で絞られない → 対象シートの <slices> にその列が無い
metadata:
  type: feedback
---

**ダッシュボードのフィルターを効かせるシートには、`<view>` 内（filter 群の後）に `<slices>` でその列を宣言する。**

```xml
<slices>
  <column>[ds].[none:地域:nk]</column>
  <column>[ds].[none:年月:nk]</column>
</slices>
```

**Why:** `<slices>` が無いと、ダッシュボードのフィルターの選択肢が **CSV の先頭の値1つだけ**に潰れる。
`values='database'` や列の並べ替え、CSV の行の並べ替えでは直らず、`<slices>` の追加が決め手だった（10回の publish で切り分け）。
クリック連動でも、行に置いていない列（例: 原文一覧のキーワード）で絞るには `<slices>` に宣言が要る。

**How to apply:**
- フィルター列ごとに `<filter class='categorical'>`（全選択なら `function='level-members'`）と `<slices>` の両方を書く
- 順序は `filter → 並べ替え → slices → aggregation`（Desktop の内容モデル。→ `feedback_twb_desktop_2026_gates.md`）
