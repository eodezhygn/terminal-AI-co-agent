import { execSync } from 'child_process';

export function createGitCheckpoint({ message, cwd = process.cwd() }) {
  if (typeof message !== 'string' || message.trim() === '') {
    return {
      success: false,
      reason: 'git_error',
      error: 'Commit message must be a non-empty string.',
    };
  }

  try {
    execSync('git rev-parse --is-inside-work-tree', {
      cwd,
      stdio: 'pipe',
    });

    const status = execSync('git status --porcelain', {
      cwd,
      stdio: 'pipe',
    }).toString('utf8').trim();

    if (!status) {
      return {
        success: false,
        reason: 'no_changes',
      };
    }

    execSync('git add .', {
      cwd,
      stdio: 'pipe',
    });

    execSync(`git commit -m ${JSON.stringify(message)}`, {
      cwd,
      stdio: 'pipe',
    });

    const commitHash = execSync('git rev-parse HEAD', {
      cwd,
      stdio: 'pipe',
    }).toString('utf8').trim();

    return {
      success: true,
      commitHash,
      message,
    };
  } catch (error) {
    return {
      success: false,
      reason: 'git_error',
      error: error?.message ?? String(error),
    };
  }
}
