// ESM module

/**
 * reduceTaskContext
 * @param {Object} params
 * @param {string} params.taskDescription
 * @param {Object} params.projectContext - structured object from context-extractor.js
 * @returns {string} compact deterministic JSON string payload (suitable for tiny local models)
 */
export function reduceTaskContext({ taskDescription = '', projectContext = {} } = {}) {
  const MAX_TOTAL_BYTES = 2048; // ~2KB target

  const norm = (text = '') => {
    if (typeof text !== 'string') return '';
    // Remove code fences
    text = text.replace(/```[\s\S]*?```/g, '');
    // Remove images and links
    text = text.replace(/!\[[^\]]*\]\([^\)]*\)/g, '');
    text = text.replace(/https?:\/\/[^\s)]+/g, '');
    // Collapse whitespace
    return text.replace(/\s+/g, ' ').trim();
  };

  const shorten = (text, n) => {
    if (!text) return '';
    if (text.length <= n) return text;
    return text.slice(0, Math.max(0, n - 1)) + '\u2026';
  };

  const detectFramework = (pkg = {}) => {
    const obj = {};
    const deps = Object.assign({}, pkg.dependencies || {}, pkg.devDependencies || {});
    const keys = Object.keys(deps).map((k) => k.toLowerCase()).sort();

    if (keys.includes('react') || keys.includes('next')) obj.frontend = 'react';
    else if (keys.includes('vue')) obj.frontend = 'vue';
    else if (keys.includes('angular')) obj.frontend = 'angular';
    else if (keys.includes('svelte')) obj.frontend = 'svelte';
    else obj.frontend = 'unknown';

    if (keys.includes('express') || keys.includes('fastify') || keys.includes('koa')) obj.backend = 'node';
    else if (keys.includes('django') || keys.includes('flask')) obj.backend = 'python';
    else obj.backend = 'unknown';

    return obj;
  };

  const countStructure = (node) => {
    let files = 0;
    let dirs = 0;
    let size = 0;

    const walk = (n) => {
      if (!n || typeof n !== 'object') return;
      for (const k of Object.keys(n).sort()) {
        const v = n[k];
        if (v && typeof v === 'object' && v.type === 'file') {
          files += 1;
          size += Number(v.size || 0);
        } else if (v && typeof v === 'object') {
          dirs += 1;
          walk(v);
        }
      }
    };

    walk(node);
    return { files, dirs, size };
  };

  const pc = projectContext || {};

  // Prepare concise summaries
  let task = shorten(norm(taskDescription), 200);

  const pkg = pc.packageJson && typeof pc.packageJson === 'object' ? pc.packageJson : null;
  const framework = detectFramework(pkg || {});

  const frontendPath = pc.structure && pc.structure.src ? 'src' : null;
  const backendPath = pc.structure && pc.structure.backendSrc ? 'backend/src' : (pc.structure && pc.structure.api ? 'api' : null);

  // Summarize docs in priority order
  const docsOrder = ['prd', 'architecture', 'securityPrd'];
  const docs = {};
  for (const k of docsOrder) {
    if (pc.docs && pc.docs[k]) {
      docs[k] = shorten(norm(pc.docs[k]), 400);
    }
  }

  // README short
  const readme = shorten(norm(pc.readme || ''), 400);

  // Structure lightweight summary
  const structureSummary = {};
  if (pc.structure && pc.structure.src) {
    structureSummary.src = countStructure(pc.structure.src);
    // list top-level entries (names) limited to 8
    structureSummary.srcTop = Object.keys(pc.structure.src).sort().slice(0, 8);
  }
  if (pc.structure && pc.structure.backendSrc) {
    structureSummary.backendSrc = countStructure(pc.structure.backendSrc);
    structureSummary.backendTop = Object.keys(pc.structure.backendSrc).sort().slice(0, 8);
  }

  // Build deterministic payload object (ordered keys)
  const payloadObj = {
    task,
    framework: { frontend: framework.frontend, backend: framework.backend },
    paths: { frontend: frontendPath, backend: backendPath },
    docs,
    readme,
    structure: structureSummary
  };

  // Compactify and enforce size limit by trimming docs/readme/task if necessary
  let out = JSON.stringify(payloadObj);
  if (out.length > MAX_TOTAL_BYTES) {
    // progressively shrink fields
    let docMax = 300;
    let taskMax = 100;
    let readmeMax = 300;
    while (out.length > MAX_TOTAL_BYTES && (docMax > 32 || taskMax > 16 || readmeMax > 32)) {
      for (const k of Object.keys(docs)) {
        docs[k] = shorten(docs[k], docMax);
      }
      task = shorten(task, taskMax);
      const readmeShort = shorten(readme, readmeMax);
      payloadObj.task = task;
      payloadObj.docs = docs;
      payloadObj.readme = readmeShort;
      out = JSON.stringify(payloadObj);
      docMax = Math.max(32, Math.floor(docMax * 0.7));
      taskMax = Math.max(16, Math.floor(taskMax * 0.7));
      readmeMax = Math.max(32, Math.floor(readmeMax * 0.7));
    }
  }

  // Final safety: if still too large, return a minimal trimmed payload
  if (out.length > MAX_TOTAL_BYTES) {
    const minimal = {
      task: shorten(task, 64),
      framework: payloadObj.framework,
      paths: payloadObj.paths,
      structure: payloadObj.structure
    };
    out = JSON.stringify(minimal);
  }

  return out;
}

export default reduceTaskContext;
