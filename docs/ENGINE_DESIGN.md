# Engine design decision: deterministic text-against-scope

Decided 2026-10-23, before any reasoning code was written and before the reveal.
Decision ID: `engine-method-deterministic-v1-2026-10-23`.

## Decision

The engine is **deterministic**. It matches terms and concepts in the project text
against the verbatim NITRD PCA scopes, then applies NITRD's published AI cross-PCA
examples and its "most specific PCA" rule. It uses no language model, at build time
or at run time.

## Why

| Criterion | Deterministic | LLM-assisted |
| --- | --- | --- |
| A coder or judge can trace *why* each proposal was made | Yes: every proposal lists the scope terms and the rule that drove it | Only as captured model prose, which is a narrative, not a mechanism |
| Reproducible in CI, without a model | Yes: same text and same scopes give the same bytes | Needs a pinned model and settings and replayed responses; any re-run against a live model drifts |
| Scramble proof (S8) | Holds directly: the output is a pure function of RePORTER text, scopes and identity | Holds only on cached responses, so S8 proves the cache, not the model |
| Grounded in public definitions only | Yes: the vocabulary is derived from the scope text | Uses the model's own priors, which can't be audited |
| Flexibility (paraphrase, context) | Lower: misses wording the scopes don't use | Higher |

The project's thesis is inspectability. An assist proposal is useful to a coder only
if the coder can see the reasoning, not just the label. Flexibility is the one thing
given up. That cost is accepted and will show in the match rate; it is not hidden.

If an LLM is ever added, it needs a new, dated protocol amendment *before* the
reveal. That amendment must cover: the pinned model ID and version; temperature 0
and fixed settings; the prompt and its hash; responses captured and committed, keyed
by (appl_id, prompt hash); and S8 running on the replayed responses, with that
limitation stated. It must not be added after the reveal.

## Method, fixed now

1. **Text.** Use the project's title, abstract, and public health relevance
   statement, plus aims where the abstract carries them. These come from the public
   RePORTER record, are cached once, and are committed with a SHA-256 for each project.
   Nothing comes from the fixture except identity.
2. **Vocabulary from the scopes only.** Each PCA's terms are the content terms and
   phrases of its verbatim `scope_text`. AI terms also draw on NITRD's statutory AI
   definition and its cross-PCA examples. Every term records the scope phrase it came
   from.
   * **Normalisation:** lower-casing, a fixed stop-list and a fixed light stemmer, all
     committed in code.
   * **Hand additions:** any synonym or expansion must be listed in a committed file.
     Each entry cites the scope phrase it expands and gives a reason. None may be
     chosen by looking at fixture suggestions or the key.
3. **Scoring.** For each PCA, the score is weighted term and phrase overlap between
   the text and that PCA's vocabulary. Phrase matches outweigh single words, and a
   term shared by many PCAs carries less weight (IDF across the 12 scopes, not across
   projects). The weights and thresholds are constants in code, fixed before the
   engine is run on the 480.
4. **The "most specific PCA" rule.**
   * **Cross-PCA examples:** NITRD's AI examples are encoded as explicit rules, each
     citing its source sentence. Examples: general machine-vision methods go to AI,
     robots that use machine vision go to IRAS; machine learning goes to AI, the
     wider data ecosystem goes to LSDMA.
   * **Specificity:** among the PCAs that qualify, the most specific wins. The scopes'
     overlap structure defines specificity, for example AW inside ACNS, or IRAS over
     AI for embodied systems. Ties are broken by a fixed PCA order.
5. **AI relevance.** `ai_relevant` is true when the text matches AI vocabulary above
   a fixed threshold, whatever the primary PCA. `primary_pca=AI` always sets it true.
6. **Advanced Wireless.** Follows format v2: `sub_pca=AW` only when ACNS is the
   primary PCA and the AW scope terms match.
7. **Abstain.** If no PCA reaches the threshold, `primary_pca` is left empty, and the
   explanation says why. A guess is never forced.

## Explainability: required output

Alongside `proposals.csv`, the engine writes `explanations.jsonl`, one line per
proposal, sorted by `appl_id`. Each line has:

* `appl_id` and `text_sha256`: the hash of the exact RePORTER text used.
* `primary_pca`, `ai_relevant`, `sub_pca`: the same values as in the CSV.
* `ranked`: the top PCAs, each with its score and matched terms. Every matched term
  gives the text span it hit and the scope phrase it came from.
* `rules_applied`: the cross-PCA or specificity rules that fired, each with its NITRD
  source sentence.
* `ai_evidence`: the AI terms that set the flag, or `[]`.
* `abstain_reason`: why no PCA was proposed, or `null`. The value must start with one
  of two fixed prefixes, which the post-reveal breakdown relies on:
  * `no_public_text`: the RePORTER record wasn't found, or had no title or abstract.
  * `below_threshold`: there was text, but no PCA reached the scope-match threshold.
    The rest of the value gives the top score and the threshold.

A coder can read any line and see which scope language drove the proposal. A judge
can re-derive it in CI.

## Enforcement

* **S8 covers explanations too.** The scramble proof requires `explanations.jsonl`,
  and the file must be byte-identical between the real-fixture run and the scrambled
  run. The explanation can't depend on a forbidden column any more than the label can.
* **No model in the engine.** The engine has no model client and no network access in
  `--offline` mode. Its only cache is RePORTER text.
* **Freeze gate.** Before freeze, the vocabulary, weights, thresholds and rules are
  committed and their hashes logged. Changing any of them after the reveal is tuning.

## What this does not claim

The output is an assist proposal for SME review (see `engine/README.md`). Term overlap
with NITRD's published scopes, plus NITRD's published specificity guidance, is a
transparent method. It does not claim to be the official UAC method, and agreement
with the held-out key is not a claim of official correctness.
