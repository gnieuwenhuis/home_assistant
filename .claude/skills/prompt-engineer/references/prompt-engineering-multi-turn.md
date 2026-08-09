# Prompt Engineering: Research-Backed Techniques for Multi-Turn Prompts

This document synthesizes practical prompt engineering patterns with academic
research on iterative LLM reasoning. All techniques target **multi-turn
prompts**--structured sequences where output from one turn becomes input to
subsequent turns.

**Meta-principle**: Multi-turn value comes from separation of concerns--each
turn has a distinct cognitive goal (generate, critique, verify, synthesize).
Mixing goals within a single turn reduces effectiveness.

**Prerequisite**: Assumes familiarity with single-turn techniques (CoT,
Plan-and-Solve, RE2). Multi-turn techniques extend single-turn methods across
message boundaries.

**Notation**: Throughout this document, `T1`, `T2`, `T3` denote Turn 1, Turn 2,
Turn 3--sequential LLM calls in a multi-turn conversation.

---

## Technique Selection Guide

| Domain             | Technique             | Trigger Condition                          | Stacks With               | Conflicts With       | Cost/Tradeoff                      | Effect                                           |
| ------------------ | --------------------- | ------------------------------------------ | ------------------------- | -------------------- | ---------------------------------- | ------------------------------------------------ |
| **Pre-Processing** | S2A Context Filtering | Input contains irrelevant/misleading noise | Any downstream technique  | --                   | 2x tokens (filter + generate)      | QA +17.5pp; math +12pp                           |
| **Refinement**     | Self-Refine           | Output quality improvable via iteration    | Any single-turn reasoning | Time-critical tasks  | 2-4x tokens per iteration          | 5-40% absolute improvement across 7 task types   |
| **Verification**   | CoVe (Question-Based) | Factual accuracy critical                  | Quote Extraction, CRITIC  | Joint verification   | 3-4x tokens                        | List QA: 17%->70%; FACTSCORE +28% rel (55.9→71.4)|
| **Verification**   | Factored Verification | Summary verification against source        | CoVe                      | Joint CoVe           | Claims x calls                     | HaluEval: 76.2% (+10pp); 45% hallucination cut   |
| **Verification**   | CRITIC (Tool-Based)   | Verifiable via search/code/calculator      | CoVe, Self-Refine         | Intrinsic correction | Tool API + 2-3x tokens             | AmbigNQ +7.7 F1; GSM8K +7.0%; 79% toxicity cut   |
| **Aggregation**    | Universal Self-Cons.† | Free-form output; exact-match SC fails     | Complexity weighting      | Greedy decoding      | N samples + 1 selection            | Matches SC on math (92.4%); enables SC for prose |
| **Aggregation**    | Multi-Chain Reasoning | Evidence scattered across attempts         | Self-Consistency          | Single-chain         | N chains + 1 meta-reasoning        | +5.7% over SC on multi-hop; 82% quality explains |
| **Aggregation**    | Complexity-Weighted   | Varying reasoning depth across samples     | USC, Self-Consistency     | Simple majority      | Minimal; selection only            | GSM8K: 80.5% vs 78.0% SC (+2.5pp)                |
| **Aggregation**    | Multi-Expert†         | Multiple valid perspectives needed         | USC                       | Iterative debate     | Single aggregation turn            | TruthfulQA: 89.4% vs 77.1% USC (+12.2pp)         |
| **Meta-Reasoning** | Cumulative Reasoning  | Complex reasoning; validated steps needed  | External verifiers        | Linear CoT           | 3+ roles/step; DAG management      | Game of 24: 98% vs 74% ToT; MATH L5 +43%         |
| **Decomposition**  | Decomposed Prompting  | Task needs specialized sub-handlers        | Any verification          | Monolithic prompts   | Handler setup overhead             | Enables tasks CoT cannot learn from few-shot     |
| **Decomposition**  | ADAPT                 | Task complexity unknown; may fail          | Self-Refine, CRITIC       | Fixed decomposition  | Recursive calls on failure         | ALFWorld +28%; WebShop +27%; TextCraft +33%      |
| **Decomposition**  | Cognitive Prompting   | Complex multi-step problem needs structure | Any verification          | Monolithic prompts   | 8 COPs overhead per problem        | GSM8K +10.8% (H-CP); LLaMA 70B: 95% solve        |
| **Decomposition**  | Table as Thought      | Constraint planning; multi-constraint tracking | Any verification      | Simple CoT           | Schema + table construction        | Calendar +10.8% over direct; planning+5.4%       |
| **Verification**   | Socratic Method       | Claims need cross-examination/dialectic    | CoVe, Factored             | Simple yes/no checks | Multi-turn dialogue overhead       | Improves validity scoring via elenchus           |
| **Prompt Design**  | Synthetic Prompting   | Few-shot demos insufficient; need diversity| Any reasoning technique   | Fixed exemplars      | 1000x backward-forward synthesis   | +15.6% over PAL; GSM8K 74.7%                     |
| **Parallel**       | Skeleton-of-Thought†  | Multi-point answers; independent sections  | Any aggregation           | Sequential reasoning | Skeleton + N expansion calls       | 1.6-2.7x speedup; net quality +0.05 to +0.22     |
| **Prompt Design**  | Active Prompting†     | Few-shot exemplar selection                | Any few-shot technique    | Random selection     | Uncertainty estimation (k samples) | GSM8K +4.8pp over random (78.6%->83.4%)          |

