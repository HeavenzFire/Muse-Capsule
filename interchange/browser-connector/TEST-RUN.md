# Validator test run — recorded output

Run 2026-10-22 in this staging tree (VM), commands exactly as shown.
`validate.py` is stdlib-only Python 3.

```
$ python3 validate.py request examples/example_request.json
PASS examples/example_request.json (request package): required fields, enums, and hard rules OK
exit=0

$ python3 validate.py result examples/example_result.json
PASS examples/example_result.json (result package): required fields, enums, and hard rules OK
exit=0

$ python3 validate.py request examples/bad_request.json
FAIL examples/bad_request.json (request package): 13 problem(s)
  - package: missing required field 'project_id'
  - package: missing required field 'conversation_reference'
  - package: missing required field 'target'
  - package: missing required field 'known_choices'
  - package: missing required field 'files_needed'
  - package: missing required field 'stop_conditions'
  - package: missing required field 'success_criteria'
  - package: missing required field 'authorization'
  - package: missing required field 'permissions'
  - package: missing required field 'timestamp'
  - field 'action_type': 'teleport_and_pay' is not one of ['read', 'sign_in', 'form', 'purchase_check', 'purchase', 'send']
  - hard rule: top-level credentials_in_packages must be false if present
  - hard rule: account_hint looks like it carries a credential (contains 'password'); identifiers only
exit=1
```

Also verified: all five JSON files in this folder (both schemas,
both examples, the bad example) parse as valid JSON.
