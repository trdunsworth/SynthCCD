import os

import pandas as pd
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, sessionmaker

# Initialize declarative base
Base = declarative_base()

class CADIncident(Base):
    """
    SQLAlchemy Model for CAD Incident Records.
    Captures raw dispatch logs along with advanced NENA Audit and NG9-1-1 compliance columns.
    Conforms to NENA-STA-020.2-2026 and NENA-STA-019.2-2022 standards.
    """
    __tablename__ = 'incidents'
    
    # Core Identifiers
    id_number = Column(UUID(as_uuid=True), primary_key=True, comment="Seeded GUID/UUID v4 unique incident identifier")
    internal_reference_number = Column(String(50), unique=True, nullable=False, comment="Unique agency reference tracking ID (e.g. LAW-260-00001)")
    agency = Column(String(10), nullable=False, comment="Emergency discipline: LAW, FIRE, or EMS")
    shift = Column(String(5), nullable=False, comment="Operational shift code on duty (A, B, C, D)")
    shift_label = Column(String(10), nullable=False, comment="Shift period label (DAY, NIGHT)")
    shift_group = Column(Integer, nullable=False, comment="Crew rotation group index")
    
    # Event Typology & Severity
    problem_nature = Column(String(100), nullable=False, comment="Standardized CAD nature code or problem classification")
    priority = Column(Integer, nullable=False, comment="Priority level code (1 to 5; 1 is highest acuity)")
    
    # Geographic Location Columns (derived from OpenStreetMap Overpass geocoding)
    prefix_directional = Column(String(10), nullable=True, comment="Street directional prefix (e.g., N, S, E, W)")
    street_number = Column(String(20), nullable=True, comment="Housenumber or structure number")
    street_name = Column(String(100), nullable=True, comment="Road or street name")
    street_type = Column(String(20), nullable=True, comment="Street type suffix (e.g., Ave, St, Blvd)")
    postfix_directional = Column(String(10), nullable=True, comment="Street directional suffix (e.g., NW, SE)")
    street_address = Column(String(255), nullable=True, comment="Seeded street address combining all parsed components")
    city = Column(String(100), nullable=True, comment="Municipality jurisdiction")
    state = Column(String(50), nullable=True, comment="State or province boundary")
    postal_code = Column(String(20), nullable=True, comment="Geocoded postal code (normalized 5-digit ZIP for US)")
    latitude = Column(Numeric(9, 6), nullable=True, comment="OSM coordinate node latitude; 0.0 when geocoding fails")
    longitude = Column(Numeric(9, 6), nullable=True, comment="OSM coordinate node longitude; 0.0 when geocoding fails")
    zone = Column(String(20), nullable=True, comment="Spatial density zone classification: URBAN, SUBURBAN, or RURAL")
    location = Column(String(255), nullable=True, comment="Fully formatted street address, city, and state string")
    
    # NENA Call Processing Lifecycle Timestamps (Timeline Map Points)
    call_start_time = Column(DateTime(timezone=True), nullable=False, comment="T1/T2: The instant the emergency call initiates or enters the network")
    incident_start_time = Column(DateTime(timezone=True), nullable=False, comment="Timestamp when the CAD incident record is opened (usually 0-3s after call start)")
    time_phone_pickup = Column(DateTime(timezone=True), nullable=False, comment="T4: Timestamp when the calltaker answers and two-way voice path begins")
    time_call_enters_queue = Column(DateTime(timezone=True), nullable=True, comment="T5: Timestamp when essential dispatcher interrogation and verification completes")
    time_first_unit_assigned = Column(DateTime(timezone=True), nullable=True, comment="T6: Timestamp when the dispatcher notifies or assigns the first response unit")
    time_unit_enroute = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when the assigned responder unit begins moving (wheels rolling)")
    time_unit_arrived = Column(DateTime(timezone=True), nullable=True, comment="T7: Timestamp when the first responder unit arrives on scene")
    time_last_unit_cleared = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when the last responder unit clears the scene")
    time_call_closed = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when the incident record is formally closed in CAD")
    time_phone_disconnect = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when the telephony session ends / caller disconnects")
    
    # Personnel Operational Workload Columns
    calltaker = Column(String(100), nullable=True, comment="Full name of calltaker handling primary interrogation")
    dispatcher = Column(String(100), nullable=True, comment="Full name of dispatcher assigning response units")
    method_of_call_reception = Column(String(50), nullable=True, comment="Line mechanism of arrival (E-911, Phone, OFFICER, Radio, Text)")
    call_disposition = Column(String(100), nullable=True, comment="Standard resolution disposition code (e.g., NR-No Report)")
    
    # High Impact Event Exclusions (NENA-STA-020.2-2026, Section 7)
    high_impact_event_flag = Column(Boolean, nullable=False, default=False, comment="Isolate from routine compliance SLA metrics if weather, disaster, or active violence surge")
    hie_type = Column(String(50), nullable=False, default='NONE', comment="Classification of event exclusion (e.g. SEVERE_WEATHER, ACTIVE_SHOOTER, NONE)")
    
    # Special Call Handling Metadata (NENA-STA-020.2-2026, Section 5.4)
    call_handling_type = Column(String(30), nullable=False, default='STANDARD', comment="Handling category for auditing dispatcher interrogation compliance")
    
    # Programmatic Durations (Explicit Seconds Columns)
    pickup_delay_seconds = Column(Numeric(6, 2), nullable=False, comment="Answering ring delay (T3 to T4)")
    pre_cad_offset_seconds = Column(Numeric(6, 2), nullable=False, comment="Ringing delay before CAD system creation")
    interview_seconds = Column(Numeric(6, 1), nullable=False, comment="Active caller interrogation and location verification duration (T4 to T5)")
    dispatch_queue_seconds = Column(Numeric(6, 1), nullable=True, comment="Dispatch queue queue delay (T5 to T6)")
    turnout_seconds = Column(Numeric(6, 1), nullable=True, comment="Wheels rolling response delay (T6 to Enroute)")
    travel_seconds = Column(Numeric(6, 1), nullable=True, comment="Transit/road travel delay (Enroute to Scene)")
    on_scene_seconds = Column(Numeric(6, 1), nullable=True, comment="Active on scene responder duration (Scene to Clear)")
    closeout_seconds = Column(Numeric(6, 1), nullable=True, comment="Wrap up administration delay (Clear to Close)")
    phone_duration_seconds = Column(Numeric(6, 1), nullable=False, comment="Total active voice session duration")
    total_elapsed_seconds = Column(Numeric(8, 1), nullable=False, comment="Overall lifecycle elapsed duration (Call Start to CAD Close)")
    
    # NextGen Core Services (NGCS) SIP Signaling & Route Telemetry (NENA-STA-019.2-2022, Sec. 3.3)
    esinet_transit_seconds = Column(Numeric(6, 3), nullable=True, comment="Latency of call transit within the ESInet (Ingress to Egress)")
    sip_ssrd_seconds = Column(Numeric(6, 3), nullable=True, comment="Successful Session Request Delay (INVITE to Ringing)")
    sip_sdd_seconds = Column(Numeric(6, 3), nullable=True, comment="Session Disconnect Delay (BYE to ACK)")
    lost_query_delay_seconds = Column(Numeric(6, 3), nullable=True, comment="Location routing translation query resolution latency")
    hold_time_seconds = Column(Numeric(6, 1), default=0.0, comment="Aggregated duration caller spent placed on hold")
    call_queued_delay_seconds = Column(Numeric(6, 1), default=0.0, comment="Duration call sat in ESRP/ACD automatic call distributor queues")
    
    # Call Transfer Metrics (NENA-STA-020.2-2026, Section 5.3)
    transferred_to_agency = Column(String(100), nullable=True, comment="Name of neighboring PSAP/ECC receiving the transferred call")
    transfer_delay_seconds = Column(Numeric(6, 2), nullable=True, comment="Interval between call transfer initialization and partner pickup")
    
    # Media and Connection Quality Telemetry (NENA-STA-019.2-2022, Section 3.3.21)
    media_jitter_ms = Column(Numeric(6, 2), nullable=True, comment="Average connection jitter reported in SIP RTCP BYE packet")
    media_packet_loss_pct = Column(Numeric(5, 2), nullable=True, comment="Connection packet loss percentage")
    mos_score = Column(Numeric(3, 2), nullable=True, comment="Voice path Mean Opinion Score (1.00 to 5.00)")

    __table_args__ = (
        CheckConstraint(agency.in_(['LAW', 'FIRE', 'EMS']), name='chk_incident_agency'),
        CheckConstraint(priority.between(1, 5), name='chk_incident_priority'),
        CheckConstraint(call_handling_type.in_(['STANDARD', 'ABANDONED', 'PREMATURE_DISCONNECT', 'SILENT_VOICE', 'NON_RESPONSIVE']), name='chk_call_handling_type'),
        CheckConstraint(mos_score.between(1.0, 5.0), name='chk_mos_score'),
        Index('idx_nena_call_start', call_start_time),
        Index('idx_nena_hie_filter', high_impact_event_flag, hie_type),
        Index('idx_nena_prio_agency', agency, priority),
        Index('idx_nena_call_handling', call_handling_type),
    )


