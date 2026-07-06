"""Scenario 09: Erase a counterparty from the local journal (GDPR Art. 17).

See scenarios/trust-toolkit/09-erase-counterparty.md.

Tier-1 local-only flow: remember -> evaluate -> recall-to-confirm ->
forget -> verify-gone. Asserts the honest-scope confirmation and the
fail-closed behaviour on a corrupt journal (both landed in the 0.7.0
publish-gate response).
"""

from __future__ import annotations

from synpareia_trust_mcp.tools.recall import (
    add_evaluation,
    find_evaluations,
    forget_counterparty,
    recall_counterparty,
    remember_counterparty,
)


class TestEraseCounterpartyFlow:
    def test_full_erasure_flow(self, app_ctx) -> None:
        ctx, _ = app_ctx
        # 1. remember + evaluate
        rec = remember_counterparty(
            namespace="slack", namespace_id="U-erase", display_name="subject", ctx=ctx
        )
        add_evaluation(
            identifier=rec["identifier"], text="left mid-deal", tags=["ghosted"], ctx=ctx
        )
        # 2. confirm it exists
        assert (
            recall_counterparty(identifier_or_name=rec["identifier"], ctx=ctx)["match_count"] == 1
        )
        # 3. erase
        result = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        # 4. honest confirmation
        assert result["forgotten"] is True
        assert result["evaluations_erased"] == 1
        assert result["scope"] == "local_journal_only"
        assert "NOT erased" in result["message"]
        # 5. verify gone
        assert (
            recall_counterparty(identifier_or_name=rec["identifier"], ctx=ctx)["match_count"] == 0
        )
        assert find_evaluations(tag="ghosted", ctx=ctx)["match_count"] == 0

    def test_idempotent_second_erase(self, app_ctx) -> None:
        ctx, _ = app_ctx
        rec = remember_counterparty(
            namespace="slack", namespace_id="U-idem", display_name="x", ctx=ctx
        )
        assert forget_counterparty(identifier=rec["identifier"], ctx=ctx)["forgotten"] is True
        second = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        assert second["ok"] is True
        assert second["forgotten"] is False

    def test_erasure_does_not_touch_other_counterparties(self, app_ctx) -> None:
        ctx, _ = app_ctx
        keep = remember_counterparty(
            namespace="slack", namespace_id="K", display_name="keeper", ctx=ctx
        )
        add_evaluation(identifier=keep["identifier"], text="solid", tags=["reliable"], ctx=ctx)
        drop = remember_counterparty(
            namespace="slack", namespace_id="D", display_name="dropme", ctx=ctx
        )
        forget_counterparty(identifier=drop["identifier"], ctx=ctx)
        assert (
            recall_counterparty(identifier_or_name=keep["identifier"], ctx=ctx)["match_count"] == 1
        )
        assert find_evaluations(tag="reliable", ctx=ctx)["match_count"] == 1

    def test_save_failure_fails_closed(self, app_ctx, monkeypatch) -> None:
        # A write-path OSError (disk full / permissions) returns the structured
        # idempotent-no-error failure rather than raising out of the tool.
        ctx, app = app_ctx

        def boom(identifier):
            raise OSError("read-only file system")

        monkeypatch.setattr(app.journal_store, "delete", boom)
        result = forget_counterparty(identifier="local:anything", ctx=ctx)
        assert result["ok"] is False
        assert result["forgotten"] is False
        assert "error" in result
