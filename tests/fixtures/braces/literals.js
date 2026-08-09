// Template literals are backtick strings, and they nest expressions. The
// scanner treats the whole thing as one literal, which is the point: a brace
// inside a template must not be counted as a block.
import { readFile } from "node:fs/promises";

function describe(name, count) {
    const label = `item ${name}: { not a block } and ' not a quote`;
    const path = `dir\\sub\\${name}.txt`;
    return label + path + count;
}

function quoting() {
    const apostrophe = "it's fine";
    const escaped = 'a \' inside';
    return apostrophe + escaped;
}
