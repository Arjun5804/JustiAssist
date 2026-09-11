from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from core.dependencies import deps
from pydantic import BaseModel, Field
from llm_provider import call_llm
from datetime import datetime
from prompts.templates import build_generation_prompt

class CasePredictionRequest(BaseModel):
    """Request model for AI case outcome prediction"""
    case_type: str = Field(..., description="criminal, civil, constitutional, family, property")
    sections_involved: List[str] = Field(default_factory=list)
    case_facts: str = Field(..., min_length=20)
    court_level: str = Field(default="sessions", description="district, sessions, high_court, supreme_court")
    jurisdiction: str = Field(default="Delhi")
    prior_proceedings: Optional[str] = None
    client_role: str = Field(default="accused", description="petitioner, respondent, accused, complainant")



class CounterArgumentRequest(BaseModel):
    """Request model for counter-argument generation"""
    legal_argument: str = Field(..., min_length=20, description="The legal argument to counter")
    case_type: str = Field(default="criminal", description="criminal, civil, constitutional, family, property")
    sections_involved: List[str] = Field(default_factory=list)
    client_role: str = Field(default="respondent", description="petitioner, respondent, accused, complainant")
    jurisdiction: str = Field(default="Delhi")
    focus_areas: List[str] = Field(default_factory=list, description="procedural, substantive, evidentiary, constitutional")



class QuizRequest(BaseModel):
    topic: str = Field(..., description="e.g. Constitutional Law, IPC, CrPC, Evidence Act, Contract Law")
    difficulty: str = Field(default="medium", description="easy, medium, hard")
    num_questions: int = Field(default=5, ge=1, le=10)
    exam_type: str = Field(default="CLAT", description="CLAT, AILET, JUDICIARY, BAR")



class MootCourtRequest(BaseModel):
    case_scenario: str = Field(..., min_length=20)
    user_role: str = Field(default="petitioner", description="petitioner or respondent")
    user_argument: str = Field(..., min_length=10)
    court_level: str = Field(default="High Court")
    round_number: int = Field(default=1)
    history: List[dict] = Field(default_factory=list, description="Previous argument exchanges")




router = APIRouter()

