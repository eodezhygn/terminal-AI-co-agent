import assert from 'assert';
import { applyPatch } from '../src/patch-engine.js';

function runTests() {
  testFunctionReplacement();
  testClassReplacement();
  testTargetNotFound();
  testUnrelatedCodePreserved();
  testImportsPreserved();
  testPlainFunction();
  testExportFunction();
  testExportAsyncFunction();
  testPlainClass();
  testExportDefaultClass();
  console.log('Patch engine tests passed.');
}

function testFunctionReplacement() {
  const original = `import fs from 'fs';

export function greet(name) {
  return \`Hello, \${name}\`;
}

const unused = 1;
`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'greet',
      replacement: `export function greet(name) {
  return \`Hi, \${name}!\`;
}
`
    }
  });

  assert.ok(patched.includes('return `Hi, ${name}!`;'));
  assert.ok(patched.includes("const unused = 1;"));
  assert.ok(patched.startsWith("import fs from 'fs';"));
}

function testClassReplacement() {
  const original = `import path from 'path';

class User {
  constructor(name) {
    this.name = name;
  }

  greet() {
    return 'Hello ' + this.name;
  }
}

export default User;
`;

  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_class',
      target: 'User',
      replacement: `class User {
  constructor(name) {
    this.name = name;
  }

  greet() {
    return \`Welcome, \${this.name}\`;
  }
}
`
    }
  });

  assert.ok(patched.includes("return `Welcome, ${this.name}`;"));
  assert.ok(patched.includes('export default User;'));
  assert.ok(patched.startsWith("import path from 'path';"));
}

function testTargetNotFound() {
  const content = `function a() { return 1; }`;
  assert.throws(
    () => applyPatch({
      content,
      patch: {
        type: 'replace_function',
        target: 'missing',
        replacement: 'function missing() {}'
      }
    }),
    { message: 'Target not found: missing' }
  );
}

function testUnrelatedCodePreserved() {
  const original = `import os from 'os';

function keep() {
  return true;
}

function replaceMe() {
  return false;
}
`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'replaceMe',
      replacement: `function replaceMe() {
  return true;
}
`
    }
  });

  assert.ok(patched.includes(`function keep() {
  return true;
}`));
  assert.ok(patched.includes(`import os from 'os';`));
}

function testImportsPreserved() {
  const original = `import { readFile } from 'fs';

export async function load(file) {
  return await readFile(file, 'utf8');
}
`;

  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'load',
      replacement: `export async function load(file) {
  return 'patched';
}
`
    }
  });

  assert.ok(patched.startsWith(`import { readFile } from 'fs';`));
  assert.ok(patched.includes("return 'patched';"));
}

function testPlainFunction() {
  const original = `let x = 1; function greet() { return 'hi'; }`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'greet',
      replacement: `function greet() { return 'hello'; }`
    }
  });
  
  assert.ok(patched.includes('return \'hello\''));
  assert.ok(patched.includes('let x = 1;'));
}

function testExportFunction() {
  const original = `let x = 1; export function greet() { return 'hi'; }`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'greet',
      replacement: `export function greet() { return 'hello'; }`
    }
  });
  
  assert.ok(patched.includes('return \'hello\''));
  assert.ok(patched.includes('let x = 1;'));
  assert.ok(patched.includes('export function greet'));
}

function testExportAsyncFunction() {
  const original = `async function fetchData() { return 'data'; }`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_function',
      target: 'fetchData',
      replacement: `async function fetchData() { return 'cached'; }`
    }
  });
  
  assert.ok(patched.includes('return \'cached\''));
  assert.ok(patched.includes('async function'));
}

function testPlainClass() {
  const original = `let x = 1; class User { getName() { return 'john'; } }`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_class',
      target: 'User',
      replacement: `class User { getName() { return 'jane'; } }`
    }
  });
  
  assert.ok(patched.includes("return 'jane'"));
  assert.ok(patched.includes('let x = 1;'));
}

function testExportDefaultClass() {
  const original = `class MyComponent { render() { return 'old'; } } export default MyComponent;`;
  const patched = applyPatch({
    content: original,
    patch: {
      type: 'replace_class',
      target: 'MyComponent',
      replacement: `class MyComponent { render() { return 'new'; } }`
    }
  });
  
  assert.ok(patched.includes("return 'new'"));
  assert.ok(patched.includes('export default MyComponent'));
}

runTests();
