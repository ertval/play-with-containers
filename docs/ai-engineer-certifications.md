# AI Engineer Certifications and Credentials

**Research date:** 2026-08-27

## Scope

This report uses Chip Huyen's *AI Engineering* framing: an AI Engineer builds
applications and production systems around foundation models. The relevant
skills include model integration, context engineering, retrieval, tool use,
agent workflows, evaluation, deployment, observability, security, latency,
cost, and product iteration.

That is broader than model training and narrower than every possible AI job.
The goal is therefore to identify credentials that provide useful evidence of
building and operating LLM-powered and agentic systems.

## Credential Types

- **Certification:** a provider-issued credential earned through a formal,
  usually proctored, exam.
- **Applied skill:** a practical lab or scenario assessment, usually narrower
  than a role-based certification.
- **Course certificate or badge:** evidence of completing training. Useful for
  learning, but not equivalent to independently validated professional skill.

## Executive Recommendation

For most engineers, the strongest combination is:

1. **AWS Certified Generative AI Developer - Professional** for broad,
   production-oriented GenAI engineering.
2. **LangChain Certified Agent Engineer** for direct agent lifecycle coverage.
3. A public project demonstrating evaluations, traces, authorization, failure
   recovery, and deployment.

Choose a platform-specific alternative when the target employer has a clear
stack: Databricks, Microsoft Azure, or Google Cloud. Add Kubernetes,
OpenTelemetry, or NVIDIA credentials only when infrastructure, observability,
or GPU serving is a meaningful part of the role.

## Ranked Certifications

