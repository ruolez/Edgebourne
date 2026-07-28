-- billing.recompute_totals() writes subtotal/tax/total onto the parent document
-- of whichever line table it was given. subscriptions was created in 004 with
-- only discount_cents, so a recurring template could not be costed and the
-- recurring list had no amount to show.
--
-- These are a snapshot of the CURRENT template, not of any generated invoice:
-- each generated invoice recomputes its own totals from its own copied lines,
-- so editing a retainer never rewrites history.

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS subtotal_cents BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tax_cents      BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_cents    BIGINT NOT NULL DEFAULT 0;