@router.post("/api/predict/case")
async def predict_case_outcome(request: CasePredictionRequest):
    """
    CasePredictAI — Predict case outcome with multiple strategic approaches.
    Uses LLM with retrieved legal context for grounded predictions.
    """
    try:
        import json as json_module

        # Step 1: Retrieve relevant statutory context for grounding
        sections_query = " ".join(request.sections_involved[:5]) if request.sections_involved else ""
        search_query = f"{request.case_type} {sections_query} {request.case_facts[:200]}"

        statutory_context = ""
        if deps.vector_store and deps.vector_store.statutory_index is not None:
            results = deps.vector_store.hybrid_search_statutory(
                search_query,
                top_k=8,
                semantic_weight=0.6,
                bm25_weight=0.4
            )
            if results:
                statutory_context = "\n\n".join([
                    f"**{r.section_number}** ({r.law_type}): {r.text[:300]}"
                    for r in results[:6]
                ])

        # Step 2: Build prediction prompt
        prediction_prompt = f"""You are CasePredictAI, an advanced legal prediction assistant specialized in Indian law.

TASK: Analyze the following case and provide a detailed prediction with multiple strategic approaches.

CASE DETAILS:
- Case Type: {request.case_type}
- Sections Involved: {', '.join(request.sections_involved) if request.sections_involved else 'Not specified'}
- Court Level: {request.court_level}
- Jurisdiction: {request.jurisdiction}
- Client Role: {request.client_role}
- Prior Proceedings: {request.prior_proceedings or 'None'}

CASE FACTS:
{request.case_facts}

RELEVANT LEGAL PROVISIONS:
{statutory_context if statutory_context else 'No specific provisions retrieved — use general legal knowledge.'}

INSTRUCTIONS — Respond in VALID JSON format ONLY (no markdown, no code fences):

{{
  "outcome_prediction": {{
    "favorable_percentage": <number 0-100>,
    "unfavorable_percentage": <number 0-100>,
    "settlement_percentage": <number 0-100>,
    "summary": "<2-3 sentence overall prediction>",
    "key_factors": ["<factor1>", "<factor2>", "<factor3>"]
  }},
  "strategies": [
    {{
      "name": "Aggressive",
      "approach": "<detailed strategy description, 3-4 sentences>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }},
    {{
      "name": "Balanced",
      "approach": "<detailed strategy description>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }},
    {{
      "name": "Conservative",
      "approach": "<detailed strategy description>",
      "pros": ["<pro1>", "<pro2>"],
      "cons": ["<con1>", "<con2>"],
      "success_rate": "<estimated percentage>",
      "recommended_actions": ["<action1>", "<action2>", "<action3>"]
    }}
  ],
  "risk_factors": [
    {{
      "risk": "<risk description>",
      "severity": "high/medium/low",
      "mitigation": "<how to mitigate>"
    }}
  ],
  "relevant_provisions": [
    {{
      "section": "<section number>",
      "law": "<act name>",
      "relevance": "<why relevant>"
    }}
  ],
  "precedent_cases": [
    {{
      "case_name": "<case name>",
      "citation": "<citation if known>",
      "relevance": "<how it applies>"
    }}
  ],
  "timeline_estimate": "<estimated duration>",
  "confidence_score": <number 0.0 to 1.0>
}}

Be thorough, specific to Indian law, and grounded in the legal provisions provided where possible.
"""

        # Step 3: Call LLM
        raw_text = await call_llm(prediction_prompt, temperature=0.4, max_tokens=3000)
        raw_text = raw_text.strip()

        # Parse JSON from response (strip markdown fences if present)
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

        prediction = json_module.loads(raw_text)

        return {
            "status": "success",
            "prediction": prediction,
            "grounded": bool(statutory_context),
            "sections_retrieved": len(statutory_context.split("**")) - 1 if statutory_context else 0
        }

    except Exception as e:
        print(f"[CasePredictAI] Error: {e}")
        # Return demo prediction
        return {
            "status": "demo",
            "prediction": _get_demo_prediction(request),
            "grounded": False,
            "sections_retrieved": 0,
            "note": "Demo prediction — AI service temporarily unavailable"
        }


