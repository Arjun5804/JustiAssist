"""
JustiAssist Bail Evaluation Agent
Core contribution: Specialized bail assessment with legal heuristics and LLM reasoning
"""

import re
import json
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field




class BailLikelihood(Enum):
    """Bail likelihood categories"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNCERTAIN = "Uncertain"


@dataclass
class BailEvaluation:
    """Structured bail evaluation result"""
    bail_likelihood: BailLikelihood
    legal_reasoning: Dict[str, Any]
    precedent_references: List[Dict[str, str]]
    explanation: str
    confidence_score: float
    applicable_sections: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bail_likelihood": self.bail_likelihood.value,
            "legal_reasoning": self.legal_reasoning,
            "precedent_references": self.precedent_references,
            "explanation": self.explanation,
            "confidence_score": self.confidence_score,
            "applicable_sections": self.applicable_sections
        }


class BailEvaluator:
    """
    Bail Evaluation Agent - Core contribution of JustiAssist.
    
    Combines:
    1. Rule-based legal heuristics (bailable/non-bailable classification)
    2. LLM reasoning with retrieved context
    3. Precedent analysis
    
    Input:
    - Relevant IPC/BNS sections
    - CrPC bail provisions
    - Similar bail precedents
    - User-provided factors (custody duration, offence severity)
    
    Output:
    - Structured bail assessment with citations
    """
    
    # First Schedule CrPC: Bailable offenses (simplified list)
    BAILABLE_SECTIONS = {
        # IPC bailable offenses (punishment <= 3 years generally)
        'IPC_279', 'IPC_280', 'IPC_283', 'IPC_285', 'IPC_286', 'IPC_289',
        'IPC_290', 'IPC_294', 'IPC_294A', 'IPC_323', 'IPC_334', 'IPC_341',
        'IPC_352', 'IPC_355', 'IPC_358', 'IPC_426', 'IPC_428', 'IPC_447',
        'IPC_448', 'IPC_489E', 'IPC_500', 'IPC_504', 'IPC_506', 'IPC_509',
        'IPC_510',
    }
    
    # Non-bailable serious offenses
    NON_BAILABLE_SECTIONS = {
        # Murder and serious harm
        'IPC_302', 'IPC_303', 'IPC_304', 'IPC_304A', 'IPC_304B',
        'IPC_307', 'IPC_308', 'IPC_326', 'IPC_326A', 'IPC_326B',
        
        # Sexual offenses
        'IPC_376', 'IPC_376A', 'IPC_376AB', 'IPC_376B', 'IPC_376C',
        'IPC_376D', 'IPC_376DA', 'IPC_376DB', 'IPC_376E',
        'IPC_354', 'IPC_354A', 'IPC_354B', 'IPC_354C', 'IPC_354D',
        
        # Kidnapping and trafficking
        'IPC_363', 'IPC_363A', 'IPC_364', 'IPC_364A', 'IPC_365',
        'IPC_366', 'IPC_366A', 'IPC_366B', 'IPC_367', 'IPC_368',
        'IPC_370', 'IPC_370A', 'IPC_371', 'IPC_372', 'IPC_373',
        
        # Robbery and dacoity
        'IPC_392', 'IPC_393', 'IPC_394', 'IPC_395', 'IPC_396',
        'IPC_397', 'IPC_398', 'IPC_399', 'IPC_400', 'IPC_401', 'IPC_402',
        
        # Serious property crimes
        'IPC_420', 'IPC_467', 'IPC_468', 'IPC_471',
        'IPC_489A', 'IPC_489B', 'IPC_489C', 'IPC_489D',
        
        # Offenses against state
        'IPC_121', 'IPC_121A', 'IPC_122', 'IPC_123', 'IPC_124A',
    }
    
    # Punishment severity mapping
    PUNISHMENT_SEVERITY = {
        'death': 10,
        'life imprisonment': 9,
        'imprisonment for life': 9,
        '10 years': 8,
        '7 years': 7,
        '5 years': 6,
        '3 years': 5,
        '2 years': 4,
        '1 year': 3,
        '6 months': 2,
        '3 months': 1,
        'fine': 0,
    }
    
    def __init__(self):
        pass
    
    async def evaluate(
        self,
        query: str,
        statutory_context: List[Dict[str, Any]],
        bail_precedents: List[Dict[str, Any]],
        custody_duration_days: Optional[int] = None,
        offence_sections: Optional[List[str]] = None
    ) -> BailEvaluation:
        """
        Evaluate bail likelihood for a case.
        
        Args:
            query: User's bail-related query
            statutory_context: Retrieved IPC/CrPC/BNS sections
            bail_precedents: Retrieved bail judgment precedents
            custody_duration_days: Days in custody (if provided)
            offence_sections: Specific IPC sections charged (if provided)
        
        Returns:
            BailEvaluation with structured assessment
        """
        # Step 1: Rule-based analysis
        rule_based_result = self._apply_legal_heuristics(
            statutory_context,
            offence_sections,
            custody_duration_days
        )
        
        # Step 2: LLM reasoning with context
        llm_analysis = await self._llm_analysis(
            query,
            statutory_context,
            bail_precedents,
            rule_based_result
        )
        
        # Step 3: Combine and structure output
        return self._combine_analysis(
            rule_based_result,
            llm_analysis,
            bail_precedents
        )
    
    def _apply_legal_heuristics(
        self,
        statutory_context: List[Dict[str, Any]],
        offence_sections: Optional[List[str]],
        custody_duration_days: Optional[int]
    ) -> Dict[str, Any]:
        """
        Apply rule-based legal heuristics.
        
        Rules based on CrPC:
        - Section 436: Bailable offenses - bail as right
        - Section 437: Non-bailable by Magistrate
        - Section 438: Anticipatory bail
        - Section 439: Bail by High Court/Sessions Court
        """
        result = {
            'bailable_status': 'Unknown',
            'max_punishment': 'Unknown',
            'severity_score': 5,  # Default medium
            'recommendation': '',
            'applicable_crpc': [],
            'factors': []
        }
        
        # Analyze sections from context
        detected_sections = set()
        for ctx in statutory_context:
            section = ctx.get('section_number', '')
            if section:
                detected_sections.add(section.upper())
        
        # Add user-provided sections
        if offence_sections:
            for s in offence_sections:
                detected_sections.add(s.upper())
        
        # Check bailable status
        is_bailable = False
        is_non_bailable = False
        
        for section in detected_sections:
            # Normalize section format
            norm_section = section.replace(' ', '_').replace('-', '_')
            if not norm_section.startswith('IPC_'):
                norm_section = f"IPC_{norm_section}"
            
            if norm_section in self.BAILABLE_SECTIONS:
                is_bailable = True
            if norm_section in self.NON_BAILABLE_SECTIONS:
                is_non_bailable = True
        
        if is_non_bailable:
            result['bailable_status'] = 'Non-bailable'
            result['applicable_crpc'] = ['CrPC Section 437', 'CrPC Section 439']
            result['severity_score'] = 8
        elif is_bailable:
            result['bailable_status'] = 'Bailable'
            result['applicable_crpc'] = ['CrPC Section 436']
            result['severity_score'] = 2
        else:
            result['bailable_status'] = 'Requires case-specific analysis'
            result['applicable_crpc'] = ['CrPC Section 437', 'CrPC Section 438']
        
        # Analyze punishment from context
        # FIXED: Only look for punishment in sections that were actually DETECTED as relevant
        # or in User Evidence chunks
        
        relevant_texts = []
        for ctx in statutory_context:
            is_evidence = ctx.get('law_type') == 'User Evidence'
            is_procedural = ctx.get('law_type', '').upper() in ('CRPC', 'BNSS')
            section = ctx.get('section_number', '').upper()
            
            # Normalize section to check against detected set
            norm_sec = section.replace(' ', '_').replace('-', '_')
            if not norm_sec.startswith('IPC_'):
                norm_sec = f"IPC_{norm_sec}"
            
            # Include text if it's User Evidence OR if it matches a relevant section
            # (Partial match check for robustness, e.g. IPC_302 matching IPC_302_PUNISHMENT)
            should_scan = is_evidence
            if not should_scan:
                for detected in detected_sections:
                    if detected in norm_sec or norm_sec in detected:
                        should_scan = True
                        break
            
            # CRITICAL FIX: Never scan procedural laws for punishment. They only mention 
            # 'death' in abstract contexts (e.g. 'if offense is punishable by death').
            if should_scan and not is_procedural:
                relevant_texts.append(ctx.get('text', '').lower())

        # Scan only filtered text
        for text in relevant_texts:
            for punishment, severity in self.PUNISHMENT_SEVERITY.items():
                if punishment in text:
                    if severity > result['severity_score']:
                        result['max_punishment'] = punishment
                        result['severity_score'] = severity
        
        # Consider custody duration
        if custody_duration_days is not None:
            result['factors'].append(f"Custody duration: {custody_duration_days} days")
            
            # Maximum detention limits under CrPC 167
            if is_non_bailable and custody_duration_days > 90:
                result['factors'].append(
                    "Exceeded 90-day limit for non-bailable offenses (CrPC 167) - "
                    "may be entitled to 'default bail'"
                )
                result['severity_score'] = max(result['severity_score'] - 2, 2)
            elif custody_duration_days > 60:
                result['factors'].append("Extended custody may favor bail consideration")
        
        # Generate recommendation
        if result['severity_score'] <= 3:
            result['recommendation'] = 'Bail likely to be granted'
        elif result['severity_score'] <= 5:
            result['recommendation'] = 'Bail possible with conditions'
        elif result['severity_score'] <= 7:
            result['recommendation'] = 'Bail difficult but not impossible'
        else:
            result['recommendation'] = 'Bail challenging due to offense severity'
        
        return result

    async def _llm_analysis(
        self,
        query: str,
        statutory_context: List[Dict[str, Any]],
        bail_precedents: List[Dict[str, Any]],
        rule_based_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM for nuanced bail analysis.
        """
        # Separate Authoritative Law vs User Evidence
        authoritative_law = []
        user_evidence = []
        
        for ctx in statutory_context:
            if ctx.get('law_type') == 'User Evidence':
                user_evidence.append(ctx)
            else:
                authoritative_law.append(ctx)
        
        # Format Authoritative Law
        law_text = "\n\n".join([
            f"[{ctx.get('law_type', 'Law')} - {ctx.get('section_number', 'Section')}]\n{ctx.get('text', '')[:600]}"
            for ctx in authoritative_law[:8]
        ])
        
        # Format User Evidence (Uploaded Docs)
        evidence_text = ""
        if user_evidence:
            evidence_text = "USER UPLOADED EVIDENCE (CASE FACTS):\n" + "\n\n".join([
                f"[Document: {ctx.get('section_number').replace('UPLOADED: ', '')}]\n{ctx.get('text', '')}"
                for ctx in user_evidence
            ])
        else:
            evidence_text = "USER UPLOADED EVIDENCE: None provided."

        # Format Precedents
        precedent_text = "\n\n".join([
            f"[Precedent: {p.get('metadata', {}).get('case_title', 'Case')}]\n{p.get('text', '')[:400]}"
            for p in bail_precedents[:3]
        ])
        
        # Heuristic display logic: Only show severity if confidence is high or relevant
        heuristic_display = ""
        if rule_based_result['max_punishment'] != 'Unknown':
            heuristic_display += f"- Detected Max Punishment (Statutory): {rule_based_result['max_punishment']}\n"
        if rule_based_result['bailable_status'] != 'Unknown':
             heuristic_display += f"- Offense Status: {rule_based_result['bailable_status']}\n"
        
        prompt = f"""You are an expert legal assistant for Indian criminal law. Analyze this bail query.

USER QUERY: {query}

{evidence_text}

RELEVANT STATUTORY PROVISIONS:
{law_text}

RELEVANT BAIL PRECEDENTS:
{precedent_text if precedent_text else "No specific precedents retrieved."}

RULE-BASED ANALYSIS (For Reference):
{heuristic_display}

INSTRUCTIONS:
1. **Analyze Evidence**: If 'USER UPLOADED EVIDENCE' contains court orders or specific facts, give them highest priority.
2. **Determine Status**: Explicitly state if bail is "Granted", "Likely", or "Unlikely".
3. **Format**: Use the STRICT structure below.

RESPONSE FORMAT:
## ⚖️ Bail Assessment

**Likelihood**: [High / Medium / Low / Granted]
**Analysis Status**: [e.g., Based on Court Order / Based on Statutory Rules]

### 📋 Key Reasoning
- [Point 1: Cite specific section or document]
- [Point 2]

### ⚠️ Risks & Factors
- [Aggravating factors if any]
- [Mitigating factors]

### 💡 Recommendation
[Specific, actionable advice for the applicant]
"""

        try:
            response = await self._call_llm(prompt)
            return {
                'llm_response': response,
                'success': True
            }
        except Exception as e:
            return {
                'llm_response': f"Unable to generate LLM analysis: {str(e)}",
                'success': False
            }

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM using centralized provider"""
        from llm_provider import call_llm
        return await call_llm(prompt)

    def _combine_analysis(
        self,
        rule_based: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        precedents: List[Dict[str, Any]]
    ) -> BailEvaluation:
        """Combine rule-based and LLM analysis into final evaluation"""
        
        llm_text = llm_analysis.get('llm_response', '')
        
        # INTELLIGENT OVERRIDE: Parse LLM's conclusion to determine actual status
        # This fixes the mismatch between LLM text and UI card
        
        # Default values from heuristics
        severity = rule_based['severity_score']
        max_punishment = rule_based['max_punishment']
        bailable_status = rule_based['bailable_status']
        likelihood = BailLikelihood.LOW
        
        # Check LLM's actual conclusion and override contradictory heuristics
        if "Likelihood: Granted" in llm_text or "Likelihood**: Granted" in llm_text:
            likelihood = BailLikelihood.HIGH
            severity = 1  # Bail was granted, so severity is minimal
            max_punishment = "N/A (Bail Granted)"
            bailable_status = "Bail Granted by Court"
        elif "Likelihood: High" in llm_text or "Likelihood**: High" in llm_text:
            likelihood = BailLikelihood.HIGH
            severity = min(severity, 3)  # Cap severity for high likelihood
            if max_punishment == "death":
                max_punishment = "Case-specific"  # Don't show misleading "death"
        elif "Likelihood: Medium" in llm_text or "Likelihood**: Medium" in llm_text:
            likelihood = BailLikelihood.MEDIUM
            severity = min(severity, 6)
        elif "Likelihood: Low" in llm_text or "Likelihood**: Low" in llm_text:
            likelihood = BailLikelihood.LOW
        else:
            # Fallback to heuristic-based calculation
            if severity <= 3:
                likelihood = BailLikelihood.HIGH
            elif severity <= 5:
                likelihood = BailLikelihood.MEDIUM
            else:
                likelihood = BailLikelihood.LOW
        
        # Calculate confidence
        confidence = 0.7
        if "Granted" in llm_text:
            confidence = 0.95
        elif bailable_status != 'Unknown':
            confidence += 0.1
        confidence = min(confidence, 0.95)
        
        # Format precedent references
        precedent_refs = []
        for p in precedents[:3]:
            precedent_refs.append({
                'case_name': p.get('metadata', {}).get('case_title', 'Unknown Case'),
                'relevance': f"Score: {p.get('score', 0):.2f}"
            })
        
        # CLEAN EXPLANATION: Use the LLM output as the primary explanation
        explanation = llm_text
        
        # Append disclaimer if not present
        if "DISCLAIMER" not in explanation:
            explanation += "\n\nDISCLAIMER: This is an AI-generated assessment for informational purposes only. Please consult a qualified advocate."
            
        return BailEvaluation(
            bail_likelihood=likelihood,
            legal_reasoning={
                'bailable_status': bailable_status,
                'max_punishment': max_punishment,
                'severity_score': severity,
                'applicable_crpc': rule_based['applicable_crpc'],
                'factors': rule_based['factors']
            },
            precedent_references=precedent_refs,
            explanation=explanation,
            confidence_score=confidence,
            applicable_sections=rule_based['applicable_crpc']
        )


if __name__ == "__main__":
    # Test the bail evaluator
    evaluator = BailEvaluator()
    
    # Mock context
    mock_statutory = [
        {
            'law_type': 'IPC',
            'section_number': 'IPC_379',
            'text': 'Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.'
        },
        {
            'law_type': 'CrPC',
            'section_number': 'CrPC_436',
            'text': 'When any person other than a person accused of a non-bailable offence is arrested or detained without warrant by an officer in charge of a police station, or appears or is brought before a Court, and is prepared at any time while in the custody of such officer or at any stage of the proceeding before such Court to give bail, such person shall be released on bail.'
        }
    ]
    
    mock_precedents = [
        {
            'text': 'In the case of State vs. certain accused, the court granted bail considering the nature of offense and period of custody...',
            'score': 0.75,
            'metadata': {'case_title': 'State vs. XYZ (2023)'}
        }
    ]
    
    import asyncio
    async def run_test():
        result = await evaluator.evaluate(
            query="Can I get bail for theft charge after 45 days in custody?",
            statutory_context=mock_statutory,
            bail_precedents=mock_precedents,
            custody_duration_days=45,
            offence_sections=['IPC_379']
        )
        print("="*60)
        print("BAIL EVALUATION RESULT")
        print("="*60)
        print(f"Likelihood: {result.bail_likelihood.value}")
        print(f"Confidence: {result.confidence_score:.2f}")
        print(f"\nLegal Reasoning: {json.dumps(result.legal_reasoning, indent=2)}")
        print(f"\nExplanation:\n{result.explanation}")
    
    asyncio.run(run_test())
