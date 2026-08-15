// C++: a brace-initialized default argument puts a `{` inside the parameter
// list. Same mechanism as the Dart named-parameter group -- the brace belongs
// to the header, or the function is not detected at all.
#include <vector>

int pickSize(const std::vector<int> &v = {1, 2},
             int fallback = 0) {
  return v.empty() ? fallback : v[0];
}
