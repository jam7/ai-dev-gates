// Dart: `dart format` wraps a signature at 80 columns, so a named-parameter
// group's `{` routinely starts a continuation line. That brace is parameter
// syntax, not a block: counting it as one used to split the header and drop
// the whole function from the count (found on a real project, where adding
// one named parameter made a 73-line function disappear from the gate).
class Wrapped {
  Future<int> doWork(String a,
      {void Function()? onBusy}) async {
    print(a);
    return 0;
  }

  // A map literal in a call argument is data too: it must not add a nesting
  // level to the enclosing function.
  void caller() {
    register('x', {
      'a': 1,
      'b': 2,
    });
    for (int i = 0; i < 3; i++) {
      print(i);
    }
  }
}
