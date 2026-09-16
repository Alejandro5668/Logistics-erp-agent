---
name: architecture-patterns
description: "Trigger: Clean Architecture, Hexagonal, ports and adapters, DDD, CQRS, arquitectura de software. Choose the right pattern for the problem's real complexity."
license: Apache-2.0
metadata:
  author: "Johan-Campo"
  version: "1.0"
---

## Activation Contract

Load when designing or reviewing the overall structure of a backend/full-stack project — technical test or work project — before or while deciding how to organize layers, the domain model, or read/write paths.

## Hard Rules

- Match architecture to scope: a simple CRUD problem does not need DDD or CQRS. Over-architecting a small problem is as bad as under-architecting a complex one.
- Clean Architecture / Hexagonal (Ports & Adapters): the domain/business layer has zero imports from frameworks, DB drivers, or HTTP libraries; framework/DB/UI code implements interfaces (ports) the domain defines, never the reverse.
- DDD: only model explicit entities/value objects/aggregates when the business has real invariants and rules to protect; otherwise plain DTOs + services are enough.
- CQRS: only split read and write models when query needs (joins, projections, reporting) genuinely diverge from write needs; never split just to look advanced.
- Dependency direction always points inward: outer layers (UI, DB, frameworks) depend on inner layers (domain, use cases); inner layers never import outer ones.

## Decision Gates

| Problem signal | Pattern |
|---|---|
| Straightforward CRUD, 1-3 entities, no complex business rules | Simple layered architecture (route/handler -> service -> repository) — see `nodejs-backend-architecture` |
| Multiple integrations (DB + external APIs + queue) you want to swap/test independently | Hexagonal: define one port per integration, adapters implement it |
| Business has real invariants, rules, or lifecycle (order states, pricing rules) | DDD: model entities/value objects/aggregates that enforce those rules |
| Read patterns (dashboards, reports, search) are shaped completely differently from write patterns | CQRS: separate query/read models from command/write models |
| None of the above signals are present | Don't add a pattern — plain layered code is the correct, honest choice |

## Execution Steps

1. List the problem's actual signals (entity count, integrations, invariants, read/write divergence) before choosing a pattern.
2. Default to the simplest layered architecture; escalate to Hexagonal/DDD/CQRS only when a specific signal from the table justifies it.
3. If escalating, name the boundary explicitly (the port, the aggregate, the command/query split) — never half-apply a pattern.
4. Keep the domain/business layer free of framework, ORM, and HTTP imports regardless of which pattern is chosen.

## Output Contract

State which pattern was chosen (or "plain layered architecture") and which signal from the Decision Gates table justified it. Flag any layer that imports outward-in (domain importing framework/DB code).

## References

- `solid-principles` skill — class/function-level principles that apply inside any of these architectures.
- `nodejs-backend-architecture` skill — the default layered baseline these patterns escalate from.