def _get_demo_prediction(request: CasePredictionRequest) -> dict:
    """Generate a structured demo prediction when LLM is unavailable"""
    sections_text = ', '.join(request.sections_involved) if request.sections_involved else 'General provisions'
    return {
        "outcome_prediction": {
            "favorable_percentage": 55,
            "unfavorable_percentage": 30,
            "settlement_percentage": 15,
            "summary": f"Based on the {request.case_type} case involving {sections_text} at the {request.court_level} level, the case presents moderate prospects. The strength of evidence and applicable legal provisions will be decisive factors.",
            "key_factors": [
                "Strength of documentary evidence",
                f"Applicable provisions under {sections_text}",
                "Judicial precedents in similar matters",
                f"Current judicial trends in {request.jurisdiction}"
            ]
        },
        "strategies": [
            {
                "name": "Aggressive",
                "approach": f"Pursue an aggressive litigation strategy by challenging the opposing party's claims head-on. File preliminary applications to establish procedural advantage and seek early hearing dates. Leverage strong constitutional arguments and recent progressive judgments.",
                "pros": ["Can lead to early resolution", "Shows strength of conviction", "May pressure opposing party"],
                "cons": ["Higher litigation costs", "Risk of adverse costs order", "May antagonize the bench"],
                "success_rate": "45%",
                "recommended_actions": [
                    "File preliminary objections immediately",
                    "Seek urgent interim relief",
                    "Compile comprehensive case law compilation"
                ]
            },
            {
                "name": "Balanced",
                "approach": f"Adopt a measured approach that combines strong legal arguments with openness to mediation. Present the case methodically while exploring settlement possibilities through court-annexed mediation. This preserves all legal options while demonstrating reasonableness.",
                "pros": ["Maintains judicial goodwill", "Preserves all options", "Cost-effective in the long run"],
                "cons": ["May take longer to resolve", "Could be perceived as indecisive"],
                "success_rate": "60%",
                "recommended_actions": [
                    "File well-researched written submissions",
                    "Express willingness for mediation",
                    "Prepare expert witness depositions"
                ]
            },
            {
                "name": "Conservative",
                "approach": f"Focus on settlement negotiations and alternative dispute resolution. Engage the opposing party through structured dialogue and seek a mutually acceptable resolution. Use the threat of prolonged litigation as leverage while keeping the door open for compromise.",
                "pros": ["Lowest litigation risk", "Preserves relationships", "Faster resolution possible"],
                "cons": ["May result in less favorable terms", "Could be seen as weakness"],
                "success_rate": "70%",
                "recommended_actions": [
                    "Initiate pre-litigation mediation",
                    "Prepare settlement term sheet",
                    "Engage senior counsel for negotiations"
                ]
            }
        ],
        "risk_factors": [
            {"risk": "Delay in judicial proceedings", "severity": "medium", "mitigation": "File applications for expedited hearing"},
            {"risk": "Adverse interpretation of key provisions", "severity": "high", "mitigation": "Prepare comprehensive legal brief with supporting precedents"},
            {"risk": "Evidentiary challenges", "severity": "medium", "mitigation": "Secure documentary evidence and affidavits early"},
            {"risk": "Cost escalation", "severity": "low", "mitigation": "Set litigation budget with periodic review"}
        ],
        "relevant_provisions": [
            {"section": sections_text.split(",")[0] if request.sections_involved else "General", "law": "Indian Penal Code / Bharatiya Nyaya Sanhita", "relevance": "Primary substantive law applicable to the case"},
            {"section": "Section 482 CrPC (Section 528 BNSS)", "law": "Code of Criminal Procedure / BNSS", "relevance": "Inherent powers of High Court for quashing"},
            {"section": "Article 21", "law": "Constitution of India", "relevance": "Fundamental right to life and personal liberty"}
        ],
        "precedent_cases": [
            {"case_name": "Arnesh Kumar v. State of Bihar", "citation": "(2014) 8 SCC 273", "relevance": "Guidelines on arrest procedures and personal liberty"},
            {"case_name": "Satender Kumar Antil v. CBI", "citation": "(2022) 10 SCC 51", "relevance": "Comprehensive bail jurisprudence and personal liberty"}
        ],
        "timeline_estimate": "6-18 months depending on strategy and court workload",
        "confidence_score": 0.65
    }


