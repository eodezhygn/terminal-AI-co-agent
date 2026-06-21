import { validateSandboxPath } from './sandbox-validator.js';

export function validateActionSafety(actions, options = {}) {
  const issues = [];

  if (!Array.isArray(actions)) {
    return { valid: false, issues: ['actions must be an array.'] };
  }

  actions.forEach((action, index) => {
    if (!action || typeof action !== 'object') {
      issues.push(`Action[${index}] must be an object.`);
      return;
    }

    const pathValue = action.path;
    if (typeof pathValue !== 'string' || !pathValue.trim()) {
      issues.push(`Action[${index}].path must be a non-empty string.`);
      return;
    }

    const validation = validateSandboxPath(pathValue, options);
    if (!validation.valid) {
      validation.issues.forEach((issue) => {
        issues.push(`Action[${index}]: ${issue}`);
      });
    }
  });

  return { valid: issues.length === 0, issues };
}
