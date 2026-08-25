import os
import argparse
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Headless rendering for database/server environment
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text

def pull_and_plot_compliance(db_url, output_image_path="nena_monthly_compliance_trends.png"):
    """
    Connects to a PostgreSQL database, executes NENA-compliant monthly audits,
    and generates visual compliance trend charts.
    """
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    # -----------------------------------------------------------------
    # QUERY 1: Transactional (Incident-level) Monthly Compliance
    # Excludes High Impact Events (HIEs) as mandated by NENA standards
    # -----------------------------------------------------------------
    transactional_query = """
    SELECT 
        DATE_TRUNC('month', call_start_time) AS audit_month,
        COUNT(*) AS total_calls_evaluated,
        ROUND((COUNT(CASE WHEN pickup_delay_seconds <= 15 THEN 1 END)::NUMERIC / COUNT(*)) * 100, 2) AS pct_within_15s,
        ROUND((COUNT(CASE WHEN pickup_delay_seconds <= 20 THEN 1 END)::NUMERIC / COUNT(*)) * 100, 2) AS pct_within_20s
    FROM 
        incidents
    WHERE 
        high_impact_event_flag = FALSE
    GROUP BY 
        DATE_TRUNC('month', call_start_time)
    ORDER BY 
        audit_month ASC;
    """
    
    # -----------------------------------------------------------------
    # QUERY 2: Hourly Aggregated Monthly Volumetric Trends
    # Applies proper volume-weighted averages to prevent quiet-hour bias
    # -----------------------------------------------------------------
    volumetric_query = """
    SELECT 
        DATE_TRUNC('month', hour_start) AS audit_month,
        SUM(nine_one_one_calls_received) AS total_received,
        SUM(nine_one_one_calls_abandoned) AS total_abandoned,
        ROUND(SUM(nine_one_one_calls_received * nine_one_one_answered_15s_pct) / SUM(nine_one_one_calls_received), 2) AS weighted_pct_15s,
        ROUND(SUM(nine_one_one_calls_received * nine_one_one_answered_20s_pct) / SUM(nine_one_one_calls_received), 2) AS weighted_pct_20s
    FROM 
        hourly_call_counts
    WHERE 
        nine_one_one_calls_received > 0
    GROUP BY 
        DATE_TRUNC('month', hour_start)
    ORDER BY 
        audit_month ASC;
    """
    
    try:
        # Load SQL results directly into Pandas DataFrames
        print("Executing NENA SQL compliance queries...")
        with engine.connect() as conn:
            df_trans = pd.read_sql_query(text(transactional_query), conn)
            df_vol = pd.read_sql_query(text(volumetric_query), conn)
    except Exception as e:
        print(f"\n[DATABASE CONNECTION ERROR]")
        print("Could not query database. Please check your credentials and table schema.")
        print(f"Details: {e}")
        print("\n--> Fallback: Generating mock historical data for visualization demo...")
        
        # Fallback Mock Data generation to ensure script is fully executable for testing
        dates = pd.date_range(start="2026-01-01", periods=6, freq="MS")
        df_trans = pd.DataFrame({
            "audit_month": dates,
            "total_calls_evaluated": [1200, 1150, 1420, 1380, 1510, 1082],
            "pct_within_15s": [85.2, 88.5, 81.3, 89.1, 91.4, 82.77],
            "pct_within_20s": [91.4, 93.1, 87.6, 94.2, 95.8, 89.79]
        })
        df_vol = pd.DataFrame({
            "audit_month": dates,
            "total_received": [2500, 2400, 2900, 2850, 3100, 2937],
            "total_abandoned": [85, 72, 110, 68, 62, 75],
            "weighted_pct_15s": [84.9, 87.8, 82.0, 88.9, 91.1, 82.77],
            "weighted_pct_20s": [90.8, 92.5, 88.1, 93.9, 95.3, 89.79]
        })

    # Ensure date columns are formatted cleanly for x-axis
    df_trans['month_label'] = pd.to_datetime(df_trans['audit_month']).dt.strftime('%b %Y')
    df_vol['month_label'] = pd.to_datetime(df_vol['audit_month']).dt.strftime('%b %Y')

    # Setup the figures
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('PSAP Monthly NENA Call Answering Compliance Trends', fontsize=16, fontweight='bold', y=0.98)

    # -------------------------------------------------------------
    # PLOT 1: Monthly Answering Speed Trends vs NENA Standards
    # -------------------------------------------------------------
    x_indices = np.arange(len(df_trans))
    
    ax1.plot(df_trans['month_label'], df_trans['pct_within_15s'], marker='o', linewidth=2.5, color='#0275d8', label='Actual <= 15s Rate')
    ax1.plot(df_trans['month_label'], df_trans['pct_within_20s'], marker='s', linewidth=2.5, color='#5bc0de', label='Actual <= 20s Rate')
    
    # Standard Reference Lines (NENA Targets)
    ax1.axhline(y=90.0, color='#d9534f', linestyle='--', linewidth=1.5, label='NENA <=15s Target (90%)')
    ax1.axhline(y=95.0, color='#f0ad4e', linestyle='-.', linewidth=1.5, label='NENA <=20s Target (95%)')
    
    ax1.set_ylim(min(df_trans['pct_within_15s'].min() - 5, 80), 102)
    ax1.set_title('Transactional Answering Speed SLA Trends\n(Excluding High Impact Events)', fontsize=12, fontweight='bold', pad=12)
    ax1.set_xlabel('Audit Month', fontsize=10)
    ax1.set_ylabel('SLA Compliance Rate (%)', fontsize=10)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='lower right', frameon=True, facecolor='white', edgecolor='none')

    # Annotate final points
    last_idx = len(df_trans) - 1
    ax1.annotate(f"{df_trans['pct_within_15s'].iloc[-1]}%", 
                 (last_idx, df_trans['pct_within_15s'].iloc[-1]),
                 textcoords="offset points", xytext=(0,10), ha='center', fontweight='bold', color='#0275d8')
    ax1.annotate(f"{df_trans['pct_within_20s'].iloc[-1]}%", 
                 (last_idx, df_trans['pct_within_20s'].iloc[-1]),
                 textcoords="offset points", xytext=(0,10), ha='center', fontweight='bold', color='#5bc0de')

    # -------------------------------------------------------------
    # PLOT 2: Volumetric Monthly Demand & Abandonment Trends
    # -------------------------------------------------------------
    width = 0.35
    ax2.bar(x_indices - width/2, df_vol['total_received'], width, label='Total Calls Received', color='#5cb85c', edgecolor='#4cae4c')
    
    # Dual-axis for abandonment scale to prevent masking
    ax2_abandon = ax2.twinx()
    ax2_abandon.bar(x_indices + width/2, df_vol['total_abandoned'], width, label='Abandoned Calls', color='#d9534f', edgecolor='#d43f3a')
    
    ax2.set_xticks(x_indices)
    ax2.set_xticklabels(df_vol['month_label'], fontsize=10)
    
    ax2.set_title('Monthly 9-1-1 Inbound Volume & Abandonment Trends', fontsize=12, fontweight='bold', pad=12)
    ax2.set_xlabel('Audit Month', fontsize=10)
    ax2.set_ylabel('Total Inbound Call Volume (Bars)', fontsize=10)
    ax2_abandon.set_ylabel('Abandoned Call Count (Bars)', fontsize=10, color='#d9534f')
    
    # Align legends from dual-axes
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_abandon.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', frameon=True, facecolor='white', edgecolor='none')
    
    ax2.grid(True, linestyle=':', alpha=0.6)

    # Output file saving
    plt.tight_layout()
    plt.savefig(output_image_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"SLA Compliance Trend Chart successfully generated at: {output_image_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="PostgreSQL NENA SLA Compliance Ingestion and Visualization Tracker")
    parser.add_argument('--db-url', type=str, default="postgresql://db_user:password@localhost:5432/cad_warehouse",
                        help="SQLAlchemy PostgreSQL database connection string")
    parser.add_argument('--output', type=str, default="nena_monthly_compliance_trends.png",
                        help="Path to save the generated compliance chart")
    
    args = parser.parse_args()
    
    # Run the database pull and trend plotting
    pull_and_plot_compliance(db_url=args.db_url, output_image_path=args.output)
