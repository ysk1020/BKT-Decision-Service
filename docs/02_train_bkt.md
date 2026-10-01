# `02_train_bkt.ipynb` — fitting and evaluating BKT

This notebook fits one Bayesian Knowledge Tracing (BKT) model per EdNet `part` (7
skills) on the training split, evaluates it against a baseline on the held-out
test split, inspects the fitted parameters for sanity, and exports the final
numbers to `app/bkt_params.json` — the only artifact the decision service
actually depends on.

## What each cell does

| Cell | Purpose |
|---|---|
| 1. Load | Reads `data/processed/train.csv` / `test.csv` (from `01_prepare_data.ipynb`) and asserts the row counts match that notebook's split: 31,454 train rows / 12,116 test rows, 400/100 students. |
| 2. Prepare columns | pyBKT expects `user_id`, `skill_name`, `correct`, `order_id`. Adds `skill_name` (= `part`, as a string) and `order_id` (a running row counter). `order_id` is used instead of `timestamp` because bundled questions share a timestamp, which would make in-bundle ordering ambiguous — pyBKT sorts internally by `order_id`. |
| 3. Fit | `Model(seed=42).fit(data=train_bkt)`. `forgets` stays at its default (`False`) — standard BKT assumes a mastered skill stays mastered (see README "No forgetting" limitation). |
| 4. Predict | `model.predict(data=test_bkt)` runs the forward algorithm one step at a time per student: `correct_predictions[t]` and `state_predictions[t]` (P(mastered) *before* seeing row *t*'s answer) are computed from rows `1..t-1` only, then row *t*'s answer is folded in afterwards. So every prediction is a genuine one-step-ahead forecast, not a fit to data it already saw. |
| 5. Baseline | For each part, the training-set average correctness, broadcast to every test row of that part. This is the "predict the skill's average" baseline E1 compares BKT against. |
| 6. E1 table | `roc_auc_score`, overall and per part, for BKT vs. baseline. |
| 7. Inspect parameters | Pivots `model.params()` into one row per part (`prior`, `learns`, `guesses`, `slips`), then checks `guesses < 0.5` and `slips < 0.5`, and compares each part's `prior` against its observed training-set correctness. |
| 8. Export | Writes `app/bkt_params.json` — 4 numbers per part (`prior`, `learn`, `guess`, `slip`). Saved under `app/`, not the git-ignored `results/`, because it's a serving artifact the Docker build needs to ship, not a throwaway eval output. |
| 9. Mastery curve | Plots `state_predictions` over time for the test student with the most part-5 interactions, as a visual sanity check that mastery rises after correct streaks and dips after wrong answers. |
| 10. Summary | Rolls up E1 and the fitted parameters into the tables below. |

## Why per-part AUC is a different question than overall AUC

Within a single part, the baseline predicts the *same* number for every row
(that part's training average), so there's no ranking information and
`roc_auc_score` is exactly 0.5 by construction — not a weak baseline, just what
a constant predictor does to a ranking metric.

- **Per-part AUC** asks "does BKT beat random guessing within this one skill?"
  Any score above 0.5 is a real, skill-specific win.
- **Overall AUC** asks "does BKT beat simply knowing which part is easy?" Pooled
  across parts, the baseline is no longer constant — it can rank an easy part's
  row above a hard part's row just from the part label. BKT's overall AUC has to
  beat that skill-difficulty signal too, not just chance.

## Outputs (verification run, `seed=42`, `num_fits=5` — the notebook's committed state)

**E1 — AUC, BKT vs. baseline**

| part | n | BKT AUC | baseline AUC |
|---|---|---|---|
| overall | 12,116 | 0.584 | 0.531 |
| 1 | 647 | 0.637 | 0.500 |
| 2 | 1,402 | 0.513 | 0.500 |
| 3 | 873 | 0.585 | 0.500 |
| 4 | 846 | 0.722 | 0.500 |
| 5 | 6,399 | 0.565 | 0.500 |
| 6 | 1,296 | 0.536 | 0.500 |
| 7 | 653 | 0.565 | 0.500 |

BKT beats the baseline everywhere, so it's picking up more than "which skill is
this" — but unevenly: part 4 gets the strongest lift (0.722 vs. 0.5), part 2 is
barely above chance (0.513). Per-student history carries far more signal for
some skills than others.

**Fitted BKT parameters per part**

| part | prior | learn | guess | slip |
|---|---|---|---|---|
| 1 | 0.289 | 0.035 | **0.547** | 0.223 |
| 2 | 0.788 | 0.050 | 0.336 | 0.294 |
| 3 | 0.593 | 0.013 | 0.340 | 0.328 |
| 4 | 0.187 | 0.103 | 0.226 | 0.389 |
| 5 | 0.131 | 0.019 | 0.445 | 0.341 |
| 6 | 0.591 | 0.060 | 0.282 | 0.337 |
| 7 | 0.570 | 0.020 | 0.206 | 0.354 |

Correctness-vs-prior mostly makes sense (part 2: highest correctness *and*
highest prior; part 4: lowest *and* lowest), but parts 1 and 5 break the
pattern — middling-to-high correctness despite a low prior — and they're
exactly the two parts with the highest `guess`. The model is explaining a
meaningful share of their "correct" answers as guessing, not mastery.

**Part 1 is degenerate.** `guess = 0.547 > 0.5` means the model would rather
attribute a correct answer to luck than to knowledge for that skill — the
textbook "degenerate parameters" failure mode in BKT fitting (Baker, Corbett &
Aleven, 2008 is the usual reference; verify before citing). Part 5's `guess`
(0.445) is close but stays under the line.

**The practical check every part still passes:** as long as `1 − slip > guess`,
a correct answer still *raises* mastery and a wrong one still *lowers* it, so
the service's updates never move backwards — they just move slowly where the
margin is small.

| part | 1 − slip | guess | margin |
|---|---|---|---|
| 1 | 0.777 | 0.547 | 0.230 |
| 2 | 0.706 | 0.336 | 0.370 |
| 3 | 0.672 | 0.340 | 0.332 |
| 4 | 0.611 | 0.226 | 0.385 |
| 5 | 0.659 | 0.445 | **0.214** |
| 6 | 0.663 | 0.282 | 0.381 |
| 7 | 0.646 | 0.206 | 0.440 |

Parts 1 and 5 have the two smallest margins — consistent with both having high
`guess` and (for part 1) the degenerate flag.

## Refit check: does `num_fits=20` fix part 1?

pyBKT's EM fit can converge to a poor local optimum from a single random
initialization; `Model(seed=42, num_fits=N)` reruns the fit from `N` random
starts and keeps the best. Tried `N=20` (vs. the notebook's default `N=5`) in a
standalone script against the same `train.csv`:

| part | prior | learn | guess | slip |
|---|---|---|---|---|
| 1 | 0.263 | 0.035 | **0.552** | 0.222 |
| 2 | 0.789 | 0.048 | 0.339 | 0.294 |
| 3 | 0.564 | 0.016 | 0.346 | 0.327 |
| 4 | 0.193 | 0.108 | 0.220 | 0.391 |
| 5 | 0.118 | 0.019 | 0.446 | 0.341 |
| 6 | 0.606 | 0.053 | 0.280 | 0.337 |
| 7 | 0.558 | 0.018 | 0.213 | 0.351 |

**Result: no improvement.** Part 1's `guess` went *up* slightly (0.547 → 0.552)
and every other part moved by ≲0.03. 20 independent random restarts converge to
essentially the same solution as 5 did — this is strong evidence that part 1's
`guess > 0.5` is a genuine property of the data (a small, high-correctness part
with little per-student signal to separate "knows it" from "got lucky"), not an
artifact of a single unlucky EM initialization. (The fit emits a flood of
`RuntimeWarning: invalid value encountered in divide` from pyBKT's internal
`EM_fit.py`, apparently from some restarts producing near-degenerate
intermediate values; it doesn't change the converged result.)

**Decision: keep the committed model (`num_fits=5`, `seed=42`) and document the
caveat rather than re-fitting or hand-patching `guess` for part 1.** A
hand-patched number would mean the deployed service no longer matches the model
that was evaluated above.

## Mastery curve (Cell 9, part 5 example student)

For the test student with the most part-5 interactions (3,460 of them): the
curve starts at the part-5 prior (0.131), oscillates in the 0.15–0.27 range for
the first ~40 interactions (rising after correct answers, dropping after wrong
ones), then a sustained correct streak pushes it from ~0.5 past 0.9 by
interaction 54. No random jumps, no flat line — the model tracks this
student's actual trajectory rather than echoing the base rate.

## What this implies for the decision service

Because parts 1 and 5 have the smallest `1 − slip − guess` margins, expect the
service to emit more `hint`/`practice` actions and move mastery more slowly for
those two parts than for the rest — a dozen-ish consecutive correct answers to
climb from the part-5 prior (0.13) to 0.95, versus far fewer for a part like 4
(prior 0.19, margin 0.385). That's not a bug in `bkt_update`/`decide`; it's what
these fitted parameters imply, and it's expected to show up in E4 (decision
sensibility).