class HourlyPhoneMetric(Base):
    """
    SQLAlchemy Model for Hourly Telephony System Call Counts.
    Captures aggregated phone center statistics matching Page 2 and 4 compliance targets.
    """
    __tablename__ = 'hourly_call_counts'
    
    hour_start = Column(DateTime(timezone=True), primary_key=True, comment="UTC timestamp representing starting hour boundary")
    hour_of_day = Column(Integer, nullable=False, comment="Local diurnal hour marker (0 to 23)")
    
    # Telephony Answering Volumes
    nine_one_one_calls_received = Column(Integer, nullable=False, comment="Total emergency 9-1-1 calls presented to PSAP equipment")
    nine_one_one_calls_abandoned = Column(Integer, nullable=False, comment="Total emergency calls where caller disconnected prior to answer")
    non_emergency_calls_received = Column(Integer, nullable=False, comment="Total secondary non-emergency calls presented")
    non_emergency_calls_abandoned = Column(Integer, nullable=False, comment="Total non-emergency calls abandoned")
    outbound_calls_placed = Column(Integer, nullable=False, comment="Total outbound lines dialed by dispatchers/supervisors")
    
    # Answering Compliance percentages (SLA buckets)
    nine_one_one_answered_10s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of emergency calls answered within <= 10s")
    nine_one_one_answered_15s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of emergency calls answered within <= 15s (NENA 90% target)")
    nine_one_one_answered_20s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of emergency calls answered within <= 20s (NENA 95% target)")
    nine_one_one_answered_40s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of emergency calls answered within <= 40s")
    
    non_emergency_answered_10s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of non-emergency calls answered within <= 10s")
    non_emergency_answered_15s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of non-emergency calls answered within <= 15s")
    non_emergency_answered_20s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of non-emergency calls answered within <= 20s")
    non_emergency_answered_40s_pct = Column(Numeric(5, 1), nullable=False, comment="Percentage of non-emergency calls answered within <= 40s")
    
    # Session Handle Time Means (Seconds)
    nine_one_one_mean_duration = Column(Numeric(6, 1), nullable=False, comment="Mean session handle time for answered emergency calls")
    non_emergency_mean_duration = Column(Numeric(6, 1), nullable=False, comment="Mean session handle time for answered non-emergency calls")
    outbound_mean_duration = Column(Numeric(6, 1), nullable=False, comment="Mean session handle time for outbound placed calls")
    call_mean_duration = Column(Numeric(6, 1), nullable=False, comment="Volume-weighted average duration across all dialed calls")
    
    # Summary Volume Metrics
    total_emergency_calls = Column(Integer, nullable=False, comment="Aggregated emergency line calls received")
    total_nonemergency_calls = Column(Integer, nullable=False, comment="Aggregated non-emergency calls received")
    total_calls = Column(Integer, nullable=False, comment="Consolidated phone call center workload volume")

    __table_args__ = (
        CheckConstraint(hour_of_day.between(0, 23), name='chk_hour_of_day'),
        Index('idx_nena_hourly_volume', hour_start),
    )


