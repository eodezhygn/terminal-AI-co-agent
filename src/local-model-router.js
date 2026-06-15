/**
 * Lightweight local model router — deterministic, pure functions.
 *
 * Exports:
 * - getModelForRole(role)
 * - getRoleForIntent(intent)
 *
 * Notes:
 * - ESM module
 * - No external calls or integrations
 * - Normalizes input with trim()+toLowerCase()
 */

/** @type {Record<string, string>} */
const ROLE_MODEL_MAP = {
  planner: 'qwen2.5:0.5b',
  coder: 'qwen2.5-coder:1.5b',
};

/** @type {Record<string, 'planner' | 'coder'>} */
const INTENT_ROLE_MAP = {
  planning: 'planner',
  implementation: 'coder',
  filesystem: 'planner',
  unknown: 'planner',
};

/**
 * Resolve a model name for a logical role.
 *
 * @param {string} role - Logical role (e.g., 'planner', 'coder')
 * @returns {string} Model identifier to use for the role.
 */
export function getModelForRole(role) {
  const normalizedRole = String(role ?? '').trim().toLowerCase();
  return (
    ROLE_MODEL_MAP[normalizedRole] || process.env.DEFAULT_MODEL || 'gemini'
  );
}

/**
 * Resolve the agent role for a given task intent.
 *
 * @param {string} intent - Intent classification (e.g., 'planning')
 * @returns {'planner'|'coder'} The mapped role.
 */
export function getRoleForIntent(intent) {
  const normalizedIntent = String(intent ?? '').trim().toLowerCase();
  return INTENT_ROLE_MAP[normalizedIntent] || 'planner';
}
