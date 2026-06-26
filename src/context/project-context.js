import fs from 'fs';
import path from 'path';

/**
 * Extracts project context by reading and prioritizing key project files.
 * @param {string} projectRoot - Root directory of the project (defaults to current working directory)
 * @returns {Object} Structured context object containing docs, packageJson, readme, and structure
 */
export function extractProjectContext(projectRoot = process.cwd()) {
  const context = {
    docs: {},
    packageJson: null,
    readme: null,
    structure: {}
  };

  // Helper function to read file safely with size limit
  const readFile = (filePath) => {
    try {
      if (!fs.existsSync(filePath)) return null;
      const stats = fs.statSync(filePath);
      if (stats.size > 200 * 1024) return null; // Skip files > 200KB
      return fs.readFileSync(filePath, 'utf-8');
    } catch {
      return null;
    }
  };

  // Read docs in priority order
  const docPaths = {
    prd: 'docs/prd.md',
    architecture: 'docs/architecture.md',
    securityPrd: 'docs/security-prd.md'
  };

  for (const [key, relPath] of Object.entries(docPaths)) {
    const fullPath = path.join(projectRoot, relPath);
    const content = readFile(fullPath);
    if (content) {
      context.docs[key] = content;
    }
  }

  // Read package.json
  const packageJsonPath = path.join(projectRoot, 'package.json');
  const packageJsonContent = readFile(packageJsonPath);
  if (packageJsonContent) {
    try {
      context.packageJson = JSON.parse(packageJsonContent);
    } catch {
      context.packageJson = packageJsonContent;
    }
  }

  // Read README.md
  const readmePath = path.join(projectRoot, 'README.md');
  const readmeContent = readFile(readmePath);
  if (readmeContent) {
    context.readme = readmeContent;
  }

  // Build project structure recursively
  const buildStructure = (dir, maxDepth = 3, currentDepth = 0) => {
    if (currentDepth >= maxDepth) return {};

    const structure = {};
    const skipDirs = new Set(['node_modules', '.git', '.env', 'dist', 'build', '.vscode']);

    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (skipDirs.has(entry.name)) continue;

        const fullPath = path.join(dir, entry.name);

        if (entry.isDirectory()) {
          structure[entry.name] = buildStructure(fullPath, maxDepth, currentDepth + 1);
        } else if (entry.isFile()) {
          try {
            const stats = fs.statSync(fullPath);
            if (stats.size <= 200 * 1024) {
              structure[entry.name] = {
                type: 'file',
                size: stats.size
              };
            }
          } catch {
            // Skip files we cannot stat
          }
        }
      }
    } catch {
      // Skip directories we cannot read
    }

    return structure;
  };

  // Include src/ and backend/src/ in structure
  const srcPath = path.join(projectRoot, 'src');
  if (fs.existsSync(srcPath)) {
    context.structure.src = buildStructure(srcPath);
  }

  const backendSrcPath = path.join(projectRoot, 'backend', 'src');
  if (fs.existsSync(backendSrcPath)) {
    context.structure.backendSrc = buildStructure(backendSrcPath);
  }

  return context;
}
