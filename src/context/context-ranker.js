// Simple, dependency-free file relevance ranker using heuristics.
// Designed to be replaced later by semantic ranking.

function normalize(text) {
  return (text || '').toLowerCase();
}

function scoreForFilenameMatch(taskText, filename) {
  const name = normalize(filename);
  const nameNoExt = name.replace(/\.[^.]+$/, '');
  let score = 0;
  const text = normalize(taskText || '');

  // exact match if task text contains full filename or filename without extension
  if (text.includes(name) || (nameNoExt && text.includes(nameNoExt))) {
    score += 1000; // exact filename match (highest)
  }

  // partial token matches
  const tokens = text.split(/[^a-z0-9]+/).filter(Boolean);
  for (const k of tokens) {
    if (!k) continue;
    if (name === k) score += 1000; // defensive: token equals filename
    else if (name.includes(k) || nameNoExt.includes(k)) score += 50;
  }

  return score;
}

function scoreForDirectoryMatch(taskKeywords, filepath) {
  const parts = normalize(filepath).split('/');
  const dirs = parts.slice(0, -1);
  let score = 0;
  for (const kw of taskKeywords) {
    if (!kw) continue;
    const k = normalize(kw);
    for (const d of dirs) {
      if (d === k) score += 200;
      else if (d.includes(k)) score += 20;
    }
  }
  return score;
}

function isTestOrDoc(filepath) {
  const p = normalize(filepath);
  return p.includes('/test') || p.endsWith('.md') || p.endsWith('.markdown') || p.includes('/tests/') || p.includes('__tests__') || p.endsWith('.spec.js') || p.endsWith('.test.js');
}

export function rankRelevantFiles(task, candidateFiles, projectContext = {}) {
  const text = typeof task === 'string' ? task : (task && (task.text || task.description || ''));
  const tokens = (text || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);

  const scored = candidateFiles.map((f, idx) => {
    let score = 0;
    // filename match
    const filename = f.split('/').pop();
    score += scoreForFilenameMatch(text, filename);
    // directory match
    score += scoreForDirectoryMatch(tokens, f);
    // small bonus for files under src/
    if (normalize(f).startsWith('src/')) score += 10;
    // penalize docs and tests for edit tasks
    const isEditTask = /(edit|change|modify|fix|update)/.test(normalize(text));
    if (isEditTask && isTestOrDoc(f)) score -= 100;
    return { path: f, score, index: idx };
  });

  // stable sort: by score desc, then original index asc to preserve stability
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.index - b.index;
  });

  return scored.map(s => s.path);
}
