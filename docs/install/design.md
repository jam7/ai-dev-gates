# install.sh 設計 — 配置先ファイルの所有者モデル

対象: `install.sh` と、それが書き込むすべての配置先。

## D-01: 配置先のファイルは 3 つの所有者クラスのどれかに属する

| クラス | 意味 | 比較 | `--force` |
|---|---|---|---|
| package | このパッケージのもの | する | 置き換える |
| user | 利用者・チームのもの | **しない** | **触らない** |
| once | 無ければ作る。以後は利用者のもの | **しない** | **触らない** |

現在の割り当て:

| 配置先 | クラス | 根拠 |
|---|---|---|
| `skills/*/` の `SKILL.md`・スクリプト・`references/`・`templates/` | package | パッケージが配る本体 |
| `skills/coding-rules/rules/*.template.md` | package | 既定ルールの原本 |
| `skills/coding-rules/rules/*.md` (template を除く) | user | チームが編集して git で共有する対象 |
| `CLAUDE.md` | once | プロジェクトの運用規約そのもの。テンプレートは出発点 |
| `.githooks/*`、`tools/check-*.py`、`tools/*.template.*` | package | パッケージが配る本体 |
| `tools/gate.conf`、`cq-baseline.txt`、`test-vocabulary.txt`、`private-allow.txt`、`refs-allow.txt` | once | 何を測るか・何を許すかの判断 |
| `.claude/hooks/` の 3 ファイル | package | パッケージが配る本体 |
| `.claude/hooks/` にある**それ以外**のファイル | user | 他人の hook。同じディレクトリを共有している |
| `settings.json` | user | マージのみ。比較も置き換えもしない |

## D-02: 判定と書き込みは同じ表を読む [不変条件]

衝突検出 (書く前の確認) と書き込みは、**同一の所有者判定**を通す。片方だけが
所有者を知っている状態を作らない。

**この不変条件が破れると何が起きるか** (実測、2026-08-28):

1. **利用者のファイルが「旧版」として報告され、`--force` で消える。**
   `CLAUDE.md` は書き込み側だけが「テンプレートで上書きするもの」と知っていて、
   判定側は「テンプレートと違う = 旧版」と報告していた。image-viewer の
   CLAUDE.md (123 行、テンプレートとの共通行 1 行) を仮リポジトリに置いて
   `--force` を実行すると、28 行のテンプレートに置き換わった。
   しかも表示は `installed CLAUDE.md (project conventions)` で成功に見える
2. **利用者のファイルの差分で、無関係な導入が全部止まる。**
   `rules/50-logging.md` に 1 行足すと、以後 `--force` なしの install は
   すべて exit 1。他の 8 skill も hook も入らない。`--force` は 1 (CLAUDE.md
   の破壊) を連れてくるので、逃げ道が無い
3. **共有ディレクトリを丸ごと比較して、他人のファイルを差分として数える。**
   `~/.claude/hooks/` に無関係な hook が 1 つあるだけで「up to date」に
   ならず、毎回コピーして `installed` と表示する

## D-03: `--force` の意味は 1 つだけ

「**package クラスのファイルを新版に置き換えてよい**」の同意。それ以外の意味を
持たせない。user と once のファイルは `--force` でも触らない。

`--force` を「利用者のファイルも初期化する」に拡張したくなったら、それは
D-01 の表が間違っている合図。表を直す方が正しい (フラグを増やすと、日常的に
必要な「更新」を選ぶたびに破壊が付いてくる)。

## D-04: 衝突はファイル単位で報告する

ディレクトリ名だけを出さない。実際に起きた誤診 (2026-08-28)。表示は
`<dest>/.claude/skills/coding-rules` だけだった。原因は
「install.sh 自身が消した `rules/80-newrule.md` 1 個」で、
`diff -rq` を取るまで分からなかった。

## D-05: 原本リポジトリでは template と実体が一致する [不変条件]

このリポジトリが持つ `CLAUDE.md` と `coding-rules/rules/*.md` は、
カスタマイズではなく**配っている原本そのもの**。差分は「原本を直して手元を
忘れた」以外に意味を持たない。

実測 (2026-08-28)。次のコミットが `CLAUDE.template.md` に「notes/ に
プログラムを置かない」を足した。

> spec-dev: notes/ as its own private repository is a supported shape

このリポジトリの `CLAUDE.md` は更新されなかった。以後 5 コミット、誰も
気づかなかった。**古い規約も規約に見える**ため。

install.sh はこれを直せない。自リポジトリへの install は skip する。
既存の CLAUDE.md も置き換えない (D-01)。よって機械で見るしかない。
`tests/check-origin.py` を gate.conf の **`always_checks`** から回す。

`extra_checks` ではない。あちらは `ext` に一致するファイルが staged の
ときだけ走るので、**ドキュメントだけのコミットを見ない**。破ったコミットが
まさにそれだった。最初は `extra_checks` に置いて、実際に素通りした
(2026-08-28、意図的に壊したコミットが 1 度通ってしまった)。

配布はしない。利用者側の CLAUDE.md とルールは**違っていて当然**で、
この義務は原本にだけある。`always_checks` という枠自体は配る
(ドキュメントで壊れる不変条件は、どのプロジェクトにもあり得る)。

## 未決 (D-06 候補)

**パッケージが新しい既定ルールを追加したとき、既存の導入先で有効になるか。**
現状は新規導入では有効 (`*.template.md` → `*.md` を生成)、更新導入では
無効のまま届く (`.md` を復元処理が消す)。同じ版でもマシンによってルールが
違う。方針を決めてから直す — ADR-002 の対象。

## 退役 (番号は再利用しない)

なし。