@router.post("/api/counter-arguments")
async def generate_counter_arguments(request: CounterArgumentRequest):
    """
    Counter Argument Generator — develop opposing viewpoints, rebuttals,
    procedural defenses, and relevant precedents.
    """
    try:
        import json as json_module

        # Step 1: Retrieve statutory context
        sections_query = " ".join(request.sections_involved[:5]) if request.sections_involved else ""
        search_query = f"{request.case_type} counter argument {sections_query} {request.legal_argument[:200]}"

        statutory_context = ""
        if deps.vector_store and deps.vector_store.statutory_index is not None:
            results = deps.vector_store.hybrid_search_statutory(
                search_query, top_k=8, semantic_weight=0.6, bm25_weight=0.4
            )
            if results:
                statutory_context = "\n\n".join([
                    f"**{r.section_number}** ({r.law_type}): {r.text[:300]}"
                    for r in results[:6]
                ])

        focus_text = ", ".join(request.focus_areas) if request.focus_areas else "all applicable areas"

        # Step 2: Build prompt
        prompt = f"""You are an expert Indian legal strategist specializing in counter-arguments and rebuttals.

TASK: Analyze the following legal argument and generate comprehensive counter-arguments from the perspective of the {request.client_role}.

ORIGINAL ARGUMENT:
{request.legal_argument}

CONTEXT:
- Case Type: {request.case_type}
- Sections: {', '.join(request.sections_involved) if request.sections_involved else 'Not specified'}
- Jurisdiction: {request.jurisdiction}
- Client Role: {request.client_role}
- Focus Areas: {focus_text}

RELEVANT LEGAL PROVISIONS:
{statutory_context if statutory_context else 'Use general Indian legal knowledge.'}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "argument_analysis": {{
    "summary": "<1-2 sentence summary of the original argument>",
    "strengths": ["<strength1>", "<strength2>"],
    "weaknesses": ["<weakness1>", "<weakness2>", "<weakness3>"]
  }},
  "opposing_viewpoints": [
    {{
      "title": "<viewpoint title>",
      "argument": "<detailed opposing argument, 2-3 sentences>",
      "legal_basis": "<statutory or constitutional basis>",
      "strength": "strong/moderate/speculative"
    }}
  ],
  "rebuttals": [
    {{
      "original_point": "<point from the original argument being rebutted>",
      "counter": "<detailed rebuttal, 2-3 sentences>",
      "supporting_law": "<relevant section or principle>"
    }}
  ],
  "procedural_defenses": [
    {{
      "defense": "<procedural defense title>",
      "description": "<how to apply this defense>",
      "relevant_provision": "<applicable CrPC/CPC/Evidence Act section>",
      "effectiveness": "high/medium/low"
    }}
  ],
  "precedents": [
    {{
      "case_name": "<case name>",
      "citation": "<citation>",
      "ratio": "<ratio decidendi or key holding>",
      "application": "<how this precedent supports the counter-argument>"
    }}
  ],
  "recommended_strategy": "<2-3 sentence overall recommended approach>",
  "confidence_score": <0.0 to 1.0>
}}

Be thorough, cite real Indian legal provisions, and provide actionable counter-arguments.
"""

        # Step 3: Call LLM
        raw = await call_llm(prompt, temperature=0.4, max_tokens=3000)
        raw = raw.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json_module.loads(raw)
        return {"status": "success", "result": result, "grounded": bool(statutory_context)}

    except Exception as e:
        print(f"[CounterArgGen] Error: {e}")
        return {
            "status": "demo",
            "result": _get_demo_counter_arguments(request),
            "grounded": False,
            "note": "Demo response — AI service temporarily unavailable"
        }


