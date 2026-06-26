import fs from 'fs';

function getLineNumber(content, index) {
  return content.slice(0, index).split("\n").length;
}

function findBlock(content, startIndex) {
  const openBraceIndex = content.indexOf("{", startIndex);

  if (openBraceIndex === -1) {
    return null;
  }

  let depth = 0;
  let endIndex = openBraceIndex;

  for (let i = openBraceIndex; i < content.length; i++) {
    const char = content[i];

    if (char === "{") {
      depth++;
    }

    if (char === "}") {
      depth--;

      if (depth === 0) {
        endIndex = i;
        break;
      }
    }
  }

  return {
    startIndex,
    endIndex: endIndex + 1,
    code: content.slice(startIndex, endIndex + 1),
    startLine: getLineNumber(content, startIndex),
    endLine: getLineNumber(content, endIndex)
  };
}

function extractImports(content) {
  const imports = [];

  const lines = content.split("\n");

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    if (
      trimmed.startsWith("import ") ||
      trimmed.startsWith("const ") &&
      trimmed.includes("require(")
    ) {
      imports.push({
        type: "import",
        startLine: index + 1,
        endLine: index + 1,
        code: line
      });
    }
  });

  return imports;
}

function extractFunctions(content) {
  const functions = [];

  const regex = /(async\s+)?function\s+([A-Za-z0-9_]+)\s*\(/g;

  let match;

  while ((match = regex.exec(content)) !== null) {
    const name = match[2];

    const block = findBlock(content, match.index);

    if (!block) {
      continue;
    }

    functions.push({
      name,
      type: "function",
      startLine: block.startLine,
      endLine: block.endLine,
      code: block.code
    });
  }

  return functions;
}

function extractClasses(content) {
  const classes = [];

  const regex = /class\s+([A-Za-z0-9_]+)/g;

  let match;

  while ((match = regex.exec(content)) !== null) {
    const name = match[1];

    const block = findBlock(content, match.index);

    if (!block) {
      continue;
    }

    classes.push({
      name,
      type: "class",
      startLine: block.startLine,
      endLine: block.endLine,
      code: block.code
    });
  }

  return classes;
}

function extractExports(content) {
  const exportsFound = [];

  const moduleExportsMatch =
    content.match(/module\.exports\s*=\s*\{([\s\S]*?)\}/);

  if (moduleExportsMatch) {
    const names = moduleExportsMatch[1]
      .split(",")
      .map(name => name.trim())
      .filter(Boolean);

    names.forEach(name => {
      exportsFound.push({
        name
      });
    });
  }

  const exportMatch =
    content.match(/export\s*\{([\s\S]*?)\}/);

  if (exportMatch) {
    const names = exportMatch[1]
      .split(",")
      .map(name => name.trim())
      .filter(Boolean);

    names.forEach(name => {
      exportsFound.push({
        name
      });
    });
  }

  return exportsFound;
}

/**
 * Extracts code context from a file by analyzing its imports, functions, classes, and exports.
 * @param {string} filePath - Path to the file to analyze
 * @returns {Object} Object containing imports, functions, classes, and exports arrays
 */
export function extractCodeContext(filePath) {
  const content = fs.readFileSync(filePath, "utf8");

  return {
    imports: extractImports(content),
    functions: extractFunctions(content),
    classes: extractClasses(content),
    exports: extractExports(content)
  };
}

// Export helper functions for internal use and testing
export {
  extractImports,
  extractFunctions,
  extractClasses,
  extractExports,
  findBlock
};
