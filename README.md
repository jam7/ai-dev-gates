# AI 開発支援 Skill 集 — 使い方ガイド

> **English**: A set of agent skills (`SKILL.md` instructions) and small
> stdlib-only Python scripts that keep AI-assisted development verifiable.
> Each one is a gate: requirements to tests with traceable IDs, a fixed guard
> set before any fix attempt, a metrics-backed review, and an opt-in commit
> hook that fails on findings nobody has declared a reason for. Works with
> Claude Code and GitHub Copilot — both read `.claude/skills/`. Everything
> runs locally; no services, no network. The guide below is in Japanese.

AI に「開発の進め方」を教え込むための Skill (指示書) 集です。
要件整理からテスト、手戻り対応までの開発の流れ全体を、AI と一緒に安全に回せるようにします。

- 対象: **Claude Code / GitHub Copilot** を使って開発する人 (AI 利用が初めてでも OK)。
  Skill の置き場所 `.claude/skills/` は両方が読み、frontmatter の書式も共通なので、
  導入手順は同じです
- 特徴: 全部ローカルで動く。外部サービス・課金・ネットワーク不要。
  スクリプトは Python 標準ライブラリのみ

## インストール

このリポジトリを clone して `install.sh` を実行します。導入先は 2 通りあります。

### A. プロジェクトに導入する (チーム試行はこちらを推奨)

対象リポジトリの `.claude/skills/` にコピーし、**リポジトリの一部として git 管理**します。
clone した全員に Skill が行き渡り、個人ごとのインストール作業が不要になります。

```bash
git clone https://github.com/jam7/ai-dev-gates.git
cd ai-dev-gates
./install.sh /path/to/your-repo     # <repo>/.claude/skills/ にコピー
cd /path/to/your-repo
git add .claude/skills CLAUDE.md
git commit -m "Add AI dev skills"
```

プロジェクト導入では、**人間向けの運用規約をまとめた CLAUDE.md** もテンプレートから
生成されます (docs/ = 現在の正、notes/ = 追記のみの記録、TODO.md = 消し込むリスト、
トレース ID の説明など)。Skill も CLAUDE.md も Markdown なので、チームの規約に
合わせた変更をコミットで共有できます。

`--hooks` を付けると、コミット時に自動で走るゲート (第 9 章) も一緒に入ります。

### B. 自分のホームに導入する (個人で常用する場合)

```bash
git clone https://github.com/jam7/ai-dev-gates.git
cd ai-dev-gates
./install.sh        # ~/.claude/skills/ にコピー。全プロジェクトで有効
```

インストール後に Claude Code / Copilot を起動 (プロジェクト導入ならそのリポジトリ内で)
すると自動的に認識されます。両方に同名 Skill を入れると紛らわしいので、
試行期間はプロジェクト側に寄せるのがおすすめです。

### 更新のしかた (上書きは起きない)

新しい版を取り込むときは、**clone したこのリポジトリを `git pull` してから
install.sh を再実行**します。

```bash
cd /path/to/ai-dev-gates
git pull
./install.sh /path/to/your-repo --hooks --force
```

install.sh は**書き込む前に全ての配置先を調べ、1 つでも上書きになるならエラーで
何もせず終了します**。チームが編集したルールや手を入れたフックを、再実行で
失うことがないようにするためです。だから更新時は `--force` が要ります。

`--force` を付けても次の 2 つは保持されます。こちら側から再生成できない、
チームの判断そのものだからです。

- `coding-rules/rules/*.md` — チームが編集したルール (`*.template.md` だけ更新)
- `tools/cq-baseline.txt` / `tools/test-vocabulary.txt` — 宣言ファイル (第 9 章)

**パスの読み替え**: この README のコマンド例は `~/.claude/skills/...` (ホーム導入) で
書いてあります。プロジェクト導入の場合はリポジトリ直下からの `.claude/skills/...` に
読み替えてください (例: `python3 .claude/skills/cq-review/cq-metrics.py src/`)。

## まず 5 分で試す

自分のコードに対して品質計測を 1 回走らせてみるのが一番早いです。

```bash
python3 ~/.claude/skills/cq-review/cq-metrics.py src/
```

長すぎる関数・深いネスト・長い引数リスト・コピペ重複の候補が一覧で出ます。
「おっ」と思ったら、この README の続きを読んでください。

## 全体像: 開発の流れと道具の対応

```
 要件 ──→ 仕様 ──→ 設計 ──→ 実装 ──→ レビュー ──→ テスト
 └────────── spec-dev (工程ゲート + トレースID) ──────────┘
                            │           │           │
                      coding-rules   cq-review    triage
                      + fix-loop   (品質レビュー  (テスト失敗
                     (規約の適用と    の自動化)     の分析)
                      試行錯誤の暴走防止)
                            │
              self-review (AI成果物にレビューパックを添付)

 ↑ 問題が後から発覚したら…
 └───────────── rework (必要な所だけやり直す) ─────────────┘

 ↑ どの工程でも、会話が長くなったら…
 └── prepare-compact (消えて困る情報をファイルへ出してから圧縮する) ──┘
```

