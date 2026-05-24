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

export interface WhyResponse {
  symbol: string;
  explanation: string;
  provenance: unknown[];
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

  async why(file: string, line: number, symbol: string): Promise<WhyResponse> {
    const params = new URLSearchParams({ file, line: String(line), symbol });
    const response = await fetch(`${this.baseUrl}/why?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) {
      throw new Error(`Why request failed: ${response.status}`);
    }
    return (await response.json()) as WhyResponse;
  }

  async fiveWhys(file: string, line: number, symbol: string): Promise<unknown> {
    const params = new URLSearchParams({ file, line: String(line), symbol });
    const response = await fetch(`${this.baseUrl}/five-whys?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) {
      throw new Error(`Five-whys request failed: ${response.status}`);
    }
    return response.json();
  }

  async counterfactual(decisionId: string): Promise<unknown> {
    const params = new URLSearchParams({ decision_id: decisionId });
    const response = await fetch(`${this.baseUrl}/counterfactual?${params}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) {
      throw new Error(`Counterfactual request failed: ${response.status}`);
    }
    return response.json();
  }

  mockStatus(): StatusResponse {
    return { ...MOCK_STATUS };
  }
}
