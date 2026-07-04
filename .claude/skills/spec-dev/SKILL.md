---
name: spec-dev
description: Gated development flow from requirements to tests with traceability IDs (R/S/D/T). Each phase has an exit checklist to catch missing information early, and IDs link requirements, spec, design, code, and tests so later changes can be traced. Use when starting a new feature/task from requirements, writing a spec or design doc, or when the user wants the requirements-to-test flow managed.
---

# spec-dev: 工程ゲート付き開発フロー

目的: 「情報不足・仕様の問題が後工程で発覚して手戻りする」ことを、
**各工程の完了条件 (ゲート)** と**トレース ID** で防ぐ。

## 成果物の置き場所と命名

```
TODO.md                                  # やることリスト (repo 直下)
docs/<feature>/requirements.md           # R-01, R-02, ... (現在の正)
docs/<feature>/spec.md                   # S-01 (実現する R を明記)
docs/<feature>/design.md                 # D-01 (実現する S を明記) + ADR
notes/YYYYMMDD-<topic>.md                # 調査メモ (作業記録)
notes/fix-sessions/YYYYMMDD-<topic>.md   # fix-loop の作業台帳
notes/reviews/YYYYMMDD-<topic>.md        # コードレビュー結果の全文 (冒頭に対象コミット)
notes/review-log.md                      # cq-review の指摘台帳
```

使い分け: docs/ は「現在の正」(要件・仕様・設計) を置き、変更時は取り消し線と理由で
履歴を残す。notes/ は「時系列の作業記録」で、上書きせず追記していく。
TODO.md は「生きたやることリスト」で、完了したら消し込む (履歴は git と notes/ に残る)。
レビュー指摘のうち今直さないものは TODO.md へ 1 行 (要点 + 場所 + あれば S-ID) で入れる。
PR ベースの開発では、レビュー結果は原則 PR コメントに残す (repo 内には置かない)。
notes/reviews/ は PR を使わないローカルレビューの全文を残したい場合に使う。

テンプレートはこの Skill の `templates/` にある。コミットやテストコメントにも
ID を書く (例: `// T-03: S-02 boundary case`)。この ID が後の影響範囲調査 (/rework) の索引になる。

## ゲートの機械チェック: trace-matrix.py

`trace-matrix.py` はこの SKILL.md と同じディレクトリにある。`$SKILL` はこの Skill の
ディレクトリ (ホーム導入なら `~/.claude/skills/spec-dev`、プロジェクト導入なら
`<repo>/.claude/skills/spec-dev`)。

```bash
python3 $SKILL/trace-matrix.py [--code src/ --code test/] [--matrix] docs/<feature>/
```

R/S/D/T の定義と参照を走査し、「spec にカバーされていない R」「design にカバーされていない S」
「テストが参照していない S」「未定義 ID の参照 (typo)」「二重定義」を検出する。
問題があると exit 1。ゲート G1 / G2 / G4 の対応表確認は目視でなくこれを実行する
(テストファイルは --code のパス中の名前に test を含むもの。T-ID はテスト内の
コメントが定義扱い)。`--matrix` で全 ID の対応表 (Markdown) も出せる。

## フェーズと出口ゲート

各ゲートの通過は**ユーザーの承認**を得てから次へ進む。ゲートで落ちた項目は
「未確定事項」として requirements.md に残し、勝手に仮定で埋めない
(仮定するなら「仮定:」と明記して承認を得る)。

### フェーズ 0: 調査・要件整理 → requirements.md
まず AI がユーザーに**要件インタビュー**を行う:
1. このタスクが解決する問題は何か。誰が使うか
2. 入力と出力の具体例 (正常系 1 つ、異常系 1 つ以上)
3. 境界条件 (0/空/最大/同時/失敗時)
4. 非機能要件 (性能、メモリ、互換性、対応環境)
5. 制約 (既存コードとの整合、変更してはいけない部分)
6. やらないこと (スコープ外の明示)

既存の notes/ を先に grep し、既知情報を質問しない。調査した内容は notes/ に保存する。

**ゲート G0**: 全 R に受入可能な形の記述がある / 未確定事項リストが空または承認済み /
「やらないこと」が 1 つ以上書かれている

### フェーズ 1: 仕様 → spec.md
各 S 項目は「どの R を実現するか」と「受入条件 (検証可能な形)」を持つ。

**ゲート G1**:
- 全 R がいずれかの S でカバーされている (対応表で確認)
- 曖昧語が残っていないか: 「適切に」「必要に応じて」「など」「高速に」「柔軟に」
  「原則として」を grep し、残す場合は定義を付ける
- 全 S に境界条件・エラー時の挙動が書かれている
- 受入条件は機械またはテストで判定可能な形か

### フェーズ 2: 設計 → design.md
モジュール分割、インタフェース (シグネチャレベル)、データフロー、エラー伝播を書く。
重要な判断は ADR ブロック (背景/選択肢/決定/理由) で残す。

**ゲート G2 (設計レビュー)**:
- 全 S がいずれかの D でカバーされている
- 各モジュールの責務が 1 文で言えるか (言えない = 凝集度不足)
- モジュール間の依存が一方向か。循環依存がないか
- インタフェースは呼び出し例が書けるレベルに具体化されているか
- エラーの発生源と処理場所が決まっているか
- 「この設計でテストを書けるか」を T の視点で確認 (テスト容易性)
- 結合度: ある S の変更が複数 D に波及しないか (するなら分割を再考)

### フェーズ 3: 実装
- D 単位で実装し、コミットメッセージに D-ID を含める (英語)
- AI 実装の場合: 複数回試行になりそうなら fix-loop Skill のプロトコルで進める
- 実装完了時に cq-review Skill でレビューし、指摘を解消してから人間レビューへ
- 人間レビュー依頼時は self-review Skill のレビューパックを付ける

**ゲート G3**: ビルドが通る / cq-review の高深刻度指摘ゼロ / 全 D に対応する実装がある

### フェーズ 4: テスト組み込み
spec.md の受入条件 1 つにつき最低 1 つのテスト (T-ID) を作る。
テストには対応する S-ID をコメントで書く。

**ゲート G4**:
- 全 S の受入条件に T が対応している (「仕様にあってテストにない ID」がゼロ)
- 境界条件・異常系のテストが正常系と同数程度あるか
- テストは実装前に失敗し実装後に通ることを確認したか (可能な場合)
- lit ベースなら結果の確認は triage Skill を使う

## 途中で問題が見つかったら

上流 (要件・仕様・設計) の誤り・不足が見つかった場合は、その場で直さず
**/rework** (rework Skill) に切り替える。トレース ID による影響範囲分析から始める。
