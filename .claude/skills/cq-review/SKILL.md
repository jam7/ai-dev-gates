---
name: cq-review
description: Structured code quality review (function extraction, coupling, nesting depth, naming — Readable Code / Clean Code viewpoints). Combines mechanical metrics (cq-metrics.py) with semantic review and outputs a severity-ranked findings table. Use when the user asks for a code quality review (cq-review), before requesting human review, or as the review gate after AI-written code.
license: MIT
---

# cq-review: コード品質の構造化レビュー

目的: 「全読みレビュー」をやめ、**機械計測で候補を絞り、AI が意味的判断を行い、
人間は裁定だけ**にする。

## ツール

`cq-metrics.py` — この SKILL.md と同じディレクトリにある (stdlib のみ、Python 3.6+、
brace 系言語対応)。`$SKILL` はこの Skill のディレクトリ (ホーム導入なら
`~/.claude/skills/cq-review`、プロジェクト導入なら `<repo>/.claude/skills/cq-review`)。

```bash
python3 $SKILL/cq-metrics.py [options] <file-or-dir>...
  --max-func-lines 60 / --max-nest 4 / --max-params 5 / --dup-window 8 / --top 20 / --ext .c,.go
  --csv --label <commit>   # 推移記録用の 1 行 CSV (label,files,functions,long,deep,params,dups)
```

品質推移を記録する場合はコミットごとに
`cq-metrics.py --csv --label $(git rev-parse --short HEAD) src/ >> cq-trend.csv` を追記する。

関数長・ネスト深さ・引数の数・重複ブロックを検出する。**ヒューリスティックな候補提示**であり
違反判定ではない (例: 設定列挙だけの長い初期化関数は問題でないことが多い)。

**既定の 60 行は上限であって合格ラインではない** (coding-rules の目安は 20-30 行)。
既定値は既存コードに後から入れても指摘が溢れないための下駄なので、レビューでは
`--max-func-lines 30` でも測り、両方の結果を見て判断する。**報告するときは
どの閾値で測ったかを必ず書く** — 「指摘ゼロ」は閾値次第でいくらでも作れる。

対象は波括弧系の言語と Python (2026-08-09 追加)。Python はブロックをインデントの
段数で数える (パーサーは使わず、`def` を正規表現で拾って本体を字下げで追う)。
`elif` 連鎖は 1 段と数える。波括弧版の `} else if (...) {` と同じ扱い。

**関数長はコード行数**で、コメント行と空行は数えない (2026-08-09 変更)。
説明を書き足すと閾値超過になるのは指標として倒錯しているため。LLVM で測ると
指摘数が 3-4 割減る (コメントの多いコードほど差が出る)。この変更を挟むと
cq-trend.csv の推移が不連続になるので、ラベルに印を付けておくとよい。

重複検出は import / include / use / using / require / package の宣言行を除外する
(2026-08-09 追加)。同じパッケージ群を使うファイル同士は import 節が丸ごと一致するが、
どの言語でも共通化できないため、そのまま数えると指摘にならないノイズが上位を占める。
Go・Scala・Python の括弧で囲む複数行 import はブロックごと除外する。
C# の `using var x = ...` や Rust の `use_cache(x)` は宣言ではないので実コードとして数える。

## 補助ツール: git-cochange.py (隠れ結合の検出)

`$SKILL/git-cochange.py` — git 履歴から「場所は離れているのに同一コミットで
一緒に変更され続けるファイルペア」を検出する (stdlib のみ、読み取り専用)。
型や include に現れない暗黙の結合 (重複した知識、共有された前提) のシグナル。

```bash
python3 $SKILL/git-cochange.py [--commits 3000|--since "1 year ago"] [--path SUBDIR]...
                               [--min-support 3] [--min-conf 0.5] [--top 30] [--csv] [REPO]
```

- support = 共起コミット数、confidence = max(P(B|A), P(A|B))
- 同一ディレクトリ・同一ステム (foo.h/foo.cpp) のペアと、merge・巨大コミット
  (>30 ファイル)、削除済みファイルは既定で除外 (自明・ノイズのため)
- 結合度・凝集度の観点 (checklist 2 節) をレビューするとき、対象ファイルが
  上位ペアに出ていないか確認する。上位ペアの共通化・知識の一元化は指摘候補

`$SKILL/cpp-coupling.py` — compile_commands.json の include グラフから、
モジュール間の循環依存・不安定度 I=Ce/(Ca+Ce)・fan-in を出す。
compile_commands.json は cmake の -DCMAKE_EXPORT_COMPILE_COMMANDS=ON で生成する。設計レビュー (spec-dev ゲート G2) の
「結合度が妥当か」の定量根拠に使う。使い方は --help (リポジトリの README.md
「結合度も測る」節にも読み方の要点がある)

## 手順

1. **範囲確定**: レビュー対象 (差分のあるファイル、または指定ディレクトリ) を決める。
   差分レビューなら `git diff --name-only` の結果に絞る。
2. **機械計測**: cq-metrics.py を実行し、フラグ箇所を得る。
3. **意味的レビュー**: フラグ箇所を起点に `references/checklist.md` の観点で読む。
   フラグゼロでも、変更の中心ファイルは結合度・命名・エラー処理の観点だけは確認する。
4. **報告**: 以下の表で出す。深刻度順。

| 箇所 (file:line) | 観点 | 深刻度 | 指摘 | 修正案 | 確度 |
|---|---|---|---|---|---|

   - 深刻度: 高 (バグ温床/変更困難を招く) / 中 (保守性低下) / 低 (好み・提案)
   - 確度: 高 (確実) / 中 / 低 (文脈次第) — 低確度を断定調で書かない
   - 「規約違反」と「好み」を区別する。好みは低深刻度に置く
5. **修正**: ユーザーが承認した指摘のみ修正する。複数回の試行になりそうなら
   fix-loop Skill のプロトコル (固定ガードテストセット + 1 変更 1 検証) で行う。
6. **記録の振り分け**:
   - 今直さない (後回し/見送り) 指摘 → repo 直下の TODO.md に 1 行
     (要点 + file:line + あれば S-ID + 出典レビュー notes/reviews/... へのリンク)
   - 繰り返し出る指摘 → `notes/review-log.md` に 1 行追記。
     3 回出た指摘は checklist.md への昇格をユーザーに提案する。

## ルール

- メトリクスの閾値超過をそのまま指摘にしない。「なぜこの長さ/深さが問題か」を
  具体的に言えるものだけ指摘にする。
- 修正案は具体的に (「関数化すべき」ではなく「X と Y の共通部を extractFoo() に切り出す」)。
- レビューだけ依頼された場合、修正を勝手に適用しない。
