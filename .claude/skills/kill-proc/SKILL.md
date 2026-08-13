---
name: kill-proc
description: Kill only the processes whose command line matches a given regex, with a mandatory list-first step. Use whenever about to kill or stop a process — instead of pkill -f, killall, or ps|grep|kill pipelines, which match bystanders (the grep itself, unrelated resident processes, even the calling session) and have repeatedly killed the user's long-running processes.
license: MIT
---

# kill-proc: 見てから、一致したものだけ殺す

背景: `ps | grep X | kill` や `pkill -f` の即興手順は巻き添えを起こす —
grep 自身が一致する、無関係な常駐プロセスのコマンドラインにたまたま語が
含まれる、最悪の場合は呼び出し元のセッションごと落とす。実際に、ユーザーの
常駐プロセスが繰り返し巻き添えで殺された。

`$SKILL/kill-proc.py` は /proc を直接読むので grep が結果に現れず、
**自分自身・祖先 (シェルとエージェント本体)・他ユーザー・カーネルスレッドを
常に除外**する。

## 使い方 — 2 段階が必須

```bash
python3 $SKILL/kill-proc.py 'REGEX'                 # 1. 一覧のみ。何も送らない
python3 $SKILL/kill-proc.py 'REGEX' --kill          # 2. 一覧と同じものに SIGTERM
python3 $SKILL/kill-proc.py 'REGEX' --kill --signal KILL   # TERM が効かなかったときだけ
```

REGEX はコマンドライン全体 (引数込み) に対する検索。例:

```bash
python3 $SKILL/kill-proc.py 'flutter run.*image_viewer'
```

## ルール

- **pkill -f / killall / ps|grep|kill を書かない。** プロセスを止めたくなったら
  常にこのツール
- **プレビューを飛ばして --kill しない。** 一覧に意図しないプロセスが 1 つでも
  居たら、殺すのではなく正規表現を狭める。「後で必要なら再起動すればいい」は
  ユーザーの常駐プロセスには当てはまらない
- 一覧が 0 件なら止める対象は既に居ない。exit 1 をエラーとして再試行しない
- 既定シグナルは TERM。KILL は TERM を送って待っても残ったときだけ
- Linux 専用 (/proc を読む)。他 OS ではユーザーに手順を確認する
