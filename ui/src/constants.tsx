/* eslint-disable react-refresh/only-export-components */
export const COLUMNS = ["Backlog", "In Progress", "Done", "Failed"];

export const API_KEY_PROVIDERS = [
  { field: "anthropic_api_key", label: "Anthropic", placeholder: "sk-ant-…" },
  { field: "openai_api_key", label: "OpenAI", placeholder: "sk-…" },
  { field: "gemini_api_key", label: "Google Gemini", placeholder: "AIza…" },
  { field: "groq_api_key", label: "Groq", placeholder: "gsk_…" },
  { field: "mistral_api_key", label: "Mistral", placeholder: "…" },
];

export const MODEL_ROLES = [
  { field: "orchestrator_model", label: "Orchestrator", hint: "Goal decomposition" },
  { field: "subagent_model", label: "Sub-agent / Coder", hint: "Code writing" },
  { field: "reviewer_model", label: "Reviewer", hint: "Quality gate" },
  { field: "refiner_model", label: "Refiner", hint: "Fix planning" },
];

export function GithubLogo({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
    </svg>
  );
}
