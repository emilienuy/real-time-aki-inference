# Real-Time AKI Inference Service

Production ML service processing HL7v2 medical messages for real-time Acute Kidney Injury detection.

## Overview

Connects to hospital information systems via HL7v2/MLLP protocol, monitors patient blood test results in real-time, and sends automated pager alerts when AKI risk is detected.

**Architecture:**
```
Hospital Lab → HL7v2 Message → MLLP → This Service → ML Inference → Pager Alert
```

**Key features:**
- Real-time streaming inference on medical messages
- HL7v2 parsing and MLLP protocol implementation
- Prometheus metrics for monitoring
- Graceful shutdown and fault tolerance
- Comprehensive testing (unit + integration)

---

## Quick Start

**Start simulator:**
```bash
python3 tools/simulator/simulator.py \
  --messages tests/fixtures/messages.mllp \
  --mllp 8440 \
  --pager 8441
```

**Run service:**
```bash
export MLLP_ADDRESS=localhost:8440
export PAGER_ADDRESS=localhost:8441
export HISTORY_CSV=tests/fixtures/history.csv

python3 -m src.main
```

**Docker:**
```bash
docker build -t aki-inference .
docker run --rm \
  -e MLLP_ADDRESS=hospital:2575 \
  -e PAGER_ADDRESS=pager:8080 \
  -v /path/to/history.csv:/data/history.csv:ro \
  aki-inference
```

---

## Technical Stack

**Medical Interoperability:**
- HL7v2 message parsing (pipe-delimited format)
- MLLP (Minimum Lower Layer Protocol) transport layer
- Persistent TCP connections with acknowledgments

**ML Pipeline:**
- Patient state management from historical CSV
- Real-time feature extraction from creatinine time series
- Logistic regression inference (<100ms latency)

**Observability:**
- Prometheus metrics: messages received, alerts sent, creatinine values
- Structured logging
- Health checks and monitoring endpoints

**Testing:**
- Unit tests for parsers, model, metrics
- Integration tests for end-to-end message flow
- HL7 simulator for local development

---

## Repository Structure

```
src/
  ├── main.py              # Service orchestration, MLLP connection
  ├── hl7.py               # HL7v2 message parsing
  ├── mllp.py              # MLLP protocol
  ├── model.py             # ML inference
  └── metrics.py           # Prometheus metrics
tests/
  ├── unit/                # Component tests
  └── integration/         # End-to-end tests
tools/simulator/           # HL7 message simulator
```

---

## Monitoring

Prometheus metrics exposed on port 8000:

- `aki_messages_received_total` - HL7 messages processed
- `aki_blood_tests_received_total` - Creatinine results parsed
- `aki_pages_sent_total` - Alerts sent
- `aki_creatinine_value` - Latest value per patient

---

## HL7v2 Example

```
MSH|^~\&|LAB|HOSPITAL|...
PID|1||12345||DOE^JOHN||19800101|M|...
OBX|1|NM|CREAT||1.8|mg/dL|0.6-1.2|H|||...
```

Service extracts patient ID (12345), test type (CREAT), and result (1.8 mg/dL), then runs inference.

---

## Production Considerations

- **Fault tolerance:** Connection retry, graceful shutdown, timeout handling
- **Scalability:** Single-threaded; use async I/O or message queue for high volume
- **Security:** Add TLS, authentication, PHI encryption for production
- **Clinical validation:** Tune threshold and validate on local patient population before deployment

---

## Testing

```bash
pytest -v
```

Tests cover HL7 parsing, MLLP protocol, ML inference, pager alerts, and end-to-end message flow.

---

## Context

Group coursework project for Software Engineering for Machine Learning Systems (Imperial College London, MSc AI).

**Team:** Emilie Nuyttens, Otis Parker, Sergio Garcia

Demonstrates:
- Medical data interoperability (HL7v2/MLLP standards)
- Real-time streaming ML inference
- Production system design (monitoring, testing, fault tolerance)

**Note:** Educational implementation - clinical deployment requires additional validation, regulatory approval, and IT integration.

---

## Further Reading

- [HL7 v2 Standard](https://www.hl7.org/implement/standards/product_brief.cfm?product_id=185)
- [MLLP Protocol](https://www.hl7.org/documentcenter/public/wg/inm/mllp_transport_specification.PDF)
- [KDIGO AKI Guidelines](https://kdigo.org/guidelines/acute-kidney-injury/)