---

## Quick Reference: Key Principles

1. **External Signals for Self-Correction** -- Intrinsic correction fails (74.7%
   keep wrong); use verification Qs, tools, or multi-sample
2. **Self-Refine for Iteration** -- 5-40% improvement when feedback is
   actionable and specific
3. **Separate Feedback from Refinement** -- Generate feedback in one turn, apply
   in another; mixing degrades both
4. **Factored over Joint Verification** -- Answer verification Qs without
   baseline in context; +3-8pp
5. **Shortform over Longform** -- 70% accuracy on individual Qs vs 17% for same
   facts in longform
6. **Open Questions over Yes/No** -- Models agree with yes/no regardless of
   correctness; open forces recall
7. **Claim Decomposition for Summaries** -- Decompose, verify each against
   source; 76.2% vs 61.2% single-prompt
8. **Tool-Interactive Verification** -- CRITIC: +7.7 F1 on QA, +7.0% math via
   external validation
9. **Filter Context Before Reasoning** -- S2A: +17.5pp by removing noise before
   main task
10. **USC for Free-Form** -- Matches SC on structured (92.4%); enables
    consistency where exact-match fails
11. **Multi-Chain for Evidence** -- +5.7% over SC; 20% of answers combine facts
    across chains that individual chains miss
12. **Meta-Reasoning over Majority** -- Second pass synthesizing all chains
    beats simple vote
13. **Complexity-Weighted Voting** -- Top-K complex chains: 80.5% vs 78.0% SC
14. **History Accumulation** -- Retain previous feedback; models learn from past
    mistakes
15. **Explicit Stopping Conditions** -- Use limits or thresholds; models rarely
    self-terminate well
16. **Track Best-So-Far** -- Quality may regress; select max-score output, not
    final
17. **Structured Aggregation** -- Multi-Expert NGT: 89.4% vs 77.1% USC on
    TruthfulQA
18. **Decompose Only on Failure** -- ADAPT's recursive approach: +28% over fixed
    plans
19. **Skeleton-First for Parallel** -- Structure before content; 1.6-2.7x
    speedup
20. **Uncertainty-Based Exemplars** -- Active Prompting: +4.8pp by annotating
    high-uncertainty Qs
21. **Exclusive Context Filtering** -- S2A T2 uses ONLY filtered context;
    including original defeats purpose
22. **LLM-Generated Verification Qs** -- Outperform heuristic/template; tailored
    to response
23. **Factor+Revise for Complex** -- Explicit cross-check between verification
    and final: +7.7pp
24. **Actionable Feedback** -- "Use n(n+1)/2 instead of loop" beats "could be
    more efficient"
25. **DAG over Linear** -- Cumulative Reasoning: propositions combine any prior
    validated nodes
26. **Self-Generated Success Heuristic** -- ADAPT uses executor LLM to determine
    completion
27. **Diverse Expert Aggregation** -- NGT: agreed + conflict-resolved + unique
    perspectives
28. **SoT Router** -- Route to skeleton-first only for multi-point independent
    answers
29. **Cognitive Operations Sequence** -- 8 COPs (goal→decompose→filter→pattern→
    abstract→generalize→integrate); H-CP reaches 95% on GSM8K
30. **Tabular Thought Structure** -- Schema design + reasoning table enables
    constraint tracking; +10.8% on calendar planning
31. **Cross-Examination for Claims** -- Socratic elenchus: test consistency via
    targeted questioning before accepting conclusions
32. **Backward-Forward Synthesis** -- Generate reasoning chain first, then
    matching question; ensures answerability and diversity

---

## 1. Context Filtering

### S2A: Pre-Processing Filter

Regenerates input to remove distractors before main task. Per Weston &
Sukhbaatar (2023): "S2A leverages LLMs to reason about what to attend to."

**Process:**

```
T1 (Filter):  original_context -> filtered_context x'
T2 (Execute): x' + task -> response  [original EXCLUDED]
```

**Filter prompt:**

```
Extract the part that is related and useful for an accurate answer.
Include the actual question. Exclude opinions and irrelevant details.

{original_context}

Extracted relevant parts:
```

**Performance:**

| Task                  | Baseline | S2A   | Delta   |
| --------------------- | -------- | ----- | ------- |
| QA with opinions      | 62.8%    | 80.3% | +17.5pp |
| Math with distractors | ~65%     | ~77%  | +12pp   |

**Critical:** Attention must be "hard not soft" (Weston & Sukhbaatar). Including
both original AND filtered context defeats the purpose--model still attends to
problematic parts.

WRONG: `T2: Use original + x' for task` RIGHT: `T2: Use ONLY x' for task`

**Stacking:** Orthogonal to all downstream techniques. Chain: S2A -> Generate ->
Verify.

---

## 2. Iterative Refinement

### Self-Refine: Feedback-Then-Improve Loop

General-purpose iterative improvement alternating FEEDBACK and REFINE turns. Per
Madaan et al. (2023): "These steps work in tandem to generate high-quality
outputs."

**Process:**

```
T1 (Generate): task -> y_0
T2 (Feedback): task + y_0 -> fb_0  [feedback ONLY, no rewrite]
T3 (Refine):   task + y_0 + fb_0 -> y_1
[Loop until stopping condition]
```

**Feedback quality requirements** (Madaan et al.):