def _get_demo_counter_arguments(req: CounterArgumentRequest) -> dict:
    sections = ', '.join(req.sections_involved) if req.sections_involved else 'General provisions'
    return {
        "argument_analysis": {
            "summary": f"The argument raises points under {sections} in a {req.case_type} matter. Analysis follows from the {req.client_role}'s perspective.",
            "strengths": [
                "Relies on established statutory framework",
                "Follows conventional legal reasoning"
            ],
            "weaknesses": [
                "Interpretation of key provisions may be contested",
                "Potential procedural irregularities not addressed",
                "Fails to account for recent judicial trends"
            ]
        },
        "opposing_viewpoints": [
            {
                "title": "Alternative Statutory Interpretation",
                "argument": "The cited provisions must be read harmoniously with other relevant sections. A purposive interpretation, as favoured by the Supreme Court, would yield a different conclusion that supports the respondent's position.",
                "legal_basis": "Section 6-8, General Clauses Act, 1897; Rule of harmonious construction",
                "strength": "strong"
            },
            {
                "title": "Constitutional Challenge",
                "argument": "The application of the cited provisions in the manner suggested violates fundamental rights guaranteed under Articles 14, 19, and 21 of the Constitution. Any interpretation must pass the test of reasonableness and proportionality.",
                "legal_basis": "Articles 14, 19, 21 — Constitution of India",
                "strength": "strong"
            },
            {
                "title": "Factual Dispute",
                "argument": "The factual foundation of the argument is contested. Material evidence suggests an alternative narrative that undermines the core premise of the original claim.",
                "legal_basis": "Sections 101-114, Indian Evidence Act (Bharatiya Sakshya Adhiniyam)",
                "strength": "moderate"
            }
        ],
        "rebuttals": [
            {
                "original_point": "Primary statutory interpretation",
                "counter": "The cited provision must be read in its entirety, including provisos and explanations. Selective reading distorts legislative intent. The Supreme Court has repeatedly held that statutes must be read as a whole.",
                "supporting_law": "Principles of statutory interpretation; CIT v. Hindustan Bulk Carriers (2003) 3 SCC 57"
            },
            {
                "original_point": "Reliance on factual assertions",
                "counter": "The burden of proof for the asserted facts lies with the proponent under Section 101 of the Evidence Act. The documentary evidence on record does not conclusively establish the claimed facts.",
                "supporting_law": "Section 101-103, Indian Evidence Act / BSA 2023"
            },
            {
                "original_point": "Applicability of cited precedent",
                "counter": "The cited precedent is distinguishable on facts. The ratio decidendi of the relied-upon judgment pertains to a materially different factual matrix and cannot be mechanically applied.",
                "supporting_law": "Doctrine of precedent; per incuriam rule"
            }
        ],
        "procedural_defenses": [
            {
                "defense": "Limitation / Delay",
                "description": "Challenge the timeliness of the action. If filing is beyond the prescribed limitation period, seek dismissal on this preliminary ground.",
                "relevant_provision": "Limitation Act, 1963; Section 3 — bar on suits beyond limitation",
                "effectiveness": "high"
            },
            {
                "defense": "Non-Joinder of Necessary Party",
                "description": "Argue that essential parties have not been impleaded, rendering the proceedings defective.",
                "relevant_provision": "Order 1 Rule 10, CPC / Section 43 BNSS",
                "effectiveness": "medium"
            },
            {
                "defense": "Lack of Territorial Jurisdiction",
                "description": "Challenge that the court lacks territorial or pecuniary jurisdiction over the subject matter.",
                "relevant_provision": "Section 15-20, CPC; Section 177-184 CrPC / BNSS",
                "effectiveness": "high"
            }
        ],
        "precedents": [
            {
                "case_name": "Lalita Kumari v. Govt. of U.P.",
                "citation": "(2014) 2 SCC 1",
                "ratio": "Mandatory FIR registration guidelines and scope of preliminary inquiry",
                "application": "Establishes procedural safeguards that may not have been followed"
            },
            {
                "case_name": "K.S. Puttaswamy v. Union of India",
                "citation": "(2017) 10 SCC 1",
                "ratio": "Right to privacy as a fundamental right under Article 21",
                "application": "Constitutional challenge to any overreach in the original argument"
            },
            {
                "case_name": "Mohd. Ahmed Khan v. Shah Bano Begum",
                "citation": "1985 AIR 945",
                "ratio": "Harmonious construction of personal law with constitutional provisions",
                "application": "Supports reading statutes consistently with constitutional values"
            }
        ],
        "recommended_strategy": f"Adopt a multi-pronged approach combining procedural challenges with substantive counter-arguments. Lead with the strongest procedural defense to seek early dismissal, while simultaneously preparing the substantive rebuttal for trial on merits.",
        "confidence_score": 0.72
    }