| Skill | 一言でいうと | 使う場面 |
|---|---|---|
| **spec-dev** | 要件→仕様→設計→実装→テストを関所 (ゲート) 付きで進める | 新しい機能・タスクの開始時 |
| **fix-loop** | 「直したら別が壊れた」のモグラたたきを防ぐ | バグ修正、複数回試行しそうな作業 |
| **coding-rules** | 書く時点で規約と Clean Code 原則を適用する (ルールは .md で追加・削除可) | AI にコードを書かせるとき常時 |
| **cq-review** | 関数化・結合度・ネストなどの品質レビューを自動化 | 実装後、人間レビューの前 |
| **self-review** | AI の成果物に「どこを見ればいいか」を付けさせる | AI にコードや設計を作らせたとき常時 |
| **triage** | テストログから失敗を抽出・分類・前回比較 | テスト実行後 |
| **rework** | 影響範囲を特定して必要な所だけやり直す | 仕様漏れ・設計ミスが後から発覚したとき |
| **prepare-compact** | 会話を圧縮する前に、消えて困る情報をファイルへ退避させる | 長い作業でコンテキストが限界に近づいたとき |

Skill は「`/spec-dev` のようにコマンドで呼ぶ」「会話で『spec-dev で進めて』と言う」の
どちらでも使えます。該当する場面では AI が自分から使うこともあります
(Copilot も frontmatter の description を見て同じように判断します)。

このほかに、Skill ではない**コミットゲート** (git hooks) が同梱されています。
決めたことを人間にも機械的に守らせる仕組みですが、**入れるのは新規プロジェクトか、
返済が終わったプロジェクトだけ**です (第 9 章)。

---

## 1. 新しいタスクを始める — spec-dev

**困りごと**: 曖昧なまま作り始めて、あとで「そういう意味じゃなかった」「この場合を
考えてなかった」となり、大きく手戻りする。

**解決**: 工程ごとに「完了条件 (ゲート)」を置き、通過はあなたが承認します。
さらに要件・仕様・設計・テストに ID (R-01, S-01, D-01, T-01) を振って相互参照するので、
あとで問題が出ても「どこに影響するか」が機械的に追えます。

### 使ってみるとこうなる

```text
あなた: 設定ファイルの読み込み機能を追加したい。spec-dev で進めて。

Claude: 要件を整理させてください。いくつか質問します。
  1. 対応する形式は何ですか (YAML / JSON / 独自形式)
  2. 設定ファイルが存在しない・壊れているときの期待動作は?
     (エラー終了 / デフォルト値で継続 / 警告して継続)
  3. 環境変数やコマンドライン引数との優先順位はありますか?
  4. 「やらないこと」を確認: 設定の動的リロードは今回のスコープ外でよいですか?

あなた: YAML。壊れてたらエラー終了。優先順位は 引数 > 設定ファイル。リロードは対象外。

Claude: docs/config-loader/requirements.md に書き出しました。
  R-01: YAML 設定ファイルの読み込み
  R-02: 不正ファイル時はエラーメッセージを出して終了
  R-03: コマンドライン引数が設定ファイルより優先
  やらないこと: 動的リロード
  未確定事項が 1 件あります: 「設定キーが未知だったとき」の挙動が未定義です。
  警告して無視 / エラーのどちらにしますか?
```

この「未確定事項」の指摘が spec-dev の価値です。**作り始める前に**穴が見つかります。
以降、仕様 (spec.md)→設計 (design.md)→実装→テストと進み、各ゲートであなたが承認します。

ゲートの対応表確認 (「全要件が仕様でカバーされているか」など) は目視ではなく、
付属の `trace-matrix.py` が機械的に行います:

```text
$ python3 ~/.claude/skills/spec-dev/trace-matrix.py --code src/ --code tests/ docs/config-loader/
== Definitions ==
  R: 3, S: 3, D: 2, T: 3
== Problems: 1 ==
  S-02: no test references it
```

「S-02 (不正ファイル検出) にテストがない」が一目で分かります。問題ゼロで exit 0 に
なるので、CI のチェックに入れることもできます。

**初心者向けのコツ**: 数行の修正にこの流れは大げさです。「新しい機能」「2 日以上かかりそう」
が目安。小さい修正はそのまま頼んで OK。

## 2. 実装と試行錯誤 — fix-loop

**困りごと**: AI に修正を頼むと「A を直したら B が壊れ、B を直したら A が壊れる」の
無限ループ (モグラたたき) に陥ることがある。

**解決**: 最初に「壊してはいけないテストのセット (ガード)」を固定し、
**1 回に 1 変更**、毎回ガード全部を確認、結果をすべて台帳に記録します。
後退したら次に進まず巻き戻します。3 回連続で進展がなければ手を止めて原因分析に戻ります。

### 使ってみるとこうなる