- **Actionable**: Contains concrete action to improve output
- **Specific**: Identifies concrete phrases to change

WRONG: `"The code could be more efficient. Consider optimizing it."` RIGHT:
`"This uses a for loop (brute force). Use n(n+1)/2 instead."`

**History accumulation improves refinement:**

```
T_n (Refine): task + y_0 + fb_0 + y_1 + fb_1 + ... + fb_{n-1} -> y_n
```

Per Madaan et al.: "Retaining history allows the model to learn from past
mistakes."

**Performance:**

| Task Type              | Improvement |
| ---------------------- | ----------- |
| Code optimization      | +13%        |
| Dialogue response      | +35-40%     |
| Constrained generation | +20%        |

**Non-monotonic warning:** Quality can improve on one dimension while regressing
on another. Track scores across iterations; select max-score output, not final.

**Stopping conditions** (models rarely self-terminate well):

1. Fixed iterations (typically 2-4)
2. Score threshold
3. Feedback includes "NO_REFINEMENT_NEEDED"

WRONG: `"Iterate until perfect."` RIGHT:
`"Iterate 3 rounds, select best by score."`

**Feedback prompt:**

```
Output: {previous_output}

Provide feedback. Identify specific phrases needing improvement,
explain why they're problematic, suggest concrete fixes.
Do NOT rewrite. Only provide feedback.
```

**Refinement prompt:**

```
Previous attempts and feedback:
- Attempt 1: {y_0} -> Feedback: {fb_0}
- Attempt 2: {y_1} -> Feedback: {fb_1}

Produce improved version. Do not repeat previous mistakes.
```

---

## 3. Verification Methods

Multi-turn verification addresses the constraint that LLMs cannot self-correct
without external signals. Per Huang et al. (2024): "Without external feedback,
self-correction fails to improve and can exacerbate errors."

Three approaches exist, each suited to different scenarios:

| Method   | External Signal     | When to Use              | Cost            |
| -------- | ------------------- | ------------------------ | --------------- |
| CoVe     | Isolated Q&A        | General factual claims   | 3-4x tokens     |
| Factored | Source documents    | Summaries with source    | Claims x calls  |
| CRITIC   | Tools (search/code) | Verifiable via execution | Tool API + 2-3x |

### CoVe: Question-Based Fact-Checking

Per Dhuliawala et al. (2023): "CoVe drafts response, plans verification
questions, answers them independently, then generates verified response."

**Process:**

```
T1 (Baseline): query -> response_0 [may hallucinate]
T2 (Plan):     query + response_0 -> verification_questions
T3 (Execute):  verification_questions ONLY -> answers  [baseline EXCLUDED]
T4 (Revise):   query + response_0 + QA_pairs -> final_response
```

**Why this works:** Same model that hallucinates in longform correctly answers
direct questions. Shortform forces factual recall; longform encourages
confabulation.

| Setting                    | Accuracy |
| -------------------------- | -------- |
| Facts in longform          | ~17%     |
| Same facts as individual Q | ~70%     |

**Critical: Factored (isolated) verification**

WRONG (joint): `T3: Answer all Qs with response_0 in context` -- copies
hallucinations RIGHT (factored): `T3a: Answer Q1 alone; T3b: Answer Q2 alone` --
independent recall

| Method        | Precision |
| ------------- | --------- |
| Baseline      | 0.13      |
| Joint CoVe    | 0.15      |
| Factored CoVe | 0.22      |

**Open questions outperform yes/no:**

WRONG: `"Was Bloomberg born in New York?"` -- model agrees regardless RIGHT:
`"Where was Bloomberg born?"` -- forces factual recall

**Factor+Revise** adds explicit cross-check for +7.7pp:

```
T3.5 (Cross-check): response_0 + QA_pairs -> inconsistency_list
T4 (Revise):        response_0 + QA_pairs + inconsistencies -> final
```

### Factored Verification: Source-Based Checking

Specialized for summaries with source material. Per George & Stuhlmuller (2023):
"Decompose summary into claims, verify each against source."

**Process:**

```
T1 (Decompose): summary -> [claim_1, claim_2, ..., claim_n]
T2 (Verify):    For each claim: source + claim -> Supported/Not + reasoning
T3 (Revise):    summary + unsupported_claims + critiques -> revised_summary
```

**Why single-prompt fails:** George & Stuhlmuller: "Single-prompt (decompose +
verify together) achieved 63.3% vs multi-prompt factored 71.2%." Separating
prevents rationalization.

**Decomposition prompt:**

```
Extract ALL claims from this summary as a "-" separated list.
Start with "The claims are:"

[summary]
```

**Verification prompt:**

```
Check if claim is supported by document. Include quotes in reasoning.

Document: [document]
Claim: [claim]

Reasoning: [with quotes]
Supported: [Yes/No]
```

**Performance (HaluEval):**

| Model   | Few-shot | CoT   | Factored |
| ------- | -------- | ----- | -------- |
| GPT-4   | 30.9%    | 75.5% | 76.2%    |
| GPT-3.5 | 58.5%    | 61.2% | 71.2%    |

**Hallucination reduction:** GPT-4: 0.84->0.46/s (-45%); Claude2: 1.55->0.95/s
(-39%)

**Warning:** Simple self-correction makes hallucinations WORSE. George &
Stuhlmuller: "Self-correct increased hallucinations from 1.55 to 2.13." Factored
succeeds because claims verified against source, not model's own reasoning.

