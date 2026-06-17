import openaiProvider from './openai.js';
import openrouterProvider from './openrouter.js';
import geminiProvider from './gemini.js';
import ollamaProvider from './ollama.js';

const providers = {
  openai: openaiProvider,
  openrouter: openrouterProvider,
  gemini: geminiProvider,
  ollama: ollamaProvider
};

const taskRoutes = [
  {
    keywords: ['architecture', 'planning', 'product', 'spec', 'ux research', 'frontend ui'],
    model: process.env.PLANNING_MODEL || 'qwen/qwen3-next-80b-a3b-instruct'
  },
  {
    keywords: ['backend', 'api', 'apis', 'ai orchestration'],
    model: process.env.CODING_MODEL || 'qwen/qwen3-coder-480b-a35b-instruct'
  },
  {
    keywords: ['debug', 'fix', 'bug', 'frontend design'],
    model: process.env.DEBUG_MODEL || 'deepseek/deepseek-v4-fast'
  },
  {
    keywords: ['summarize', 'summary', 'recap', 'overview', 'explain', 'brief'],
    model: process.env.FALLBACK_MODEL || 'gemini-2.5-flash'
  }
];

export function getProviderByName(name) {
  if (!name) return null;
  return providers[name.toLowerCase()] || null;
}

export function getAvailableProviders() {
  return Object.values(providers).filter((provider) => provider.isAvailable());
}

export function getConfiguredDefaultProvider() {
  const configured = process.env.DEFAULT_PROVIDER?.toLowerCase();
  if (configured) {
    const provider = getProviderByName(configured);
    if (provider?.isAvailable()) {
      return provider;
    }
  }

  const available = getAvailableProviders();
  if (available.some((provider) => provider.name === 'openrouter')) {
    return openrouterProvider;
  }

  return available[0] || null;
}

export function modelToProvider(model) {
  if (!model) return null;
  const normalized = model.toLowerCase();

  if (normalized.startsWith('qwen/') || normalized.startsWith('deepseek/')) {
    return openrouterProvider;
  }

  if (normalized.startsWith('gemini-')) {
    return geminiProvider;
  }

  if (normalized.startsWith('gpt-') || normalized.startsWith('text-') || normalized.startsWith('gpt4') || normalized.startsWith('gpt-4')) {
    return openaiProvider;
  }

  return null;
}

export function selectTaskModel(prompt) {
  if (!prompt || !prompt.trim()) {
    return process.env.FALLBACK_MODEL || 'gemini-2.5-flash';
  }

  const lowerPrompt = prompt.toLowerCase();
  for (const route of taskRoutes) {
    if (route.keywords.some((keyword) => lowerPrompt.includes(keyword))) {
      return route.model;
    }
  }

  return process.env.FALLBACK_MODEL || 'gemini-2.5-flash';
}

export function chooseProviderAndModel({ explicitModel, prompt }) {
  if (explicitModel) {
    const provider = modelToProvider(explicitModel);
    if (provider) {
      if (!provider.isAvailable()) {
        throw new Error(`No AI provider configured for explicit model. Ensure the provider for ${explicitModel} is available in .env.`);
      }
      return { provider, model: explicitModel };
    }

    const fallback = getConfiguredDefaultProvider();
    if (!fallback) {
      throw new Error('No AI provider configured. Add OPENROUTER_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY to .env.');
    }
    return { provider: fallback, model: explicitModel };
  }

  const routedModel = selectTaskModel(prompt);
  const routedProvider = modelToProvider(routedModel);
  if (routedProvider?.isAvailable()) {
    return { provider: routedProvider, model: routedModel };
  }

  const fallbackProvider = getConfiguredDefaultProvider();
  if (!fallbackProvider) {
    throw new Error('No AI provider configured. Add OPENROUTER_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY to .env.');
  }

  return {
    provider: fallbackProvider,
    model: fallbackProvider.getDefaultModel()
  };
}

export function getAvailableProviderNames() {
  return getAvailableProviders().map((provider) => provider.name);
}