```text
あなた: このテスト失敗を直して。前に似た修正で別のテストが壊れたことがあるから fix-loop で。

Claude: fix-loop で進めます。
  目標: parser_test の escape_string ケースを通す
  ガードセット: parser_test 全体 + 過去にこの領域で壊れた tokenizer_test (計 42 テスト、約 2 分)
  ベースライン取得中… escape_string のみ FAIL、他 41 PASS。台帳 notes/fix-sessions/20260704-escape.md を作成。

  試行 1: エスケープ処理の順序が原因と仮説。unescape() の \\ 処理を最後に移動。
  → ガード実行: escape_string PASS、しかし raw_string が FAIL に後退。
  この変更は巻き戻します。raw_string が壊れた理由から、原因は順序ではなく
  raw モード判定の欠落と分かりました。

  試行 2: unescape() に raw モードの早期 return を追加。
  → ガード実行: 42 テスト全部 PASS。ベースライン比で純改善 +1、後退 0。
```

ポイントは試行 1 で「壊れたまま次に進まない」こと。台帳が残るので、
次に同じ場所を触るときは「ここは raw_string が壊れやすい」が引き継がれます。

## 3. AI の成果物を受け取る — self-review

**困りごと**: AI が出したコードや設計を全部読んで検証するのに時間がかかる。

**解決**: AI に成果物と一緒に「レビューパック」(根拠・影響範囲・テスト証跡・
重点確認ポイント) を出させます。あなたは重点確認ポイントから読めば済みます。

**発動条件**: この Skill は人間が呼ばなくても動きます。各 Skill には「どういう場面で
使うか」の記述 (description) があり、AI はそれを常に見ています。self-review の
発動条件は「パッチ・設計・複数ファイル変更を人間のレビューに出すとき」なので、
**AI が成果物を提示しようとしたタイミング**で自動的に適用されます (自明な数行の
変更には付きません)。ただし自動発動はベストエフォートなので、確実に効かせたいときは
「レビューパック付きで出して」と言うか、プロジェクトの CLAUDE.md に
「コードを提示するときは self-review を適用する」と 1 行書いてください。

### 使ってみるとこうなる (下の例に人間の発言がないのは、AI がパッチを出す側だから)

```text
Claude: (パッチ本体のあと…)
  ---
  ## レビューパック
  変更の要約: 設定キーの重複時に後勝ちだった挙動を、警告付き後勝ちに変更。
  根拠: R-02 のエラーメッセージ要件に対し、重複は「不正」ではなく「警告」と仕様化 (S-04)。
  影響範囲: config_loader.cpp のみ。呼び出し元 3 箇所は戻り値の型が不変のため影響なし (grep で確認済み)。
  テスト証跡: ctest -R config 実行、12/12 PASS。重複キーの新規テスト T-07 を追加済み。
  重点確認ポイント:
    1. config_loader.cpp:88 — 警告の出力先を stderr にしたが、ログ機構に乗せるべきかは判断が必要
    2. 仕様上「3 個以上の重複」の文言が曖昧なまま (S-04 に注記)
  ---
```

「テスト証跡: 未実行」と正直に書くルールなので、**未実行のまま「動くはず」と
言わせない**のが肝です。重点確認ポイントは「AI が自信のない順」に並びます。

## 4. コード品質のレビュー — cq-review

**困りごと**: 関数化は十分か、結合度は妥当か、ネストが深すぎないか… といった
Readable Code / Clean Code 観点のレビューは、観点が多くて全読みになりがち。

**解決**: 機械で測れるもの (関数の長さ・ネストの深さ・引数の数・コピペ重複) は
スクリプト `cq-metrics.py` が数秒で洗い出し、AI はその候補に対して
「本当に問題か、どう直すべきか」の判断だけを行います。指摘は深刻度・確度付きの表で出ます。

### 使ってみるとこうなる

```text
あなた: 今回の変更を cq-review でレビューして。

Claude: 変更ファイル 3 つを計測しました。
  == Long functions (> 60 lines): 1 ==
    src/loader.cpp:120  parseConfig()  95 lines
  == Deep nesting (> 4 levels): 1 ==
    src/loader.cpp:158  parseConfig()  depth 6
  == Duplicated blocks (>= 8 significant lines): 1 ==
    ~11 lines x 2 sites: src/loader.cpp:203, src/loader.cpp:241

  意味的レビューの結果:

  | 箇所 | 観点 | 深刻度 | 指摘 | 修正案 | 確度 |
  |---|---|---|---|---|---|
  | loader.cpp:158 | ネスト | 高 | 6 段ネストの中心はエラー分岐。読解も変更も困難 | ガード節で早期 return に書き換え (3 段になる) | 高 |
  | loader.cpp:203,241 | 重複 | 中 | 型変換+検証の 11 行が 2 箇所で同一 | validateAndConvert() に切り出し | 高 |
  | loader.cpp:120 | 関数長 | 低 | 95 行だが内容はキー種別の列挙で凝集している | 分割は不要と判断。指摘のみ | 中 |

あなた: 1 と 2 だけ直して。

Claude: 承知しました。2 件なので fix-loop は使わず、修正後に既存テストで確認します。
```

3 件目のように「閾値超過でも問題なし」と判断させるのが特徴です。
機械的なしきい値警告を人間が仕分ける、の逆をやります。

