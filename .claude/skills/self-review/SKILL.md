---
name: self-review
description: Attach a structured self-review to any non-trivial design or patch before presenting it, so the human can review by focus points instead of reading everything. Use when presenting a patch, design, or multi-file change for human review, or when the user asks "review this before I look".
---

# self-review: AI 出力にレビューパックを付ける

目的: 人間のレビューを「全部読む」から「重点確認」に変える。
パッチや設計を提示するとき、本体の**後ろ**に以下のレビューパックを付ける。
簡潔に — 各項目 1〜3 行。長いレビューパックは本末転倒。

## レビューパック形式

```markdown
---
## レビューパック

**変更の要約**: (1 文)

**根拠**: 根本原因 → この修正がそれを解決する理由。推測が混ざる場合は「推測:」と明記。

**影響範囲**: この変更が触る他の機能/ターゲット/呼び出し元。
「影響なし」と書く場合は、なぜ無いと言えるか (検索した・テストした) を添える。

**テスト証跡**: 実際に実行したコマンドと結果。実行していないなら「未実行」と正直に書き、
実行すべきコマンドを示す。

**重点確認ポイント**: 人間に見てほしい 1〜3 箇所 (file:line)。
「ここは自信がない」「ここは仕様判断が必要」を優先して挙げる。

**未解決事項**: あれば。なければ省略。
```

## ルール

- テスト証跡を捏造しない。実行していないものは「未実行」と書く。
- 自信のない箇所を隠さない。重点確認ポイントは「自信のない順」に並べる。
- 3 行以下の自明な変更にはレビューパック不要 (過剰適用しない)。
- コンパイラ関連の変更では `references/compiler-checklist.md` を確認し、
  該当する項目があれば影響範囲/重点確認ポイントに反映する。
- コード品質 (関数化・結合度・ネスト・命名) は提示前に
  cq-review Skill の `references/checklist.md` で自己チェックし、
  未解消の観点があれば「重点確認ポイント」に正直に挙げる。
