# tests/ — スクリプトの安全網

```bash
python3 tests/run.py            # 全ケース実行。差分があれば exit 1
python3 tests/run.py --update   # golden を現在の出力で更新
python3 tests/run.py --list     # ケース名の一覧
```

## これは何か

`tests/fixtures/` の入力に対してスクリプトを走らせ、出力を `tests/golden/` の
記録と比較します。**「正しい挙動」ではなく「今の挙動」を固定**する
characterization test です (README 第 10 章ステップ 3 で他プロジェクトに勧めている
やり方を、自分に適用したもの)。

目的はリファクタリングで挙動が動いたことを見えるようにすることです。差分が出たら
「変更が間違っている」か「golden を更新すべき」かのどちらかで、後者ならコミット
メッセージで理由を言える必要があります。

## fixture が押さえている判断

閾値を最小にした `metrics-inventory` ケースで**全関数が数値付きで一覧**されるので、
閾値を超えないものも固定されます。

| 判断 | 押さえている fixture |
|---|---|
| Python の `elif` 連鎖は 1 段 | `python/shapes.py` の `Holder.chain` (depth 1) |
| 複数行シグネチャ・継続行はネストでない | `wrapped` / `continued` (depth 0) |
| `self` / `cls` は引数に数えない | `Holder.__init__` (2 params) |
| メソッドは `Class.method` で報告 | `Holder.*` |
| 入れ子 `def` も個別に報告 | `outer.inner` |
| タブ字下げを 8 桁に正規化 | `python/tabs.py` |
| Python コメント中の `'` でファイルが壊れない | `python/shapes.py` 冒頭 |
| Go の import ブロックは重複でない | `braces/receiver.go` と `twin.go` |
| 行単位の import も重複でない | `python/imports_a.py` と `imports_b.py`、`braces/decls*.cs` |
| C# の `using var` は import でなく実コード | `braces/decls.cs` |
| Go のレシーバは引数でなくメソッド名を報告 | `braces/receiver.go` の `Load` |
| 制御構文・初期化子は関数でない | `braces/shapes.c` |
| JS のテンプレートリテラル内の `{}` はブロックでない | `braces/literals.js` |
| **Rust のライフタイムで走査がずれる (既知の限界)** | `braces/literals.rs` |

settings.json のマージ (`register-claude-hooks.py`) は `--dry-run` で結果を印字させ、
書き込まずに固定しています。押さえているのは次の判断です。

| 判断 | 押さえている fixture |
|---|---|
| 他人の hook を残し、自分の group を足す | `hooks/settings-other.json` |
| 2 回目は何も言わない・書かない (冪等) | `hooks/settings-home.json` (`--home`) |
| ホーム登録済みを複製せず付け替える | `hooks/settings-home.json` (`--project`) |
| 想定外の形は書かずに exit 2 | `hooks/settings-broken.json` |
| 設定ファイルがまだ無い場合 | (存在しないパスを渡す) |

## 記録されている既知の限界

golden は「今の挙動」なので、**バグや限界もそのまま記録されます**。意図的です。

- **Rust のライフタイム** (`fn longest<'a>(...)`) — `'a` が文字リテラルの開始と
  読まれ、次のアポストロフィまでが文字列扱いになるため、その関数が検出されません。
  `literals.rs` の `longest` が一覧に出てこないのがその記録です。直したら
  golden に「関数が 1 つ増える」差分が出ます

## 注意

- **fixture はわざと汚いコードです**。深いネスト・長い引数列を意図的に含むので、
  リポジトリ全体に cq-metrics.py をかけると `tests/fixtures` が大量に引っかかります。
  計測するときはスコープから外してください
- golden は出力そのものなので、**書式を変える修正でも差分が出ます**。それは想定内で、
  `--update` して差分を目視し、コミットメッセージに理由を書きます
- 変異テストで確認済み: `#` コメント対応・継続行スキップ・import 除外 (行/ブロック)・
  self 除外・クラス接頭辞・Go レシーバ・ネスト深さ・関数長のいずれを壊しても
  ケースが落ちます
