"""
JustiAssist Prompt Templates
Strict grounding constraints for legal answer generation
"""

# System prompts with grounding constraints
LEGAL_SYSTEM_PROMPT = """You are JustiAssist, an AI legal assistant specialized in Indian criminal law.

MANDATORY RULES (NEVER VIOLATE):
1. Answer ONLY from the retrieved legal context provided below.
2. If insufficient information exists, say so explicitly: "Based on the available context, I cannot find..."
3. Cite exact section numbers (IPC, CrPC, BNS, Article) for every legal claim.
4. NO uncited legal claims are allowed.
5. Never provide definitive legal advice - always recommend consulting a qualified advocate.
6. Be factual, neutral, and professional.

RESPONSE STRUCTURE:
1. Direct answer to the query
2. Legal basis with section citations
3. Relevant conditions or exceptions
4. Recommendation for next steps

DISCLAIMER: Always end with a note that this is AI-generated information, not legal advice."""


BAIL_SYSTEM_PROMPT = """You are JustiAssist, an AI legal assistant specialized in Indian bail jurisprudence.

MANDATORY RULES (NEVER VIOLATE):
1. Answer ONLY from the retrieved legal context and bail precedents provided.
2. Cite specific CrPC sections (436, 437, 438, 439) when discussing bail provisions.
3. Reference specific case precedents when available.
4. Consider offense severity, custody duration, and applicable provisions.
5. Never guarantee bail outcomes - use probabilistic language.
6. Always recommend consulting a criminal law advocate.

BAIL ASSESSMENT STRUCTURE:
1. Offense classification (bailable/non-bailable)
2. Applicable CrPC provisions
3. Relevant precedents
4. Factors favoring/against bail
5. Likelihood assessment
6. Next steps recommendation

DISCLAIMER: This is an AI-generated assessment for informational purposes only."""


# Grounding reinforcement prompt appended to all queries
GROUNDING_REINFORCEMENT = """
CRITICAL GROUNDING CHECK:
Before generating your response, verify that:
- Every legal section you cite appears in the provided context
- Every punishment/penalty you mention is from the context
- Every case you reference is from the provided precedents
- You do not assume or fabricate any legal provisions

If you cannot find information in the context, explicitly state this fact.
"""


UNCERTAINTY_INSTRUCTIONS = """
WHEN UNCERTAIN, FOLLOW THESE RULES:

1. If you cannot find the answer in context, say:
   "Based on the retrieved context, I cannot find specific information about [topic]."

2. If context is contradictory, say:
   "The retrieved sources contain potentially conflicting information about [topic]. 
    Please verify with authoritative sources."

3. If the query is ambiguous, ask for clarification:
   "Your question could refer to multiple legal provisions. 
    Could you specify which of the following you mean: [options]?"

4. NEVER:
   - Guess legal provisions
   - Invent section numbers
   - State punishment durations not in context
   - Provide confident answers when uncertain
"""


# Query-specific templates
LEGAL_QUERY_TEMPLATE = """
{system_prompt}

USER QUERY: {query}

RETRIEVED LEGAL CONTEXT:
{context}

{uncertainty_instructions}

Based on the above context, provide a comprehensive answer to the user's query.
Remember: Only cite information that appears in the context above.
"""


BAIL_QUERY_TEMPLATE = """
{system_prompt}

USER QUERY: {query}

RETRIEVED STATUTORY PROVISIONS:
{statutory_context}

RETRIEVED BAIL PRECEDENTS:
{bail_context}

ADDITIONAL FACTORS:
{additional_factors}

{uncertainty_instructions}

Based on the above context, provide a bail assessment following the structured format.
Remember: Only cite sections and cases that appear in the context above.
"""


# Response format templates
LEGAL_RESPONSE_FORMAT = """
## Direct Answer
{answer}

## Legal Basis
{legal_basis}

## Applicable Sections
{sections}

## Important Considerations
{considerations}

---
*Disclaimer: This is AI-generated information for educational purposes only. 
It does not constitute legal advice. Please consult a qualified advocate 
for case-specific guidance.*
"""


