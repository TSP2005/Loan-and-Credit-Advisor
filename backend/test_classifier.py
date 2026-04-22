"""LLM classifier quick test — run from backend/ directory"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from orchestrator.intent_classifier import classify_and_extract

history_after_loan = [
    {'role': 'user', 'content': 'I need a 50000 loan for a wedding'},
    {'role': 'assistant', 'content': 'Personal Loan Assessment Rs.50000... Compliance & Eligibility... approval likelihood 90%'},
]

tests = [
    ('I need a 50000 loan for a wedding',      50000,    'personal_loan', 'loan_inquiry',    None),
    ('I want 50 lakhs home loan for 20 years', 5000000,  'home_loan',     'loan_inquiry',    None),
    ('give me 2 crore home loan',              20000000, 'home_loan',     'loan_inquiry',    None),
    ('why pmay wont be eligible for me',       None,     None,            'policy_question', history_after_loan),
    ('what is the MUDRA loan scheme',          None,     None,            'policy_question', None),
    ('Hi how are you',                         None,     None,            'general',         None),
    ('I need a 1.5 lakh personal loan',        150000,   'personal_loan', 'loan_inquiry',    None),
    ('loan for a car worth 8 lakhs',           800000,   'car_loan',      'loan_inquiry',    None),
    ('how to improve my credit score',         None,     None,            'policy_question', None),
]

print('=== LLM INTENT + EXTRACTION TEST ===')
passed = 0
for msg, exp_amt, exp_type, exp_intent, hist in tests:
    r = classify_and_extract(msg, hist)
    intent_ok = r['intent'] == exp_intent
    amt = r.get('loan_amount') or 0
    amt_ok = exp_amt is None or abs(amt - exp_amt) < 1
    type_ok = exp_type is None or r.get('loan_type') == exp_type
    ok = intent_ok and amt_ok and type_ok
    if ok:
        passed += 1
    status = 'OK  ' if ok else 'FAIL'
    failures = []
    if not intent_ok: failures.append('intent got=' + r['intent'] + ' want=' + exp_intent)
    if not amt_ok: failures.append('amt got=' + str(int(amt)) + ' want=' + str(exp_amt))
    if not type_ok: failures.append('type got=' + str(r.get('loan_type')) + ' want=' + str(exp_type))
    fail_str = ' | ' + ', '.join(failures) if failures else ''
    print('[' + status + '] ' + msg[:55] + fail_str)

print()
print('RESULT: ' + str(passed) + '/' + str(len(tests)) + ' passed')
