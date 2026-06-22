import fs from 'fs/promises';
import path from 'path';

/**
 * @typedef {Object} Action
 * @property {string} type
 * @property {string} path
 * @property {string} [content]
 */

/**
 * @typedef {Object} ActionResult
 * @property {string} action
 * @property {string} path
 * @property {boolean} [success]
 * @property {boolean} [simulated]
 * @property {string} [error]
 */

/**
 * @typedef {Object} ExecuteActionsOptions
 * @property {boolean} [dryRun]
 */

/**
 * Resolve a filesystem path before acting on it.
 * @param {string} targetPath
 * @returns {string}
 */
function resolvePath(targetPath) {
  return path.resolve(targetPath);
}

/**
 * Verify that a path is provided and is a string.
 * @param {Action} action
 * @returns {ActionResult|null}
 */
function validateActionPath(action) {
  if (!action || typeof action.path !== 'string' || action.path.trim() === '') {
    return {
      action: action?.type || 'unknown',
      path: action?.path || '',
      success: false,
      error: 'Action path must be a non-empty string'
    };
  }
  return null;
}

/**
 * @param {Action} action
 * @param {boolean} dryRun
 * @returns {Promise<ActionResult>}
 */
async function executeAction(action, dryRun) {
  const baseResult = {
    action: action?.type || 'unknown',
    path: action?.path || ''
  };

  const validationError = validateActionPath(action);
  if (validationError) {
    return validationError;
  }

  const resolvedPath = resolvePath(action.path);

  if (dryRun) {
    return {
      ...baseResult,
      success: true,
      simulated: true
    };
  }

  try {
    switch (action.type) {
      case 'create_file': {
        const directory = path.dirname(resolvedPath);
        if (directory && directory !== '.') {
          await fs.mkdir(directory, { recursive: true });
        }
        await fs.writeFile(resolvedPath, action.content || '', 'utf8');
        return { ...baseResult, success: true };
      }
      case 'edit_file': {
        try {
          await fs.access(resolvedPath);
        } catch {
          return { ...baseResult, success: false, error: 'File does not exist' };
        }
        await fs.writeFile(resolvedPath, action.content || '', 'utf8');
        return { ...baseResult, success: true };
      }
      case 'delete_file': {
        try {
          await fs.access(resolvedPath);
        } catch {
          return { ...baseResult, success: false, error: 'File does not exist' };
        }
        await fs.rm(resolvedPath);
        return { ...baseResult, success: true };
      }
      default:
        return {
          ...baseResult,
          success: false,
          error: `Unsupported action type: ${action.type}`
        };
    }
  } catch (error) {
    return {
      ...baseResult,
      success: false,
      error: error?.message || 'Action execution failed'
    };
  }
}

/**
 * Execute a sequence of validated actions.
 * @param {Action[]} actions
 * @param {ExecuteActionsOptions} [options]
 * @returns {Promise<{success:boolean, results:ActionResult[], error?:string}>}
 */
export async function executeActions(actions, options = {}) {
  if (!Array.isArray(actions)) {
    return {
      success: false,
      error: 'Actions must be an array'
    };
  }

  const dryRun = Boolean(options.dryRun);
  const results = [];

  for (const action of actions) {
    const result = await executeAction(action, dryRun);
    results.push(result);
  }

  return {
    success: results.every((result) => result.success === true),
    results
  };
}
