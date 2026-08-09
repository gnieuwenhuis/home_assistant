# Baseline Code Quality

Quality concerns detectable from the current codebase state. These are checked at planning time before writing new code.

## 1. Naming Precision

Detect: Does the name accurately describe what this does?

Grep: `Manager`, `Handler`, `Utils`, `Helper`, `Data`, `Info`, `process`, `handle`, `do`

- [high] Names describing HOW not WHAT (loopOverItems -> processOrders)
- [high] Verbs that lie (get that mutates, validate that parses)
- [medium] Wrong abstraction level (implementation details in public API names)
- [medium] Vague names (Manager, Handler, Utils, Helper, Data, Info)
- [low] Negated booleans (isNotValid -> isInvalid, disableFeature -> featureEnabled)

Not a smell: Generic names in generic contexts (item in a generic collection, T in type params).

Stop: Flag only when name actively misleads. Imperfect names that are still accurate are style preferences.

## 2. Function Composition

Detect: Can I describe this function's purpose in one sentence?

Grep: Functions >50 lines, parameter counts >4

- [high] God functions (multiple unrelated responsibilities in one function)
- [high] Long parameter lists (4+ params signals missing concept)
- [medium] Deep nesting (3+ levels of conditionals)
- [medium] Mixed abstraction levels (high-level orchestration mixed with low-level details)
- [low] Boolean parameters that fork behavior (split into two functions)

Not a smell: Long functions that do one thing linearly (e.g., state machine, parser). Nesting depth from error handling.

Stop: Flag when function has multiple unrelated responsibilities. Length alone is not a smell.

## 3. Boolean Expression Complexity

Detect: Is this boolean expression too complex to read at a glance?

Grep: `and.*and`, `or.*or`, `&&.*&&`, `||.*||`, `not.*not`, `!.*!`

- [medium] Multi-clause boolean expressions (3+ AND/OR terms -> extract named predicate)
- [medium] Negated compound conditions (not (a and b) -> clearer positive form)
- [low] Mixed AND/OR without parentheses clarifying precedence
- [low] Double/triple negatives (if not disabled, if not is_invalid)

Not a smell: Complex conditions with clear structure and comments explaining the logic.

Stop: Flag when expression requires mental evaluation to understand. Well-commented complex conditions are acceptable.

## 4. Missing Domain Modeling

Detect: Are domain concepts hiding in raw conditions?

Grep: `== 'admin'`, `== "admin"`, `status ==`, `role ==`, `type ==`, magic numbers

- [high] Domain predicates hiding in raw conditions (user.role == 'admin' -> user.can_edit())
- [high] Magic value comparisons (status == 3 -> Status.APPROVED)
- [medium] String comparisons for state (mode == 'active' -> enum)
- [medium] Business rules buried in conditions (extract to domain object method)

Not a smell: Explicit comparisons in domain layer implementation itself. Config values compared once at startup.

Stop: Flag when same domain concept is checked via raw comparison in 2+ places.

## 5. Type-Based Branching

Detect: Is type-checking being used where polymorphism fits better?

Grep: `isinstance`, `typeof`, `instanceof`, `hasattr`, `in dict`, `.type ==`

- [high] isinstance/typeof chains (3+ branches -> polymorphism candidate)
- [medium] Attribute-presence checks (hasattr/in dict as type dispatch)
- [low] Duck typing conditionals that should be protocols/interfaces

Not a smell: Single isinstance check for input validation. Type narrowing for type safety.

Stop: Flag when same type dispatch appears in 2+ places. Single-use type checks are often appropriate.

## 6. Control Flow Smells

Detect: Is the control flow harder to follow than necessary?

Grep: `elif.*elif.*elif`, `switch`, `case`, `? :.*? :`, ternary chains

- [high] Long if/elif chains (5+ branches -> lookup table or strategy pattern)
- [medium] Nested ternaries (2+ levels -> extract to named variables)
- [medium] Early-return candidates buried in nested else branches
- [low] Conditional assignment cascades
- [low] Implicit else branches hiding edge cases

Not a smell: Exhaustive pattern matching. State machines with explicit states.

Stop: Flag when control flow obscures intent. Explicit branching for documented cases is acceptable.

## 7. State and Flags

Detect: Are boolean flags creating implicit state machines?

Grep: `is_.*=`, `has_.*=`, `_flag`, `_state`, multiple boolean assignments

- [high] Boolean flag tangles (3+ flags interacting = implicit state machine)
- [medium] Stateful conditionals depending on mutation order
- [low] Defensive null chains (x and x.y and x.y.z -> optional chaining or null object)

Not a smell: Single boolean for simple on/off state. Builder pattern flags.

Stop: Flag when flags interact in ways that require mental state tracking. Independent flags are fine.

## 8. Conditional Anti-Patterns

Detect: Is there a simpler way to express this condition?

Grep: `if.*return True.*else.*return False`, `try:.*except:.*pass`, `and do_`

- [medium] if cond: return True else: return False (just return cond)
- [medium] Exception-based control flow (try/except as if/else)
- [low] Short-circuit side effects (cond and do_thing())
- [low] Yoda conditions without clear benefit (if 5 == x)

Not a smell: Exception handling for actual exceptional conditions. Short-circuit for lazy evaluation.

Stop: Flag mechanical anti-patterns only. Intent-preserving variations are style preferences.

## 9. Dependency Injection

Detect: Can I test this function without network/disk/database?

