# Coherence

Quality concerns about repetition, consistency, and dead code. These patterns indicate the same concept expressed in multiple ways, or code that should not exist.

Each pattern applies at two scopes with different thresholds:

| Scope    | Detection method                        | Typical threshold |
| -------- | --------------------------------------- | ----------------- |
| File     | Single-file review, local fix           | 2+ occurrences    |
| Codebase | Cross-file search, coordinated refactor | 3+ files          |

Use file-scope thresholds for single-file review. Use codebase-scope for architecture review or coordinated refactoring.

---

## 1. Duplication

Detect: If I fixed a bug here, where else would I need to fix it?

Grep: Identical multi-line blocks, similar function bodies, function names suggesting similar purpose across modules

| Scope    | Threshold | Example                                          |
| -------- | --------- | ------------------------------------------------ |
| File     | 2+        | Same logic in multiple branches of same function |
| Codebase | 3+ files  | Same algorithm implemented in multiple modules   |

Severity:

- [high] Same code block duplicated (3+ lines, logic not just boilerplate)
- [medium] Copy-paste with minor variations
- [low] Common pattern not extracted to shared location

Not a smell: Intentionally different logic serving different purposes. Test setup code. Generated/vendored code. Deliberate isolation for modularity. Similar code in different bounded contexts.

Stop: Flag when bug fix would require changing multiple locations AND the duplication is unintentional.

---

## 2. Naming Consistency

Detect: Are there multiple names for the same concept?

Grep: Synonyms as variable prefixes (user/account/customer, config/settings/options, id/uid/identifier)

| Scope    | Threshold | Example                                                   |
| -------- | --------- | --------------------------------------------------------- |
| File     | 2+ names  | `user` and `account` referring to same entity in one file |
| Codebase | 3+ names  | `userId` in auth/, `uid` in api/, `id` in models/         |

Severity:

- [high] Synonym drift causing confusion at integration points
- [medium] Inconsistent abbreviations (id vs identifier)
- [low] Style inconsistency without semantic confusion

Not a smell: Different names for genuinely different concepts. External API naming conventions. Domain-specific terminology. Legacy compatibility aliases in bounded migration.

Stop: Flag when same semantic concept has multiple names AND causes confusion about whether they refer to the same thing.

---

## 3. Validation Scattering

Detect: Is this validation duplicated?

Grep: Repeated regex patterns, duplicate bounds checks, email/phone/format validation across locations

| Scope    | Threshold | Example                                                 |
| -------- | --------- | ------------------------------------------------------- |
| File     | 3+        | Same validation check in multiple functions of one file |
| Codebase | 5+ files  | Email validation implemented differently per service    |

Severity:

- [high] Validation rules diverged between implementations
- [medium] Same validation repeated without shared implementation
- [low] Defensive re-validation deeper in call chain

Not a smell: Validation at trust boundaries. Defense-in-depth by design. Context-specific validation rules. Service boundary validation.

Stop: Flag when identical validation appears N+ times AND implementations have diverged or will diverge.

---

## 4. Business Rule Scattering

Detect: Where is the single source of truth for this rule?

Grep: Repeated conditional patterns, magic numbers in multiple places, pricing/permission/eligibility logic

| Scope    | Threshold | Example                                                 |
| -------- | --------- | ------------------------------------------------------- |
| File     | 2+        | Policy decision made in multiple functions of same file |
| Codebase | 3+ files  | Same business rule enforced in multiple services        |

Severity:

- [high] Same business decision in multiple places that could diverge
- [medium] Business logic mixed with infrastructure code
- [low] Rules embedded in raw conditionals instead of named predicates

Not a smell: Orchestration calling multiple rule checks. Rules intentionally duplicated for service isolation. Per-tenant/region rule variations. Caching of computed rules.

Stop: Flag when same business decision is made in N+ places AND they have diverged or could diverge independently.

---

## 5. Condition Pattern Repetition

Detect: Should this condition be a named predicate?

Grep: Identical boolean expressions, repeated guard clauses, permission/feature-flag check patterns

| Scope    | Threshold | Example                                                |
| -------- | --------- | ------------------------------------------------------ |
| File     | 3+        | Same boolean expression in multiple places within file |
| Codebase | 5+ files  | Same permission check scattered across many files      |

Severity:

- [high] Identical condition in N+ places (extracting reduces bug surface)
- [medium] Repeated feature flag conditions
- [low] Same guard clause pattern across related functions

Not a smell: Standard guard clauses (null checks, bounds checks). Framework-required patterns. Simple conditions that read clearly inline.

Stop: Flag when identical condition appears N+ times AND extracting to named predicate would reduce bug surface area.

---

## 6. Error Pattern Consistency

Detect: Is error handling consistent?

Grep: Mixed exception/return-code patterns, inconsistent error message formats, varying error context

| Scope    | Threshold | Example                                                                |
| -------- | --------- | ---------------------------------------------------------------------- |
| File     | 2+ styles | Exceptions in some functions, return codes in others within same class |
| Codebase | 3+ styles | Different error patterns per module/team at same abstraction level     |

Severity:

- [high] Incompatible error patterns for similar operations
- [medium] Inconsistent exception hierarchies
- [low] No standard for error context/wrapping

Not a smell: Different patterns for different abstraction levels (domain vs API vs infra). Wrapper functions translating between error styles. Legacy code under active migration.

Stop: Flag when same abstraction level uses N+ incompatible error patterns for similar operations AND no migration plan exists.

---

## 7. Interface Consistency

Detect: Would a user of these APIs be surprised by inconsistency?

Grep: Similar function signatures with different parameter orders, CRUD operation patterns, service method signatures

| Scope    | Threshold | Example                                                        |
| -------- | --------- | -------------------------------------------------------------- |
| File     | 2+        | Similar functions with different parameter orders in same file |
| Codebase | 3+ APIs   | Similar endpoints with incompatible signatures across modules  |

Severity:

- [high] APIs with similar purposes have incompatible signatures AND share consumers
- [medium] Inconsistent naming conventions across related functions
- [low] Mixed sync/async for similar operations without clear reason

Not a smell: Intentional API differences. Domain-specific conventions. Versioned APIs. Overloads with clear distinct purpose.

Stop: Flag when APIs with similar purposes have inconsistent signatures AND confusion impacts consumers.

---

## 8. Zombie Code

Detect: If I deleted this, would any test fail or behavior change?

Grep: Commented blocks, `#if 0`, unreachable branches, unused variables, exported symbols with 0 callers, feature flags

| Scope    | Threshold | Example                                                              |
| -------- | --------- | -------------------------------------------------------------------- |
| File     | presence  | Commented-out code >5 lines, unreachable branches, unused locals     |
| Codebase | 0 refs    | Exported function with no callers, dead feature flags, unused config |

File-scope patterns:

- [high] Commented-out code blocks (>5 lines of code, not documentation)
- [high] Unreachable branches (else after unconditional return, dead switch cases)
- [medium] Unused local variables or parameters
- [low] Functions defined but never called within file

Codebase-scope patterns:

- [high] Exported functions with 0 callers anywhere in codebase
- [high] Feature flags always true/false (never toggled in any environment)
- [medium] Dead flags (feature shipped, flag never removed)
- [low] Configuration options never read
- [low] Dead modules (no imports from any live code path)

Not a smell: Commented code with explanation (debugging aid). Unused params required by interface contract. Public API entry points. Plugin interfaces. Feature flags controlled externally.

Stop: Flag when code is demonstrably unreachable/unused AND is not a public API entry point, plugin interface, or documented debugging aid.