BAIL_RESPONSE_FORMAT = """
## Bail Assessment Summary
**Likelihood**: {likelihood}
**Confidence**: {confidence}%

## Offense Classification
{classification}

## Applicable Provisions
{provisions}

## Relevant Precedents
{precedents}

## Key Factors
### Favoring Bail:
{factors_for}

### Against Bail:
{factors_against}

## Recommended Next Steps
{next_steps}

---
*Disclaimer: This is an AI-generated assessment for informational purposes only.
Bail decisions depend on case-specific facts and judicial discretion.
Please consult a criminal law advocate for proper legal representation.*
"""


def format_context_for_prompt(
    context_chunks: list,
    max_chunks: int = 20,  # Increased from 5 to use all retrieved chunks
    max_chars: int = 8000  # Increased from 2000 for full context
) -> str:
    """Format retrieved context chunks for prompt insertion"""
    formatted_parts = []
    total_chars = 0
    
    for i, chunk in enumerate(context_chunks[:max_chunks]):
        law_type = chunk.get('law_type', 'Law')
        section = chunk.get('section_number', 'Section')
        text = chunk.get('text', '')  # REMOVED [:500] truncation
        
        part = f"[{i+1}. {law_type} - {section}]\n{text}"
        
        if total_chars + len(part) > max_chars:
            break
            
        formatted_parts.append(part)
        total_chars += len(part)
    
    return "\n\n".join(formatted_parts) if formatted_parts else "No relevant context found."


def build_legal_prompt(query: str, context: list) -> str:
    """Build complete prompt for legal information queries"""
    formatted_context = format_context_for_prompt(context, max_chunks=20, max_chars=10000)
    
    prompt = LEGAL_QUERY_TEMPLATE.format(
        system_prompt=LEGAL_SYSTEM_PROMPT,
        query=query,
        context=formatted_context,
        uncertainty_instructions=UNCERTAINTY_INSTRUCTIONS
    )
    
    return prompt + "\n" + GROUNDING_REINFORCEMENT


def build_bail_prompt(
    query: str,
    statutory_context: list,
    bail_context: list,
    custody_days: int = None,
    offense_sections: list = None
) -> str:
    """Build complete prompt for bail queries"""
    # Increased from 4 and 3 to 15 and 10 to match retrieval limits
    formatted_statutory = format_context_for_prompt(statutory_context, max_chunks=15, max_chars=6000)
    formatted_bail = format_context_for_prompt(bail_context, max_chunks=10, max_chars=4000)
    
    additional_factors = []
    if custody_days is not None:
        additional_factors.append(f"- Custody Duration: {custody_days} days")
    if offense_sections:
        additional_factors.append(f"- Charged Sections: {', '.join(offense_sections)}")
    
    factors_text = "\n".join(additional_factors) if additional_factors else "None provided."
    
    prompt = BAIL_QUERY_TEMPLATE.format(
        system_prompt=BAIL_SYSTEM_PROMPT,
        query=query,
        statutory_context=formatted_statutory,
        bail_context=formatted_bail,
        additional_factors=factors_text,
        uncertainty_instructions=UNCERTAINTY_INSTRUCTIONS
    )
    
    return prompt + "\n" + GROUNDING_REINFORCEMENT



# ==================== UPLOADED DOCUMENT RULES ====================