Grep: `datetime.now`, `time.time`, `os.environ`, `open(`, `requests.`, `http.`

- [high] Hard-coded dependencies (new Date() inline -> inject clock)
- [high] Global state access (avoid or inject)
- [medium] Side effects mixed with computation (separate pure logic from effects)
- [medium] Concrete class dependencies (depend on interface, not implementation)
- [low] Environment coupling (reads env vars directly -> inject config)
- [low] Time-dependent logic (inject clock for testability)

Not a smell: Entry points that wire dependencies. Test utilities. Scripts meant to run directly.

Stop: Flag when untestable code is in business logic. Infrastructure code at boundaries is expected to have dependencies.

## 10. Type Design

Detect: What domain concepts are represented as primitives here?

Grep: `str` for IDs, `float` for money, `dict` passed through call chain, `Any`, `object`

- [high] Primitive obsession (userId as string -> UserId type with validation)
- [high] Missing value objects (money as float -> Money(amount, currency))
- [medium] Stringly-typed data (JSON strings -> typed objects)
- [medium] Leaky abstractions (callers must know implementation details)
- [low] Optional explosion (many nullable fields -> consider separate types for states)

Not a smell: Primitives in internal implementation. Serialization boundaries. Performance-critical paths.

Stop: Flag when primitives cross API boundaries without validation. Internal use of primitives is acceptable.

## 11. Error Handling

Detect: What happens if this operation fails?

Grep: `except:`, `catch (`, `catch(`, `pass`, `# TODO`, `raise Error(`

- [high] Swallowed exceptions (empty catch blocks)
- [high] Generic catches (catch Exception -> catch specific errors)
- [medium] Errors at wrong abstraction level (low-level errors leaking to callers)
- [low] Missing context (raise Error('failed') -> raise Error(f'order {id}: {reason}'))

Not a smell: Generic catch at top-level with logging. Intentionally swallowed expected errors with comment.

Stop: Flag when error handling obscures or loses information. Documented catch-all with logging is acceptable.

## 12. Modern Idioms

Detect: Is there a newer language feature that simplifies this?

Grep: `for i in range(len(`, `+ str(`, `.format(`, callback patterns, `null` checks

- [medium] Old iteration patterns (manual index loops -> for-each, enumerate)
- [medium] Deprecated API usage
- [low] Missing language features (no destructuring, no pattern matching)
- [low] Legacy patterns (callbacks -> async/await)
- [low] Outdated idioms (string concatenation -> f-strings/templates)
- [low] Manual null checks (-> optional chaining, null coalescing)

Not a smell: Intentional use of older patterns for compatibility. Performance-critical code avoiding allocations.

Stop: Flag when modern idiom is clearly better AND available in the project's language version. Do not flag style preferences.

## 13. Readability

Detect: Can I understand this without reading other files?

Grep: Boolean literals in function calls, magic numbers, unexplained constants

- [high] Boolean trap (fn(True, False) -> fn(enabled=True, debug=False))
- [medium] Magic numbers/strings (42 -> MAX_RETRIES = 42)
- [medium] Positional args where named params would clarify intent
- [low] Dense expressions (nested ternaries -> named intermediate variables)
- [low] Missing WHY comments on non-obvious decisions
- [low] Implicit ordering dependencies between calls (document or make explicit)

Not a smell: Well-known constants (0, 1, -1, 100). Boolean in obviously-named function (setEnabled(true)).

Stop: Flag when meaning requires external lookup. Self-evident code needs no comments.

## 14. Documentation Staleness

Moved. A docstring or comment that contradicts its code is `incoherence`
territory (dimensions A, B, D) — it detects and resolves those repository-wide.
No refactor dimension cites this section.

Section numbers are stable citation keys; this heading stays so the numbering
below does not shift.

## 15. Test Quality as Documentation

Detect: Do tests communicate expected behavior?

Grep: `test_works`, `test_ok`, `test_success`, `test_case_`, `test_1`, `assert True`

- [high] Test name matches low-information pattern (test_works, test_ok, test_success, test_case_1)
- [high] Test contains 0 assertions
- [medium] Test name shorter than 3 tokens (excluding test\_ prefix)
- [medium] Test name describes implementation, not behavior
- [low] Test only asserts True, None, or trivial values
- [low] Multiple similar test functions with minor input variations (use parameterized/table-driven)

Not a smell: Tests referencing ticket numbers (TEST-1234, JIRA-567) for traceability. Smoke tests named test_works.

Stop: Flag when test name gives no behavioral information AND is not a ticket/regression reference.

## 16. Generated and Vendored Code Awareness

Moved. Undocumented provenance for generated, vendored, or non-code assets is
`doc-sync` territory — it owns the README beside the asset, and
`src/places_signals/data/README.md` is its model for the pattern. No refactor
dimension cites this section.

Section numbers are stable citation keys; this heading stays so the numbering
below does not shift.

## 17. Schema-Code Coherence

Detect: Does code reference schema fields that don't exist, or ignore fields that do?

Grep: Schema file extensions (.proto, .graphql, .json schema), field access patterns

- [high] Code references field not in schema definition
- [high] Schema field unused in any code path (dead field)
- [medium] Type mismatch between schema and code representation

Not a smell: Divergence a comment explains by naming what still depends on it. Fields used only in specific deployment configs.

Stop: Flag when field name in code has 0 matches in corresponding schema file, or schema field has 0 references in codebase, and no comment names a consumer.