# =====================================================================
# PROGRAMMATIC DDL UTILITY
# =====================================================================
def print_postgresql_ddl():
    """Prints PostgreSQL-specific DDL syntax based on the SQLAlchemy models."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    
    # Empty mock engine to compile PostgreSQL syntax
    create_engine('postgresql://')
    
    print("-- =====================================================================")
    print("-- POSTGRESQL NENA PERFORMANCE AUDIT COMPLIANT DDL SCHEMA")
    print("-- Generated via SQLAlchemy Declarative base Models")
    print("-- =====================================================================\n")
    
    for table_model in [CADIncident, HourlyPhoneMetric]:
        create_stmt = CreateTable(table_model.__table__).compile(dialect=postgresql.dialect())
        print(f"{str(create_stmt).strip()};\n")


# =====================================================================
# INGESTION PIPELINE TEMPLATE (PANDAS TO SQLALCHEMY)
# =====================================================================
def import_csv_to_postgres(db_url, incidents_csv_path, hourly_csv_path):
    """
    Ingests synthetic datasets (e.g. SynthCCD outputs) into our PostgreSQL database.
    Performs data alignment, timezone coercion, and bulk inserts.
    """
    print(f"Connecting to database: {db_url}...")
    engine = create_engine(db_url)
    
    # Ensure tables are created (and indexes automatically built)
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # 1. Ingest Incidents Dataset
    if os.path.exists(incidents_csv_path):
        print(f"Loading incidents CSV: {incidents_csv_path}...")
        df_inc = pd.read_csv(incidents_csv_path)
        
        # Parse datetime columns to timestamp with timezone
        datetime_cols = [
            'call_start_time', 'incident_start_time', 'time_phone_pickup', 
            'time_call_enters_queue', 'time_first_unit_assigned', 'time_unit_enroute', 
            'time_unit_arrived', 'time_last_unit_cleared', 'time_call_closed', 
            'time_phone_disconnect'
        ]
        for col in datetime_cols:
            if col in df_inc.columns:
                df_inc[col] = pd.to_datetime(df_inc[col]).dt.tz_localize('UTC') # Coerce to tz-aware UTC
                
        # Fill missing timezone dates with None (represented as SQL NULL)
        df_inc = df_inc.replace({pd.NaT: None})
        
        # Map DataFrame columns to ORM records
        records_to_insert = []
        for _, row in df_inc.iterrows():
            # Derive special handling type (audits TTY interrogation on non-responsive calls)
            handling_type = 'STANDARD'
            dispo = str(row.get('call_disposition', '')).upper()
            if 'ABANDONED' in dispo:
                handling_type = 'ABANDONED'
            elif 'SILENT' in dispo:
                handling_type = 'SILENT_VOICE'
                
            inc = CADIncident(
                id_number=row['id_number'],
                internal_reference_number=row['internal_reference_number'],
                agency=row['agency'],
                shift=row['shift'],
                shift_label=row['shift_label'],
                shift_group=int(row['shift_group']),
                problem_nature=row['problem_nature'],
                priority=int(row['priority']),
                prefix_directional=row.get('prefix_directional') if pd.notna(row.get('prefix_directional')) else None,
                street_number=row.get('street_number') if pd.notna(row.get('street_number')) else None,
                street_name=row.get('street_name') if pd.notna(row.get('street_name')) else None,
                street_type=row.get('street_type') if pd.notna(row.get('street_type')) else None,
                postfix_directional=row.get('postfix_directional') if pd.notna(row.get('postfix_directional')) else None,
                street_address=row.get('street_address') if pd.notna(row.get('street_address')) else None,
                city=row.get('city') if pd.notna(row.get('city')) else None,
                state=row.get('state') if pd.notna(row.get('state')) else None,
                postal_code=str(row.get('postal_code')) if pd.notna(row.get('postal_code')) else None,
                latitude=row.get('latitude') if pd.notna(row.get('latitude')) else 0.0,
                longitude=row.get('longitude') if pd.notna(row.get('longitude')) else 0.0,
                zone=row.get('zone') if pd.notna(row.get('zone')) else 'URBAN',
                location=row.get('location') if pd.notna(row.get('location')) else None,
                call_start_time=row['call_start_time'],
                incident_start_time=row['incident_start_time'],
                time_phone_pickup=row['time_phone_pickup'],
                time_call_enters_queue=row['time_call_enters_queue'],
                time_first_unit_assigned=row['time_first_unit_assigned'],
                time_unit_enroute=row['time_unit_enroute'],
                time_unit_arrived=row['time_unit_arrived'],
                time_last_unit_cleared=row['time_last_unit_cleared'],
                time_call_closed=row['time_call_closed'],
                time_phone_disconnect=row['time_phone_disconnect'],
                calltaker=row.get('calltaker'),
                dispatcher=row.get('dispatcher'),
                method_of_call_reception=row.get('method_of_call_reception'),
                call_disposition=row.get('call_disposition'),
                
                # High Impact Event Exclusions
                high_impact_event_flag=False, # Default: false (exclude storm/crisis spikes manually)
                hie_type='NONE',
                call_handling_type=handling_type,
                
                # Numeric Seconds
                pickup_delay_seconds=row['pickup_delay_seconds'],
                pre_cad_offset_seconds=row['pre_cad_offset_seconds'],
                interview_seconds=row['interview_seconds'],
                dispatch_queue_seconds=row['dispatch_queue_seconds'] if pd.notna(row['dispatch_queue_seconds']) else None,
                turnout_seconds=row['turnout_seconds'] if pd.notna(row['turnout_seconds']) else None,
                travel_seconds=row['travel_seconds'] if pd.notna(row['travel_seconds']) else None,
                on_scene_seconds=row['on_scene_seconds'] if pd.notna(row['on_scene_seconds']) else None,
                closeout_seconds=row['closeout_seconds'] if pd.notna(row['closeout_seconds']) else None,
                phone_duration_seconds=row['phone_duration_seconds'],
                total_elapsed_seconds=row['total_elapsed_seconds'],
                
                # Simulated placeholder network telemetry
                esinet_transit_seconds=0.015, # 15 ms ESInet transit latency
                sip_ssrd_seconds=row['pickup_delay_seconds'] * 0.1, # Mock SIP connection delay
                sip_sdd_seconds=0.08, # 80 ms disconnect teardown
                lost_query_delay_seconds=0.045, # 45 ms LoST resolver response
                hold_time_seconds=0.0,
                call_queued_delay_seconds=0.0,
                
                # Connection Jitter & MOS Voip Qualities
                media_jitter_ms=2.1,
                media_packet_loss_pct=0.01,
                mos_score=4.41 # High Quality VOIP score
            )
            records_to_insert.append(inc)
            
        print(f"Bulk saving {len(records_to_insert)} incident records...")
        session.bulk_save_objects(records_to_insert)
        session.commit()
        print("Incidents loaded successfully.")

    # 2. Ingest Phone Metrics Dataset
    if os.path.exists(hourly_csv_path):
        print(f"Loading hourly call counts CSV: {hourly_csv_path}...")
        df_hr = pd.read_csv(hourly_csv_path)
        
        df_hr['hour_start'] = pd.to_datetime(df_hr['hour_start']).dt.tz_localize('UTC')
        
        records_to_insert = []
        for _, row in df_hr.iterrows():
            pm = HourlyPhoneMetric(
                hour_start=row['hour_start'],
                hour_of_day=int(row['hour_of_day']),
                nine_one_one_calls_received=int(row['nine_one_one_calls_received']),
                nine_one_one_calls_abandoned=int(row['nine_one_one_calls_abandoned']),
                non_emergency_calls_received=int(row['non_emergency_calls_received']),
                non_emergency_calls_abandoned=int(row['non_emergency_calls_abandoned']),
                outbound_calls_placed=int(row['outbound_calls_placed']),
                nine_one_one_answered_10s_pct=row['nine_one_one_answered_10s_pct'],
                nine_one_one_answered_15s_pct=row['nine_one_one_answered_15s_pct'],
                nine_one_one_answered_20s_pct=row['nine_one_one_answered_20s_pct'],
                nine_one_one_answered_40s_pct=row['nine_one_one_answered_40s_pct'],
                non_emergency_answered_10s_pct=row['non_emergency_answered_10s_pct'],
                non_emergency_answered_15s_pct=row['non_emergency_answered_15s_pct'],
                non_emergency_answered_20s_pct=row['non_emergency_answered_20s_pct'],
                non_emergency_answered_40s_pct=row['non_emergency_answered_40s_pct'],
                nine_one_one_mean_duration=row['nine_one_one_mean_duration'],
                non_emergency_mean_duration=row['non_emergency_mean_duration'],
                outbound_mean_duration=row['outbound_mean_duration'],
                call_mean_duration=row['call_mean_duration'],
                total_emergency_calls=int(row['total_emergency_calls']),
                total_nonemergency_calls=int(row['total_nonemergency_calls']),
                total_calls=int(row['total_calls'])
            )
            records_to_insert.append(pm)
            
        print(f"Bulk saving {len(records_to_insert)} hourly phone metrics records...")
        session.bulk_save_objects(records_to_insert)
        session.commit()
        print("Hourly phone metrics loaded successfully.")
        
    session.close()
    print("Database Pipeline ingestion completed successfully.")


if __name__ == '__main__':
    print_postgresql_ddl()