### CRITIC: Tool-Interactive Verification

Uses external tools (search, code, calculators) instead of LLM knowledge. Per
Gou et al. (2024): "CRITIC allows LLMs to validate outputs similar to human tool
interaction."

**Process:**

```
T1 (Generate): query -> response_0
T2 (Verify):   response_0 + tools -> verification_results + critique
T3 (Correct):  If issues: query + response_0 + critique -> corrected
               If passed: return response_0
```

**Tool selection:**

| Domain     | Tool               | Verification Method           |
| ---------- | ------------------ | ----------------------------- |
| Factual QA | Search engine      | Query for supporting evidence |
| Math       | Python interpreter | Execute, compare results      |
| Toxicity   | Classifier         | Score output, flag issues     |
| Code       | Interpreter        | Execute, check errors         |

**Performance:**

| Task               | Baseline | +CRITIC | Delta  |
| ------------------ | -------- | ------- | ------ |
| AmbigNQ (QA)       | 47.4 F1  | 55.1 F1 | +7.7   |
| GSM8K (Math)       | 81.0%    | 88.0%   | +7.0pp |
| Toxicity reduction | --       | --      | 79.2%  |

**Verification prompt:**

```
Previous output: {response_0}

Verify correctness using available tools. For each claim/calculation:
1. Identify what needs verification
2. Use appropriate tool to check
3. Report supported or refuted

If issues found, explain what's wrong and how to fix.
```

**Key insight:** CRITIC's improvement comes from external signal, not additional
reasoning. Per Gou et al.: "Exclusive reliance on self-correction without
external feedback may deteriorate performance."

**Iteration effects:** Performance typically peaks at 2-3 iterations with
diminishing returns thereafter. Additional cycles add token cost without
proportional accuracy gains.

**Stacking:** All three verification methods share the contaminated-context
anti-pattern. Can combine when different verification types needed (e.g., CoVe
for knowledge claims + CRITIC for calculations).

### Socratic Method: Cross-Examination for Verification

Uses structured questioning techniques to validate claims and expose weaknesses.
Per Chang (2023): "When the expert partner is a language model, the Socratic
method can be effectively employed without the issues that may arise in human
interactions."

**Key techniques:**

| Method    | Purpose                          | When to Use              |
| --------- | -------------------------------- | ------------------------ |
| Elenchus  | Test consistency via questioning | Validate argument logic  |
| Dialectic | Expose missing counterarguments  | Check for omissions      |
| Maieutics | Draw out implicit knowledge      | Expand understanding     |

**Process:**

```
T1 (Define):    Extract claim and supporting reasons from response
T2 (Elenchus):  For each reason, rate argument validity + source credibility
T3 (Dialectic): Generate counterarguments; rate rival reasoning
T4 (Aggregate): Weighted sum of validity × credibility scores
```

**Verification prompts:**

```
# Elenchus (cross-examination)
What is the evidence for reason [r] to support conclusion [Ω]?
How strongly does [r] support [Ω]? Rate validity [1-10] and credibility [1-10].

# Dialectic (counterargument)
Is there a counterargument against [r ⇒ Ω]? Provide counter reasons.
```

**Why this works:** Chang: "Methods definition, elenchus, and dialectic clarify
user queries and assess the quality of language model-generated text, leading to
improved precision and accuracy."

**Stacking:** Combine with CoVe (factored question generation) and CRITIC
(tool-based validation) for comprehensive verification.

---

## 4. Aggregation Strategies

Techniques sampling multiple responses and selecting/synthesizing best output.
Use when: (1) free-form makes exact-match voting impossible, (2) evidence
scattered across attempts, (3) multiple valid perspectives exist.

### Universal Self-Consistency (USC): Free-Form Selection

Extends self-consistency to outputs where exact-match voting fails. Per Chen et
al. (2023): "USC leverages LLMs to select the most consistent answer among
candidates."

**Process:**

```
T1 (Sample):  Generate N responses with temp > 0
T2 (Select):  query + all_N_responses -> index of most consistent
```

**Selection prompt:**

```
Responses to: {question}

Response 0: {r_0}
Response 1: {r_1}
...

Select most consistent based on majority consensus.
The most consistent response is Response:
```

**Why this works:** Assessing consistency is easier than correctness. Per Chen
et al.: "LLMs are generally able to examine response consistency across tasks."

**Performance:**

| Task                   | Greedy | USC  | Standard SC |
| ---------------------- | ------ | ---- | ----------- |
| GSM8K                  | 91.3   | 92.4 | 92.7        |
| TruthfulQA (free-form) | 62.1   | 67.7 | N/A         |

**Optimal sample count:** 8 samples balances accuracy and cost. More plateaus or
degrades from context limits.

### Multi-Chain Reasoning (MCR): Evidence Synthesis

Uses chains as evidence sources, not just answer votes. Per Yoran et al. (2023):
"Sampled chains collect pieces of evidence, not just predictions."

**Process:**

```
T1: Generate N reasoning chains with intermediate steps
T2: Concatenate all chains into unified context
T3 (Meta-reason): query + multi_chain_context -> final_answer + explanation
```

**Why MCR beats SC:** SC discards reasoning, only votes answers. MCR preserves
reasoning, synthesizes facts. Different chains contain complementary facts that
combined yield correct answer even when individual chains fail.

