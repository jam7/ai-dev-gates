---
name: rework
description: Handle late-discovered upstream problems (spec gaps, wrong assumptions, insufficient design/coupling) with trace-based impact analysis and a minimal, regression-guarded redo plan. Use when a requirement/spec/design problem is found after implementation started, or when the user says they need to redo work because earlier information was wrong or insufficient.
---

# rework: 手戻りの構造化プロトコル

目的: 「後から仕様の問題が分かってやり直し」を、場当たりの修正ではなく
**上流から順に直し、影響範囲を機械的に列挙し、回帰ガード付きで最小修正**する。

## 手順

### 1. 問題の層を特定する
発覚した問題が本当はどの工程の誤りかを先に確定する (症状の層で直さない):

| 層 | 典型症状 |
|---|---|
| 要件 (R) | そもそも欲しいものが違った、前提条件が違った |
| 仕様 (S) | 境界条件・エラー挙動が未定義/誤り、受入条件が検証不能 |
| 設計 (D) | 結合度が高すぎた、関数化・分割が不十分、責務の置き場所が誤り |
| 実装 | 設計は正しいがコードが設計とずれている (→ rework 不要。fix-loop で直す) |

### 2. 上流の文書を先に直す
コードを触る前に、該当する requirements.md / spec.md / design.md を修正する。
- 旧内容は消さず `~~取り消し線~~` + 「変更 (YYYY-MM-DD): 理由」で残す
  (同じ検討を繰り返さないため。設計判断の変更は ADR を追記)
- 文書がないプロジェクトの場合、最低限「何が誤りで何に変えるか」のメモを作ってから進む

### 3. 影響範囲を列挙する
変更した ID から下流をたどる:
```bash
grep -rn "R-03\|S-05" docs/ notes/          # 文書間の参照
grep -rn "S-05\|D-02" --include=*.c --include=*.h --include=*.go -r src/ test/
git log --oneline --grep="D-02"              # 関連コミット
```
トレース ID がない (spec-dev 以前の) 資産は、シンボル名・キーワードで代用し、
Serena MCP や LSP があれば参照検索を使う。

結果を**影響表**にする:

| 影響先 (文書/コード/テスト) | 影響内容 | 対処 (修正/作り直し/影響なし) | 規模感 |
|---|---|---|---|

### 4. 最小修正計画を提示し、承認を得る
- 「作り直す範囲」と「生かす範囲」を明示する。全部作り直しを既定にしない
- 生かす範囲については「なぜ影響を受けないか」を 1 行で言う
- **この計画のユーザー承認を得てから**コード修正に入る

### 5. 回帰ガード付きで修正する
fix-loop Skill のプロトコルで実施する:
- ガードテストセット = 影響表に挙がったテスト + その周辺の既存テスト
- ベースライン取得 → 1 変更 1 検証 → 台帳記録
- 影響表の項目を 1 つずつ消し込む (台帳と対応させる)

### 6. 終了処理
- R↔S↔D↔T の対応表が新しい内容で整合しているか再確認する
- 「なぜこの手戻りが起きたか」を 1 行で要件インタビュー項目 (spec-dev フェーズ 0) に
  昇格できないか検討し、できるならユーザーに提案する (同じ手戻りの再発防止)

## ルール

- 文書・コードの削除やブランチ操作など破壊的な操作は必ず事前確認する
- 影響範囲が 3 ファイル以下で層が実装のみなら、このプロトコルは過剰。fix-loop だけで進めてよい
