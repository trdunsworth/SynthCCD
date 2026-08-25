# Next-Generation 9-1-1 Supplementary Standards Alignment Guide

This guide details the major public safety and communications standards that supplement **NENA-STA-020.2-2026** and **NENA-STA-019.2-2022** for 9-1-1 Centers. Integrating these standards into your data warehouse schema and synthetic data generators (such as SynthCCD) allows public safety authorities to develop robust, automated, and nationally standardized reporting templates.

---

## 1. APCO 2.103-2019: Common Incident Types for Data Exchange
* **Focus:** Standardized Event Typology and Classification
* **Overview:** Historically, individual public safety agencies and Computer-Aided Dispatch (CAD) vendors developed proprietary, localized codes for emergency incidents (e.g., code "10-50" for a motor vehicle accident in one county, but "Crash" in another). This standard defines a unified, national vocabulary of common incident types across law enforcement, fire, and EMS disciplines.
* **Supplemental Value:** Under NENA call-taking guidelines, dispatch centers must categorize and document incidents with accurate descriptors to support workload audits and legal defense. Using standardized APCO 2.103 event codes inside your CAD data model ensures that compliance reports can be seamlessly run across adjacent jurisdictional boundaries without requiring complex data-translation tables.

---

## 2. NENA-STA-024.1-202Y: Emergency Incident Data Objects (EIDO)
* **Focus:** Next-Generation JSON/XML Incident Handoff Payloads
* **Overview:** The EIDO represents the standardized, XML/JSON-structured data packet used to share active emergency incident details (caller metadata, verified location, active dispatch logs, and responder states) between adjacent PSAPs, Next-Generation Core Services (NGCS), and CAD-to-CAD applications.
* **Supplemental Value:** A major challenge in Next-Generation routing is measuring handoff and subscription latencies when transferring calls to secondary or adjacent centers. By programming your testing pipeline to produce mock EIDO JSON payloads conforming to NENA-STA-024, your reporting templates can actively measure:
  * EIDO conveyance and subscription response delays.
  * Handoff/transfer overlap durations during "warm/attended transfers".
  * Parsing latencies at recipient CAD systems.

---

## 3. NFPA 1225: Emergency Services Communications Systems
* **Focus:** Turnout and Unit Dispatching Response Benchmarks
* **Overview:** NFPA 1225 (which succeeds NFPA 1221) establishes strict operational benchmarks for the secondary phases of an emergency call—specifically the intervals following call processing. This includes "dispatch time" (the interval to notify units) and "turnout time" (the interval from notification to wheels rolling).
* **Supplemental Value:** While NENA standards focus heavily on telephony answering speed and initial call processing, NFPA 1225 provides the pass/fail percentiles for dispatch dispatching and on-scene response times by responder discipline (Fire vs. EMS). Adding NFPA 1225 parameters to your audit templates creates a complete, end-to-end "Call Ingress to On-Scene Arrival" compliance workflow.

---

## 4. APCO/NENA ANS 1.107.1-2015: Quality Assurance & Improvement Programs
* **Focus:** Quality Assurance Sampling and Evaluation
* **Overview:** This ANSI-approved standard outlines the structural requirements for establishing Quality Assurance (QA) and Quality Improvement (QI) programs within Emergency Communications Centers. It details the exact statistical sample sizes required to audit dispatcher performance based on an agency's overall call volume.
* **Supplemental Value:** Page 4 of your Performance Audit Workbook highlights operator-level performance reviews. Incorporating APCO/NENA ANS 1.107 allows your database to dynamically calculate and extract a randomized, statistically valid subset of incident records (e.g., auditing 2% of standard calls vs. 100% of high-acuity calls), automating the center's monthly QA supervisor workflows.

---

## 5. NENA-STA-010.3-2021 (i3): Next-Generation Core Logging Services
* **Focus:** NG9-1-1 Standard Log Event Schemas
* **Overview:** The NENA i3 standard defines the structural architecture of Next-Generation 9-1-1 systems, including how core functional elements write logging events (e.g., `SessionStartLogEvent`, `SessionEndLogEvent`, `SessionStateChangeLogEvent`, and `CallStateChangeLogEvent`) to the Logging Service.
* **Supplemental Value:** Standardizing your PostgreSQL schema column names and event keys to match the exact schema of i3 Logging Service events (such as tracking `callIdSIP`, `direction`, `standardPrimaryCallType`, and `state` parameters) ensures that your reporting templates can run native queries directly against production i3 Logging nodes without modification.

---

## Technical Integration Matrix

| Standard Reference | Operational Dimension | Impact on Synthetic Data Models | Impact on Reporting Templates |
| :--- | :--- | :--- | :--- |
| **APCO 2.103** | Incident Typology | Maps simulated problem natures to a standard national index. | Standardizes volume charts across multi-agency databases. |
| **NENA-STA-024 (EIDO)** | Incident Transport | Generates valid EIDO JSON payloads to test pipeline schemas. | Audits transit handoff delays and payload completeness. |
| **NFPA 1225** | Responder Dispatch | Controls lognormal turnout and travel time defaults. | Provides specific turnout SLA thresholds by discipline. |
| **APCO/NENA 1.107** | Quality Assurance | Seeds personnel roster sizes and workload distributions. | Programmatically calculates randomized QA audit sample sizes. |
| **NENA-STA-010 (i3)** | Telephony Logging | Structures raw schemas using standard i3 log events. | Queries SIP signaling and session state changes directly. |
