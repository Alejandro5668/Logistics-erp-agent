---
name: solid-principles
description: "Trigger: SOLID, DRY, KISS, YAGNI, principios de diseño, POO. Apply class/function-level design principles when writing or reviewing OOP code."
license: Apache-2.0
metadata:
  author: "Johan-Campo"
  version: "1.0"
---

## Activation Contract

Load when writing or reviewing classes, functions, modules, or interfaces in any OOP-capable language (TypeScript, JavaScript, C#, etc.). Applies to both throwaway technical-test code and long-lived work projects.

## Hard Rules

- Single Responsibility: a class/module has exactly one reason to change; split it if it has two.
- Open/Closed: add behavior via a new implementation of an interface/abstract type; do not add a new condition to existing tested logic.
- Liskov Substitution: a subtype must work anywhere its base type is expected — never throw, no-op, or narrow preconditions on an inherited method.
- Interface Segregation: keep interfaces small and role-specific; never force a class to implement a method it doesn't use.
- Dependency Inversion: depend on interfaces/abstractions owned by the high-level module; inject dependencies, never construct them inline inside business logic.
- DRY: extract logic duplicated 2+ times (or any duplicated business rule) into one named function.
- KISS: choose the simplest design that satisfies today's requirement; reject abstractions that don't reduce real duplication or real change-risk.
- YAGNI: do not add config, interfaces, or extension points for a requirement nobody has asked for yet.

## Decision Gates

| Situation | Action |
|---|---|
| Class/function has 2+ unrelated reasons to change | Split by responsibility (SRP) |
| New variant of existing behavior is needed | Add a new implementation, don't branch old code with if/switch (OCP) |
| A subclass overrides a method to throw or no-op | Redesign — likely an LSP violation; prefer composition |
| An interface forces unused methods on implementers | Split into smaller interfaces (ISP) |
| A class builds its own dependency with `new` | Inject it via constructor/parameter instead (DIP) |
| Same logic copy-pasted 2+ times | Extract one shared function (DRY) |
| Tempted to add a generic layer "just in case" | Stop — apply YAGNI, build the concrete case first |

## Execution Steps

1. Before writing, name the single responsibility of the class/function you're adding.
2. Depend on interfaces for anything that could vary; never `new` a concrete dependency inside business logic (DIP).
3. When reviewing, check every class/interface against the Decision Gates table above.
4. Remove or flag any abstraction that doesn't serve a requirement that exists today (YAGNI).
5. Re-read for duplicated logic to extract (DRY) and for cleverness that isn't load-bearing (KISS).

## Output Contract

State which SOLID/DRY/KISS/YAGNI principle motivated each non-obvious design choice. Flag any violation found during review with the specific principle it breaks and the smallest fix.

## References

- `architecture-patterns` skill — system-level structure (Clean/Hexagonal/DDD/CQRS) built on top of these class-level principles.
- `nodejs-backend-architecture` skill — concrete Node.js/TypeScript layering that already applies SRP and DIP.
