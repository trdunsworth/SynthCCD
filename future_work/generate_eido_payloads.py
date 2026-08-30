import datetime
import json
import os
import uuid

import pandas as pd

# URN Prefix constants for NENA i3 compatibility
INCIDENT_URN_PREFIX = "urn:emergency:uid:incident:indymo:"
CALL_URN_PREFIX = "urn:emergency:uid:call:indymo:"
ELEMENT_URN = "urn:nena:element:psap-ecc-indymo:psap-active-01"

# APCO 2.103.2-2019 Common Incident Type lookup map
# Maps SynthCCD problem_nature to standard APCO registry literals
APCO_INCIDENT_TYPE_MAP = {
    "Active Shooter": "ACTSHOOT",
    "Structure Fire": "FIRE",
    "Cardiac Arrest": "CARDIAC",
    "Assault": "ASSAULT",
    "Harassment": "HARASS",
    "Burglary In Progress": "BURG",
    "Weapons Violation": "WEAPON",
    "Reckless Driving": "TRAFFIC",
    "DUI / Impaired Driver": "DUI",
    "Theft Report": "THEFT",
    "Vandalism": "VANDAL",
    "Noise Complaint": "NOISE",
    "Animal Complaint": "ANIMAL",
    "Fire Alarm": "ALMA",
    "Gas Leak": "GAS",
    "Smoke Investigation": "SMOKE",
    "CO Investigation": "CO",
    "Electrical Wiring Problem": "ELECTRICAL",
    "Elevator Rescue": "RESCUE",
    "Lockout / Public Service": "PUBLIC_SERVICE",
    "Difficulty Breathing": "BREATH",
    "Chest Pain": "CHEST",
    "Unconscious Person": "UNCONSCIOUS",
    "Seizure": "SEIZURE",
    "Overdose": "OVERDOSE",
    "Fall Injury": "FALL",
    "Diabetic Problem": "DIABETIC",
    "Sick Person": "SICK"
}

