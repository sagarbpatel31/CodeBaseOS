export type NodeType =
  | "File"
  | "Symbol"
  | "Commit"
  | "PR"
  | "Issue"
  | "Discussion"
  | "Decision"
  | "Person"
  | "Repository"
  | "Identity"
  | "Episode"
  | "ReviewComment";

export const NODE_COLORS: Record<NodeType, string> = {
  File: "#3B82F6",
  Symbol: "#06B6D4",
  Commit: "#22C55E",
  PR: "#F97316",
  Issue: "#EAB308",
  Discussion: "#EC4899",
  Decision: "#F59E0B",
  Person: "#FFFFFF",
  Repository: "#8B5CF6",
  Identity: "#A78BFA",
  Episode: "#6EE7B7",
  ReviewComment: "#FCA5A5",
};

export const NODE_TYPES: NodeType[] = Object.keys(NODE_COLORS) as NodeType[];

export function nodeColor(type: string): string {
  return NODE_COLORS[type as NodeType] ?? "#94A3B8";
}