スクリプト単体でも使えます (AI 不要、CI に入れることも可能):

```bash
python3 ~/.claude/skills/cq-review/cq-metrics.py --max-nest 4 src/
```

対象は波括弧系の言語 (C/C++/Go/Java/JS/TS/Rust/Dart/Kotlin/Swift/C#) と
**Python** です。Python もパーサーは使わず、`def` を正規表現で拾って本体を
インデントの段数で数えます。他言語と同じ「ざっくり測る」精度で、
`elif` の連鎖は波括弧の `} else if (...) {` と同様に 1 段と数えます。

**関数の長さはコード行数で、コメントと空行は数えません。** 説明を書き足したら
「長すぎる」と言われるのでは、指標が説明を書くなと言っていることになるためです
(実際にこのツール自身がその状態になりました)。コメントの多いコードほど従来より
指摘が減ります。LLVM で測ると 3-4 割減りました。

### 結合度も測る — git-cochange.py / cpp-coupling.py

cq-metrics.py が見るのは 1 ファイル内の形だけです。「触ると別の場所が壊れる」という
**結合の問題はファイルをまたぐ**ので、cq-review には補助ツールが 2 つ同梱されています。
どちらも読み取り専用・stdlib のみで、cq-review の意味的レビューの材料になります。

**(1) git-cochange.py — 履歴から隠れた結合を探す** (準備不要、これだけで動く)

```bash
python3 ~/.claude/skills/cq-review/git-cochange.py --commits 3000 .
```

```text
== Co-change pairs (support >= 3, confidence >= 0.50) ==
    7x  conf 0.88  src/parser.cpp(8)  <->  src/codegen/emit.cpp(7)
    5x  conf 1.00  src/opts.cpp(5)  <->  docs/options.md(5)
```

support = 同一コミットで一緒に変わった回数、confidence = 片方が変わったとき
もう片方も変わる確率です。**別ディレクトリ・別名なのに confidence が高いペアが
暗黙の結合の候補** (重複した知識、共有された前提、片方だけ直すと壊れる関係)。
型や include には現れないので、静的解析では見つかりません。
自明なペア (同一ディレクトリ、foo.h/foo.cpp) と巨大コミットは既定で除外済みです。

**(2) cpp-coupling.py — include グラフからモジュール間の依存を測る** (C/C++)

`compile_commands.json` が必要です (`cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`。
configure だけで生成され、ビルドは不要)。

```bash
python3 ~/.claude/skills/cq-review/cpp-coupling.py --root src --module-depth 2 \
        build/compile_commands.json
```

```text
== Module cycles: 1 ==
  src/parser <-> src/sema
== Module metrics (top fan-in) ==
  src/support                    Ca=52  Ce=2   I=0.04
  src/sema                       Ca=18  Ce=21  I=0.54 [cycle]
```

- **Module cycles** (モジュール間の循環依存) が設計上の最優先課題です
- I = 不安定度 = Ce/(Ca+Ce)。**Ca が大きくても I ≈ 0 なら健全**
  (安定したものに皆が依存するのは正しい形)。危ないのは
  「よく変わるもの (I が高い) に多数がぶら下がっている」パターンです
- `--module-depth` はモジュール = ディレクトリの深さ。まず 2 で実行し、
  出てくる名前が「設計単位」として自然になる深さに調整します

設計レビュー (spec-dev のゲート「結合度が妥当か」) の定量的な根拠としても使えます。
両ツールの詳細は `--help` を参照してください。

## 5. コーディング規約を守らせる — coding-rules

**困りごと**: AI に実装を頼むと、動くけれど規約や Clean Code の原則から外れたコードが
出てくる。レビューで直させると往復が増える。

**解決**: 書く前にルールファイルを読み込ませ、書く最中に適用させます。ルールは
`.claude/skills/coding-rules/rules/*.md` にあり、**チームが .md を追加・編集・削除して
git で共有できます**。デフォルト (Clean Code の要点。cq-review のチェックリストと共通) は
同梱済みで、スキルを更新してもチームのルールは install.sh が保持します。

### 使ってみるとこうなる

```text
あなた: 設定ファイルのマージ処理を実装して。

Claude: coding-rules のルールを読み込みます: 00-principles.md, 10-naming.md の 2 ファイル。
  周囲のコード (config/ 以下) の流儀を確認… 命名は snake_case、エラーは Result 型で伝播。
  実装します。

  (実装コード…)

  ## レビューパック
  (中略)
  準拠メモ:
  - 適用: 00-principles (関数 60 行以内 → merge を 3 関数に分割)、10-naming (単位接尾辞)
  - 既存流儀を優先: エラーメッセージの文体はルールでなく既存コードに合わせた
  - cq-metrics 確認済み: 変更ファイルに新規フラグなし
```

### チームのルールを足す・消す

```bash
vi .claude/skills/coding-rules/rules/10-naming.md   # 追加 (書式は 90-rule-format.md)
rm .claude/skills/coding-rules/rules/00-principles.md  # デフォルトの無効化も可
git add -A && git commit -m "Add naming rules"
```

細部 (命名スタイルなど) は周囲の既存コード優先、構造 (関数化・重複・ネスト) は
ルール優先、という使い分けなので、既存コードベースに入れても差分が汚れません。

## 6. テスト結果の確認 — triage

**困りごと**: テストログが数千〜数万行。どれが新しい失敗でどれが既知か、
毎回目視で探している。(lit = LLVM 系のテストツール。make check-llvm などのログが対象)

**解決**: スクリプトが FAIL/XPASS/UNRESOLVED/TIMEOUT を抽出し、ベースライン
(既知の失敗リスト) や前回ログと比較して「新規/直った/既知」に自動分類。
AI は新規失敗だけを調査して分類レポートを出します。

### 使ってみるとこうなる

```text
あなた: check-llvm.log をトリアージして。ベースラインは test-baselines/develop.txt。

Claude: 比較しました: 全 62784 テスト中、失敗 3 件。
  NEW failures (1): FAIL: LLVM :: CodeGen/RISCV/rvv/setcc.ll
  STILL failing (2): (既知のため調査スキップ)

  新規失敗を調査します。
  … setcc.ll の失敗は CHECK 行の期待値と生成コードのレジスタ割当の差分です。
  直近の変更 abc1234 (スケジューラ調整) 以降に発生しており、生成コードは
  正しく命令数も同じです。分類: test-update-needed (テスト期待値の更新で対応)。

  | テスト | 分類 | 原因 | 推奨アクション | 確度 |
  |---|---|---|---|---|
  | rvv/setcc.ll | test-update-needed | abc1234 でレジスタ割当が変化 | CHECK 行を更新 | 高 |
```

ベースラインの更新 (「この失敗は既知としてよいか」) は必ず人間の承認を取ります。
調査せずに失敗を「既知」に押し込んで隠すことはしません。

## 7. 問題が後から発覚した — rework

**困りごと**: 実装まで進んだあとで「仕様に漏れがあった」「関数の分け方が悪かった」と
判明。どこまで戻ってやり直せばいいか分からず、全部見直しになりがち。

**解決**: まず「どの工程の誤りか」を特定し、上流の文書 (仕様書・設計書) を先に直します。
次にトレース ID (spec-dev で振ったもの) を grep して**影響を受ける箇所だけ**を列挙し、
最小の修正計画をあなたに承認してもらってから、fix-loop の回帰ガード付きで直します。

### 使ってみるとこうなる

```text
あなた: 設定ファイルの機能、環境変数でも上書きできる必要があった。
       要件から漏れてた。rework で対応して。

Claude: 問題の層は「要件」です。requirements.md に R-04 (環境変数による上書き、
  優先順位: 引数 > 環境変数 > ファイル) を追加し、変更履歴を残しました。

  影響範囲を調べます: grep で R-04 関連 (優先順位 S-02) の下流を追跡…

  | 影響先 | 影響内容 | 対処 | 規模感 |
  |---|---|---|---|
  | spec.md S-02 (優先順位) | 3 段階に変更 | 修正 | 小 |
  | design.md D-01 (Loader) | 読み込み元の追加 | 修正 | 小 |
  | design.md D-02 (Merger) | 優先順位ロジック変更 | 修正 | 中 |
  | src/loader.cpp | D-01 対応 | 修正 | 小 |
  | src/merger.cpp | D-02 対応 | 修正 | 中 |
  | tests/ T-03, T-04 | 優先順位のケース追加 | 修正+追加 | 中 |
  | S-01/S-03 系 (パース・エラー処理) | 優先順位と独立 | **影響なし** | - |

  つまり、パース処理とエラー処理はそのまま生かせます。作り直すのは
  優先順位まわりの 2 モジュールとテストだけです。この計画で進めてよいですか?

あなた: OK。

Claude: fix-loop で進めます。ガードセット: config 関連テスト全部…
```

「影響なし」の行に注目してください。**全部やり直さない**ための根拠を AI が示し、
必要な所だけを、回帰を監視しながら直します。これが手戻りコストを最小にする仕組みです。

## 8. 会話が長くなってきた — prepare-compact

**困りごと**: 長い作業を続けると Claude のコンテキスト (会話の記憶) が限界に達し、
自動で要約されます。要約は劣化するので、「却下したはずの案を再提案してくる」
「さっき訂正した間違いを繰り返す」が起きます。`/compact` を手で打っても同じです。

**解決**: 圧縮の前に、会話にしか無い情報を洗い出して**ファイルへ書き出します**
(設計判断は ADR、残タスクは TODO、繰り返し効く指示は memory)。
書けたものは圧縮の引数から外し、**どこにも書けなかった数項目だけ**を
`/compact` の引数文字列にまとめて渡します。要約に頼らないのが要点です。
書き出す先は**そのプロジェクトが既に使っている場所**が優先で (CLAUDE.md の
ディレクトリ規約、無ければ既存ファイルの置き方に合わせる)、下の例はこのリポジトリの
規約の場合です。

### 使ってみるとこうなる

```text
あなた: コンテキストがそろそろ限界。compact する前に整理して。

Claude: 会話にしか無い情報を洗い出しました。まずファイルに出せるものを出します。
  - 却下案「Loader を 2 クラスに分ける」とその理由 → docs/config-loader/design.md の ADR-03 に追記
  - 残タスク 3 件 → TODO.md に追記
  - 「警告は stderr でなくログ機構へ」という指示 → memory に保存 (type: feedback)

  残りは 2 件だけです。この引数で実行してください:

  /compact config-loader の実装中。S-04 (重複キー警告) まで実装・テスト済みで次は T-07 の追加。詳細は docs/config-loader/design.md と TODO.md にある。会話にしか無い点: (1) 未 push のコミットが 2 本あり、レビューまでブランチを切り替えない (2) ctest -R config は -j1 で走らせる (並列だと一時ファイルが衝突する。今日訂正した点)

  残す理由: (1) は一時的な作業状態でファイルの置き場所がない、(2) は暗黙知で
  ドキュメント化の判断がまだできていないため。
  残さないもの: 却下案・残タスク・指示は上のファイルに書いたので引数から外しました。
```

`/compact` はユーザーのコマンドなので Claude 側から実行できません。**引数を提示するところまで**が
この Skill の仕事です。「残さないもの」を明示させるので、「あれは入れなくていいのか」と
確認する手間がなくなります。

実データ (実機のホスト名・実パス・ログ) を repo に書かない取り決めがあるプロジェクトでは、
圧縮の引数にも書きません (引数は会話に残り、要約経由でコミットメッセージに紛れ込みえるため)。

---

## 9. 決めたことを維持する — コミットゲート (git hooks)

ここまでの Skill は Claude への指示書ですが、この章だけは**人間にも機械的に効く
ゲート**です。`./install.sh <repo> --hooks` で入り、`git commit` / `git push` のたびに
自動で走ります (Claude Code や Copilot がコミットするときも同じように止まります)。

**先に読んでください**: これは**きれいなリポジトリを維持するための道具**であって、
汚れたリポジトリを掃除する道具ではありません。入れどきの判断は「いつ入れるか」節に
あります。途中まで進んだプロジェクトなら、まだ入れないのが正解です。

**困りごと**: レビューで直しても、次のコミットでまた長い関数や重複が増える。
かといって「60 行超えたら弾く」にすると、意図的に長い関数まで弾かれて誰もが
`--no-verify` を使うようになる。

**解決**: 閾値ではなく**宣言**をゲートにします。cq-metrics.py が出したフラグは、
`tools/cq-baseline.txt` に理由付きで 1 行書かれていなければコミットが通りません。
**その 1 行を書くことがレビュー**です。

### 使ってみるとこうなる

```text
$ git commit -m "add archive reader"
Undeclared structural findings:
  src/big.go:3  Big()  69 lines

Either restructure, or add the key to tools/cq-baseline.txt with the reason it is worth keeping.
The keys are:
  long src/big.go::Big
```

直すか、`tools/cq-baseline.txt` に理由を書くかの二択になります。

```text
# 仕様書と並べて読めることに価値がある。分割すると対応が追えなくなる
long src/big.go::Big
```

キーに**行番号を含まない** (`long <path>::<function>`) ので、編集で揺れません。
逆に、**baseline にあるのにもう検出されない項目も報告されます**。「もう存在しない
コードのために守り続けている判断」が溜まるのを防ぐためです (元プロジェクトでは
5 件中 3 件が陳腐化していました)。

### もう 1 つのゲート: 私的データの流出防止

`tools/check-private.py` は、ホーム配下の絶対パス・プライベート IP・長い数値 ID を
全ファイルで弾きます。さらに**語彙リスト方式**の検査があります: テストデータや
ドキュメントの例に出てくる「内容らしきもの」(区切りを含むパス、メディアファイル名、
CJK 文字列) は、`tools/test-vocabulary.txt` に宣言された名前だけで組み立てる、という
ルールです。

拒否リストではなく許可リストなのが肝です。**拒否リストは誰かが思いついた名前しか
止められませんが、語彙方式なら「誰も知らなかった名前」が止まります**。実データを
ログからコピペしてテストに貼る、という事故がまさにそれです。

語彙リストは強力な反面うるさいので、**`tools/test-vocabulary.txt` を置いたときだけ
有効**になります (置くまでは構造チェックだけ)。有効にするには同梱の
`tools/test-vocabulary.template.txt` をコピーして書き足してください。

`pre-push` では、push される**全リビジョンとコミットメッセージ**を検査します。
pre-commit は 1 コミットずつしか見ないので、「追加して後のコミットで消した」データが
中間リビジョンに残ったまま公開されるためです (実際にこれで漏れた事例があります)。

### 設定

PJ 固有の設定は `.githooks/pre-commit` の先頭 2 行だけです。

```sh
ext=".dart"        # 構造チェックの対象拡張子 (空 = 全部)
scope="lib src"    # 対象ディレクトリ (空 = リポジトリ全体)
```

### いつ入れるか — 「入れない」判断が重要です

**入れるのは、新規プロジェクトの最初か、返済が打ち止めになったあとだけです。**

途中まで進んだプロジェクトに入れると、初回から大量に落ちます。そこで
`check-metrics.py --list` の結果をそのまま `cq-baseline.txt` に流し込みたくなりますが、
**それをやると宣言ファイルが「債務の置き場」になり、この仕組みは死にます**。
宣言の値打ちは「1 行書くことがレビューになる」点にあるので、理由を書けない行が
並んだ時点でただの無視リストです。しかも大量に並ぶと、そこに新しい指摘が
紛れ込んでも誰も気づきません。

途中のプロジェクトでは、代わりに **cq-review (第 4 章) で返済します**。第 10 章の
手順でバッチに分けて潰していき、**「残っているものは全部、理由を書ける意図的な判断だ」
と言える状態になってから**ゲートを入れてください。そのとき初めて、`cq-baseline.txt` は
最初から「意図的に残している構造の一覧」として書けます。

| 状況 | 使うもの |
|---|---|
| 新規プロジェクト | 最初からゲートを入れる (違反ゼロから始まる) |
| 途中まで進んでいる | cq-review で返済する。ゲートはまだ入れない |
| 返済が打ち止めになった | 残りを理由付きで宣言し、ゲートを入れる |

## 10. 既存プロジェクトに後から導入する — 計測からリファクタリングまで

**シナリオ**: 開発中のプロジェクトにこのツール群を導入し、たまっているコード品質の
問題を安全に返済していく。新規開発 (spec-dev から始める) と並ぶ、もう 1 つの典型的な
使い始め方です。

### ステップ 1: 導入して現状を計測する (10 分)

```bash
./install.sh /path/to/your-repo    # プロジェクトに導入
cd /path/to/your-repo
python3 .claude/skills/cq-review/cq-metrics.py src/   # 現状把握
python3 .claude/skills/cq-review/cq-metrics.py --csv --label baseline src/ >> cq-trend.csv
python3 .claude/skills/cq-review/git-cochange.py --commits 3000 .   # 隠れた結合
```

2 行目の CSV が「改善前」の記録になります。以後コミットごとに追記すると改善が数字で残ります。
3 行目の git-cochange は既存プロジェクトでこそ効きます (履歴が長いほど精度が上がる)。
「離れているのに毎回一緒に変わるペア」は、次のステップでバッチにまとめる単位の候補です。

### ステップ 2: 修正方針を決める (Claude と一緒に)

検出結果をそのまま上から潰さないのがコツです。Claude に計画を立てさせます:

```text
あなた: cq-metrics の結果を分析して、修正計画を立てて。まだ直さないで。

Claude: 32 件の指摘は実質 5 つの構造問題に集約されます。
  | バッチ | 対象 | 内容 | リスク |
  |---|---|---|---|
  | 1 | 画面 A ↔ 画面 B | ほぼクローンの 2 画面。共通化で指摘の 1/3 が消える | 中 (UI、目視必須) |
  | 2 | ソースアダプタ 3 種 | 定型重複 → 基底クラス化 | 低 |
  | ...
  なお a.dart:1 の重複は import 文の並びが似ているだけなので対処不要です。
```

ポイント: **1 バッチ = 1 つの構造問題 = 1 ブランチ**。「直さない判断」(閾値超過でも
問題なし、と AI が言う項目) も計画に含めます。目標は指摘ゼロではなく
「同じ変更を 2 箇所にしなくて済むようになること」です。

### ステップ 3: リファクタリング用の安全網を準備する

リファクタリングは「挙動を変えずに構造を変える」作業なので、挙動が変わっていない
ことを確認する手段を先に固定します:

- **ガードセット**を決める: 静的チェック (lint/analyze) + 既存テスト + ビルド成功
- テストが薄いプロジェクトでは、触る予定のモジュールに**現状の挙動を固定するテスト**
  (characterization test) を先に数本書きます。「正しい挙動」でなく「今の挙動」を
  記録するのが目的なので、Claude に頼めばすぐできます:

```text
あなた: バッチ 3 で services/cache/ を触る予定。先にこの層の現状の挙動を固定する
       テストを書いて。

Claude: disk_cache の公開メソッド 5 つについて、現在の入出力を記録するテストを
  8 本作りました。1 本だけ確認してください: get() はキーが無いとき例外でなく
  null を返しています。これは現状の挙動として固定してよいですか?
```

- UI を触るバッチでは**目視スモークテストの手順** (3 操作くらい) を決めておきます

### ステップ 4: バッチごとに fix-loop で実施する

```text
あなた: バッチ 2 (ソースアダプタの基底クラス化) を fix-loop で進めて。
       ガードセットは flutter analyze + flutter test + ビルド。

Claude: fix-loop で進めます。ベースライン取得中… analyze 0 件、テスト 10/10 PASS。
  試行 1: 共通部を BaseHttpSource に抽出、まず google_drive_source だけ移行。
  → ガード実行: すべて PASS。試行 2: http_source を移行…
```

1 つ抽出するたびにガードセットを回す (1 変更 1 検証) ので、「リファクタリングしたら
動かなくなった、どこでだ?」が起きません。バッチ完了時に self-review のレビューパックが
付くので、重点確認ポイントだけ見てコミットします。

### ステップ 5: 記録して次のバッチへ

```bash
python3 .claude/skills/cq-review/cq-metrics.py --csv --label $(git rev-parse --short HEAD) src/ >> cq-trend.csv
```

flagged の数が下がっていくのが見えます。全バッチ終了後、繰り返し出た指摘パターンは
checklist.md に追加しておくと、次からのレビューで最初から検出されます。

### ステップ 6: 打ち止めになったら、そこで初めてゲートを入れる

バッチを回しきって「**残っているものは全部、理由を書ける意図的な判断だ**」と
言える状態になったら、コミットゲート (第 9 章) の出番です。

```bash
./install.sh . --hooks
```

このとき `tools/cq-baseline.txt` には、**残した各項目の理由を手で書きます**。
`--list` の出力を機械的に流し込まないでください。書けない行が 1 つでもあるなら、
まだ返済が終わっていないという意味です。ゲートを入れるのを遅らせる方が、
無視リストを抱えるより安全です。

## よくある質問

**Q. 全部の Skill を毎回使うの?**
いいえ。日常の小さな修正はそのまま頼めば OK。目安:
新機能 → spec-dev / 試行錯誤しそう → fix-loop / 出てきた成果物 → self-review は常時 /
実装後 → cq-review / テスト後 → triage / 上流の誤り発覚 → rework /
会話が長くなった → prepare-compact。

**Q. AI が勝手にファイルを消したり書き換えたりしない?**
Skill 側に「破壊的操作・ベースライン更新・修正計画は人間の承認を取る」ルールを
書いてあります。承認を求められたら内容を確認してから答えてください。

**Q. AI の指摘は信用していい?**
指摘には確度 (高/中/低) が付きます。確度: 低は「文脈次第」の意味なので、
そこだけあなたの判断で裁定してください。むしろ低確度を断定してこないことが重要です。

**Q. 秘密情報は大丈夫?**
同梱スクリプト 7 つ (cq-metrics.py, git-cochange.py, cpp-coupling.py,
trace-matrix.py, parse-lit-log.py, check-metrics.py, check-private.py) は
完全ローカル・読み取り専用で外部送信なし。むしろ check-private.py は
「私的データをリポジトリに入れない」ためのゲートです (第 9 章)。
AI アシスタント自体の利用ポリシーは所属組織のルールに従ってください。

## ファイル一覧

```
~/.claude/skills/
├── spec-dev/       SKILL.md + trace-matrix.py + templates/ (requirements/spec/design の雛形)
├── fix-loop/       SKILL.md (台帳の書式もここに)
├── coding-rules/   SKILL.md + rules/ (00-principles / 10-complexity / 90-rule-format)
├── cq-review/      SKILL.md + cq-metrics.py + git-cochange.py + cpp-coupling.py
│                   + references/checklist.md
├── self-review/    SKILL.md + references/compiler-checklist.md
├── triage/         SKILL.md + parse-lit-log.py
├── rework/         SKILL.md
└── prepare-compact/ SKILL.md
```

コミットゲート (`--hooks` を付けたときだけ、リポジトリ直下に配置):

```
<repo>/
├── .githooks/      pre-commit / pre-push (core.hooksPath で有効化される)
└── tools/          check-metrics.py + check-private.py
                    + cq-baseline.txt / test-vocabulary.txt (宣言ファイル。
                      *.template.txt が原本で、install.sh は上書きしない)
```

- スクリプト 7 つは Python 3.6+ 標準ライブラリのみ。単体実行可 (`--help` あり)。
  cq-metrics.py は `--csv --label <commit>` で品質推移の記録もできる
  (git-cochange.py / cpp-coupling.py も `--csv` 対応)
- `coding-rules/rules/` には `*.md` (有効なルール) と `*.template.md` (デフォルトの原本) が
  並びます。install.sh で更新するとき `*.md` はチームのものとして保持され、
  `*.template.md` だけが差し替わります
- おまけ: `prompts/weekly-report.md` — git log と作業記録から
  週報ドラフトを作るコピペ用プロンプト (Skill ではないので、使うとき中身を貼る)

## 質問・改善要望

この Skill 集は Markdown の指示書なので、チームの規約に合わせて自由に編集できます。
チェックリストへの項目追加 (「うちのレビューでよく出る指摘」の昇格) が特に効果的です。

## ライセンス

MIT License ([LICENSE](LICENSE))。改変・再配布・商用利用のいずれも自由で、
著作権表示とライセンス文を残すことだけが条件です。

**この資産は「編集して使う」ことを前提にしています。** ルール
(`coding-rules/rules/*.md`) もチェックリストもチェックの閾値も、自分たちの
現場に合わせて変えてください。フォークして自チームの版を育てるのが正しい
使い方です。変更したファイルに印を付ける義務もありません。