**Key finding (Yoran et al.):** "20% of correct MCR answers combine facts from
multiple chains; 10% are better than any individual chain." This explains why
meta-reasoning over evidence outperforms simple majority voting.

**Example (Yoran et al.):**

```
Q: Did Brad Peyton need to know about seismology?

Chain 1 (No): Directors don't need seismology
Chain 2 (Yes): Peyton directed San Andreas, about earthquake
Chain 3 (No): Seismology isn't required for directors

SC vote: No (2-1)

MCR synthesis: Peyton directed San Andreas (earthquake film)
               + seismology = study of earthquakes
               -> Yes (director of earthquake film needed seismology knowledge)
```

**Performance:** Multi-hop QA +5.7% over SC; 82% high-quality explanations.

### Complexity-Weighted Voting

Weights votes by reasoning complexity. Per Fu et al. (2023): "Vote over top K
complex chains."

**Process:**

```
T1: Generate N chains with answers
T2: Rank by complexity (count steps), select top K
T3: Majority vote among K complex chains only
```

**Why this works:** Simple chains reflect shortcuts or luck. Complex chains
demonstrate thorough reasoning. More steps -> more likely correct.

**Performance (GSM8K):** Standard SC 78.0% vs Complexity top-K 80.5% (+2.5pp)

**Implementation:** No additional LLM calls--post-process to count steps,
filter, vote.

### Multi-Expert Prompting: Perspective Aggregation

Simulates multiple domain experts with structured aggregation. Per Long et al.
(2024): "Aggregates expert responses in single turn without iterative
refinement."

**NGT aggregation:**

```
Step 1: Generate n expert identities; each provides independent response
Step 2: Aggregate via Nominal Group Technique:
        - Identify agreed viewpoints (>50% consensus)
        - Identify conflicts; resolve via majority vote
        - Identify unique perspectives
        - Generate aggregated response from all viewpoints
        - Select best among individual + aggregated
```

**Performance:**

| Method       | TruthfulQA |
| ------------ | ---------- |
| Zero-shot    | 68.1%      |
| Self-refine  | 75.9%      |
| USC          | 77.1%      |
| Multi-expert | **89.4%**  |

**Critical:** Full NGT framework required. Simply generating experts and picking
best performs much worse.

WRONG: `Generate 3 expert responses, pick best` RIGHT:
`NGT: agreement -> conflict resolution -> unique perspectives -> aggregate`

**Stacking:** Combine techniques--filter by complexity, then USC selection, or
MCR synthesis of USC-selected outputs.

---

## 5. Meta-Reasoning

### Cumulative Reasoning (CR): DAG-Based Validation

For complex reasoning requiring validated step accumulation. Per Zhang et al.
(2024): "CR dynamically constructs DAG of validated steps; new propositions
derive from any combination of prior nodes."

**Three roles:**

```
PROPOSER: Generates candidate steps from current DAG
VERIFIER: Validates proposals (LLM or external tool)
REPORTER: Monitors DAG, determines when to conclude
```

**Coordination loop:**

```
Initialize: DAG = {original_question}

Loop:
  Propose: DAG -> candidate_step
  Verify:  candidate + relevant_nodes -> Valid/Invalid
  If Valid: Add to DAG
  Report:  DAG -> "Continue" or "Conclude: answer"

Until Reporter concludes or iteration limit
```

**Why CR beats Tree of Thoughts:** ToT explores paths independently. CR
integrates validated knowledge across paths into shared DAG. New propositions
combine facts from ANY prior validated nodes.

**Performance:**

| Task         | CoT-SC | ToT | CR      |
| ------------ | ------ | --- | ------- |
| Game of 24   | 9%     | 74% | **98%** |
| MATH Level 5 | --     | --  | +43%    |

**Proposer prompt:**

```
Problem: {question}

Validated reasoning:
{dag_nodes}

Generate ONE atomic proposition advancing reasoning.
Must be: derivable from above, specific, verifiable, single logical step.
```

**Verifier prompt:**

```
Proposition: {candidate}
Supporting context: {relevant_nodes}

Is this valid? Explain reasoning, conclude "VALID" or "INVALID".
```

**Reporter prompt:**

```
Problem: {question}
Validated propositions: {all_nodes}

Sufficient to answer conclusively?
If YES: "CONCLUDE" + final answer
If NO: "CONTINUE" + what additional reasoning needed
```

**Stacking:** Replace LLM verifier with tool-based (Python, theorem prover) for
stronger guarantees.

---

## 6. Decomposition

### Decomposed Prompting (DECOMP): Specialized Handlers

Modular approach delegating sub-tasks to specialized handlers. Per Khot et al.
(2023): "Both decomposer and sub-task handlers have own few-shot prompts."

**Two-layer architecture:**

```
Layer 1 (Decomposer): complex_task -> sequence of sub-task calls
Layer 2 (Handlers):   Each sub-task type has specialized few-shot prompt
```

**Example:**

```
Complex: "Birthplace of Titanic's director?"

Decomposer:
  1. RETRIEVE("Who directed Titanic?")
  2. RETRIEVE("Where was {result1} born?")

Handlers:
  RETRIEVE("Who directed Titanic?") -> "James Cameron"
  RETRIEVE("Where was James Cameron born?") -> "Kapuskasing, Ontario"
```

WRONG: Single generic handler for all sub-tasks RIGHT: Specialized handlers with
own few-shot examples

### ADAPT: Decompose on Failure

