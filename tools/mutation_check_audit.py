"""Second mutation round (audit): state machine, receipt identity and the audit fixes.

Run from the repository root (mutants live in a temporary directory; the real contract is never
modified):
    python tools/mutation_check_audit.py
"""
import os
import subprocess
import tempfile

SRC = "contracts/workproof.py"
# Mutants live in a temporary directory (the file stem must stay "workproof"); the real
# contract is never modified.
MUTANT = os.path.join(tempfile.mkdtemp(prefix="workproof_mut_"), "workproof.py")
orig = open(SRC, encoding="utf-8").read()


def sub(old, new):
    assert orig.count(old) == 1, (orig.count(old), old[:70])
    return orig.replace(old, new)


M = {
 "N01 client may accept its own job": sub('        if sender == job.client:\n            _fail(ERR_EXPECTED, "client cannot accept its own job")\n', ''),
 "N02 replay: evaluated receipt can be evaluated again": sub('        if receipt.status != RCPT_PENDING:\n            _fail(ERR_EXPECTED, "receipt is not pending evaluation")\n', ''),
 "N03 evaluate ignores job state": sub('        if job.status != JOB_IN_PROGRESS:\n            _fail(ERR_EXPECTED, "job is not in progress")\n', ''),
 "N04 anyone can submit a delivery": sub('        if sender != job.worker:\n            _fail(ERR_EXPECTED, "only the assigned worker can submit a delivery")\n', ''),
 "N05 delivery limit not enforced": sub('        if int(job.delivery_count) >= MAX_DELIVERIES:\n            _fail(ERR_EXPECTED, "delivery limit reached")\n', ''),
 "N06 previous pending receipt not superseded": sub('                previous.status = RCPT_SUPERSEDED\n', '                pass\n'),
 "N07 receipt id reused across jobs (delivery-index based)": sub('        receipt_id = "rcpt-" + str(number)\n', '        receipt_id = "rcpt-" + str(int(job.delivery_count) + 1)\n'),
 "N08 any stranger may request an evaluation": sub('        if sender != job.client and sender != job.worker:\n            _fail(ERR_EXPECTED, "only the client or the worker can request an evaluation")\n', ''),
 "N09 job always ends VERIFIED": sub('        job.status = verdict["overall_status"]\n', '        job.status = JOB_VERIFIED\n'),
 "N10 receipt not bound to latest delivery": sub('''        if (
            delivery_index < 1
            or delivery_index > len(job.receipt_ids)
            or job.receipt_ids[delivery_index - 1] != receipt_id
        ):
            _fail(ERR_EXPECTED, "receipt does not match the job delivery index")
''', ''),
 "N11 F1 reverted: 1-char quotes accepted": sub('MIN_EXCERPT_LEN = 8\n', 'MIN_EXCERPT_LEN = 1\n'),
 "N12 F2 reverted: any port accepted": sub('    if port is not None and port != 443:\n', '    if False:\n'),
 "N13 F2 reverted: TLD shape not checked": sub('    if not tld_ok:\n', '    if False:\n'),
 "N14 F2 reverted: reserved TLDs allowed": sub('    if tld in RESERVED_TLDS:\n', '    if False:\n'),
 "N15 F3 reverted: receipt/job agreement not compared": sub('        if str(receipt.agreement_hash) != str(job.agreement_hash):\n', '        if False:\n'),
 "N18 receipt worker not compared with job worker": sub('        if receipt.worker != job.worker:\n            _fail(ERR_EXPECTED, "receipt worker does not match the job worker")\n', ''),
 "N16 terms hash not committed at creation": sub('        job.terms_hash = _terms_hash(clean_title, clean_description, clean_criteria)\n', '        job.terms_hash = ""\n'),
 "N17 evaluated receipt leaves worker unset on job accept": sub('        job.worker = sender\n', '        pass\n'),
}
survivors = []
for name, src in M.items():
    open(MUTANT, "w", encoding="utf-8").write(src)
    r = subprocess.run(["pytest", "tests/direct/test_workproof_functional.py", "tests/direct/test_workproof_equivalence.py",
                        "tests/direct/test_workproof_audit.py", "-q", "-x", "-p", "no:cacheprovider"], capture_output=True, text=True, env={**os.environ, "WORKPROOF_CONTRACT": MUTANT})
    f = [l for l in r.stdout.splitlines() if l.startswith("FAILED")][:1]
    killed = r.returncode != 0
    print(("KILLED  " if killed else "SURVIVED"), name, "->", (f[0].split("::", 1)[1][:90] if f else ""))
    if not killed:
        survivors.append(name)
print("\nsurvivors:", survivors)
