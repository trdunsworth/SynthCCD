SELECT * FROM './synth911gen3\output\RVA_incidents.parquet'

CREATE OR REPLACE VIEW RVA_incidents AS
SELECT * FROM './synth911gen3\output\RVA_incidents.parquet';

CREATE OR REPLACE VIEW RVA_volumes AS
SELECT * FROM './synth911gen3\output\RVA_hourly_call_counts.csv';

SELECT * FROM RVA_volumes;

