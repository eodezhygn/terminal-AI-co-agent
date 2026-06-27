# Patch-Engine Bug Fix Summary

## The Bug

The `patch-engine.js` had a critical bug in the `findDeclarationBlock()` function that prevented it from correctly matching exported functions and classes preceded by non-word characters (spaces, semicolons, etc.).

### Root Cause

The regex pattern used to locate declarations is:
```
(?:^|[^\w$])(?:export\s+)?(?:default\s+)?(?:async\s+)?${kind}\s+${target}\b
```

This pattern includes an alternation at the start: `(?:^|[^\w$])` which means:
- Match either the start of a line/string (`^`)
- **OR** a non-word character that is not `$` (`[^\w$]`)

**The Problem:** When the regex matched with a non-word character (like a space), that character became part of the matched string in `match[0]`. However, the code treated `match.index` as the start of the declaration to replace, which pointed to the non-word character, not the declaration itself.

### Example of the Bug

Given code:
```javascript
let x = 1; export function greet() { return "hi"; }
```

The regex would match ` export function greet` (including the leading space at position 8), but:
- `match.index` = 8 (pointing to the space)
- The replacement would start from position 8, **removing the space**
- Result: `let x = 1;export function greet() { return "hello"; }` (missing space)

## The Fix

The fix detects when a non-word character was matched and adjusts the replacement range accordingly:

```javascript
let declStart = match.index;
let searchOffset = match[0].length;

// If the pattern matched a non-word character (via [^\w$], not ^), we need to skip it
// This occurs when the first char of match[0] is a non-word character like space, ;, etc.
if (match[0][0] && !/\w/.test(match[0][0])) {
  // Skip the non-word character - it should be preserved
  declStart += 1;
  searchOffset -= 1;
}

const braceIndex = content.indexOf('{', declStart + searchOffset);
```

### How It Works

1. Check if the first character of the matched string is a non-word character
2. If yes, increment `declStart` by 1 to skip that character
3. Decrement `searchOffset` by 1 to maintain correct brace-finding position
4. This preserves the non-word character in the output

### Result

Now the code correctly handles all declaration patterns:
- `function name() {}` ✓
- `export function name() {}` ✓
- `export async function name() {}` ✓
- `class Name {}` ✓
- `export default class Name {}` ✓

With spaces, semicolons, or other non-word characters properly preserved in the surrounding code.

## Tests Added

Comprehensive test coverage was added for:
1. `testPlainFunction()` - Detects plain functions
2. `testExportFunction()` - Detects exported functions with preceding non-word characters
3. `testExportAsyncFunction()` - Detects async functions
4. `testPlainClass()` - Detects plain classes
5. `testExportDefaultClass()` - Detects exported default classes

All tests verify that:
- The target is correctly identified and replaced
- Surrounding code is preserved
- Non-word characters (spaces, semicolons) are not removed

## Verification

- All original tests pass ✓
- All new tests pass ✓
- Full test suite passes ✓
- No external dependencies added ✓
- Public API unchanged ✓