Recursive approach decomposing only when executor fails. Per Prasad et al.
(2024): "ADAPT recursively decomposes to adapt to task complexity and LLM
capability."

**Recursive structure:**

```
ADAPT(task, depth):
  If depth > max_depth: Return failure

  result = Executor(task)

  If success: Return result
  Else:
    plan = Planner(task)  # Decompose
    For each sub_task in plan:
      sub_result = ADAPT(sub_task, depth + 1)
    Return aggregated results
```

**Why ADAPT beats fixed plans:** Plan-and-Execute creates fixed plans upfront,
fails when sub-tasks unexpectedly difficult. ADAPT decomposes only on failure,
matching depth to actual difficulty.

**Performance:**

| Dataset   | ReAct | Plan-Execute | ADAPT     |
| --------- | ----- | ------------ | --------- |
| ALFWorld  | 43.3% | 43.3%        | **71.6%** |
| WebShop   | 32.0% | 17.0%        | **44.0%** |
| TextCraft | 19.0% | 27.0%        | **52.0%** |

**Self-generated success heuristic:** Prasad et al.: "Executor LLM determines
completion without gold rewards."

WRONG: Always decompose to max depth RIGHT: Try execution first, decompose only
on failure

**Stacking:** Combine with Self-Refine for failed sub-tasks, CRITIC for
tool-validated execution.

### Cognitive Prompting (CP): Structured Problem-Solving Operations

Guides LLMs through sequence of cognitive operations (COPs) mimicking human
problem-solving. Per Kramer & Baumann (2024): "CP structures problem-solving
into a sequence of COPs, enabling LLMs to address complex tasks across domains
like mathematics, logic, and decision-making."

**Eight cognitive operations:**

```
1. Goal Clarification: Define the objective clearly
2. Decomposition: Break down the problem into manageable parts
3. Filtering: Focus on the most relevant information
4. Reorganization: Arrange information to reveal structure
5. Pattern Recognition: Identify recurring patterns or relationships
6. Abstraction: Extract fundamental principles from patterns
7. Generalization: Apply abstracted principles to larger problem
8. Integration: Synthesize components into cohesive solution
```

**Three variants:**

| Variant | Description                           | Performance |
| ------- | ------------------------------------- | ----------- |
| D-CP    | Fixed sequence of COPs                | Baseline    |
| SA-CP   | LLM self-selects COP sequence         | +flexible   |
| H-CP    | SA-CP + few-shot CoT from solutions   | **95%**     |

**Process prompt (SA-CP):**

```
Solve the following problem by choosing and applying appropriate
cognitive operations from the list below. For each step, provide
concise reasoning before moving on.

[8 COPs listed]

Problem: {question}
Please start with "Goal Clarification" and proceed step by step.
```

**Performance (GSM8K):**

| Model      | Zero-shot | D-CP  | SA-CP | H-CP      |
| ---------- | --------- | ----- | ----- | --------- |
| LLaMA 70B  | ~88%      | ~92%  | ~93%  | **95%**   |
| Qwen 32B   | ~92%      | ~95%  | ~96%  | **97%**   |

**Why this works:** Kramer & Baumann: "Unlike methods such as CoT, CP provides
multi-dimensional depth without manual solution design."

**Critical:** Goal Clarification must come first; Integration must come last.
Most frequent SA-CP sequence: GC→DC→PR (goal clarification→decomposition→pattern
recognition).

WRONG: `Jump directly to solving` RIGHT:
`Start with Goal Clarification, proceed through operations systematically`

**Stacking:** Combine with verification methods (CoVe, CRITIC) for validated
multi-step reasoning.

### Table as Thought: Structured Reasoning via Schema

Uses tabular schema to structure and track reasoning. Per Sun et al. (2025):
"Table as Thought employs a table as a container to represent one or more
structured thoughts."

**Process:**

```
T1 (Schema):   query -> design table schema (column headers)
T2 (Populate): iteratively populate reasoning table rows
T3 (Verify):   check constraints and consistency
T4 (Answer):   extract final answer from table
```

**Algorithm:**

```
S = DESIGN_SCHEMA(Q)           # Define table schema for query
T = Initialize_empty_table(S)
while not SUFFICIENT(T, Q):
    Θ = REFLECT(T, Q)          # Generate possible updates
    T = UPDATE_TABLE(T, Θ)     # Apply updates
return T
```

**Schema design example (calendar scheduling):**

```
Headers: Participant Name | Availability Start | Availability End |
         Meeting Duration | Schedule Constraint | Proposed Time
```

**Performance:**

| Task               | Direct | CoT   | Text as Thought | Table as Thought |
| ------------------ | ------ | ----- | --------------- | ---------------- |
| Calendar (GPT-4o)  | 64.0%  | 64.5% | 69.4%           | **74.8%**        |
| TravelPlanner      | 0.56%  | 0.56% | 0.0%            | **1.11%** (given)|

**Why this works:** Sun et al.: "Headers in the table schemas are designed to
represent essential reasoning steps and key information pertinent to the task.
These headers act as anchors for organizing and verifying intermediate and final
reasoning outputs."

**Critical:** Schema design quality determines success. Predefined schemas often
outperform LLM-designed schemas on complex planning tasks.

| Ablation              | Calendar Accuracy |
| --------------------- | ----------------- |
| Full Table as Thought | 42.3%             |
| w/o Schema Design     | 36.2% (−6.1)      |
| w/o Verification      | 38.5% (−3.8)      |

