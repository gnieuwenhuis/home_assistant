# Drift Code Quality

Quality concerns that are ONLY detectable through codebase-wide analysis. These have no meaningful local variant -- the problem is inherently about relationships between files, modules, or components.

Requires periodic review or tooling that sees the whole codebase.

## 1. Module Structure

Detect: Do changes ripple to unrelated modules?

Grep: Import graphs, dependency declarations, module boundaries

- [high] Circular dependencies (A imports B imports A)
- [high] Layer violations (domain importing infrastructure)
- [medium] Wrong cohesion (unrelated things grouped in same module)
- [medium] Missing facades (module internals exposed directly)
- [low] God modules (too many responsibilities in one module)

Not a smell: Circular deps within same bounded context. Infrastructure adapters importing domain. Shared kernel patterns.

Stop: Flag when dependency causes compilation order issues OR when layer violation allows infrastructure to corrupt domain.

## 2. Architecture

Detect: Would adding a feature require touching many components?

Grep: Component boundaries, service interfaces, configuration locations

- [high] Wrong component boundaries (features awkwardly split)
- [high] Single points of failure (no fallback, no retry paths)
- [medium] Scaling bottlenecks (synchronous where async needed)
- [medium] Monolith patterns in distributed code (or vice versa)
- [low] Missing abstraction layers (everything directly coupled)
- [low] Configuration scattered (no central policy, settings in many places)

Not a smell: Intentional coupling for simplicity. Early-stage monolith. Bounded contexts with shared kernel.

Stop: Flag when architecture forces cross-cutting changes for single-domain features.

## 3. Cross-File Comprehension

Detect: How many files must I read to understand this flow?

Grep: Call chains, event handlers, callback registrations

- [high] Implicit contracts between files (caller must know callee internals)
- [medium] Hidden dependencies (file A assumes file B ran first)
- [low] Scattered control flow (one operation spans 5+ files with no orchestrator)

Not a smell: Well-documented module boundaries. Plugin architectures. Event-driven designs with clear event contracts.

Stop: Flag when understanding a single operation requires reading 5+ files with no documentation of the flow.

## 4. Abstraction Opportunities

Detect: What domain concept is hiding across these repeated patterns?

Grep: Parallel implementations, similar transformation chains, repeated configuration shapes

- [high] Same transformation applied in multiple files (3+ occurrences)
- [medium] Parallel class hierarchies doing similar things differently
- [medium] Copy-paste inheritance (similar classes with minor variations)
- [low] Data transformation pipelines with identical structure
- [low] Configuration patterns repeated without abstraction

Not a smell: Intentionally similar but independent implementations. Domain-specific variations. Templates/generators producing similar code.

Stop: Flag when pattern appears in 3+ implementations AND the fix is extracting shared abstraction. These become visible only after seeing multiple implementations.

## 5. Feature Flag Sprawl

Detect: How are feature flags checked across the codebase?

Grep: Feature flag checks, toggle patterns, conditional feature code

- [high] Feature flags checked inconsistently (different conditions for same flag)
- [medium] Flag dependencies not documented (flag A requires flag B)

Not a smell: Flags with intentionally different behavior per context. A/B test variations. Gradual rollout logic.

Stop: Flag when same feature flag is checked with different logic in different places AND the difference is unintentional.

Note: Dead flags (feature shipped, never removed) are covered in coherence.md Zombie Code.
