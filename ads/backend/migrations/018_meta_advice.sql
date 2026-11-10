-- Roadmap 5.3: Meta's recommendations can be applied from Today, and the Monday summary brings
-- back the benchmarks only the Mac's Ads MCP can read.
ALTER TABLE meta_changes DROP CONSTRAINT meta_changes_level_check;
ALTER TABLE meta_changes ADD CONSTRAINT meta_changes_level_check CHECK (level IN ('campaign', 'adset', 'ad', 'study', 'form', 'account'));
UPDATE desk_schedules SET prompt = prompt || E' Then read the benchmarks (ads_insights_industry_benchmark, ads_insights_performance_vs_peers, ads_insights_auction_ranking_benchmarks) and post the comparison with `desk benchmarks --file` (items: label, ours, peers, note), so Today shows it.'
WHERE name = 'Monday summary';