WRONG: Single-row tables for complex constraints RIGHT: Multi-row tables with
fine-grained intermediate steps

**Stacking:** Combine with verification modules for constraint-checking; works
well with structured planning tasks.

---

## 7. Parallel Generation

### Skeleton-of-Thought (SoT): Structure Before Content

Creates answer structure before content, enabling parallel expansion. Per Ning
et al. (2024): "Guide LLM to give skeleton first, then write parallelly."

**Process:**

```
T1 (Skeleton): question -> numbered list of 3-5 word points
T2+ (Expand):  For each point (parallelizable):
               question + skeleton + point_index -> 1-2 sentence expansion
```

**Skeleton prompt:**

```
Give skeleton only (not full content) for answering. Provide numbered
list of points, each 3-5 words. Generally 3-10 points.

{question}

Skeleton:
1.
```

**Expansion prompt:**

```
Continue ONLY point {index}. Write 1-2 sentences. Do NOT continue other points.

{index}. {point_skeleton}
```

**Performance:**

| Model  | Speedup | Net Quality |
| ------ | ------- | ----------- |
| Claude | 1.83x   | +0.08       |
| GPT-4  | 1.65x   | +0.05       |

**When SoT works:** Multi-point answers, knowledge questions with independent
facts. **When SoT fails:** Math (sequential steps), coherent short answers, code
with dependencies.

**SoT Router:** Route to SoT only when appropriate:

```
How to answer?
A. Independent list points (use SoT)
B. Dependent list points (use normal)
C. Not a list (use normal)
```

---

## 8. Prompt Design

### Active Prompting: Uncertainty-Based Exemplar Selection

Selects optimal few-shot exemplars based on model uncertainty. Per Diao et al.
(2023): "Uncertainty-based selection determines which questions are most helpful
to annotate."

**Process:**

```
Stage 1: For each candidate, generate k predictions with temp > 0
         Calculate uncertainty (disagreement/entropy)
Stage 2: Select n questions with highest uncertainty
Stage 3: Human annotates reasoning chains for selected
Stage 4: Use annotated exemplars for few-shot on test set
```

**Uncertainty metrics:**

```
Disagreement: u = unique_answers / k
Entropy: u = -sum(p(ans) * log(p(ans)))
```

**Performance:**

| Dataset | Random-CoT | Active-Prompt | Delta  |
| ------- | ---------- | ------------- | ------ |
| GSM8K   | 78.6%      | 83.4%         | +4.8pp |
| CSQA    | 74.5%      | 78.8%         | +4.3pp |

**Insight:** Diao et al.: "Selected uncertain cases transfer to different
models." Exemplars from one model often work well with others.

WRONG: Select exemplars model gets correct easily RIGHT: Select where model
shows highest disagreement

### Synthetic Prompting: Self-Generated Demonstrations

Augments limited seed examples with LLM-synthesized demonstrations. Per Shao et
al. (2023): "We prompt an LLM to generate more examples by alternating between
two processes: the backward process, where the LLM synthesizes a question based
on a self-generated reasoning chain; and the forward process, where the LLM
produces a reasoning chain for the synthesized question."

**Backward-forward synthesis:**

```
Backward (question synthesis):
  1. Sample topic word from diverse set
  2. Set target complexity (# reasoning steps)
  3. Generate reasoning chain of target complexity
  4. Generate question matching reasoning chain

Forward (chain refinement):
  1. Generate refined reasoning chain for synthesized question
  2. Sample m chains, keep if >50% agree on answer
  3. Store shortest consistent chain with question
```

**Backward prompt:**

```
# I implement a Python function called solution() to solve the following question.
# The question is about {topic}.
def solution():
""" {target_complexity}-line function """
# 1
...
Question: [synthesized based on self-generated chain]
```

**Selection scheme (In-Cluster Complexity):**

```
1. Cluster synthesized examples by semantic similarity
2. From each cluster, select most complex example (longest chain)
3. Use selected examples as diverse, informative demonstrations
```

**Performance:**

| Dataset       | PAL   | Vanilla Synth | Synthetic Prompting |
| ------------- | ----- | ------------- | ------------------- |
| GSM8K (4seed) | 73.1% | 72.7%         | **75.3%**           |
| Repeat Copy   | 81.3% | 81.3%         | **84.4%**           |
| Colored Obj   | 94.4% | 93.1%         | **97.3%**           |

**Why this works:** Shao et al.: "The backward process ensures questions are
answerable and well-defined. The forward process refines the reasoning chain to
be more precise and consistent with the question."

**Critical conditions for quality:**

| Condition         | Effect on Synthesis                         |
| ----------------- | ------------------------------------------- |
| Topic word        | Ensures diversity; without: 62.5% same topic|
| Target complexity | Controls difficulty; without: much simpler  |
| Reasoning chain   | Ensures answerability; without: 37.5% wrong |

WRONG: Synthesize questions directly without reasoning chain first RIGHT:
Generate reasoning chain first, then matching question (backward process)

**Stacking:** Use synthesized examples to improve any few-shot technique. Works
with PAL, CoT, or any reasoning chain format.

---

## 9. Context Management

Multi-turn accumulates context. Manage token limits by:

1. **Summarize history:** After N iterations, summarize previous attempts
2. **Keep recent + best:** Retain only most recent and best-scoring output
3. **Structured extraction:** Extract key points from feedback, not full text

