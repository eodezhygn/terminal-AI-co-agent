#!/usr/bin/env node
import {  analyzeProject } from './project-analyzer.js';
import 'dotenv/config';
import { readFile, writeFile, createFolder } from './fs.js';
import { execShell } from './terminal.js';
import { callAI, getProvider, resolveAIProviderName } from './ai.js';
import { findRelevantFiles, compressFileForContext } from './context.js';
import { debugShell } from './debug.js';
import { Planner } from './planner.js';
import { AgentManager } from './agent-manager.js';
import { LongRunningTaskManager } from './longRunning.js';
import { SimpleAgent } from './agents/simpleAgent.js';
import { embedText, getEmbeddingProvider } from './embeddings.js';
import { formatApprovalPlan, promptApproval, formatTerminalApprovalPlan, promptTerminalApproval } from './approval.js';
import { executePlan, executeTerminalActions } from './executor.js';
import { executeActions } from './executor/action-executor.js';

function usage() {
  console.log(`
Terminal AI Co-Agent CLI

Usage:
  ai read <path>
  ai write <path> <content>
  ai mkdir <path>
  ai exec <command>
  ai retry <command>
  ai debug <command>
  ai select <query>
  ai context <path>
  ai plan <task description>
  ai embed "<text>"
  ai agent-list
  ai agent-run <agent> <task>
  ai longrun <name> <command>
  ai longrun-status <taskId>
  ai ai [--model <model>] <prompt>

Examples:
  ai ai Design architecture for app
  ai ai "\nBuild architecture\nRequirements:\n- offline first\n- GPS\n"
  cat prompt.txt | ai ai

Environment:
  OPENAI_API_KEY, OPENROUTER_API_KEY, or GEMINI_API_KEY
  DEFAULT_PROVIDER optionally chooses the default provider
  DEFAULT_MODEL optionally chooses the default model
  AI_BASE_URL optionally overrides the provider endpoint
`);
}

async function readStdin() {
  return new Promise((resolve, reject) => {
    let input = '';
    process.stdin.setEncoding('utf8');

    process.stdin.on('data', (chunk) => {
      input += chunk;
    });

    process.stdin.on('end', () => {
      resolve(input);
    });

    process.stdin.on('error', reject);
  });
}

function parseAIArguments(args) {
  const parts = [...args];
  const separatorIndex = parts.indexOf('--');
  const candidateParts = separatorIndex !== -1 ? parts.slice(0, separatorIndex) : parts;
  const promptParts = separatorIndex !== -1 ? parts.slice(separatorIndex + 1) : [...parts];
  const parsed = { explicitModel: null, promptParts };

  const modelFlagIndex = candidateParts.findIndex((arg) => arg === '--model' || arg.startsWith('--model='));
  if (modelFlagIndex !== -1) {
    const flag = candidateParts[modelFlagIndex];
    if (flag === '--model') {
      parsed.explicitModel = candidateParts[modelFlagIndex + 1];
      candidateParts.splice(modelFlagIndex, 2);
    } else {
      parsed.explicitModel = flag.split('=')[1];
      candidateParts.splice(modelFlagIndex, 1);
    }

    if (separatorIndex === -1) {
      parsed.promptParts = candidateParts;
    }
  }

  return parsed;
}

const manager = new AgentManager();
const longRunning = new LongRunningTaskManager();
const defaultAgent = new SimpleAgent('local', async (task) => {
  return `local agent executed task: ${task}`;
});
manager.registerAgent(defaultAgent);
const planner = new Planner({ agents: [defaultAgent] });

