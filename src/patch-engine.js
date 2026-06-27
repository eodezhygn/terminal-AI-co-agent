export function applyPatch({ content, patch }) {
  if (typeof content !== 'string') {
    throw new Error('Content must be a string');
  }
  if (!patch || typeof patch !== 'object') {
    throw new Error('Patch must be an object');
  }

  const { type, target, replacement } = patch;
  if (typeof type !== 'string' || typeof target !== 'string' || typeof replacement !== 'string') {
    throw new Error('Patch must include type, target, and replacement strings');
  }

  const matcher = getPatchMatcher(type, target);
  if (!matcher) {
    throw new Error(`Unsupported patch type: ${type}`);
  }

  const match = matcher(content);
  if (!match) {
    throw new Error(`Target not found: ${target}`);
  }

  return content.slice(0, match.start) + replacement + content.slice(match.end);
}

function getPatchMatcher(type, target) {
  if (type === 'replace_function') {
    return (content) => findDeclarationBlock(content, target, 'function');
  }
  if (type === 'replace_class') {
    return (content) => findDeclarationBlock(content, target, 'class');
  }
  return null;
}

function findDeclarationBlock(content, target, kind) {
  const pattern = new RegExp(
    `(?:^|[^\w$])(?:export\s+)?(?:default\s+)?(?:async\s+)?${kind}\\s+${escapeRegExp(target)}\\b`,
    'm'
  );
  const match = pattern.exec(content);
  if (!match) {
    return null;
  }

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
  if (braceIndex === -1) {
    return null;
  }

  const blockEnd = findMatchingBrace(content, braceIndex);
  if (blockEnd === -1) {
    return null;
  }

  return { start: declStart, end: blockEnd };
}

function findMatchingBrace(content, startIndex) {
  let depth = 0;
  let state = null;
  const length = content.length;

  for (let index = startIndex; index < length; index += 1) {
    const char = content[index];
    const next = content[index + 1];

    if (state === 'single') {
      if (char === "'" && content[index - 1] !== '\\') {
        state = null;
      }
      continue;
    }
    if (state === 'double') {
      if (char === '"' && content[index - 1] !== '\\') {
        state = null;
      }
      continue;
    }
    if (state === 'template') {
      if (char === '`' && content[index - 1] !== '\\') {
        state = null;
        continue;
      }
      if (char === '$' && next === '{') {
        index += 1;
        depth += 1;
        continue;
      }
      if (char === '}' && depth > 1) {
        depth -= 1;
        continue;
      }
      continue;
    }
    if (state === 'lineComment') {
      if (char === '\n') {
        state = null;
      }
      continue;
    }
    if (state === 'blockComment') {
      if (char === '*' && next === '/') {
        state = null;
        index += 1;
      }
      continue;
    }

    if (char === "'") {
      state = 'single';
      continue;
    }
    if (char === '"') {
      state = 'double';
      continue;
    }
    if (char === '`') {
      state = 'template';
      continue;
    }
    if (char === '/' && next === '/') {
      state = 'lineComment';
      index += 1;
      continue;
    }
    if (char === '/' && next === '*') {
      state = 'blockComment';
      index += 1;
      continue;
    }
    if (char === '{') {
      depth += 1;
      continue;
    }
    if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return index + 1;
      }
      continue;
    }
  }

  return -1;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