| Rank | Credential | Best signal | Main limitation |
|---|---|---|---|
| 1 | [AWS Certified Generative AI Developer - Professional](https://aws.amazon.com/certification/certified-generative-ai-developer-professional/) | Broad production LLM application engineering | AWS-specific; multiple-choice exam rather than a build assessment |
| 2 | [LangChain Certified Agent Engineer](https://academy.langchain.com/pages/certifications-lcae) | Building, testing, deploying, and monitoring agents | Framework-specific and newer than major cloud certifications |
| 3 | [Databricks Certified Generative AI Engineer Associate](https://www.databricks.com/learn/certification/genai-engineer-associate) | Governed enterprise RAG and GenAI applications | Strongly Databricks-shaped; verify current availability |
| 4 | [Google Cloud Professional Agentic Architect](https://cloud.google.com/learn/certification/agentic-architect/) | Agent architecture, workflow evaluation, deployment, and governance | Beta credential; recognition and final scope are still developing |
| 5 | [Microsoft Azure AI Apps and Agents path](https://learn.microsoft.com/en-us/training/paths/develop-ai-agents-azure/) | Azure Foundry agents, tools, MCP, identity, and enterprise operations | Current learning and Applied Skills path is clearer than a single professional certification |
| 6 | [Google Cloud Professional Machine Learning Engineer](https://cloud.google.com/learn/certification/machine-learning-engineer/) | Broad ML platform and MLOps production engineering | Less direct coverage of agent tools and workflows |
| 7 | [AWS Certified Machine Learning Engineer - Associate](https://aws.amazon.com/certification/certified-machine-learning-engineer-associate/) | Deployment, orchestration, monitoring, and ML operations | Not primarily an LLM or agent credential |
| 8 | [NVIDIA-Certified Professional: Generative AI LLMs](https://www.nvidia.com/en-us/learn/certification/generative-ai-llm-professional/) | LLM infrastructure, serving, GPUs, and optimization | Weak evidence of agent orchestration and product engineering |
| 9 | [CNCF Certified Cloud Native Platform Engineer](https://www.cncf.io/training/certification/cnpe/) | Platform APIs, GitOps, security, observability, and operations | No LLM-specific assessment |
| 10 | [CNCF Certified Kubernetes Administrator](https://www.cncf.io/training/certification/cka/) or [CKAD](https://training.linuxfoundation.org/certification/certified-kubernetes-application-developer-ckad/) | Hands-on deployment and troubleshooting | Infrastructure credential, not an AI credential |

### Short notes

**AWS GenAI Developer Professional** is the best single mature credential for
production GenAI on AWS. Its published scope includes foundation-model
integration, RAG, knowledge bases, prompt management, agents, security,
governance, evaluation, monitoring, troubleshooting, and cost optimization.
The exam is 75 questions, 180 minutes, and costs approximately $300 USD.

**LangChain Certified Agent Engineer** is the most direct specialist credential
for agent work. It covers building, testing, deploying, and monitoring agents
in four equally weighted domains. The online-proctored exam is 40 questions,
costs approximately $99 USD, and is valid for 24 months.

**Databricks Certified Generative AI Engineer Associate** covers application
design, data preparation, LLM application development, deployment, governance,
evaluation, and monitoring. The exam is 45 questions, 90 minutes, and costs
approximately $200 USD. It is especially valuable in Databricks environments.

**Google Professional Agentic Architect** is the closest topical match to the
modern agentic meaning of AI engineering. The announced beta includes a
proctored exam and hands-on labs and is expected to open registration on
2026-09-03. Beta credentials should be treated as promising but provisional.

**Microsoft** has strong current Foundry material covering custom tools, MCP,
RAG, multi-agent solutions, publishing, tracing, evaluation, Application
Insights, Entra identity, RBAC, content filters, and private networking. The
older Azure AI Engineer Associate / AI-102 credential is retired and should not
be recommended as current.

## Anthropic and OpenAI

The foundation-model labs matter because their APIs, tools, agent patterns, and
documentation shape real engineering practice. They should, however, be
compared honestly with formal certifications.

| Provider | Current official offering | Assessment strength | Best use |
|---|---|---|---|
| **Anthropic** | [Claude Academy](https://academy.claude.com/), public courses, completion badges, and partner-only Claude certifications | Public courses use quizzes and badges; partner exams are proctored but require partner access | Learn Claude API, MCP, Claude Code, context engineering, tools, and agent patterns |
| **OpenAI** | [OpenAI Academy](https://academy.openai.com/), including [Agents and Workflows](https://academy.openai.com/public/courses/agents-and-workflows-bieml) | Course-completion certificates; no verified public proctored OpenAI Engineer exam found | Learn OpenAI workflows and demonstrate implementation through projects |

### Anthropic

Anthropic's public [Building with the Claude API](https://academy.claude.com/courses/building-with-the-claude-api)
course is highly relevant to agent engineering. It covers tool use, RAG,
embeddings, reranking, MCP, Claude Code, computer use, agent architectures,
evaluation, and production patterns. Claude Academy also offers courses on
MCP, subagents, agent skills, and Claude Code.

These public offerings generally result in a completion badge or certificate,
not an independently proctored professional certification.

Anthropic also documents partner-only credentials through the
[Claude Partner Academy](https://anthropic-partners.skilljar.com/page/partner-certifications):

| Credential | Published format | Relevance |
|---|---|---|
| Claude Certified Developer - Foundations | 53-question, 120-minute proctored exam | Best Anthropic partner credential for application engineering; covers integration, agents, prompting, MCP, safety, and evaluation |
| Claude Certified Architect - Foundations | 60-question, 120-minute proctored exam | Strong agentic architecture, orchestration, tools, MCP, and reliability coverage |
| Claude Certified Architect - Professional | 63-question, 120-minute proctored exam | Strongest partner credential for solution design, evaluation, governance, lifecycle, and operations |
| Claude Certified Associate - Foundations | 60-question, 120-minute proctored exam | Aimed more at consultants, sellers, and delivery leads than builders |

These certifications are explicitly designed for Anthropic partners, are
published as valid for 12 months, and are not broadly available substitutes
for a general AI Engineer certification. They are valuable for Anthropic
consulting and implementation roles when eligibility is available.

Useful Anthropic technical references include [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents),
[Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
and [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents).

### OpenAI

OpenAI Academy offers free learning resources such as AI Foundations, Applied
AI Foundations, and Agents and Workflows. The platform describes these as
course-completion certificates. No official, broadly available, proctored
credential equivalent to an AWS Professional or Google Cloud Professional
certification was identified as of the research date.

OpenAI's technical material is nevertheless valuable. The [Agents SDK](https://openai.github.io/openai-agents-python/),
[Agents guide](https://platform.openai.com/docs/guides/agents), [Cookbook](https://cookbook.openai.com/),
and [Evals guide](https://platform.openai.com/docs/guides/evals) cover tools,
MCP, orchestration, handoffs, state, guardrails, tracing, retrieval, and
regression testing. These resources create stronger technical evidence when
used in a deployed project than an Academy completion certificate alone.

Do not describe an OpenAI Academy course as an "OpenAI Certified AI Engineer"
credential. A precise resume entry is, for example: "Completed OpenAI Academy:
Agents and Workflows."

## Capability Comparison

Ratings describe the published scope of the credential or learning offering,
not guaranteed competence. **Strong** means explicitly covered or assessed;
**Partial** means narrower or platform-specific; **Low** means little evidence.

| Offering | Integration | Context / RAG | Tools / agents | Evaluation | Observability | Security | Deployment / cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| AWS GenAI Developer Professional | Strong | Strong | Strong | Strong | Strong | Strong | Strong |
| LangChain Certified Agent Engineer | Partial | Partial | Strong | Strong | Strong | Partial | Strong |
| Databricks GenAI Engineer Associate | Strong | Strong | Partial | Strong | Strong | Strong | Strong |
| Google Professional Agentic Architect | Strong | Partial | Strong | Strong | Partial | Strong | Strong |
| Microsoft Foundry agent path | Strong | Strong | Strong | Strong | Strong | Strong | Strong |
| Anthropic public Academy | Strong | Strong | Strong | Partial | Partial | Partial | Strong |
| Anthropic partner certifications | Strong | Strong | Strong | Strong | Partial | Strong | Strong |
| OpenAI Academy | Partial | Partial | Partial | Partial | Low | Partial | Low |
| OpenAI SDK and documentation | Strong | Strong | Strong | Strong | Strong | Strong | Partial |

## What to Build Alongside a Certification

The portfolio is often more persuasive than the certificate. A strong project
should include:

- a clear user and business objective, plus a simple non-agent baseline;
- retrieval experiments with measurable grounding and relevance results;
- typed tools with authorization, timeouts, retries, idempotency, and human
  approval for risky writes;
- state management and explicit handling of invalid tools, bad parameters,
  partial failure, and inefficient plans;
- an evaluation dataset, regression tests, failure categories, automated
  metrics, and sampled human review;
- prompt, model, retrieval, and tool version tracking;
- deployment, secrets management, rollback, and resource limits;
- traces containing retrieved context, tool calls, latency, token usage, cost,
  and errors;
- a design document explaining tradeoffs, rejected complexity, safety risks,
  and operational decisions.

## Final Choice by Career Target

- **General AI application engineer:** AWS GenAI Developer Professional plus
  LangChain Certified Agent Engineer.
- **Anthropic-focused consultant or implementation engineer:** Claude Certified
  Developer or Architect, if partner eligibility is available, plus a public
  Claude API/MCP project.
- **OpenAI-focused application engineer:** OpenAI Academy Agents and Workflows
  plus an Agents SDK project with evaluations and traces; add a broadly
  recognized cloud certification for formal credential signal.
- **Azure enterprise engineer:** Microsoft Foundry agent path and current
  Applied Skills assessments, plus a deployed Foundry solution.
- **Databricks enterprise AI engineer:** Databricks GenAI Engineer Associate.
- **Platform or infrastructure AI engineer:** one agent/GenAI certification
  plus CNPE, CKA/CKAD, CKS, OpenTelemetry, or NVIDIA according to the role.

## Sources and Currency Note

Primary sources are linked throughout. Certification names, exam availability,
pricing, validity, and product platforms are changing rapidly. Confirm the
provider's official exam page before paying or listing a credential. In
particular, verify Google Agentic Architect beta details, Databricks exam
availability, Microsoft's current credential catalog, and Anthropic partner
eligibility.