@router.post("/api/sandbox/quiz")
async def generate_quiz(request: QuizRequest):
    """Generate entrance exam MCQs for legal preparation."""
    try:
        import json as json_module

        prompt = f"""You are a legal exam expert for Indian law entrance exams.

Generate {request.num_questions} multiple-choice questions for {request.exam_type} exam preparation.

Topic: {request.topic}
Difficulty: {request.difficulty}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "questions": [
    {{
      "id": 1,
      "question": "<question text>",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "A",
      "explanation": "<detailed explanation with legal reasoning and any relevant section/case>",
      "difficulty": "{request.difficulty}",
      "topic_tag": "<sub-topic>"
    }}
  ]
}}

Make questions realistic for {request.exam_type}, test conceptual understanding, and provide thorough explanations citing Indian statutes and cases where relevant.
"""
        raw = await call_llm(prompt, temperature=0.6, max_tokens=3000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        result = json_module.loads(raw)
        return {"status": "success", "quiz": result}

    except Exception as e:
        print(f"[Sandbox Quiz] Error: {e}")
        return {"status": "demo", "quiz": _get_demo_quiz(request), "note": "Demo quiz — AI service unavailable"}


# --- DOCUMENT GENERATION ROUTES ---

class DocumentGenerationRequest(BaseModel):
    template_type: str
    form_data: Dict[str, Any]

@router.post("/api/documents/generate")
async def generate_legal_document(request: DocumentGenerationRequest):
    """
    Generate a professional legal document draft using AI & statutory context.
    """
    try:
        # 1. Search for statutory context related to the document type
        query = f"Statutory provisions and formal drafting structure for {request.template_type.replace('_', ' ')} in India"
        stat_results = deps.vector_store.hybrid_search_statutory(query, top_k=5)
        
        # 2. Build generation prompt
        prompt = build_generation_prompt(request.template_type, request.form_data, stat_results)
        
        # 3. Call LLM
        answer = await call_llm(prompt, temperature=0.3, max_tokens=3000)
        answer = answer.strip()
        
        return {
            "status": "success",
            "document_draft": answer,
            "template": request.template_type,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[Document Gen] Error: {e}")
        # Fallback to a demo/structured draft if AI fails
        return {
            "status": "demo",
            "document_draft": f"IN THE COURT OF THE [DESIGNATION OF COURT] AT [LOCATION]\n\nCase No: [CASENO] of 2024\n\nIn the matter of: \n{request.form_data.get('petitioner_name', '[PETITIONER]')} ...Petitioner\n\nVERSUS\n\n{request.form_data.get('respondent_name', '[RESPONDENT]')} ...Respondent\n\nSubject: {request.template_type.replace('_', ' ').upper()} \n\nMOST RESPECTFULLY SHOWETH:\n\n1. That the petitioner is a law-abiding citizen of India.\n2. That the facts of the case are {request.form_data.get('facts', '[FACTS]')}.\n3. [ADDITIONAL GROUNDS BASED ON CONTEXT]\n\nPRAYER: Most respectfully prayed that this Hon'ble Court may be pleased to grant the relief as sought in the interest of justice.",
            "note": "Demo draft - server issue"
        }


def _get_demo_quiz(req: QuizRequest) -> dict:
    demos = {
        "Constitutional Law": [
            {"id": 1, "question": "Which Article of the Indian Constitution guarantees the Right to Equality?", "options": ["A) Article 12", "B) Article 14", "C) Article 19", "D) Article 21"], "correct_answer": "B", "explanation": "Article 14 guarantees equality before law and equal protection of laws. It embodies the concept of rule of law and prohibits class legislation while permitting reasonable classification.", "difficulty": req.difficulty, "topic_tag": "Fundamental Rights"},
            {"id": 2, "question": "The 'basic structure' doctrine was propounded in which landmark case?", "options": ["A) Golaknath v. State of Punjab", "B) Kesavananda Bharati v. State of Kerala", "C) Minerva Mills v. Union of India", "D) Maneka Gandhi v. Union of India"], "correct_answer": "B", "explanation": "In Kesavananda Bharati v. State of Kerala (1973), the Supreme Court held that Parliament's amending power under Article 368 does not extend to altering the basic structure of the Constitution.", "difficulty": req.difficulty, "topic_tag": "Constitutional Amendments"},
            {"id": 3, "question": "Which part of the Constitution deals with Directive Principles of State Policy?", "options": ["A) Part III", "B) Part IV", "C) Part IVA", "D) Part V"], "correct_answer": "B", "explanation": "Part IV (Articles 36-51) contains the Directive Principles of State Policy. Unlike Fundamental Rights (Part III), DPSPs are non-justiciable but fundamental in governance.", "difficulty": req.difficulty, "topic_tag": "DPSP"},
            {"id": 4, "question": "The concept of 'due process of law' was read into Article 21 in:", "options": ["A) A.K. Gopalan v. State of Madras", "B) Maneka Gandhi v. Union of India", "C) Olga Tellis v. Bombay Municipal Corporation", "D) Bachan Singh v. State of Punjab"], "correct_answer": "B", "explanation": "In Maneka Gandhi v. Union of India (1978), the Supreme Court expanded Article 21 by holding that 'procedure established by law' must be just, fair and reasonable — effectively reading in due process.", "difficulty": req.difficulty, "topic_tag": "Article 21"},
            {"id": 5, "question": "Residuary powers of legislation under the Indian Constitution belong to:", "options": ["A) State Legislature", "B) Concurrent List", "C) Parliament", "D) Local Bodies"], "correct_answer": "C", "explanation": "Under Article 248 read with Entry 97 of the Union List, residuary powers of legislation vest in Parliament. This is unlike the US Constitution where residuary powers lie with the states.", "difficulty": req.difficulty, "topic_tag": "Legislative Powers"},
        ],
        "IPC": [
            {"id": 1, "question": "Section 300 of IPC defines:", "options": ["A) Culpable Homicide", "B) Murder", "C) Attempt to Murder", "D) Grievous Hurt"], "correct_answer": "B", "explanation": "Section 300 IPC defines Murder. It specifies four clauses when culpable homicide amounts to murder. The distinction between murder (S.300) and culpable homicide not amounting to murder (S.299) is a key exam topic.", "difficulty": req.difficulty, "topic_tag": "Offences Against Body"},
            {"id": 2, "question": "Which section of IPC deals with the right of private defence?", "options": ["A) Section 96-106", "B) Section 76-85", "C) Section 107-120", "D) Section 34-38"], "correct_answer": "A", "explanation": "Sections 96-106 IPC cover the right of private defence of body and property. Section 96 states nothing is an offence done in exercise of private defence. Section 100 specifies when the right extends to causing death.", "difficulty": req.difficulty, "topic_tag": "General Exceptions"},
            {"id": 3, "question": "Criminal conspiracy is defined under which section?", "options": ["A) Section 107", "B) Section 120A", "C) Section 34", "D) Section 149"], "correct_answer": "B", "explanation": "Section 120A IPC defines criminal conspiracy as an agreement by two or more persons to do an illegal act or a legal act by illegal means. Section 120B prescribes the punishment.", "difficulty": req.difficulty, "topic_tag": "Criminal Conspiracy"},
            {"id": 4, "question": "The maxim 'actus non facit reum nisi mens sit rea' relates to:", "options": ["A) Strict liability", "B) Mens rea", "C) Res judicata", "D) Promissory estoppel"], "correct_answer": "B", "explanation": "This maxim means 'an act does not make a person guilty unless there is a guilty mind'. Mens rea is a fundamental principle of criminal law, embodied across IPC provisions.", "difficulty": req.difficulty, "topic_tag": "General Principles"},
            {"id": 5, "question": "Defamation under IPC is dealt with in:", "options": ["A) Section 499", "B) Section 503", "C) Section 415", "D) Section 463"], "correct_answer": "A", "explanation": "Section 499 IPC defines defamation — making or publishing an imputation concerning any person intending to harm, or knowing it would harm, that person's reputation. Section 500 prescribes punishment.", "difficulty": req.difficulty, "topic_tag": "Defamation"},
        ],
    }
    topic_questions = demos.get(req.topic, demos.get("Constitutional Law"))
    return {"questions": topic_questions[:req.num_questions]}


@router.post("/api/sandbox/moot-court")
async def moot_court_exchange(request: MootCourtRequest):
    """Moot Court simulator — AI plays opposing counsel and judge."""
    try:
        import json as json_module

        history_text = ""
        if request.history:
            for h in request.history[-4:]:
                history_text += f"\n[{h.get('role', 'unknown').upper()}]: {h.get('content', '')}\n"

        opposing = "respondent" if request.user_role == "petitioner" else "petitioner"

        prompt = f"""You are simulating an Indian {request.court_level} moot court proceeding.

CASE SCENARIO:
{request.case_scenario}

The student is arguing as the {request.user_role}. This is round {request.round_number}.

PREVIOUS EXCHANGES:
{history_text if history_text else "None — this is the opening round."}

STUDENT'S CURRENT ARGUMENT ({request.user_role.upper()}):
{request.user_argument}

Respond in VALID JSON ONLY (no markdown, no code fences):

{{
  "opposing_counsel": {{
    "argument": "<2-3 sentence counter-argument from {opposing}'s side>",
    "objections": ["<objection if any>"],
    "authorities_cited": ["<case or section cited>"]
  }},
  "judge_observations": {{
    "questions_to_student": ["<probing question 1>", "<probing question 2>"],
    "observations": "<1-2 sentence observation on the strength of arguments>",
    "ruling_hint": "<hint about which way the court is leaning>"
  }},
  "scoring": {{
    "argument_strength": <1-10>,
    "legal_reasoning": <1-10>,
    "citation_quality": <1-10>,
    "persuasiveness": <1-10>,
    "overall": <1-10>,
    "feedback": "<specific constructive feedback for the student>"
  }},
  "suggested_rebuttal_points": ["<point 1>", "<point 2>"]
}}

Be realistic, educational, and provide constructive feedback. Cite real Indian cases and statutes.
"""
        raw = await call_llm(prompt, temperature=0.5, max_tokens=2000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        result = json_module.loads(raw)
        return {"status": "success", "result": result}

    except Exception as e:
        print(f"[Moot Court] Error: {e}")
        return {
            "status": "demo",
            "result": _get_demo_moot_response(request),
            "note": "Demo response — AI service unavailable"
        }


def _get_demo_moot_response(req: MootCourtRequest) -> dict:
    opposing = "respondent" if req.user_role == "petitioner" else "petitioner"
    return {
        "opposing_counsel": {
            "argument": f"The learned {opposing} respectfully submits that the {req.user_role}'s argument, while creative, overlooks settled jurisprudence. The precedent cited is distinguishable on facts and the statutory interpretation urged is contrary to legislative intent.",
            "objections": ["The argument assumes facts not in evidence", "Misapplication of the cited precedent"],
            "authorities_cited": ["State of Maharashtra v. Indian Hotel & Restaurants (2013) 6 SCC 568", "Section 397 CrPC — Revisional jurisdiction"]
        },
        "judge_observations": {
            "questions_to_student": [
                "Counsel, how do you distinguish the Supreme Court's observation in the cited precedent from the facts of the present case?",
                "What is the specific statutory provision that confers jurisdiction on this court to grant the relief you seek?"
            ],
            "observations": "The court notes that both sides have raised interesting points of law. However, the petitioner's reliance on constitutional provisions requires stronger factual foundation.",
            "ruling_hint": "The court is inclined to examine the procedural aspects more closely before addressing the merits."
        },
        "scoring": {
            "argument_strength": 7,
            "legal_reasoning": 6,
            "citation_quality": 5,
            "persuasiveness": 7,
            "overall": 6,
            "feedback": "Good foundational argument but needs stronger citation support. Consider citing specific Supreme Court judgments and connecting the ratio decidendi directly to your factual matrix. Also address potential counter-arguments pre-emptively."
        },
        "suggested_rebuttal_points": [
            "Distinguish the opposing counsel's cited case on its specific factual matrix",
            "Invoke the constitutional angle under Article 21 to strengthen your position",
            "Address the procedural objection by citing the court's inherent powers under Section 482 CrPC"
        ]
    }