async function main() {
  const [, , command, ...rest] = process.argv;

  if (!command) {
    usage();
    process.exit(1);
  }

  try {
    switch (command) {
      case 'read': {
        const [filePath] = rest;
        if (!filePath) throw new Error('Missing file path.');
        const content = await readFile(filePath);
        process.stdout.write(content);
        break;
      }
      case 'write': {
        const [filePath, ...contentParts] = rest;
        if (!filePath) throw new Error('Missing file path.');
        if (contentParts.length === 0) throw new Error('Missing content.');
        await writeFile(filePath, contentParts.join(' '));
        console.log(`Wrote ${filePath}`);
        break;
      }
      case 'mkdir': {
        const [folderPath] = rest;
        if (!folderPath) throw new Error('Missing folder path.');
        await createFolder(folderPath);
        console.log(`Created ${folderPath}`);
        break;
      }
      case 'exec': {
        const commandString = rest.join(' ');
        if (!commandString) throw new Error('Missing shell command.');
        const result = await execShell(commandString);
        process.stdout.write(result.stdout);
        if (result.stderr) process.stderr.write(result.stderr);
        process.exit(result.code ?? 0);
        break;
      }
      case 'retry': {
        const commandString = rest.join(' ');
        if (!commandString) throw new Error('Missing shell command.');
        const result = await debugShell(commandString, { retries: 2, delayMs: 500, ai: false });
        process.stdout.write(result.result.stdout);
        if (result.result.stderr) process.stderr.write(result.result.stderr);
        if (!result.success) {
          console.error(result.analysis);
          process.exit(result.result.code ?? 1);
        }
        break;
      }
      case 'debug': {
        const commandString = rest.join(' ');
        if (!commandString) throw new Error('Missing shell command.');
        const result = await debugShell(commandString, { retries: 1, delayMs: 300, ai: Boolean(getProvider()) });
        process.stdout.write(result.result.stdout);
        if (result.result.stderr) process.stderr.write(result.result.stderr);
        if (result.analysis) {
          console.log(`\nDebug summary: ${result.analysis}`);
        }
        if (result.aiSuggestion) {
          console.log('\nAI suggestion:');
          console.log(result.aiSuggestion);
        }
        if (!result.success) {
          process.exit(result.result.code ?? 1);
        }
        break;
      }
      case 'select': {
        const query = rest.join(' ').trim();
        if (!query) throw new Error('Missing search query.');
        const files = await findRelevantFiles(process.cwd(), query, { maxFiles: 10 });
        console.log(files.join('\n'));
        break;
      }
      case 'context': {
        const [filePath] = rest;
        if (!filePath) throw new Error('Missing file path.');
        const content = await compressFileForContext(filePath);
        process.stdout.write(content);
        break;
      }
      case 'plan': {
        const description = rest.join(' ').trim();
        if (!description) throw new Error('Missing task description.');
        const plan = planner.createPlan(description);
        console.log(JSON.stringify(plan, null, 2));
        break;
      }
      case 'embed': {
        const text = rest.join(' ').trim();
        if (!text) throw new Error('Missing text to embed.');
        const vector = await embedText(text);
        console.log(JSON.stringify({ provider: getEmbeddingProvider() || 'stub', length: vector.length }));
        break;
      }
      case 'agent-list': {
        const agents = manager.listAgents();
        console.log(agents.map((agent) => agent.name).join('\n'));
        break;
      }
      case 'agent-run': {
        const [agentName, ...taskParts] = rest;
        if (!agentName) throw new Error('Missing agent name.');
        
        // Parse --model flag from task arguments
        const { explicitModel, promptParts } = parseAIArguments(taskParts);
        const task = promptParts.join(' ').trim();
        if (!task) throw new Error('Missing task description.');

        // Phase 1: Generate approval plan
        const approvalPlan = planner.createApprovalPlan(task);
        console.log(formatApprovalPlan(approvalPlan));

        // Phase 1: Get filesystem approval
        const filesystemApproved = await promptApproval();
        if (!filesystemApproved) {
          console.log('\nCANCELLED: No changes were made.');
          break;
        }

        console.log('\nFilesystem execution approved.');
        
        // Phase 2: Execute filesystem actions
        const projectContext = await analyzeProject(  process.cwd() );

const executionPlan = planner.createExecutionPlan( task, projectContext );
        const filesystemResult =  await executeActions(executionPlan, {    dryRun: false  });

        // Phase 3: Check for terminal actions
        const terminalActions = approvalPlan.terminalActions || [];
        let terminalResult = { executed: [], failed: [], skipped: [], total: 0 };

        if (terminalActions.length > 0) {
          console.log(formatTerminalApprovalPlan(terminalActions));
          
          const terminalApproved = await promptTerminalApproval();
          if (!terminalApproved) {
            console.log('\nSkipped terminal execution.');
          } else {
            console.log('\nTerminal execution approved.');
            terminalResult = await executeTerminalActions(terminalActions);
          }
        }

        // Final summary
        console.log('\n═══════════════════════════════');
        console.log('EXECUTION SUMMARY');
        console.log('═══════════════════════════════\n');

        console.log('Filesystem operations:');

const successfulActions =
  filesystemResult.results.filter(r => r.success);

const failedActions =
  filesystemResult.results.filter(r => !r.success);

console.log(`  Success: ${filesystemResult.success}`);
console.log(`  Actions: ${filesystemResult.results.length}`);
console.log(`  Successful: ${successfulActions.length}`);
console.log(`  Failed: ${failedActions.length}`);


        console.log('\nTerminal commands:');
        console.log(`  Executed: ${terminalResult.executed.length}`);
        console.log(`  Failed: ${terminalResult.failed.length}`);
        console.log(`  Skipped: ${terminalResult.skipped.length}`);
/*
        if (filesystemResult.createdFiles.length > 0) {
          console.log('\nCreated files:');
          filesystemResult.createdFiles.forEach((file) => console.log(`  - ${file}`));
        }

        if (filesystemResult.editedFiles.length > 0) {
          console.log('\nEdited files:');
          filesystemResult.editedFiles.forEach((file) => console.log(`  - ${file}`));
        }

        if (filesystemResult.skipped.length > 0) {
          console.log('\nSkipped files:');
          filesystemResult.skipped.forEach((file) => console.log(`  - ${file}`));
        }

        if (filesystemResult.failed.length > 0) {
          console.log('\nFailed file actions:');
          filesystemResult.failed.forEach(({ action, error }) => {
            console.log(`  - ${action.path || action.type}: ${error}`);
          });
        }
*/
        if (terminalResult.executed.length > 0) {
          console.log('\nExecuted commands:');
          terminalResult.executed.forEach(({ command }) => console.log(`  - ${command}`));
        }

        if (terminalResult.failed.length > 0) {
          console.log('\nFailed commands:');
          terminalResult.failed.forEach(({ command, error, blocked }) => {
            if (blocked) {
              console.log(`  - ${command} (BLOCKED: ${error})`);
            } else {
              console.log(`  - ${command}: ${error}`);
            }
          });
        }

        console.log('\n═══════════════════════════════\n');

        break;
      }
      case 'longrun': {
        const [name, ...commandParts] = rest;
        if (!name) throw new Error('Missing task name.');
        const commandString = commandParts.join(' ').trim();
        if (!commandString) throw new Error('Missing command.');
        const taskId = longRunning.createTask(name, async () => {
          const result = await execShell(commandString);
          if (result.code !== 0) {
            throw new Error(result.stderr || `Command failed with code ${result.code}`);
          }
          return result.stdout.trim();
        });
        console.log(taskId);
        break;
      }
      case 'longrun-status': {
        const [taskId] = rest;
        if (!taskId) throw new Error('Missing task ID.');
        const task = longRunning.getTask(taskId);
        if (!task) {
          throw new Error(`Task not found: ${taskId}`);
        }
        console.log(JSON.stringify(task, null, 2));
        break;
      }
      case 'ai': {
        const { explicitModel, promptParts } = parseAIArguments(rest);
        let prompt = promptParts.join(' ').trim();

        if (!prompt && !process.stdin.isTTY) {
          prompt = (await readStdin()).trim();
        }

        if (!prompt) throw new Error('Missing prompt text.');
        const providerName = resolveAIProviderName(prompt, explicitModel);
        console.log(`Provider: ${providerName}`);
        const output = await callAI(prompt, { model: explicitModel });
        process.stdout.write(output + '\n');
        break;
      }
      default:
        throw new Error(`Unknown command: ${command}`);
    }
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}

main();
