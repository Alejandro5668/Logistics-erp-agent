# Skill Registry — Logistics-erp-agent

**Generated**: 2026-09-15  
**Project**: Logistics-erp-agent  
**Scope**: Backend agent + LangChain + FastAPI  

## Project-Level Skills

| Skill | Trigger | Path | Version |
|-------|---------|------|---------|
| `architecture-patterns` | Clean Architecture, Hexagonal, ports and adapters, DDD, CQRS, arquitectura de software | `.claude/skills/architecture-patterns/SKILL.md` | 1.0 |
| `solid-principles` | SOLID, DRY, KISS, YAGNI, principios de diseño, POO | `.claude/skills/solid-principles/SKILL.md` | 1.0 |
| `fastapi-backend-architecture` | FastAPI, backend Python, arquitectura backend Python, router service repository, Pydantic, SQLAlchemy async | `.claude/skills/fastapi-backend-architecture/SKILL.md` | 1.0 |
| `api-contract-first` | contrato API, OpenAPI, generar tipos TypeScript, openapi-typescript, sincronizar frontend backend | `.claude/skills/api-contract-first/SKILL.md` | 1.0 |
| `pytest` | When writing Python tests - fixtures, mocking, markers | `.claude/skills/pytest/SKILL.md` | 1.0 |

## Agent-Level Skills

| Skill | Trigger | Path | Version | Scope |
|-------|---------|------|---------|-------|
| `azure-deploy` | Azure/Bicep infrastructure deployment, Container Apps, VNet/Private Endpoint | `.agents/skills/azure-deploy/SKILL.md` | (Microsoft) | F-A3 (Infrastructure) |

## Project Conventions

| Convention File | Applies To | Status |
|-----------------|-----------|--------|
| `CLAUDE.md` | Entire project | Active — defines stack, skills, ramas, commits, and SDD scope |
| `docs/00-planning.md` | Feature breakdown and work order | Active — Track A (docs) + Track B (code, SDD) |

## Skill Activation Rules

**When to use each skill** (from CLAUDE.md):

- **architecture-patterns**: Structuring a new module (`app/agent`, `app/tools`, `app/rag`, `app/security`, `app/api`) before writing code.
- **solid-principles**: Writing any class or function with non-trivial logic (tools, graph nodes, middleware) before committing.
- **fastapi-backend-architecture**: Building or modifying `app/api/` (routes, dependencies, streaming).
- **api-contract-first**: Defining endpoint contract (request/response, streaming shape) before implementation.
- **pytest**: Writing tests for tools, agent, or API — all Track B code must have at least one test that fails if logic breaks.
- **azure-deploy**: Working on `infra/main.bicep` or deployment design (F-A3) — VNet, Private Endpoint, Container Apps.

## SDD Scope

**Track A** (Docs) — direct delivery, no SDD:
- F-A1: Architecture diagram + guardrails + session memory
- F-A2: LLMOps strategy (Ragas/Phoenix KPIs)
- F-A3: Azure deployment design + Bicep
- F-A4: Incident response + leadership

**Track B** (Code) — SDD complete (proposal → spec → design → tasks → apply):
- F-B1: Mock ERP data layer (SQLite/SQLAlchemy)
- F-B2: Tax discrepancy logic
- F-B3: RAG pipeline (Chroma + metadata filtering)
- F-B4: Security guardrail (PII/prompt injection detection)
- F-B5: Agent core (create_agent + tools + checkpointer)
- F-B6: FastAPI streaming API

## Next Steps

Skill registry is ready for use. Subagents and orchestrators can reference exact SKILL.md paths for each phase of SDD work. Registry will be updated after each new skill addition.
