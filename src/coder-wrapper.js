import { getModelForRole } from './local-model-router.js';

/**
 * Runs the coder model with deterministic metadata-only response (stub)
 * @param {Object} config - Configuration object
 * @param {string} config.role - Model role (default: 'coder')
 * @param {Object} config.reducedContext - Reduced context for the task
 * @returns {Object} Metadata-only response with stub status
 */
export async function runCoder({ role = 'coder', reducedContext }) {
  // Select model using getModelForRole
  const selectedModel = getModelForRole(role);

  // Build metadata-only response (no AI generation)
  const response = {
    role,
    selectedModel,
    task: reducedContext?.task || null,
    contextSize: reducedContext ? Object.keys(reducedContext).length : 0,
    status: 'stub',
    generatedCode: null
  };

  return response;
}
