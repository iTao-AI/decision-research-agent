# P2A Real-Source Proof

Executed on 2026-06-25 against the fixed
`talent-agent-hiring-signals-v1` manifest.

## Result

- Manifest hash:
  `6eef614ee58f65c10980ed48d43ad6ee52129402ad3879a678c3627b34fc7281`
- Run: `run_3f0cd851906141fa8edff985736b7883`
- Sources inspected: 6
- Human verification: 6 verified, 0 rejected, 0 unresolved
- Publication: revision 2, current, `ready`
- Fresh review: revision 2, `approved`
- Delivery: `ready`

The reviewed JSON and Markdown artifacts both resolve to content hash
`5d5b061de2bf30159b64b64e75c78a0582868a0a038f85730f289d0d9cadbb13`.

## Sources

| Sample | Source | Decision |
|---|---|---|
| `real_source_001` | [OpenAI: Software Engineer, Agent Infrastructure](https://openai.com/careers/software-engineer-agent-infrastructure-san-francisco/) | `verify` |
| `real_source_002` | [OpenAI: Applied AI Engineer, Codex Core Agent](https://openai.com/careers/applied-ai-engineer-codex-core-agent-san-francisco/) | `verify` |
| `real_source_003` | [OpenAI: Software Engineer, Cloud Agents](https://openai.com/careers/software-engineer-cloud-agents-san-francisco/) | `verify` |
| `real_source_004` | [LangChain: Fullstack Software Engineer, Applied AI](https://jobs.ashbyhq.com/langchain/c75915ba-a32b-4e17-873d-19b47564170d) | `verify` |
| `real_source_005` | [Google: Software Engineer, Agentic AI Systems, Cloud Security](https://www.google.com/about/careers/applications/jobs/results/138036920247558854-software-engineer-aiml-agentic-ai-systems-cloud-security) | `verify` |
| `real_source_006` | [Google: Senior Software Engineer, Agentic AI Systems, Cloud Security](https://www.google.com/about/careers/applications/jobs/results/106025468234212038-senior-software-engineer-agentic-ai-systems-cloud-security) | `verify` |

Each decision was made after comparing the persisted observation with the
identified public source. The LangChain page is JavaScript-rendered; its
listing was also checked through the official Ashby job-board posting API.

## Boundary

This report proves one fixed six-record workflow through ordinary Evidence,
human verification, immutable publication, and fresh durable review. It is not
a crawler, source archive, market-coverage benchmark, role-availability
guarantee, hiring-outcome claim, or production-readiness claim.

The machine-readable result is
[p2a-real-source-proof.json](p2a-real-source-proof.json).