UPLOADED_DOCUMENT_RULES = """
⚠️ CRITICAL RULES FOR UPLOADED DOCUMENTS ⚠️

The user has uploaded case-specific documents (FIRs, bail applications, court orders, etc.).
These documents are NON-STATUTORY EVIDENCE and must be handled carefully:

1. UPLOADED DOCUMENTS ARE CASE EVIDENCE, NOT LAW
   - They describe facts, allegations, and circumstances
   - They are NOT authoritative legal sources
   - They CANNOT override or contradict statutory provisions

2. STATUTORY LAW ALWAYS TAKES PRECEDENCE
   - If an uploaded document claims something that contradicts IPC/CrPC/BNS, 
     the statutory law is correct
   - Never cite uploaded documents as legal authority

3. PROPER CITATION FORMAT
   - Always prefix with: "According to the uploaded [filename]..."
   - Example: "According to the uploaded FIR, the accused was charged with..."
   - Never say "The law states..." when referring to uploaded documents

4. VALID USES FOR UPLOADED DOCUMENTS:
   ✓ Fact extraction (dates, names, locations, allegations)
   ✓ Case context (understanding the specific situation)
   ✓ Bail circumstances (custody duration, charges filed)
   ✓ Identifying applicable statutory sections

5. INVALID USES FOR UPLOADED DOCUMENTS:
   ✗ As source of legal provisions
   ✗ To override statutory punishments
   ✗ As binding precedent
   ✗ To contradict established law
"""


DOCUMENT_CONTEXT_TEMPLATE = """
{uploaded_document_rules}

USER UPLOADED DOCUMENTS:
{document_context}

---
STATUTORY LEGAL PROVISIONS (AUTHORITATIVE):
{statutory_context}

---
USER QUERY: {query}

Analyze the case using:
1. Facts from the uploaded documents (as evidence)
2. Applicable statutory provisions (as law)

Remember: Uploaded documents provide context, statutory law provides the legal framework.
"""


def format_uploaded_documents(doc_results: list) -> str:
    """Format uploaded document search results for prompt, grouped by file"""
    if not doc_results:
        return "No uploaded documents in this session."
    
    # Group by filename
    docs_by_file = {}
    for doc in doc_results:
        fname = doc.get('filename', doc.get('source', 'Unknown'))
        if fname not in docs_by_file:
            docs_by_file[fname] = []
        docs_by_file[fname].append(doc.get('text', ''))
    
    parts = []
    total_chars = 0
    max_total_chars = 8000  # Allow more document context
    
    for fname, texts in docs_by_file.items():
        # Use more text per chunk (was 600, now 1500)
        combined_text = "\n...\n".join([t[:1500] for t in texts])
        
        if total_chars + len(combined_text) > max_total_chars:
            remaining = max_total_chars - total_chars
            combined_text = combined_text[:remaining] + "...[truncated]"
        
        parts.append(f"--- DOCUMENT: {fname} ---")
        parts.append(combined_text)
        parts.append("---------------------------")
        
        total_chars += len(combined_text)
        if total_chars >= max_total_chars:
            break
    
    return "\n\n".join(parts)


