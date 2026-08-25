-- =====================================================================
-- POSTGRESQL NENA-COMPLIANT AUTOMATIC HIE TRIGGER SUITE
-- Table: incidents
-- Compliance: NENA-STA-020.2-2026, Section 7 (High Impact Events)
-- Description: Triggers and procedures to automatically detect, flag, 
--              and manage High Impact Event (HIE) exclusions in real-time.
-- =====================================================================

-- ---------------------------------------------------------------------
-- STEP 1: HIE Configuration Table
-- ---------------------------------------------------------------------
-- A centralized configuration table allows public safety administrators
-- to fine-tune spike thresholds and critical problem lists without 
-- ever redeploying database trigger source code.
CREATE TABLE IF NOT EXISTS hie_configuration (
    config_key VARCHAR(50) PRIMARY KEY,
    config_value VARCHAR(100) NOT NULL,
    description TEXT
);

-- Populate Default Auditing Thresholds
-- Default threshold is set to 45 calls in a rolling hour. Adjust this
-- to match your center's specific Busy Hour Call Volume (BHCV) baselines.
INSERT INTO hie_configuration (config_key, config_value, description) VALUES
('auto_flag_problem_types', 'Active Shooter,Terrorist Attack,Plane Crash,Hazmat Major,Mass Casualty', 'Comma-separated problem types that instantly trigger HIE classification'),
('volumetric_spike_threshold', '45', 'Number of 9-1-1 calls received in a rolling window to automatically flag as a High Impact Event'),
('volumetric_rolling_interval', '1 hour', 'SQL Interval duration for the rolling volume-spike detection window')
ON CONFLICT (config_key) DO UPDATE 
SET config_value = EXCLUDED.config_value;

-- ---------------------------------------------------------------------
-- STEP 2: PL/pgSQL Trigger Function
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_detect_and_flag_hie()
RETURNS TRIGGER AS $$
DECLARE
    v_auto_flag_problems TEXT;
    v_spike_threshold INT;
    v_rolling_interval INTERVAL;
    v_recent_call_count INT;
BEGIN
    -- 1. Load active configurations from hie_configuration table
    SELECT config_value::TEXT INTO v_auto_flag_problems 
    FROM hie_configuration WHERE config_key = 'auto_flag_problem_types';
    
    SELECT config_value::INT INTO v_spike_threshold 
    FROM hie_configuration WHERE config_key = 'volumetric_spike_threshold';
    
    SELECT config_value::INTERVAL INTO v_rolling_interval 
    FROM hie_configuration WHERE config_key = 'volumetric_rolling_interval';

    -- 2. CRITICAL LEVEL AUTO-FLAG (Rule 1: Immediate Threat Categories)
    -- If the incoming call matches any extremely high-acuity problem types, flag instantly.
    IF v_auto_flag_problems IS NOT NULL AND 
       string_to_array(LOWER(v_auto_flag_problems), ',') @> ARRAY[LOWER(TRIM(NEW.problem_nature))] THEN
        NEW.high_impact_event_flag := TRUE;
        NEW.hie_type := 'CRITICAL_INCIDENT_EXCLUSION';
        RETURN NEW;
    END IF;

    -- 3. VOLUMETRIC SPIKE AUTO-FLAG (Rule 2: Sudden rolling call volume anomaly)
    -- Query the database to find how many incidents have been logged in the immediate historical window.
    SELECT COUNT(*) INTO v_recent_call_count
    FROM incidents
    WHERE call_start_time >= NEW.call_start_time - v_rolling_interval
      AND call_start_time < NEW.call_start_time;

    -- If rolling call volume exceeds our target threshold, flag the new incoming record.
    IF v_recent_call_count >= v_spike_threshold THEN
        NEW.high_impact_event_flag := TRUE;
        NEW.hie_type := 'VOLUMETRIC_SPIKE_AUTO_DETECT';
    END IF;

    -- Return the updated row to write to storage
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- STEP 3: Create the Trigger on the Incidents Table
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_detect_hie ON incidents;

CREATE TRIGGER trg_detect_hie
    BEFORE INSERT ON incidents
    FOR EACH ROW
    EXECUTE FUNCTION fn_detect_and_flag_hie();

-- ---------------------------------------------------------------------
-- STEP 4: Supervisor Operational Overrides (NENA Compliance Rule)
-- ---------------------------------------------------------------------
-- NENA standard states routine spikes (daily traffic, concerts, tourism)
-- should NOT be excluded from SLAs. Since a volumetric trigger might 
-- flag a routine post-concert surge as an HIE, we provide a clean override 
-- query for agency supervisors to manually audit and clear routine surges.
CREATE OR REPLACE PROCEDURE pr_override_routine_volume_surges(
    p_start_time TIMESTAMP WITH TIME ZONE,
    p_end_time TIMESTAMP WITH TIME ZONE,
    p_reason VARCHAR(100) -- e.g., 'CONCERT_TRAFFIC', 'ROUTINE_SPIKE'
)
AS $$
BEGIN
    UPDATE incidents
    SET high_impact_event_flag = FALSE,
        hie_type = 'NONE'
    WHERE call_start_time BETWEEN p_start_time AND p_end_time
      AND hie_type = 'VOLUMETRIC_SPIKE_AUTO_DETECT';
      
    RAISE NOTICE 'Cleared automatic volumetric HIE flags for routine surge: %', p_reason;
END;
$$ LANGUAGE plpgsql;
