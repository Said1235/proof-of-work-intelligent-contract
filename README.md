# WorkProof

An [Intelligent Contract](https://docs.genlayer.com/developers/intelligent-contracts) for [GenLayer](https://www.genlayer.com) that turns a digital work agreement into a verifiable outcome.

A client publishes a job with 2-5 acceptance criteria, a worker accepts it, delivers a public HTTPS URL, and GenLayer's validators evaluate the delivered content **against the criteria that were fixed before the work started**. The result is stored per criterion, with literal evidence quotes and the SHA-256 of the exact bytes that were judged.

> **Status:** the contract has passed an adversarial audit in direct-test mode (`docs/AUDIT_REPORT.md`): **`PASS WITH LIMITATIONS`**. It has **not** been run through real multi-validator consensus on GenLayer Studio and no deployment has been source-verified yet. Do not treat any deployment as audited until you complete the steps in [Deploying](#deploying).

## How it works

```
create_job ──► OPEN ──accept_job──► IN_PROGRESS ──submit_delivery──► receipt PENDING
                                          │
                                 evaluate_delivery (consensus)
                      ┌───────────────────┼────────────────────┐
                  VERIFIED          NEEDS_REVISION        INCONCLUSIVE
                  (terminal)     (corrective delivery, max 2 deliveries per job)
```

`evaluate_delivery(receipt_id)` takes **only** the receipt id. Terms, parties and criteria always come from contract storage.

The security property the contract is built around:

> No verification result is stored unless the validators have independently checked every decisive field of the receipt, using the same agreement terms and evidence they fetched themselves.

How that is enforced:

- **Independent evidence.** Every validator fetches the URL itself, hashes the exact bytes (SHA-256) and must obtain the same `evidence_hash` and size as the leader.
- **Exact per-criterion agreement.** Each criterion's `status` (`MET` / `NOT_MET` / `UNVERIFIABLE`) and `reason_code` must match the validator's own evaluation. Agreeing only on the overall status is not enough.
- **Complete and ordered.** The result must cover exactly the original criteria `C1..Cn`, in order: nothing missing, duplicated, extra or renamed.
- **Evidence you can check.** A `MET` needs a quote that appears literally in the deliverable (at least 8 characters, or the whole short document). Without it the criterion is downgraded to `UNVERIFIABLE`, so an invented approval cannot become `VERIFIED`.
- **Derived, never trusted.** The overall status is computed by code from the criterion statuses. There is no score, threshold or free-text summary.
- **Unambiguous records.** Receipts are keyed by a contract-generated id (`rcpt-<n>`), bound to their job, delivery index and agreement hash, and never overwritten.
- **Fail safe.** HTTP errors, empty/oversized/non-UTF-8 content and unusable model output abort the transaction; nothing is stored. `INCONCLUSIVE` is a completed business outcome, not an error.

Full details: [`docs/DESIGN.md`](docs/DESIGN.md).

## Public interface

| Method | Kind | Arguments | Returns |
|---|---|---|---|
| `create_job` | write | `title: str`, `description: str`, `criteria: list[str]` | `job_id` (`"job-<n>"`) |
| `accept_job` | write | `job_id: str` | - |
| `submit_delivery` | write | `job_id: str`, `url: str` | `receipt_id` (`"rcpt-<n>"`) |
| `evaluate_delivery` | write | `receipt_id: str` | - |
| `get_job` | view | `job_id: str` | job dict (`found: false` if absent) |
| `get_receipt` | view | `receipt_id: str` | receipt dict (`found: false` if absent) |
| `get_receipt_id` | view | `job_id: str`, `delivery_index: int` (1-based) | receipt id or `""` |
| `get_job_receipts` | view | `job_id: str` | list of receipt dicts |

Write calls revert with a message prefix: `[EXPECTED]` (invalid call), `[EXTERNAL]` (source problem), `[TRANSIENT]` (source temporarily unavailable) or `[LLM_ERROR]` (unusable model output).

**Integrating a client.** A receipt holds a valid evaluation only when `status == "EVALUATED"`. A reverted, pending or undetermined transaction means *no evaluation yet*; do not confuse it with the business result `INCONCLUSIVE`. Never identify a delivery by comparing wallet history: use `get_receipt_id(job_id, n)`.

## Repository layout

```
contracts/workproof.py          The contract (audited source)
variants/next-sdk/              Mechanically ported variant for the newer SDK generation (lint-checked only)
tests/direct/                   Direct-mode tests: functional, equivalence attacks, adversarial audit
tests/integration/              Consensus tests for GenLayer Studio (see below)
tools/                          Mutation checks, scenario matrix, variant generator, GLSim launcher
docs/DESIGN.md                  Design and behavior reference
docs/AUDIT_REPORT.md            Audit findings, evidence and remaining limitations
```

## Getting started

Requirements: Python 3.12 and internet access (the GenVM runners are downloaded on first use).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

genvm-lint check contracts/workproof.py     # lint + schema validation
pytest tests/direct -q                      # direct-mode test suite
```

The toolchain is pinned by commit in `requirements.txt` (`genlayer-test` 0.29.2, `genvm-linter` 0.11.1-rc.2, `genlayer-py` 0.18.0). The contract targets the SDK runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`.

## Tests

| Suite | What it covers |
|---|---|
| `tests/direct/test_workproof_functional.py` | lifecycle, permissions, limits, safe failure, indexing |
| `tests/direct/test_workproof_equivalence.py` | forged leader results the validator must reject (and that must never be stored) |
| `tests/direct/test_workproof_audit.py` | differential fuzzing against an independent oracle, stateful invariant fuzzing, targeted probes |
| `tests/integration/test_workproof.py` | leader + validators consensus on Studio with mock validators (plus an opt-in live test) |

In a clean install, all 283 direct-mode tests pass. In direct mode the validator is invoked explicitly on forged results and the stored state is then checked. This is a model of consensus, **not** real multi-validator consensus.

### Integration tests

They need a GenLayer network with consensus:

```bash
gltest tests/integration/test_workproof.py -v -s
# optional, real LLM validators against a page you control:
WORKPROOF_LIVE_URL=https://example.org/page gltest tests/integration/test_workproof.py -k live -s
```

`tools/run_glsim_nocache.py` starts the local GLSim simulator with a workaround for a deployment bug in GLSim 0.29.2. GLSim assigns the same sender to every transaction, so it cannot exercise the client/worker flows; use Studio.

### Tooling

```bash
python tools/mutation_check.py          # weakens the validator rules 15 ways; the suite must fail each time
                                        # (M03 is a documented equivalent mutant and is expected to survive)
python tools/mutation_check_audit.py    # same for state machine, identity and the audit fixes
python tools/port_to_next_sdk.py        # regenerates variants/next-sdk/ from the contract
```

Mutants are written to a temporary directory and loaded through the `WORKPROOF_CONTRACT` environment variable; the real contract is never modified.

## Deploying

Deployment is intentionally not scripted. Use the official GenLayer CLI (`npm install -g genlayer`, then `genlayer deploy`), and then:

1. Compute the commitment of the source you deployed: `sha256sum contracts/workproof.py`. The audited version is `14d94364fe24ff5511d6ec1ab5bc35635aabc0470efc9c81d45ad4748b94b51a`.
2. Retrieve the deployed code with `genlayer code <address>` and `genlayer schema <address>` and confirm that its hash and schema match.
3. Run the integration tests on Studio.

Only after (2) and (3) can that deployment be considered to match the audited source.

## Known limitations

- Prompt-injection resistance is defense in depth, not immunity: a model fooled identically on every node can still approve a criterion that quotes a real sentence of the document.
- A quote proves presence in the document, not relevance to the criterion.
- Up to 200 characters per criterion of the deliverable are stored publicly on chain; the raw document is not.
- The contract cannot decide whether a DNS name resolves to a private address; node-level network policy must block that.
- The newer-SDK variant has been linted but never executed.

See `docs/AUDIT_REPORT.md` for the complete list.