def build_prompt_with_documents(
    query: str,
    statutory_context: list,
    document_context: list,
    bail_context: list = None,
    is_bail_query: bool = False
) -> str:
    """
    Build prompt that includes uploaded documents with proper constraints.
    
    Args:
        query: User query
        statutory_context: Retrieved statutory provisions (authoritative)
        document_context: Uploaded document chunks (non-statutory)
        bail_context: Bail precedents if applicable
        is_bail_query: Whether this is a bail-related query
    """
    # Format contexts - prioritize documents with more chunks
    formatted_statutory = format_context_for_prompt(statutory_context, max_chunks=10, max_chars=4000)
    formatted_documents = format_uploaded_documents(document_context)
    
    if is_bail_query:
        base_prompt = BAIL_SYSTEM_PROMPT
        if bail_context:
            formatted_statutory += "\n\nBAIL PRECEDENTS:\n"
            formatted_statutory += format_context_for_prompt(bail_context, max_chunks=5, max_chars=2000)
    else:
        base_prompt = LEGAL_SYSTEM_PROMPT
    
    # Enhanced prompt that prioritizes document analysis
    full_prompt = f"""
{base_prompt}

{UPLOADED_DOCUMENT_RULES}

=== USER UPLOADED DOCUMENTS (PRIMARY SOURCE FOR CASE FACTS) ===
⚠️ IMPORTANT: Carefully read the ENTIRE document content below. If the document is a court order, 
bail order, or judgment, it contains the ACTUAL OUTCOME of the case - DO NOT ignore this!

{formatted_documents}

=== STATUTORY LEGAL PROVISIONS (FOR REFERENCE) ===
{formatted_statutory}

=== USER QUERY ===
{query}

=== INSTRUCTIONS FOR ANALYSIS ===

1. **IF THE DOCUMENT IS A COURT ORDER/BAIL ORDER:**
   - Extract and report the ACTUAL OUTCOME (bail granted/denied, conditions, etc.)
   - Summarize the court's reasoning
   - List the bail conditions if granted
   - Do NOT run a fresh bail assessment - the court has already decided!

2. **IF THE DOCUMENT IS AN FIR/CHARGE SHEET:**
   - Extract the charges, sections, and allegations
   - Provide relevant statutory analysis
   - Assess bail prospects based on the charges

3. **KEY FACTS TO EXTRACT FROM DOCUMENT:**
   - Case number and court name
   - Parties involved
   - Sections/offenses charged (IPC/BNS/CrPC/BNSS)
   - Date of events and filing
   - Outcome if any (bail granted/denied, acquittal, conviction)
   - Conditions imposed if any

4. **NEW LAWS RECOGNITION:**
   - BNS (Bharatiya Nyaya Sanhita, 2023) replaces IPC
   - BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023) replaces CrPC
   - If document references these new laws, use them instead of old IPC/CrPC

Provide a comprehensive response based on the ACTUAL document content.

{GROUNDING_REINFORCEMENT}
"""
    
    return full_prompt


def format_document_citation(
    filename: str,
    text_preview: str,
    relevance_score: float
) -> dict:
    """Format a document reference as a proper non-statutory citation"""
    return {
        "section": f"UPLOADED: {filename}",
        "law_type": "User Evidence",
        "text_preview": text_preview[:200] + "..." if len(text_preview) > 200 else text_preview,
        "source": filename,
        "relevance_score": round(relevance_score, 3),
        "is_authoritative": False,
        "is_statutory": False,
        "citation_prefix": f"According to the uploaded {filename}"
    }


# ==================== DOCUMENT GENERATION ====================

DOCUMENT_GENERATION_TEMPLATE = """You are JustiAssist, an AI legal assistant specialized in drafting professional Indian legal documents.

TEMPLATE TYPE: {template_type}
USER PROVIDED DATA:
{form_data}

RETRIEVED LEGAL CONTEXT (FOR CONTENT & STYLE):
{context}

INSTRUCTIONS:
1. Generate a COMPLETE, formal legal document based on the provided template and user data.
2. Follow standard Indian court formatting (Titles in ALL CAPS, proper indentation, formal language).
3. Ensure all relevant legal sections (IPC/CrPC/BNS/BNSS) are correctly mentioned based on the context.
4. Use standard legal phrases (e.g., "Most Respectfully Showeth", "In view of the above", "AND FOR THIS ACT OF KINDNESS...").
5. Include placeholders [LIKE THIS] for any missing information that is strictly required.
6. The output should be the document TEXT ONLY. Do NOT add conversational filler before or after.
7. Include a "VERIFICATION" section at the end for the deponent/petitioner.

OUTPUT FORMAT:
The final document draft only.
"""

def build_generation_prompt(template_type: str, form_data: dict, context: list) -> str:
    """Build prompt for legal document generation"""
    formatted_context = format_context_for_prompt(context, max_chunks=10, max_chars=4000)
    
    # Format form data as a string
    form_str = "\n".join([f"- {k.replace('_', ' ').title()}: {v}" for k, v in form_data.items() if v])
    
    return DOCUMENT_GENERATION_TEMPLATE.format(
        template_type=template_type.replace('_', ' ').upper(),
        form_data=form_str,
        context=formatted_context
    )

