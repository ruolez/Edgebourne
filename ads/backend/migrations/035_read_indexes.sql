-- Audit 3 (2026-11-11), performance: the ad page, Compare and the Tests list read one ad's (or ad set's)
-- days and leads; ad_daily is keyed by (day, ad_id) and leads had no index on the ad, so each of those
-- scanned the whole table.
CREATE INDEX ad_daily_ad_idx ON ad_daily (ad_id, day);
CREATE INDEX ad_daily_adset_idx ON ad_daily (adset_id, day);
CREATE INDEX leads_ad_idx ON leads (ad_id, created_time DESC);
CREATE INDEX leads_adset_idx ON leads (adset_id);