WRONG:

```
[Full y_0] [Full fb_0] [Full y_1] [Full fb_1] ...
```

RIGHT:

```
Previous attempts summary:
- Attempt 1: Failed due to [issue]
- Attempt 2: Improved [aspect] but [remaining issue]
- Attempt 3: Best so far, minor [aspect] issue

Latest attempt: [full y_3]
```

**Conversation template:**

```
SYSTEM: [Base prompt with single-turn techniques]

T1 (Generate): USER: [Task] -> ASSISTANT: [y_0]
T2 (Analyze):  USER: [Critique/verify y_0] -> ASSISTANT: [Feedback]
T3 (Refine):   USER: [Refine with T2 output] -> ASSISTANT: [y_1]
[Repeat]
T_final:       USER: [Extract in format] -> ASSISTANT: [Final]
```

---

## 10. Anti-Patterns

### Intrinsic Self-Correction

"Review and improve without external signals" fails--74.7% keep original;
changes more likely wrong (Huang et al. 2024).

WRONG: `T1: Solve -> T2: Review and fix` RIGHT:
`T1: Solve -> T2: Generate verification Qs -> T3: Answer (isolated) -> T4: Revise`

### Mixed-Goal Turn

Combining distinct operations in single turn degrades both.

WRONG: `Generate, then critique it, then improve it` RIGHT:
`T1: Generate -> T2: Critique (feedback only) -> T3: Improve`

### Contaminated Context

Including original when answering verification questions.

WRONG: `Original: [hallucinations] + Verification Q: Where was X born?` RIGHT:
`Verification Q: Where was X born? [original NOT in context]`

### Yes/No Verification

Phrasing verification as yes/no confirmations.

WRONG: `"Is it true Bloomberg was born in New York?"` RIGHT:
`"Where was Bloomberg born?"`

### Infinite Loop

No explicit stopping condition.

WRONG: `Keep improving until perfect` RIGHT:
`Improve for 3 iterations, output best version`

### Forgotten History

Discarding previous iterations in refinement.

WRONG: `Here is feedback. Improve. [no previous attempts]` RIGHT:
`Attempts: 1: y_0 -> fb_0; 2: y_1 -> fb_1. Improve, avoid previous mistakes.`

### Vague Feedback

Feedback without actionable specifics.

WRONG: `Response could be improved. Some parts unclear.` RIGHT:
`Paragraph 2 uses "electron transport chain" without definition. Add: "process converting light to chemical energy."`

### Majority Fallacy

Assuming majority vote always correct.

WRONG: `3/5 say X, so X is correct` RIGHT:
`Weight by complexity, or use MCR to synthesize evidence from all chains`

---

## Research Citations

**Primary sources (in project corpus):**

- Chang, E.Y. (2023). "Prompting Large Language Models With the Socratic
  Method." Stanford University.
- Dhuliawala, S., et al. (2023). "Chain-of-Verification Reduces Hallucination in
  Large Language Models." arXiv.
- Fu, Y., et al. (2023). "Complexity-Based Prompting for Multi-Step Reasoning."
  arXiv.
- George, C. & Stuhlmuller, A. (2023). "Factored Verification: Detecting and
  Reducing Hallucination in Summaries." arXiv.
- Gou, Z., et al. (2024). "CRITIC: Large Language Models Can Self-Correct with
  Tool-Interactive Critiquing." arXiv.
- Huang, J., et al. (2024). "Large Language Models Cannot Self-Correct Reasoning
  Yet." arXiv.
- Khot, T., et al. (2023). "Decomposed Prompting: A Modular Approach for Solving
  Complex Tasks." arXiv.
- Kramer, O. & Baumann, J. (2024). "Unlocking Structured Thinking in Language
  Models with Cognitive Prompting." arXiv.
- Madaan, A., et al. (2023). "Self-Refine: Iterative Refinement with
  Self-Feedback." arXiv.
- Prasad, A., et al. (2024). "ADAPT: As-Needed Decomposition and Planning with
  Language Models." arXiv.
- Shao, Z., et al. (2023). "Synthetic Prompting: Generating Chain-of-Thought
  Demonstrations for Large Language Models." arXiv.
- Sun, Y., et al. (2025). "Table as Thought: Exploring Structured Thoughts in
  LLM Reasoning." arXiv.
- Weston, J. & Sukhbaatar, S. (2023). "System 2 Attention (Is Something You
  Might Need Too)." arXiv.
- Yoran, O., et al. (2023). "Answering Questions by Meta-Reasoning over Multiple
  Chains of Thought." arXiv.
- Zhang, Y., et al. (2024). "Cumulative Reasoning with Large Language Models."
  TMLR.
- Zhang, Y., Yuan, Y. & Yao, A. (2024). "Meta Prompting for AI Systems."
  Tsinghua University. arXiv.

**External sources (not in project corpus):**

- Chen, X., et al. (2023). "Universal Self-Consistency for Large Language Model
  Generation." arXiv. †
- Diao, S., et al. (2023). "Active Prompting with Chain-of-Thought for Large
  Language Models." arXiv. †
- Long, D.X., et al. (2024). "Multi-expert Prompting Improves Reliability,
  Safety and Usefulness of LLMs." arXiv. †
- Ning, X., et al. (2024). "Skeleton-of-Thought: Prompting LLMs for Efficient
  Parallel Generation." ICLR. †
