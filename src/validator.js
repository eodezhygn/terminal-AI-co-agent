export function validateFileWrite({ path: filePath, content, projectContext = {} }) {
  const warnings = [];
  const normalizedPath = (filePath || '').replace(/\\\\/g, '/');

  if (!normalizedPath || normalizedPath.startsWith('/') || normalizedPath.includes('..')) {
    warnings.push(`Path appears unsafe or invalid: ${filePath}`);
  }

  if (!content || !content.trim()) {
    warnings.push(`Generated content for ${filePath} is empty or whitespace.`);
    return { valid: false, warnings };
  }

  if (/\.tsx?$/.test(normalizedPath)) {
    if (!/import\s+React|export\s+default|function\s+[A-Z]/.test(content) && normalizedPath.endsWith('.tsx')) {
      warnings.push(`React/TSX file ${filePath} may not contain expected React patterns.`);
    }
    if (normalizedPath.includes('/features/auth/') && !/tailwind|className=/.test(content)) {
      warnings.push(`Expected Tailwind styling in auth feature file ${filePath}.`);
    }
  }

  if (normalizedPath.endsWith('/auth/login.ts')) {
    if (!/export\s+async\s+function\s+login/.test(content)) {
      warnings.push(`Backend login endpoint ${filePath} may not export async function login.`);
    }
    if (!/res\.json\(|res\.status\(/.test(content)) {
      warnings.push(`Backend login endpoint ${filePath} may not use Express req/res patterns.`);
    }
  }

  return { valid: warnings.length === 0, warnings };
}

/**
 * Validate generated code returned from the coder wrapper.
 *
 * @param {Object} result
 * @param {string} result.status
 * @param {any} result.generatedCode
 * @returns {{ valid: boolean, issues: string[] }}
 */
export function validateGeneratedCode(result) {
  const issues = [];

  if (!result || typeof result !== 'object') {
    return { valid: false, issues: ['Result must be an object.'] };
  }

  if (result.status !== 'success') {
    issues.push('status must equal "success".');
  }

  if (result.generatedCode === undefined || result.generatedCode === null) {
    issues.push('generatedCode must exist.');
  }

  if (typeof result.generatedCode !== 'string') {
    issues.push('generatedCode must be a string.');
  }

  if (typeof result.generatedCode === 'string') {
    const trimmed = result.generatedCode.trim();

    if (!trimmed) {
      issues.push('generatedCode.trim() must not be empty.');
    }

    if (result.generatedCode.length <= 20) {
      issues.push('generatedCode length must be greater than 20 characters.');
    }

    const normalized = trimmed.toLowerCase();
    const prohibited = ['as an ai', 'i cannot', "i'm unable"];

    prohibited.forEach((phrase) => {
      if (normalized.includes(phrase)) {
        issues.push(`generatedCode must not contain "${phrase}".`);
      }
    });
  }

  return { valid: issues.length === 0, issues };
}
