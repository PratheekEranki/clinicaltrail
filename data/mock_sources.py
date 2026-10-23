"""Mock data sources matching interface_contract.md exactly.

Used until Sai Teja's data/sources/* functions land. The rows are seeded with
a deliberate trial-vs-real-world disagreement so the Evaluator has something
to flag in a demo.
"""

_TRIALS = [
    {"nct_id": "NCT_MOCK_001", "title": "Mock Trial: ACE Inhibitors in Elderly Diabetics",
     "phase": "Phase 3", "status": "Completed", "primary_outcome": "MACE reduction at 5 years",
     "enrollment": "2400", "condition": "Type 2 Diabetes", "intervention": "Lisinopril",
     "start_date": "2020-01-01"},
    {"nct_id": "NCT_MOCK_002", "title": "Mock Trial: Ramipril and Cardiovascular Mortality in Adults 65+ with T2DM",
     "phase": "Phase 4", "status": "Completed", "primary_outcome": "Cardiovascular death, 22% relative risk reduction",
     "enrollment": "1850", "condition": "Type 2 Diabetes", "intervention": "Ramipril 10mg",
     "start_date": "2019-06-15"},
]

_LITERATURE = [
    {"pmid": "MOCK_001", "title": "Mock Paper: Cardiovascular outcomes and ACE inhibitors",
     "abstract": "Background: Mock abstract for testing. ACE inhibitor use was associated with "
                 "a significant reduction in major adverse cardiovascular events among older "
                 "adults with type 2 diabetes.",
     "publication_date": "2023-01-01", "journal": "Mock Journal", "authors": "Smith J, et al."},
    {"pmid": "MOCK_002", "title": "Mock Paper: Attenuated benefit of ACE inhibition in patients over 75",
     "abstract": "Background: In a pooled analysis, cardiovascular benefit of ACE inhibitors was "
                 "attenuated in patients older than 75, with higher rates of hyperkalemia and "
                 "acute kidney injury.",
     "publication_date": "2024-03-10", "journal": "Mock Geriatrics Review", "authors": "Lee K, Patel R"},
]

_OUTCOMES = [
    {"condition": "Type 2 Diabetes", "treatment": "ACE Inhibitor",
     "outcome_metric": "MACE at 5 years", "value": "18.3%",
     "population_age_group": "65-80", "n_patients": "12400", "source_dataset": "MOCK_DATASET"},
    {"condition": "Type 2 Diabetes", "treatment": "No RAAS blockade",
     "outcome_metric": "MACE at 5 years", "value": "19.1%",
     "population_age_group": "65-80", "n_patients": "9800", "source_dataset": "MOCK_DATASET"},
]


def query_trials(sub_question: str) -> list[dict]:
    return [dict(r) for r in _TRIALS]


def query_literature(sub_question: str) -> list[dict]:
    return [dict(r) for r in _LITERATURE]


def query_outcomes(sub_question: str) -> list[dict]:
    return [dict(r) for r in _OUTCOMES]
