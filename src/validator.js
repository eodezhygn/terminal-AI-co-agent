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
const VALID_ACTION_TYPES = new Set([
  'create_file',
  'edit_file',
  'append_file',
  'create_folder',
  'read_file'
]);

function validateAction(action, index) {
  const issues = [];

  if (!action || typeof action !== 'object') {
    issues.push(`Action[${index}] must be an object.`);
    return issues;
  }

  if (typeof action.type !== 'string' || !VALID_ACTION_TYPES.has(action.type.trim())) {
    issues.push(`Action[${index}].type must be one of ${[...VALID_ACTION_TYPES].join(', ')}.`);
  }

  if (typeof action.path !== 'string' || !action.path.trim()) {
    issues.push(`Action[${index}].path must be a non-empty string.`);
  }

  return issues;
}

export function validateActions(actions) {
  const issues = [];

  if (!Array.isArray(actions)) {
    return { valid: false, issues: ['actions must be an array.'] };
  }

  if (actions.length === 0) {
    return { valid: false, issues: ['actions must contain at least one action.'] };
  }

  actions.forEach((action, index) => {
    issues.push(...validateAction(action, index));
  });

  return { valid: issues.length === 0, issues };
}

export function validateGeneratedCode(result) {
  const issues = [];

  if (!result || typeof result !== 'object') {
    return { valid: false, issues: ['Result must be an object.'] };
  }

  if (result.status !== 'success') {
    issues.push('status must equal "success".');
  }

  let hasValidGeneratedCode = false;
  let generatedCodeIssues = [];

  if (result.generatedCode !== undefined && result.generatedCode !== null) {
    if (typeof result.generatedCode !== 'string') {
      generatedCodeIssues.push('generatedCode must be a string.');
    } else {
      const trimmed = result.generatedCode.trim();

      if (!trimmed) {
        generatedCodeIssues.push('generatedCode.trim() must not be empty.');
      }

      if (result.generatedCode.length <= 20) {
        generatedCodeIssues.push('generatedCode length must be greater than 20 characters.');
      }

      const normalized = trimmed.toLowerCase();
      const prohibited = ['as an ai', 'i cannot', "i'm unable"];

      prohibited.forEach((phrase) => {
        if (normalized.includes(phrase)) {
          generatedCodeIssues.push(`generatedCode must not contain "${phrase}".`);
        }
      });

      if (generatedCodeIssues.length === 0) {
        hasValidGeneratedCode = true;
      }
    }
  }

  const actions = Array.isArray(result.actions) ? result.actions : [];
  const actionValidation = actions.length > 0 ? validateActions(actions) : { valid: false, issues: ['actions must contain at least one action.'] };
  const hasValidActions = actionValidation.valid;

  if (!hasValidGeneratedCode && !hasValidActions) {
    issues.push('At least one of generatedCode or actions must be present and valid.');
  }

  if (!hasValidGeneratedCode && generatedCodeIssues.length > 0) {
    issues.push(...generatedCodeIssues);
  }

  if (!hasValidGeneratedCode && !hasValidActions && actionValidation.issues.length > 0) {
    issues.push(...actionValidation.issues);
  }

  return { valid: hasValidGeneratedCode || hasValidActions, issues };
}
