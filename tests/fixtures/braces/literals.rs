// Rust: a lifetime looks like an unterminated char literal, and that is the
// shape most likely to desync a quote-counting scanner.
//
// It does desync it: `longest` below is NOT reported, because `'a` opens a
// literal that runs to the next apostrophe. The golden file records that, so
// the day someone teaches the scanner about lifetimes, the diff will show
// this function appearing. Predates the indentation and chunk-skipping work
// -- checked against the version before both.
use std::collections::HashMap;

pub fn longest<'a>(first: &'a str, second: &'a str) -> &'a str {
    let marker = '\'';
    let text = "a } brace and a { brace in a string";
    if first.len() > second.len() { first } else { text }
}

pub fn tabulate(rows: &HashMap<String, i32>) -> usize {
    rows.len()
}
