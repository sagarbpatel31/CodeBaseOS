export interface StatusResponse {
  costSpent: number;
  costCap: number;
  nodeCount: number;
  repoCount: number;
  merkleOk: boolean;
  merkleHead: string;
}

export interface SummaryResponse {
  symbol: string;
  file: string;
  line: number;
  summary: string;
}

export interface Citation {
  type: string;
  title: string;
  url: string;
}

export interface WhyResponse {
  file: string;
  line: number;
  explanation: string;
  citations?: Citation[];
  context_nodes: number;
  cost_usd: number;
}

export interface WhyStep {
  level: number;
  question: string;
  answer: string;
}

export interface FiveWhysResponse {
  file: string;
  line: number;
  chain: WhyStep[];
  context_nodes: number;
  cost_usd: number;
}

export interface CounterfactualResponse {
  decision: string;
  analysis: string;
  context_nodes: number;
  cost_usd: number;
}

export interface HandoffResponse {
  module: string;
  overview: string;
  start_here: string;
  key_files: string[];
  key_people: string[];
  key_decisions: string[];
  context_nodes: number;
  cost_usd: number;
}

export interface ProvenanceHop {
  order: number;
  type: string;
  title: string;
  detail: string;
  when: string;
  url?: string;
}
export interface VerifiedEdge {
  predicate: string;
  context: string;
  confidence: number;
}
export interface ProvenanceResponse {
  file: string;
  line: number;
  chain: ProvenanceHop[];
  verified_edges: VerifiedEdge[];
  context_nodes: number;
  cost_usd: number;
}
export interface ExplainFileResponse {
  file: string;
  summary: string;
  owner: string;
  key_points: string[];
  key_decisions: string[];
  context_nodes: number;
  cost_usd: number;
}

export interface DiffChange {
  type: string;
  title: string;
  when: string;
}
export interface DiffResponse {
  since: string;
  until: string;
  file: string;
  count: number;
  changes: DiffChange[];
}

export interface BusFactorResponse {
  repo: string;
  contributors: { name: string; commits: number }[];
  total_commits: number;
  unique_authors: number;
  bus_factor: number;
  risk: string;
}

const MOCK_STATUS: StatusResponse = {
  costSpent: 0.0,
  costCap: 5.0,
  nodeCount: 0,
  repoCount: 0,
  merkleOk: true,
  merkleHead: '',
};

export class CodebaseOSClient {
  constructor(public readonly baseUrl: string) {}

