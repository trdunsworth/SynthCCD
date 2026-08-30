import matplotlib

matplotlib.use('Agg')
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def create_charts():
    # Load the data
    incidents_path = '/workspace/knowledge/IndyMo_incidents.csv'
    hourly_path = '/workspace/knowledge/IndyMo_hourly_call_counts.csv'
    
    try:
        incidents_df = pd.read_csv(incidents_path)
        hourly_df = pd.read_csv(hourly_path)
    except FileNotFoundError as e:
        print(f"Error loading files. Ensure they are placed in /workspace/knowledge/. Details: {e}")
        return

    # Calculate weighted answering speed percentages for 9-1-1
    total_911_rec = hourly_df['nine_one_one_calls_received'].sum()
    if total_911_rec > 0:
        w_10s = (hourly_df['nine_one_one_answered_10s_pct'] * hourly_df['nine_one_one_calls_received']).sum() / total_911_rec
        w_15s = (hourly_df['nine_one_one_answered_15s_pct'] * hourly_df['nine_one_one_calls_received']).sum() / total_911_rec
        w_20s = (hourly_df['nine_one_one_answered_20s_pct'] * hourly_df['nine_one_one_calls_received']).sum() / total_911_rec
        w_40s = (hourly_df['nine_one_one_answered_40s_pct'] * hourly_df['nine_one_one_calls_received']).sum() / total_911_rec
    else:
        w_10s = w_15s = w_20s = w_40s = 0.0

    # Calculate Turnout and Travel Times by Agency
    agencies = ['LAW', 'FIRE', 'EMS']
    turnout_means = []
    travel_means = []
    for agency in agencies:
        agency_data = incidents_df[incidents_df['agency'] == agency]
        turnout_means.append(agency_data['turnout_seconds'].mean() if len(agency_data) > 0 else 0.0)
        travel_means.append(agency_data['travel_seconds'].mean() if len(agency_data) > 0 else 0.0)

    # Setup the figures
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('IndyMo Agency NENA Performance Audit Insights', fontsize=16, fontweight='bold', y=0.98)

    # -------------------------------------------------------------
    # PLOT 1: 9-1-1 Answering Speed Rate vs NENA Benchmarks
    # -------------------------------------------------------------
    thresholds = ['<= 10s', '<= 15s', '<= 20s', '<= 40s']
    rates = [w_10s, w_15s, w_20s, w_40s]
    bar_colors = ['#ced4da', '#d9534f', '#f0ad4e', '#5cb85c'] # Highlight standard ones in custom colors
    
    bars1 = ax1.bar(thresholds, rates, color=bar_colors, edgecolor='#495057', width=0.6)
    ax1.set_ylim(0, 110)
    ax1.set_title('9-1-1 Emergency Call Answering Speed\n(Weighted Compliance Rates)', fontsize=12, fontweight='bold', pad=12)
    ax1.set_xlabel('Call Answering Time Thresholds', fontsize=10)
    ax1.set_ylabel('Percentage of Calls Answered (%)', fontsize=10)
    ax1.grid(axis='y', linestyle='--', alpha=0.5)

    # Add values on top of bars
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Add NENA Standard Reference Lines
    ax1.axhline(y=90.0, color='#d9534f', linestyle=':', linewidth=1.5, label='NENA <=15s Target (90%)')
    ax1.axhline(y=95.0, color='#f0ad4e', linestyle='-.', linewidth=1.5, label='NENA <=20s Target (95%)')
    ax1.legend(loc='lower right', frameon=True, facecolor='white', edgecolor='none')

    # -------------------------------------------------------------
    # PLOT 2: Stacked Operational Dispatch Response Times
    # -------------------------------------------------------------
    bar_width = 0.5
    indices = np.arange(len(agencies))
    
    # Draw Turnout and Travel stacked
    ax2.bar(indices, turnout_means, bar_width, label='Turnout Time (Station to Roll)', color='#0275d8', edgecolor='#025aa5')
    ax2.bar(indices, travel_means, bar_width, bottom=turnout_means, label='Travel Time (Transit to Scene)', color='#5bc0de', edgecolor='#31b0d5')
    
    ax2.set_xticks(indices)
    ax2.set_xticklabels(agencies, fontsize=10, fontweight='bold')
    ax2.set_ylim(0, max(np.array(turnout_means) + np.array(travel_means)) * 1.15)
    ax2.set_title('Operational Response Times by Responder Discipline\n(Average Turnout & Travel Breakdown)', fontsize=12, fontweight='bold', pad=12)
    ax2.set_xlabel('Emergency Response Agency', fontsize=10)
    ax2.set_ylabel('Duration (Seconds)', fontsize=10)
    ax2.grid(axis='y', linestyle='--', alpha=0.5)
    ax2.legend(loc='upper left', frameon=True, facecolor='white', edgecolor='none')

    # Annotate bar segments with values
    for i in range(len(agencies)):
        t_val = turnout_means[i]
        tr_val = travel_means[i]
        total_val = t_val + tr_val
        
        # Turnout label
        ax2.text(i, t_val / 2.0, f"{t_val:.1f}s", ha='center', va='center', color='white', fontsize=9, fontweight='bold')
        # Travel label
        ax2.text(i, t_val + (tr_val / 2.0), f"{tr_val:.1f}s", ha='center', va='center', color='black', fontsize=9, fontweight='bold')
        # Total response time on top
        ax2.text(i, total_val + (total_val * 0.02), f"Total: {total_val:.1f}s", ha='center', va='bottom', fontsize=10, fontweight='bold')

    plt.tight_layout()
    os.makedirs('/workspace/scratch', exist_ok=True)
    fig_path = '/workspace/scratch/nena_performance_trends_matplotlib.png'
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close()
    print("Matplotlib Visualization successfully saved to scratch.")

if __name__ == '__main__':
    create_charts()