def format_rfc3339(timestamp_str):
    """Converts a standard SynthCCD datetime string to RFC 3339 format."""
    if pd.isna(timestamp_str) or not timestamp_str:
        return None
    try:
        # SynthCCD uses standard M/D/YYYY H:M format
        dt = datetime.strptime(str(timestamp_str), "%m/%d/%Y %H:%M").replace(tzinfo=datetime.UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    except ValueError:
        try:
            dt = datetime.strptime(str(timestamp_str), "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.UTC)
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        except ValueError:
            return str(timestamp_str)

def row_to_eido(row):
    """Transforms a single SynthCCD CAD Incident row into a fully-nested,

    NENA-STA-021.1b-2021 compliant EIDO JSON payload.
    """
    row_id = str(row.get('id_number', uuid.uuid4()))
    ref_num = str(row.get('internal_reference_number', 'UNKNOWN'))
    agency_type = str(row.get('agency', 'LAW')).upper()
    
    # Generate unique IDs for cross-component linking
    incident_tracking_id = f"{INCIDENT_URN_PREFIX}{ref_num}"
    call_id = f"{CALL_URN_PREFIX}{row_id}"
    agency_id = f"agency:{agency_type.lower()}-indymo"
    calltaker_agent_id = f"agent:calltaker-{row.get('calltaker', 'unknown').lower().replace(' ', '_')}"
    dispatcher_agent_id = f"agent:dispatcher-{row.get('dispatcher', 'unknown').lower().replace(' ', '_')}"
    location_id = f"location:incident-scene-{row_id}"
    resource_id = f"resource:unit-{row_id}@indymo-{agency_type.lower()}"

    # Standardize APCO Incident types
    problem_nature = row.get('problem_nature', 'Administrative')
    common_incident_type = APCO_INCIDENT_TYPE_MAP.get(problem_nature, "ADMIN")

    # Mapping NENA Agency roles & types
    agency_role_map = {
        "LAW": "police",
        "FIRE": "fire",
        "EMS": "ems"
    }
    resolved_agency_type = agency_role_map.get(agency_type, "police")

    # Map disposition to standard code (NENA-STA-021.1b-2021 Table 2-12)
    raw_disp = str(row.get('call_disposition', 'UNDEFINED'))
    common_disp_code = "CLOSED"
    if "FALSE" in raw_disp:
        common_disp_code = "FALSE_ALARM"
    elif "RE" in raw_disp:
        common_disp_code = "REPORT_WRITTEN"
    elif "NR" in raw_disp:
        common_disp_code = "RESOLVED_NO_REPORT"

    # Assemble the parent EIDO wrapper (NENA-STA-021.1b-2021 Components)
    eido = {
        "$id": f"urn:nena:eido:indymo:{row_id}",
        "eidoVersion": "1.0",
        "issuingElementIdentification": ELEMENT_URN,
        
        # 1. Agency Component (Required)
        "agencyComponent": [
            {
                "$id": agency_id,
                "agencyRoleDescriptionRegistryText": ["CallReceiving", "Dispatching"],
                "agencyType": [resolved_agency_type],
                "incidentOwningAgencyIndicator": True
            }
        ],

        # 2. Agent Component (Conditional - references the agencies)
        "agentComponent": [
            {
                "$id": calltaker_agent_id,
                "agentRoleRegistryText": ["Calltaker"],
                "agencyReference": {"$ref": f"#{agency_id}"},
                "agentJcard": f"FN:{row.get('calltaker', 'Billy Smith')}"
            },
            {
                "$id": dispatcher_agent_id,
                "agentRoleRegistryText": ["Dispatcher"],
                "agencyReference": {"$ref": f"#{agency_id}"},
                "agentJcard": f"FN:{row.get('dispatcher', 'David Obasanjo')}"
            }
        ],

        # 3. Location Component (PIDF-LO Civic/Geodetic translation)
        "locationComponent": [
            {
                "$id": location_id,
                "locationTypeDescriptionRegistryText": "CurrentIncident",
                "locationByValue": {
                    "civicAddress": {
                        "street": str(row.get('street_name', '')),
                        "houseNumber": str(row.get('street_number', '')),
                        "streetType": str(row.get('street_type', '')),
                        "city": str(row.get('city', 'Independence')),
                        "state": str(row.get('state', 'MO')),
                        "postalCode": str(row.get('postal_code', '64050')),
                        "country": "US"
                    },
                    "wgs84LocationEllipse": {
                        "point": {
                            "latitude": float(row.get('latitude', 0.0)) if not pd.isna(row.get('latitude')) else 0.0,
                            "longitude": float(row.get('longitude', 0.0)) if not pd.isna(row.get('longitude')) else 0.0
                        },
                        "semiMajorAxis": 10.0,
                        "semiMinorAxis": 10.0,
                        "rotation": 0.0
                    }
                }
            }
        ],

        # 4. Incident Component (General tracking indexes)
        "incidentComponent": {
            "$id": f"incident-info-{row_id}",
            "incidentTrackingIdentifier": incident_tracking_id,
            "incidentTypeInternalCode": problem_nature,
            "incidentTypeInternalText": problem_nature,
            "incidentTypeCommonRegistryText": common_incident_type,
            "incidentCommonPriorityNumber": int(row.get('priority', 3)),
            "internalIncidentId": ref_num,
            "agentReference": [{"$ref": f"#{calltaker_agent_id}"}],
            "locationReference": [{"$ref": f"#{location_id}"}],
            "disposition": [
                {
                    "dispositionCommonRegistryCode": common_disp_code,
                    "dispositionPrimaryIndicator": True,
                    "dispositionDescriptionText": raw_disp
                }
            ]
        },

        # 5. Call Component (SIP / Logging Service records)
        "callComponent": [
            {
                "$id": f"call-info-{row_id}",
                "callIdentifier": call_id,
                "callStartTimestamp": format_rfc3339(row.get('call_start_time')),
                "answerDate": format_rfc3339(row.get('time_phone_pickup')),
                "disconnectDate": format_rfc3339(row.get('time_phone_disconnect')),
                "standardPrimaryCallType": "Emergency",
                "calltakerAgentReference": {"$ref": f"#{calltaker_agent_id}"},
                "locationReference": [{"$ref": f"#{location_id}"}]
            }
        ]
    }

    # 6. Dispatch & Emergency Resource components (If units were assigned/arrived)
    if not pd.isna(row.get('time_first_unit_assigned')):
        eido["emergencyResourceComponent"] = [
            {
                "$id": resource_id,
                "emergencyResourceTypeCommonRegistryText": "PatrolUnit" if agency_type == "LAW" else "FireEngine" if agency_type == "FIRE" else "Ambulance",
                "primaryUnitStatusRegistryText": "Assigned",
                "resourceAttributeRegistryText": ["AdvancedEMT"] if agency_type == "EMS" else ["Basic"],
                "unitStatusInternal": ["DISPATCHED"],
                "agentReference": [{"$ref": f"#{dispatcher_agent_id}"}]
            }
        ]
        
        eido["dispatchComponent"] = [
            {
                "$id": f"dispatch-info-{row_id}",
                "dispatchTimestamp": format_rfc3339(row.get('time_first_unit_assigned')),
                "wheelsRollingTimestamp": format_rfc3339(row.get('time_unit_enroute')),
                "onSceneTimestamp": format_rfc3339(row.get('time_unit_arrived')),
                "agencyReference": {"$ref": f"#{agency_id}"},
                "agentReference": {"$ref": f"#{dispatcher_agent_id}"},
                "emergencyResourceReference": [{"$ref": f"#{resource_id}"}]
            }
        ]

    # JSON-LD Context Mapping (NENA-STA-021.1b-2021 OpenAPI context)
    eido["@context"] = {
        "@vocab": "./JSON-LD_Contexts/EmergencyIncidentDataObjectType.jsonld"
    }

    return eido

def generate_eido_batch(csv_path, output_dir, max_records=10):
    """Processes a batch of CAD incidents and saves structured EIDO JSON files."""
    print(f"Reading CAD incidents from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    
    print(f"Translating top {max_records} rows into valid EIDOs...")
    for idx, row in df.head(max_records).iterrows():
        eido_payload = row_to_eido(row)
        filename = f"eido_{row.get('internal_reference_number', idx)}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(eido_payload, f, indent=2)
        generated_files.append(filepath)
        
    print(f"EIDO Generation Complete. Saved {len(generated_files)} payloads to {output_dir}")
    return generated_files

if __name__ == "__main__":
    src_csv = "/workspace/knowledge/IndyMo_incidents.csv"
    out_folder = "/workspace/scratch/eido_payloads"
    generate_eido_batch(src_csv, out_folder, max_records=5)
