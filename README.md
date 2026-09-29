# BKT-Decision-Service

A containerized knowledge-tracing service that takes a single student interaction event and returns an updated mastery estimate together with the next instructional action. It is deployed on Google Cloud Run.

> **Status: work in progress.** Sections marked _TBD_ will be filled in as the prototype is built and evaluated.

This repository is **Part 3** of the course project _"A Cloud and Big Data Architecture for Real-Time Adaptive Tutoring"_ (Cloud Computing and Big Data, VILNIUS TECH). The streaming data pipeline from Part 2 is in [PySpark-Data-Processing](https://github.com/ysk1020/PySpark-Data-Processing).

---

## What this service does

In the course project architecture, a student's interaction passes through seven steps, from the event occurring to a response being returned. This repository implements **Step 6**: a containerized service that uses the student's knowledge state to decide what the student should receive next.

```
student event  ──►  BKT mastery update  ──►  decision rule  ──►  action
(user, question,     P(mastered) for the      e.g. low mastery      hint / easier task /
 answer, time)       skill (EdNet "part")     → hint                next task / feedback
```

## Approach

| Component        | Choice                                                                                | Reason                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Data             | 500-student EdNet-KT1 sample from Part 2, joined with EdNet-Content question metadata | Reuses the Part 2 sample; the join adds response correctness and the skill label         |
| Skill definition | EdNet `part` (7 skills)                                                               | Enough data per skill at sample scale, and no multi-tag ambiguity                        |
| Model            | Bayesian Knowledge Tracing via [pyBKT](https://github.com/CAHLR/pyBKT)                | Interpretable per-skill mastery, and each request needs only a few arithmetic operations |
| Service          | FastAPI                                                                               | _TBD_                                                                                    |
| Packaging        | Docker                                                                                | Required for Cloud Run; runs the same way locally and in the cloud                       |
| Deployment       | Google Cloud Run                                                                      | Managed container platform chosen for model serving in the Part 1 architecture           |
| Learner state    | In memory, single instance                                                            | Prototype simplification; see [Limitations](#limitations)                                |

## Repository structure (planned)

```
BKT-Decision-Service/
├── notebooks/
│   ├── 01_prepare_data.ipynb     # join sample with question metadata, compute correctness
│   └── 02_train_bkt.ipynb        # fit BKT, evaluate on held-out students
├── app/
│   └── main.py                   # FastAPI service
├── scripts/
│   └── replay_events.py          # sends EdNet events to the service, logs responses and latency
├── results/                      # experiment outputs
├── Dockerfile
├── requirements.txt
└── README.md
```

## Data

- **Input:** the time-ordered 500-student sample produced by the Part 2 sampler notebook (43,574 interactions).
- **Question metadata:** `questions.csv` from EdNet-Contents, which provides `correct_answer` and `part` for each question.
- **Derived column:** `correct = (user_answer == correct_answer)`.

Neither dataset is included in this repository. See the Part 2 README for how the sample is created.

## API (draft)

_TBD. The request and response format will be defined before implementation._

## Running locally

_TBD_

## Deploying to Cloud Run

_TBD_

## Evaluation

| #   | Question                                        | Measure                                                                                                                         | Result |
| --- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------ |
| E1  | Does BKT predict better than a simple baseline? | AUC for next-response correctness on held-out students, compared with a baseline that predicts each skill's average correctness | _TBD_  |
| E2  | How large is the cold-start delay on Cloud Run? | First-request latency with minimum instances set to 0 versus 1                                                                  | _TBD_  |
| E3  | How does latency behave under concurrent load?  | Median and 95th-percentile latency at increasing concurrency                                                                    | _TBD_  |
| E4  | Are the decisions sensible?                     | Mastery trajectory and actions for sample students; how actions are distributed across mastery levels                           | _TBD_  |

## Limitations

- **Single instance, in-memory state.** Learner state lives in the service's own memory, so the service is capped at one instance. With several instances, each would hold a different partial view of a student. The full architecture stores state in Bigtable for this reason.
- **Coarse skills.** EdNet's 7 parts are much broader than real skills.
- **No forgetting.** Standard BKT assumes a mastered skill stays mastered.
- **Only the serving path is implemented.** Pub/Sub ingestion, Bigtable and pipeline-wide monitoring from the Part 1 architecture are not deployed.

## References

- EdNet dataset: _TBD (use the citation from the course project document)_
- pyBKT: _TBD_
- Bayesian Knowledge Tracing, Corbett & Anderson: _TBD (use the thesis citation)_
