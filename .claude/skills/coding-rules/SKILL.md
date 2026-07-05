---
name: coding-rules
description: Apply coding rules and clean-code principles at write time, before and while writing code. Loads all team-extensible rule files from this skill's rules/*.md. Use whenever writing or modifying code — implementation tasks, refactoring, bug fixes — not only when the user mentions rules explicitly.
---

# coding-rules: 書く時点で規約を守る

cq-review が「書いた後のレビュー」なのに対し、これは「書く前・書く最中」の適用。
レビューで指摘されることを最初から書かない。

## ルールの読み込み

コーディング開始前に `$SKILL/rules/` の `*.md` を**ファイル名順にすべて読む**
($SKILL はこの Skill のディレクトリ。ホーム導入なら `~/.claude/skills/coding-rules`、
プロジェクト導入なら `<repo>/.claude/skills/coding-rules`)。

- 読むのは `*.md` のみ。`*.template.md` は読まない (デフォルトの参照原本。
  対応する .md をチームが削除している場合、そのルールは「無効化された」とみなす)
- ファイル間で矛盾したら、番号の大きいファイルが優先 (後勝ち)
- ルールの追加・変更・削除は rules/*.md を直接編集して git commit で共有する。
  書式は `90-rule-format.md` を見る
- install.sh はスキル更新時に `*.md` を保持し `*.template.md` だけ更新するので、
  チームの編集は消えない

## 優先順位 (上ほど強い)

1. プロジェクトの CLAUDE.md
2. $SKILL/rules/*.md (番号の大きい順)
3. 周囲の既存コードの流儀
4. 一般的な良識

ただし、既存コードとルールが矛盾したときは**矛盾の種類**で扱いが変わる:

- **細部** (命名スタイル・記法・フォーマット・コメントスタイル):
  周囲の既存コードを優先する。ルールとの矛盾はレビューパックで報告する
- **構造** (関数化・重複排除・ネスト深さ・引数の数・エラー処理・結合度):
  ルールを優先する。既存コードが違反していても新規コードは準拠して書く。
  既存部分の修正はスコープ外 — 気づいた違反は TODO.md 行きを提案するにとどめる

## 実装の流れ

1. rules/*.md を読む (このセッションでまだ読んでいない場合)
2. 変更対象の周囲コードを読み、細部の流儀 (命名・フォーマット) を把握する
3. 実装する。構造ルール (関数化・ネスト・重複) は書きながら適用する
4. セルフチェック:
   - 適用対象のルールを 1 つずつ確認する
   - cq-review Skill の cq-metrics.py を変更ファイルに実行し、新たなフラグ
     (長い関数・深いネスト・重複) を自分で作っていないか機械確認する
5. 提示時のレビューパック (self-review Skill) に**準拠メモ**を含める:
   - 読み込んだルールファイルと、特に効いたルール
   - 既存流儀を優先してルールから外れた箇所 (あれば)
   - 従えなかったルールと理由 (あれば。黙って逸脱しない)

## ルール

- rules/ の実ファイルを必ず読む。「読んだことにして」進めない
- ルールに従えない事情があるときは、準拠メモに理由を書く (無言の逸脱が最悪)
- ルール準拠を口実に、依頼されていない既存コードの書き直しを始めない
