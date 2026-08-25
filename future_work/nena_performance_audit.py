import pandas as pd
import numpy as np
import warnings

# Suppress runtime warnings for cleaner terminal output
warnings.simplefilter(action='ignore', category=FutureWarning)

def run_audit():
    # Load data
    incidents_path = '/workspace/knowledge/IndyMo_incidents.csv'
    hourly_path = '/workspace/knowledge/IndyMo_hourly_call_counts.csv'
    
    try:
        incidents_df = pd.read_csv(incidents_path)
        hourly_df = pd.read_csv(hourly_path)
    except FileNotFoundError as e:
        print(f"Error loading files. Ensure they are placed in /workspace/knowledge/. Details: {e}")
        return
    
    # -------------------------------------------------------------
    # PART 1: Telephony System Compliance Audit
    # -------------------------------------------------------------
    total_911_rec = hourly_df['nine_one_one_calls_received'].sum()
    total_911_abd = hourly_df['nine_one_one_calls_abandoned'].sum()
    total_911_ans = total_911_rec - total_911_abd
    pct_911_abd = (total_911_abd / total_911_rec) * 100 if total_911_rec > 0 else 0
    
    total_non_emerg_rec = hourly_df['non_emergency_calls_received'].sum()
    total_non_emerg_abd = hourly_df['non_emergency_calls_abandoned'].sum()
    total_non_emerg_ans = total_non_emerg_rec - total_non_emerg_abd
    pct_non_emerg_abd = (total_non_emerg_abd / total_non_emerg_rec) * 100 if total_non_emerg_rec > 0 else 0
    
    # Weighted average for answering speed thresholds
    def get_weighted_pct(pct_col, rec_col):
        total_rec = hourly_df[rec_col].sum()
        if total_rec == 0:
            return 0.0
        weighted_sum = (hourly_df[pct_col] * hourly_df[rec_col]).sum()
        return weighted_sum / total_rec

    w_911_10s = get_weighted_pct('nine_one_one_answered_10s_pct', 'nine_one_one_calls_received')
    w_911_15s = get_weighted_pct('nine_one_one_answered_15s_pct', 'nine_one_one_calls_received')
    w_911_20s = get_weighted_pct('nine_one_one_answered_20s_pct', 'nine_one_one_calls_received')
    w_911_40s = get_weighted_pct('nine_one_one_answered_40s_pct', 'nine_one_one_calls_received')

    w_non_10s = get_weighted_pct('non_emergency_answered_10s_pct', 'non_emergency_calls_received')
    w_non_15s = get_weighted_pct('non_emergency_answered_15s_pct', 'non_emergency_calls_received')
    w_non_20s = get_weighted_pct('non_emergency_answered_20s_pct', 'non_emergency_calls_received')
    w_non_40s = get_weighted_pct('non_emergency_answered_40s_pct', 'non_emergency_calls_received')
    
    # Average Call Durations weighted by hourly answered calls
    hourly_ans_911 = hourly_df['nine_one_one_calls_received'] - hourly_df['nine_one_one_calls_abandoned']
    hourly_ans_non = hourly_df['non_emergency_calls_received'] - hourly_df['non_emergency_calls_abandoned']
    hourly_outbound = hourly_df['outbound_calls_placed']
    
    mean_911_dur = (hourly_df['nine_one_one_mean_duration'] * hourly_ans_911).sum() / hourly_ans_911.sum() if hourly_ans_911.sum() > 0 else 0
    mean_non_dur = (hourly_df['non_emergency_mean_duration'] * hourly_ans_non).sum() / hourly_ans_non.sum() if hourly_ans_non.sum() > 0 else 0
    mean_out_dur = (hourly_df['outbound_mean_duration'] * hourly_outbound).sum() / hourly_outbound.sum() if hourly_outbound.sum() > 0 else 0
    overall_mean_dur = (hourly_df['call_mean_duration'] * hourly_df['total_calls']).sum() / hourly_df['total_calls'].sum() if hourly_df['total_calls'].sum() > 0 else 0

    # -------------------------------------------------------------
    # PART 2: CAD Incident Performance Metrics
    # -------------------------------------------------------------
    total_incidents = len(incidents_df)
    
    # Agency Breakdown
    agency_counts = incidents_df['agency'].value_counts()
    agency_pcts = incidents_df['agency'].value_counts(normalize=True) * 100
    
    # Priority Breakdown
    priority_counts = incidents_df['priority'].value_counts().sort_index()
    priority_pcts = incidents_df['priority'].value_counts(normalize=True).sort_index() * 100
    
    # Pickup Delay (Answering speed on incident level)
    mean_pickup = incidents_df['pickup_delay_seconds'].mean()
    median_pickup = incidents_df['pickup_delay_seconds'].median()
    
    # Call Processing Compliance (interview_seconds)
    p1_calls = incidents_df[incidents_df['priority'] == 1]
    other_calls = incidents_df[incidents_df['priority'] > 1]
    
    p1_total = len(p1_calls)
    p1_compliant = len(p1_calls[p1_calls['interview_seconds'] <= 60])
    p1_compliance_pct = (p1_compliant / p1_total) * 100 if p1_total > 0 else 0
    
    other_total = len(other_calls)
    other_compliant = len(other_calls[other_calls['interview_seconds'] <= 90])
    other_compliance_pct = (other_compliant / other_total) * 100 if other_total > 0 else 0
    
    overall_compliant = p1_compliant + other_compliant
    overall_compliance_pct = (overall_compliant / total_incidents) * 100 if total_incidents > 0 else 0
    
    # Turnout and Travel Times (by Agency)
    turnout_by_agency = incidents_df.groupby('agency')['turnout_seconds'].agg(['mean', 'median'])
    travel_by_agency = incidents_df.groupby('agency')['travel_seconds'].agg(['mean', 'median'])
    
    incidents_df['response_time_seconds'] = incidents_df['turnout_seconds'] + incidents_df['travel_seconds']
    response_by_agency = incidents_df.groupby('agency')['response_time_seconds'].agg(['mean', 'median'])
    
    # Shift-level Analysis
    shift_pickup = incidents_df.groupby('shift')['pickup_delay_seconds'].mean()
    shift_interview = incidents_df.groupby('shift')['interview_seconds'].mean()
    
    # Shift Compliance (loop-based to avoid DataFrameGroupBy.apply Deprecation warnings)
    shift_compliance = {}
    shift_groups = incidents_df.groupby('shift')
    
    def get_shift_compliance_pct(group):
        p1 = group[group['priority'] == 1]
        other = group[group['priority'] > 1]
        comp_p1 = len(p1[p1['interview_seconds'] <= 60])
        comp_other = len(other[other['interview_seconds'] <= 90])
        total = len(group)
        return ((comp_p1 + comp_other) / total) * 100 if total > 0 else 0

    for name, group in shift_groups:
        shift_compliance[name] = get_shift_compliance_pct(group)
    
    # Disposition Breakdown
    disp_counts = incidents_df['call_disposition'].value_counts()
    disp_pcts = incidents_df['call_disposition'].value_counts(normalize=True) * 100

    # -------------------------------------------------------------
    # PRINT PERFORMANCE SUMMARY REPORT
    # -------------------------------------------------------------
    print("================================================================================")
    print("               NENA 9-1-1 PERFORMANCE AUDIT SUMMARY REPORT")
    print("================================================================================")
    print(f"Data Sources: IndyMo_hourly_call_counts.csv | IndyMo_incidents.csv")
    print("================================================================================")
    print("\n--- SECTION 1: TELEPHONY SYSTEM COMPLIANCE AUDIT ---")
    print(f"Total 9-1-1 Emergency Calls Received:  {total_911_rec:,}")
    print(f"Total 9-1-1 Emergency Calls Answered:  {total_911_ans:,}")
    print(f"Total 9-1-1 Emergency Calls Abandoned: {total_911_abd:,} ({pct_911_abd:.2f}% abandonment rate)")
    print("\n9-1-1 Call Answering Speed (Weighted Averages):")
    print(f"  - Answered within <= 10 seconds: {w_911_10s:.2f}%")
    print(f"  - Answered within <= 15 seconds: {w_911_15s:.2f}%  <-- NENA Standard: >= 90%")
    print(f"  - Answered within <= 20 seconds: {w_911_20s:.2f}%  <-- NENA Standard: >= 95%")
    print(f"  - Answered within <= 40 seconds: {w_911_40s:.2f}%")
    
    meets_15s = "PASS" if w_911_15s >= 90 else "FAIL"
    meets_20s = "PASS" if w_911_20s >= 95 else "FAIL"
    print(f"\n9-1-1 ANSWERING COMPLIANCE STATUS:")
    print(f"  - NENA 15-second Standard (90%): {meets_15s} (Actual: {w_911_15s:.2f}%)")
    print(f"  - NENA 20-second Standard (95%): {meets_20s} (Actual: {w_911_20s:.2f}%)")
    
    print(f"\nTotal Non-Emergency Calls Received:   {total_non_emerg_rec:,}")
    print(f"Total Non-Emergency Calls Answered:   {total_non_emerg_ans:,}")
    print(f"Total Non-Emergency Calls Abandoned:  {total_non_emerg_abd:,} ({pct_non_emerg_abd:.2f}% abandonment rate)")
    print("\nNon-Emergency Answering Speed (Weighted Averages):")
    print(f"  - Answered within <= 10 seconds: {w_non_10s:.2f}%")
    print(f"  - Answered within <= 15 seconds: {w_non_15s:.2f}%")
    print(f"  - Answered within <= 20 seconds: {w_non_20s:.2f}%")
    print(f"  - Answered within <= 40 seconds: {w_non_40s:.2f}%")
    
    print("\nAverage Call Handling Durations (Mean Seconds):")
    print(f"  - 9-1-1 Emergency Calls: {mean_911_dur:.2f} seconds ({(mean_911_dur/60):.2f} minutes)")
    print(f"  - Non-Emergency Calls:   {mean_non_dur:.2f} seconds ({(mean_non_dur/60):.2f} minutes)")
    print(f"  - Outbound Placed Calls: {mean_out_dur:.2f} seconds ({(mean_out_dur/60):.2f} minutes)")
    print(f"  - Overall Call Average:  {overall_mean_dur:.2f} seconds ({(overall_mean_dur/60):.2f} minutes)")
    
    print("\n================================================================================")
    print("--- SECTION 2: COMPUTER-AIDED DISPATCH (CAD) PERFORMANCE AUDIT ---")
    print(f"Total CAD Incidents Evaluated: {total_incidents:,}")
    
    print("\nAgency Workload Distribution:")
    for agency, count in agency_counts.items():
        print(f"  - {agency:<4} : {count:>4} incidents ({agency_pcts[agency]:.2f}%)")
        
    print("\nPriority Code Distribution:")
    for prio, count in priority_counts.items():
        desc = "Imminent Life Threat" if prio == 1 else "Standard Emergency" if prio <= 3 else "Lower Acuity"
        print(f"  - Priority {prio} ({desc:<20}) : {count:>4} incidents ({priority_pcts[prio]:.2f}%)")

    print("\nIncident Answering Speed (Pickup Delay):")
    print(f"  - Mean Delay:   {mean_pickup:.2f} seconds")
    print(f"  - Median Delay: {median_pickup:.2f} seconds")

    print("\nNENA Call Processing / Interview Seconds Compliance:")
    print(f"  - Priority 1 (Standard: <= 60s) : {p1_compliant:>4} / {p1_total:>4} compliant ({p1_compliance_pct:.2f}%)")
    print(f"  - Priority 2-5 (Standard: <= 90s): {other_compliant:>4} / {other_total:>4} compliant ({other_compliance_pct:.2f}%)")
    print(f"  - OVERALL PROCESSING COMPLIANCE : {overall_compliant:>4} / {total_incidents:>4} compliant ({overall_compliance_pct:.2f}%)")

    print("\nOperational Response Times by Agency (Mean / Median in Seconds):")
    print(f"  {'Agency':<5} | {'Turnout (Wheels)':<18} | {'Travel (Transit)':<18} | {'Total Response':<18}")
    print("-" * 75)
    for agency in ['LAW', 'FIRE', 'EMS']:
        turn_mean = turnout_by_agency.loc[agency, 'mean']
        turn_med = turnout_by_agency.loc[agency, 'median']
        trav_mean = travel_by_agency.loc[agency, 'mean']
        trav_med = travel_by_agency.loc[agency, 'median']
        resp_mean = response_by_agency.loc[agency, 'mean']
        resp_med = response_by_agency.loc[agency, 'median']
        print(f"  {agency:<5} | {turn_mean:>6.1f}s / {turn_med:>5.1f}s     | {trav_mean:>6.1f}s / {trav_med:>5.1f}s     | {resp_mean:>6.1f}s / {resp_med:>5.1f}s")

    print("\n================================================================================")
    print("--- SECTION 3: SHIFT AND OPERATOR ANALYSIS ---")
    print(f"  {'Shift':<5} | {'Mean Pickup Delay':<18} | {'Mean Interview Sec':<18} | {'Processing Compliance':<20}")
    print("-" * 75)
    for s in sorted(incidents_df['shift'].unique()):
        p_delay = shift_pickup.loc[s]
        i_sec = shift_interview.loc[s]
        comp = shift_compliance[s]
        label = incidents_df[incidents_df['shift'] == s]['shift_label'].iloc[0]
        print(f"  {s:<5} ({label:<5}) | {p_delay:>16.2f}s | {i_sec:>16.2f}s | {comp:>18.2f}%")

    print("\nIncident Disposition Code Breakdown:")
    for disp, count in disp_counts.items():
        print(f"  - {disp:<25} : {count:>4} incidents ({disp_pcts[disp]:.2f}%)")
    print("================================================================================")

if __name__ == '__main__':
    run_audit()
