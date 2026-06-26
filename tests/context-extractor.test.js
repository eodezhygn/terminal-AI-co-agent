import assert from 'assert';
import fs from 'fs/promises';
import path from 'path';
import { extractCodeContext, extractImports, extractFunctions, extractClasses, extractExports } from '../src/context/code-context.js';

async function runTests() {
  const tempDir = './tests/.tmp/code-context';
  await fs.rm(tempDir, { recursive: true, force: true });
  await fs.mkdir(tempDir, { recursive: true });

  console.log('Testing code context extraction...');

  // Test 1: Function extraction
  const functionFile = path.join(tempDir, 'functions.js');
  const functionContent = `
function simpleFunction() {
  console.log('hello');
}

async function asyncFunction() {
  return 'world';
}

function anotherFunction(param) {
  return param * 2;
}
  `;
  await fs.writeFile(functionFile, functionContent);
  const functionResult = extractCodeContext(functionFile);
  assert.strictEqual(functionResult.functions.length, 3, 'Should extract 3 functions');
  assert.strictEqual(functionResult.functions[0].name, 'simpleFunction');
  assert.strictEqual(functionResult.functions[1].name, 'asyncFunction');
  assert.strictEqual(functionResult.functions[2].name, 'anotherFunction');
  console.log('✓ Function extraction test passed');

  // Test 2: Class extraction
  const classFile = path.join(tempDir, 'classes.js');
  const classContent = `
class Animal {
  constructor(name) {
    this.name = name;
  }
  
  speak() {
    console.log(this.name);
  }
}

class Dog extends Animal {
  bark() {
    console.log('woof');
  }
}
  `;
  await fs.writeFile(classFile, classContent);
  const classResult = extractCodeContext(classFile);
  assert.strictEqual(classResult.classes.length, 2, 'Should extract 2 classes');
  assert.strictEqual(classResult.classes[0].name, 'Animal');
  assert.strictEqual(classResult.classes[1].name, 'Dog');
  console.log('✓ Class extraction test passed');

  // Test 3: Import extraction
  const importFile = path.join(tempDir, 'imports.js');
  const importContent = `
import fs from 'fs';
import { readFile, writeFile } from 'fs/promises';
const path = require('path');
const { createFolder } = require('./utils.js');

function doSomething() {
  console.log('work');
}
  `;
  await fs.writeFile(importFile, importContent);
  const importResult = extractCodeContext(importFile);
  assert(importResult.imports.length >= 4, 'Should extract at least 4 imports');
  const importCodes = importResult.imports.map(imp => imp.code.trim());
  assert(importCodes.some(code => code.includes('import fs')), 'Should find fs import');
  assert(importCodes.some(code => code.includes('const path')), 'Should find path require');
  console.log('✓ Import extraction test passed');

  // Test 4: Export extraction
  const exportFile = path.join(tempDir, 'exports.js');
  const exportContent = `
export function helper() {
  return 'help';
}

export class MyClass {
  constructor() {}
}

export {
  helper,
  MyClass
};
  `;
  await fs.writeFile(exportFile, exportContent);
  const exportResult = extractCodeContext(exportFile);
  assert(exportResult.exports.length >= 2, 'Should extract at least 2 exports');
  const exportNames = exportResult.exports.map(exp => exp.name);
  assert(exportNames.includes('helper'), 'Should find helper export');
  assert(exportNames.includes('MyClass'), 'Should find MyClass export');
  console.log('✓ Export extraction test passed');

  // Test 5: Empty file handling
  const emptyFile = path.join(tempDir, 'empty.js');
  await fs.writeFile(emptyFile, '');
  const emptyResult = extractCodeContext(emptyFile);
  assert.strictEqual(emptyResult.imports.length, 0, 'Empty file should have no imports');
  assert.strictEqual(emptyResult.functions.length, 0, 'Empty file should have no functions');
  assert.strictEqual(emptyResult.classes.length, 0, 'Empty file should have no classes');
  assert.strictEqual(emptyResult.exports.length, 0, 'Empty file should have no exports');
  console.log('✓ Empty file handling test passed');

  // Test 6: Combined extraction
  const combinedFile = path.join(tempDir, 'combined.js');
  const combinedContent = `
import { someFunc } from './lib.js';

class Calculator {
  add(a, b) {
    return a + b;
  }
}

function multiply(a, b) {
  return a * b;
}

export {
  Calculator,
  multiply
};
  `;
  await fs.writeFile(combinedFile, combinedContent);
  const combinedResult = extractCodeContext(combinedFile);
  assert(combinedResult.imports.length > 0, 'Should have imports');
  assert.strictEqual(combinedResult.functions.length, 1, 'Should have 1 function');
  assert.strictEqual(combinedResult.classes.length, 1, 'Should have 1 class');
  assert(combinedResult.exports.length > 0, 'Should have exports');
  console.log('✓ Combined extraction test passed');

  console.log('\nAll tests passed! ✓');
}

runTests().catch((error) => {
  console.error('Test failed:', error.message);
  process.exit(1);
});
