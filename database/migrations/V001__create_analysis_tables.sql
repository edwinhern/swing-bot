-- V001: Create core tables for stock analysis pipeline
-- This migration creates tables to store pipeline run history and individual stock analyses

-- Table: analysis_runs
-- Tracks each execution of the research pipeline
CREATE TABLE IF NOT EXISTS analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    
    -- Summary metrics
    total_stocks_scanned INT NOT NULL DEFAULT 0,
    stocks_passed_discovery INT NOT NULL DEFAULT 0,
    stocks_passed_technical INT NOT NULL DEFAULT 0,
    stocks_passed_quick_scan INT NOT NULL DEFAULT 0,
    stocks_fully_analyzed INT NOT NULL DEFAULT 0,
    
    -- Cost tracking
    estimated_cost_usd DECIMAL(10, 4) DEFAULT 0,
    
    -- Configuration used for this run
    config_json JSONB,
    
    -- Error tracking
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Table: stock_analyses  
-- Stores individual stock analysis results
CREATE TABLE IF NOT EXISTS stock_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(id) ON DELETE CASCADE,
    
    -- Stock identification
    ticker VARCHAR(10) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    sub_industry VARCHAR(255),
    
    -- Analysis timestamp
    analyzed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Technical data (from Polygon)
    current_price DECIMAL(10, 2),
    fifty_two_week_low DECIMAL(10, 2),
    fifty_two_week_high DECIMAL(10, 2),
    percent_from_low DECIMAL(6, 2),
    rsi DECIMAL(5, 2),
    sma_20 DECIMAL(10, 2),
    sma_50 DECIMAL(10, 2),
    technical_score INT CHECK (technical_score >= 0 AND technical_score <= 100),
    
    -- Sentiment data (from Perplexity)
    sentiment_score INT CHECK (sentiment_score >= 0 AND sentiment_score <= 100),
    fundamental_score INT CHECK (fundamental_score >= 0 AND fundamental_score <= 100),
    composite_score INT CHECK (composite_score >= 0 AND composite_score <= 100),
    
    -- Recommendation
    recommendation VARCHAR(20) CHECK (recommendation IN ('strong_buy', 'buy', 'hold', 'avoid')),
    confidence VARCHAR(10) CHECK (confidence IN ('high', 'medium', 'low')),
    target_price DECIMAL(10, 2),
    stop_loss DECIMAL(10, 2),
    timeline VARCHAR(20),
    
    -- Stage tracking (which stages this stock passed)
    passed_discovery_gate BOOLEAN DEFAULT FALSE,
    passed_technical_gate BOOLEAN DEFAULT FALSE,
    passed_quick_scan_gate BOOLEAN DEFAULT FALSE,
    completed_deep_research BOOLEAN DEFAULT FALSE,
    completed_final_scoring BOOLEAN DEFAULT FALSE,
    
    -- Full results as JSON (for detailed queries)
    technical_analysis_json JSONB,
    quick_scan_json JSONB,
    deep_research_json JSONB,
    recommendation_json JSONB,
    
    -- Catalysts and risks (arrays)
    key_catalysts TEXT[],
    risk_factors TEXT[],
    citations TEXT[],
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Table: watchlist
-- User-defined stocks to monitor
CREATE TABLE IF NOT EXISTS watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Alert settings
    alert_on_score_above INT CHECK (alert_on_score_above >= 0 AND alert_on_score_above <= 100),
    alert_on_recommendation VARCHAR(20)[],
    
    -- Last analysis reference
    last_analysis_id UUID REFERENCES stock_analyses(id),
    last_analyzed_at TIMESTAMP WITH TIME ZONE,
    
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_stock_analyses_ticker ON stock_analyses(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_run_id ON stock_analyses(run_id);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_recommendation ON stock_analyses(recommendation);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_composite_score ON stock_analyses(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_analyzed_at ON stock_analyses(analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_started_at ON analysis_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist(ticker);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE OR REPLACE TRIGGER update_analysis_runs_updated_at
    BEFORE UPDATE ON analysis_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_stock_analyses_updated_at
    BEFORE UPDATE ON stock_analyses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_watchlist_updated_at
    BEFORE UPDATE ON watchlist
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

