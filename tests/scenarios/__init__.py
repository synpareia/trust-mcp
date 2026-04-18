"""Scenario tests — aim-level verification, not just function-level.

Each test class here corresponds 1:1 to a markdown user story in
`scenarios/trust-toolkit/*.md`. The markdown describes WHAT a user
wants and what "done" looks like; the test verifies that the product
actually delivers it.

Scenario tests differ from unit tests in three ways:

1. They exercise entire user journeys (multiple tool calls in order).
2. They assert on the *aim* (Bob can verify Alice's claim), not just
   the function return shape.
3. They use stubs — never internal mocks — for external services.

See `scenarios/README.md` for the format.
"""