  async status(): Promise<StatusResponse> {
    const response = await fetch(`${this.baseUrl}/status`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(2_500),
    });
    if (!response.ok) {
      throw new Error(`Status request failed: ${response.status} ${response.statusText}`);
    }
    return (await response.json()) as StatusResponse;
  }

  async summary(file: string, line: number, symbol: string): Promise<SummaryResponse> {
    const params = new URLSearchParams({ file, line: String(line), symbol });
    const response = await fetch(`${this.baseUrl}/summary?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) {
      throw new Error(`Summary request failed: ${response.status}`);
    }
    return (await response.json()) as SummaryResponse;
  }

  async why(file: string, line: number, repo = ''): Promise<WhyResponse> {
    const params = new URLSearchParams({ file, line: String(line) });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/why?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) {
      throw new Error(`Why request failed: ${response.status}`);
    }
    return (await response.json()) as WhyResponse;
  }

  async baselineRag(file: string, line: number, repo = ''): Promise<WhyResponse> {
    const params = new URLSearchParams({ file, line: String(line) });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/baseline-rag?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) {
      throw new Error(`Baseline-RAG request failed: ${response.status}`);
    }
    return (await response.json()) as WhyResponse;
  }

  async fiveWhys(file: string, line: number, repo = ''): Promise<FiveWhysResponse> {
    const params = new URLSearchParams({ file, line: String(line) });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/five-whys?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(25_000),
    });
    if (!response.ok) {
      throw new Error(`Five-whys request failed: ${response.status}`);
    }
    return (await response.json()) as FiveWhysResponse;
  }

  async counterfactual(decision: string): Promise<CounterfactualResponse> {
    const params = new URLSearchParams({ decision });
    const response = await fetch(`${this.baseUrl}/counterfactual?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(25_000),
    });
    if (!response.ok) {
      throw new Error(`Counterfactual request failed: ${response.status}`);
    }
    return (await response.json()) as CounterfactualResponse;
  }

  async handoff(module: string, repo = ''): Promise<HandoffResponse> {
    const params = new URLSearchParams({ module });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/handoff?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      throw new Error(`Handoff request failed: ${response.status}`);
    }
    return (await response.json()) as HandoffResponse;
  }

  async provenance(file: string, line: number, repo = ''): Promise<ProvenanceResponse> {
    const params = new URLSearchParams({ file, line: String(line) });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/provenance?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      throw new Error(`Provenance request failed: ${response.status}`);
    }
    return (await response.json()) as ProvenanceResponse;
  }

  async ingestRepo(
    repo: string,
    opts: { commits?: number; prs?: number; issues?: number; auto?: boolean } = {}
  ): Promise<{
    repo: string;
    ingested: Record<string, number>;
    total_commits?: number;
    ingested_commits?: number;
    complete?: boolean;
  }> {
    const params = new URLSearchParams({ repo });
    if (opts.auto) params.set('auto', '1');
    if (opts.commits != null) params.set('commits', String(opts.commits));
    if (opts.prs != null) params.set('prs', String(opts.prs));
    if (opts.issues != null) params.set('issues', String(opts.issues));
    const response = await fetch(`${this.baseUrl}/repos?${params}`, {
      method: 'POST',
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(180_000),
    });
    if (!response.ok) {
      throw new Error(`Ingest failed: ${response.status}`);
    }
    return (await response.json()) as {
      repo: string;
      ingested: Record<string, number>;
      total_commits?: number;
      ingested_commits?: number;
      complete?: boolean;
    };
  }

  async explainFile(file: string, repo = ''): Promise<ExplainFileResponse> {
    const params = new URLSearchParams({ file });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/explain-file?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      throw new Error(`Explain-file request failed: ${response.status}`);
    }
    return (await response.json()) as ExplainFileResponse;
  }

  async diff(opts: { repo?: string; since: string; until: string; file?: string }): Promise<DiffResponse> {
    const params = new URLSearchParams({ since: opts.since, until: opts.until });
    if (opts.repo) params.set('repo', opts.repo);
    if (opts.file) params.set('file', opts.file);
    const response = await fetch(`${this.baseUrl}/diff?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) {
      throw new Error(`Diff request failed: ${response.status}`);
    }
    return (await response.json()) as DiffResponse;
  }

  async ask(q: string, repo = ''): Promise<{ answer: string; citations: Citation[] }> {
    const params = new URLSearchParams({ q });
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/ask?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`Ask request failed: ${response.status}`);
    return (await response.json()) as { answer: string; citations: Citation[] };
  }

  async risk(repo = ''): Promise<{ files: { path: string; author: string; risk: string }[] }> {
    const params = new URLSearchParams();
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/risk?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) throw new Error(`Risk request failed: ${response.status}`);
    return (await response.json()) as { files: { path: string; author: string; risk: string }[] };
  }

  async auditReport(repo = ''): Promise<{ markdown: string }> {
    const params = new URLSearchParams();
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/audit-report?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`Audit-report request failed: ${response.status}`);
    return (await response.json()) as { markdown: string };
  }

  async busFactor(repo = ''): Promise<BusFactorResponse> {
    const params = new URLSearchParams();
    if (repo) params.set('repo', repo);
    const response = await fetch(`${this.baseUrl}/bus-factor?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) {
      throw new Error(`Bus-factor request failed: ${response.status}`);
    }
    return (await response.json()) as BusFactorResponse;
  }

  mockStatus(): StatusResponse {
    return { ...MOCK_STATUS };
  }
}
