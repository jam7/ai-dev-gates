---
name: triage
description: Triage lit test failures from check-* logs. Extracts FAIL/XPASS/UNRESOLVED/TIMEOUT, diffs against a baseline or previous run, investigates new failures, and produces a classified report. Use when the user asks to triage/analyze test results, check a lit log, or compare test runs.
---

# lit テスト失敗トリアージ

対象: llvm-lit ベースのテストログ (make check-llvm / check-clang / ninja check-* など)。
どのプロジェクトでも使える。プロジェクト固有の事情 (既知の失敗、方針) は各プロジェクトの
CLAUDE.md や test-baselines/ を参照する。

## ツール

`parse-lit-log.py` — この SKILL.md と同じディレクトリにある (stdlib のみ、Python 3.6+)。
以下 `$SKILL` はこの Skill のディレクトリを指す (ホーム導入なら `~/.claude/skills/triage`、
プロジェクト導入なら `<repo>/.claude/skills/triage`)。

```bash
python3 $SKILL/parse-lit-log.py summary <log>...     # 集計+失敗一覧
python3 $SKILL/parse-lit-log.py fails <log>...       # 失敗名のみ (機械可読)
python3 $SKILL/parse-lit-log.py diff <old> <new>     # NEW/FIXED/STILL
python3 $SKILL/parse-lit-log.py detail <log> [pat]   # 失敗の詳細ブロック
python3 $SKILL/parse-lit-log.py save <log> <base>    # ベースライン保存
python3 $SKILL/parse-lit-log.py check <log> <base>   # ベースライン比較
```

check / diff は NEW failure があると exit 1 を返す (スクリプトからの利用向け)。

## 手順

1. **抽出**: `summary` でログ全体の状況を把握する。巨大ログを直接 Read しない。
2. **比較基準の確定**:
   - プロジェクトに `test-baselines/` があれば最新ベースラインと `check`
   - 前回のログが指定されていれば `diff`
   - どちらも無ければ全失敗を NEW として扱い、ベースライン作成を提案する
3. **NEW failure の調査** (1 件ずつ):
   - `detail <log> <テスト名の一部>` で失敗詳細を取得
   - テストファイル本体を読み、何を検証するテストか把握する
   - `git log --oneline -10 -- <テストファイル> <関連ソース>` で最近の変更を確認
   - 分類する:
     - **regression**: 最近の自分/マージの変更が原因
     - **test-update-needed**: 実装は正しいがテストの期待値が古い
     - **environment**: ツールチェーン/環境依存 (パス、バージョン、並列数)
     - **flaky**: タイミング依存・再実行で通る可能性
     - **pre-existing**: ベースライン漏れの既知問題
4. **報告**: 以下の表で出す。

| テスト | 種別 | 分類 | 原因 (推定) | 推奨アクション | 確度 |
|---|---|---|---|---|---|

5. **ベースライン更新**: `save` の実行は**必ずユーザー確認を取ってから**。
   NEW failure を調査せずにベースラインへ入れて隠さない。

## ルール

- ログ・テスト・ソースの読み取りは自由に行ってよい。ビルドやテストの再実行
  (make / ninja / apptainer 等) はプロジェクトのルールに従い、必要ならユーザーに確認する。
- 原因が確定できない場合は「確度: 低」と明記し、確認に必要な次の一手 (実行すべきコマンド) を添える。
- FAIL 0 件のときも summary の数値 (Passed/Unsupported 等) を報告し、前回と大きな乖離が
  ないか (テスト数の急減など) を確認する。
