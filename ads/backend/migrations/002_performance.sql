-- Ads mirror and daily results per ad, synced from Meta every hour.
CREATE TABLE ads (
    id TEXT PRIMARY KEY,                 -- Meta ad id
    name TEXT NOT NULL,
    campaign_id TEXT,
    adset_id TEXT,
    status TEXT,
    effective_status TEXT,
    thumbnail_url TEXT,
    review_feedback JSONB,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ad_daily (
    day DATE NOT NULL,                   -- in the ad account's time zone
    ad_id TEXT NOT NULL,
    campaign_id TEXT,
    adset_id TEXT,
    ad_name TEXT,
    spend_cents INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    reach INTEGER NOT NULL DEFAULT 0,
    link_clicks INTEGER NOT NULL DEFAULT 0,
    leads INTEGER NOT NULL DEFAULT 0,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, ad_id)
);
CREATE INDEX ad_daily_campaign_idx ON ad_daily (campaign_id, day);
