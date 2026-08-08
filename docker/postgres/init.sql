-- =====================================================
-- ENERGY FORECASTING PLATFORM DATABASE SCHEMA
-- =====================================================


-- =====================================================
-- Forecasting providers
-- =====================================================

CREATE TABLE IF NOT EXISTS providers (

    id SERIAL PRIMARY KEY,

    name VARCHAR(50) UNIQUE NOT NULL,

    description TEXT,

    created_at TIMESTAMPTZ DEFAULT now()

);


-- =====================================================
-- Renewable energy assets
-- =====================================================

CREATE TABLE IF NOT EXISTS assets (

    id SERIAL PRIMARY KEY,

    asset_name VARCHAR(100) UNIQUE NOT NULL,

    asset_type VARCHAR(50) DEFAULT 'wind_turbine',

    location VARCHAR(100),

    capacity_kw NUMERIC,

    created_at TIMESTAMPTZ DEFAULT now()

);



-- =====================================================
-- Historical SCADA measurements
-- InfluxDB -> PostgreSQL
-- Main forecasting dataset
-- =====================================================

CREATE TABLE IF NOT EXISTS wind_measurements (

    id BIGSERIAL PRIMARY KEY,

    turbine VARCHAR(50) NOT NULL,

    timestamp TIMESTAMPTZ NOT NULL,

    wind_speed NUMERIC NOT NULL,

    direction INTEGER,

    power NUMERIC NOT NULL,

    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE(turbine, timestamp)

);



CREATE INDEX IF NOT EXISTS idx_wind_timestamp
ON wind_measurements(timestamp);


CREATE INDEX IF NOT EXISTS idx_wind_turbine
ON wind_measurements(turbine);



-- =====================================================
-- Weather observations
-- Future ML features
-- =====================================================

CREATE TABLE IF NOT EXISTS weather_observations (

    id BIGSERIAL PRIMARY KEY,

    asset_id INTEGER
        REFERENCES assets(id)
        ON DELETE CASCADE,

    timestamp TIMESTAMPTZ NOT NULL,

    temperature NUMERIC,

    wind_speed NUMERIC,

    wind_direction NUMERIC,

    pressure NUMERIC,

    created_at TIMESTAMPTZ DEFAULT now()

);



CREATE INDEX IF NOT EXISTS idx_weather_timestamp
ON weather_observations(timestamp);



-- =====================================================
-- Forecast predictions
-- From providers or ML models
-- =====================================================

CREATE TABLE IF NOT EXISTS forecast_predictions (

    id BIGSERIAL PRIMARY KEY,


    provider_id INTEGER
        REFERENCES providers(id)
        ON DELETE CASCADE,


    asset_id INTEGER
        REFERENCES assets(id)
        ON DELETE CASCADE,


    forecast_time TIMESTAMPTZ NOT NULL,


    predicted_power_kw NUMERIC,


    created_at TIMESTAMPTZ DEFAULT now()

);



CREATE INDEX IF NOT EXISTS idx_forecast_time
ON forecast_predictions(forecast_time);



-- =====================================================
-- Forecast evaluation
-- Prediction vs actual
-- =====================================================

CREATE TABLE IF NOT EXISTS forecast_evaluations (

    id BIGSERIAL PRIMARY KEY,


    prediction_id INTEGER
        REFERENCES forecast_predictions(id)
        ON DELETE CASCADE,


    actual_power_kw NUMERIC,


    error_kw NUMERIC,


    absolute_error_kw NUMERIC,


    created_at TIMESTAMPTZ DEFAULT now()

);



-- =====================================================
-- Provider performance history
-- MAE/RMSE/Bias monitoring
-- =====================================================

CREATE TABLE IF NOT EXISTS evaluation_runs (

    id SERIAL PRIMARY KEY,


    run_time TIMESTAMPTZ DEFAULT now(),


    provider_id INTEGER
        REFERENCES providers(id)
        ON DELETE CASCADE,


    mae NUMERIC,


    rmse NUMERIC,


    bias NUMERIC,


    correlation NUMERIC,


    weight NUMERIC,


    sample_count INTEGER

);



CREATE INDEX IF NOT EXISTS idx_evaluation_provider
ON evaluation_runs(provider_id);



-- =====================================================
-- Grid curtailment events
-- =====================================================

CREATE TABLE IF NOT EXISTS curtailment_events (

    id SERIAL PRIMARY KEY,


    run_time TIMESTAMPTZ DEFAULT now(),


    asset_id INTEGER
        REFERENCES assets(id)
        ON DELETE CASCADE,


    total_potential_kwh NUMERIC,


    total_delivered_kwh NUMERIC,


    total_curtailed_kwh NUMERIC,


    pct_energy_lost NUMERIC,


    pct_time_curtailed NUMERIC,


    economic_loss_eur NUMERIC

);



-- =====================================================
-- Initial providers
-- =====================================================

INSERT INTO providers
(name, description)

VALUES

(
'provider_A',
'Synthetic high accuracy forecasting provider'
),

(
'provider_B',
'Synthetic provider with systematic negative bias'
),

(
'provider_C',
'Synthetic provider with high variance noise'
)

ON CONFLICT(name)
DO NOTHING;



-- =====================================================
-- Initial wind turbine
-- =====================================================

INSERT INTO assets
(
asset_name,
asset_type,
capacity_kw,
location
)

VALUES

(
't1',
'wind_turbine',
2000,
'Synthetic Wind Farm'
)

ON CONFLICT(asset_name)
DO NOTHING;