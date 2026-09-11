"""
JustiAssist Query Reformulator Agent
Enhances queries for better retrieval by expanding terms and extracting legal references
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ReformulatedQuery:
    """Result of query reformulation"""
    original_query: str
    enhanced_query: str
    extracted_sections: List[str]
    extracted_law_types: List[str]
    search_terms: List[str]
    metadata_filters: Dict[str, str]


class QueryReformulator:
    """
    Enhances user queries for better legal document retrieval.
    
    Functions:
    1. Expands legal acronyms (IPC, CrPC, BNS)
    2. Extracts section numbers
    3. Identifies law types for filtering
    4. Generates alternative search terms
    """
    
    # Comprehensive legal acronym expansions (50+ terms)
    ACRONYMS = {
        # Primary Laws
        'ipc': 'Indian Penal Code',
        'crpc': 'Code of Criminal Procedure',
        'cr.p.c': 'Code of Criminal Procedure',
        'cr.pc': 'Code of Criminal Procedure',
        'bnss': 'Bharatiya Nagarik Suraksha Sanhita',
        'bns': 'Bharatiya Nyaya Sanhita',
        'bsa': 'Bharatiya Sakshya Adhiniyam',
        'cpc': 'Code of Civil Procedure',
        
        # Courts & Legal Entities
        'sc': 'Supreme Court',
        'hc': 'High Court',
        'dc': 'District Court',
        'sessions court': 'Court of Sessions',
        
        # Legal Proceedings
        'fir': 'First Information Report',
        'pil': 'Public Interest Litigation',
        'slp': 'Special Leave Petition',
        'writ': 'Writ Petition',
        'appeal': 'Criminal Appeal',
        'revision': 'Revision Petition',
        'chargesheet': 'Charge Sheet',
        
        # Bail Related
        'ab': 'Anticipatory Bail',
        'regular bail': 'Regular Bail',
        'interim bail': 'Interim Bail',
        'default bail': 'Statutory Bail',
        
        # Legal Terms
        'sec': 'Section',
        'art': 'Article',
        'cls': 'Clause',
        'para': 'Paragraph',
        'sch': 'Schedule',
        'r/w': 'read with',
        'u/s': 'under section',
        'vs': 'versus',
        'v.': 'versus',
        
        # Evidence & Investigation
        'io': 'Investigating Officer',
        'pp': 'Public Prosecutor',
        'adpp': 'Additional Public Prosecutor',
        'pw': 'Prosecution Witness',
        'dw': 'Defence Witness',
        'mw': 'Material Witness',
        'exh': 'Exhibit',
        
        # Miscellaneous
        'ndps': 'Narcotic Drugs and Psychotropic Substances Act',
        'pocso': 'Protection of Children from Sexual Offences Act',
        'sc/st': 'Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act',
        'pmla': 'Prevention of Money Laundering Act',
        'uapa': 'Unlawful Activities Prevention Act',
        'nr': 'Not Reported',
        'air': 'All India Reporter',
        'scr': 'Supreme Court Reports',
        'scc': 'Supreme Court Cases',
        'cri.l.j': 'Criminal Law Journal',
    }
    
    # Comprehensive legal term synonyms for query expansion (30+ terms)
    SYNONYMS = {
        # Crimes - Violent
        'murder': ['homicide', 'killing', 'culpable homicide', 'unlawful killing', 'death caused'],
        'assault': ['hurt', 'battery', 'criminal force', 'causing injury', 'grievous hurt'],
        'kidnapping': ['abduction', 'kidnap', 'wrongful confinement', 'wrongful restraint'],
        'rape': ['sexual assault', 'sexual offence', 'sexual violence', 'outraging modesty'],
        'robbery': ['dacoity', 'extortion', 'armed robbery', 'forcible taking'],
        
        # Crimes - Property
        'theft': ['stealing', 'larceny', 'dishonest misappropriation', 'dishonest taking'],
        'cheating': ['fraud', 'deception', 'dishonest inducement', 'fraudulent misrepresentation'],
        'criminal breach of trust': ['misappropriation', 'breach of trust', 'cbt'],
        'mischief': ['damage to property', 'destruction of property', 'criminal damage'],
        'trespass': ['criminal trespass', 'house trespass', 'lurking house trespass'],
        
        # Crimes - Public Order
        'rioting': ['unlawful assembly', 'affray', 'public disorder'],
        'defamation': ['libel', 'slander', 'injury to reputation'],
        'nuisance': ['public nuisance', 'common nuisance'],
        
        # Bail & Liberty
        'bail': ['release', 'liberty', 'freedom from custody', 'temporary release', 'judicial release'],
        'anticipatory bail': ['pre-arrest bail', 'advance bail', 'protection from arrest'],
        'default bail': ['statutory bail', 'indefeasible right', 'release on expiry', 'bail under section 167'],
        'investigation period': ['custody period', 'detention period', 'remand period', 'ninety days', 'sixty days'],
        'custody': ['detention', 'imprisonment', 'confinement', 'incarceration'],
        'arrest': ['apprehension', 'detention', 'taken into custody'],
        
        # Punishments
        'punishment': ['penalty', 'sentence', 'imprisonment', 'sanction'],
        'fine': ['monetary penalty', 'pecuniary punishment', 'financial penalty'],
        'imprisonment': ['incarceration', 'jail', 'custody', 'confinement'],
        'death penalty': ['capital punishment', 'death sentence', 'execution'],
        'life imprisonment': ['life sentence', 'imprisonment for life'],
        
        # Legal Concepts
        'offence': ['crime', 'criminal act', 'violation', 'breach'],
        'accused': ['defendant', 'alleged offender', 'person charged'],
        'victim': ['complainant', 'injured party', 'aggrieved person'],
        'witness': ['eyewitness', 'testimony giver', 'deponent'],
        'evidence': ['proof', 'testimony', 'documentation', 'material'],
        'investigation': ['inquiry', 'probe', 'examination'],
        'trial': ['prosecution', 'court proceedings', 'legal proceedings'],
        'conviction': ['finding of guilt', 'pronouncement of guilt', 'guilty verdict'],
        'acquittal': ['discharge', 'exoneration', 'not guilty verdict', 'release'],
    }
    
    # Hindi/English section number patterns (comprehensive)
    SECTION_PATTERNS = {
        'IPC': [
            # English patterns
            r'(?:ipc|indian penal code)\s*(?:section|sec\.?|धारा)?\s*(\d+[A-Za-z]*)',
            r'(?:section|sec\.?|धारा)\s*(\d+[A-Za-z]*)\s*(?:of\s*)?(?:ipc|indian penal code)',
            r'ipc[\s_-]*(\d+[A-Za-z]*)',
            r'(?:u/s|under section)\s*(\d+[A-Za-z]*)\s*(?:ipc)',
            # Hindi patterns
            r'आईपीसी\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
            r'भारतीय दंड संहिता\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
        ],
        'CrPC': [
            # English patterns
            r'(?:crpc|cr\.?p\.?c\.?|code of criminal procedure)\s*(?:section|sec\.?|धारा)?\s*(\d+[A-Za-z]*)',
            r'(?:section|sec\.?|धारा)\s*(\d+[A-Za-z]*)\s*(?:of\s*)?(?:crpc|cr\.?p\.?c\.?)',
            r'crpc[\s_-]*(\d+[A-Za-z]*)',
            r'(?:u/s|under section)\s*(\d+[A-Za-z]*)\s*(?:crpc)',
            # Hindi patterns  
            r'सीआरपीसी\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
            r'दंड प्रक्रिया संहिता\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
        ],
        'BNS': [
            r'(?:bns|bharatiya nyaya sanhita)\s*(?:section|sec\.?|धारा)?\s*(\d+[A-Za-z]*)',
            r'(?:section|sec\.?|धारा)\s*(\d+[A-Za-z]*)\s*(?:of\s*)?(?:bns)',
            r'bns[\s_-]*(\d+[A-Za-z]*)',
            r'भारतीय न्याय संहिता\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
        ],
        'BNSS': [
            r'(?:bnss|bharatiya nagarik suraksha sanhita)\s*(?:section|sec\.?|धारा)?\s*(\d+[A-Za-z]*)',
            r'(?:section|sec\.?)\s*(\d+[A-Za-z]*)\s*(?:of\s*)?(?:bnss)',
            r'भारतीय नागरिक सुरक्षा संहिता\s*(?:धारा)?\s*(\d+[A-Za-z]*)',
        ],
        'Constitution': [
            r'(?:article|art\.?|अनुच्छेद)\s*(\d+[A-Za-z]*)',
            r'fundamental right',
            r'मौलिक अधिकार',
        ],
    }
    
    
    def reformulate(self, query: str) -> ReformulatedQuery:
        """
        Reformulate a query for better retrieval.
        
        Args:
            query: Original user query
            
        Returns:
            ReformulatedQuery with enhanced query and extracted metadata
        """
        query_lower = query.lower().strip()
        
        # Extract section numbers
        extracted_sections = self._extract_sections(query_lower)
        
        # Identify law types
        extracted_law_types = self._extract_law_types(query_lower)
        
        # Expand acronyms
        expanded_query = self._expand_acronyms(query)
        
        # Generate search terms
        search_terms = self._generate_search_terms(query_lower)
        
        # Build enhanced query
        enhanced_parts = [expanded_query]
        
        # Add synonyms for key terms
        for term, synonyms in self.SYNONYMS.items():
            if term in query_lower:
                # Add most relevant synonym
                enhanced_parts.append(synonyms[0])
        
        # Add section context
        for section in extracted_sections:
            if section not in expanded_query:
                enhanced_parts.append(f"Section {section}")
        
        enhanced_query = " ".join(enhanced_parts)
        
        # Build metadata filters
        metadata_filters = {}
        if len(extracted_law_types) == 1:
            metadata_filters['law_type'] = extracted_law_types[0]
        
        return ReformulatedQuery(
            original_query=query,
            enhanced_query=enhanced_query,
            extracted_sections=extracted_sections,
            extracted_law_types=extracted_law_types,
            search_terms=search_terms,
            metadata_filters=metadata_filters
        )
    
    def _extract_sections(self, query: str) -> List[str]:
        """Extract section numbers from query"""
        sections = []
        
        for law_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, query, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, str) and match:
                        section_id = f"{law_type}_{match.upper()}"
                        if section_id not in sections:
                            sections.append(section_id)
        
        return sections
    
    def _extract_law_types(self, query: str) -> List[str]:
        """Identify which law types are mentioned"""
        law_types = []
        
        if any(term in query for term in ['ipc', 'indian penal code', 'penal code']):
            law_types.append('IPC')
        
        if any(term in query for term in ['crpc', 'cr.p.c', 'criminal procedure', 'code of criminal']):
            law_types.append('CrPC')
        
        if any(term in query for term in ['bns', 'bharatiya nyaya', 'nyaya sanhita']):
            law_types.append('BNS')
        
        if any(term in query for term in ['constitution', 'article', 'fundamental right']):
            law_types.append('Constitution')
        
        if any(term in query for term in ['bail', 'judgment', 'precedent', 'case law']):
            law_types.append('Judgment')
        
        return law_types
    
    def _expand_acronyms(self, query: str) -> str:
        """Expand legal acronyms in query"""
        result = query
        
        for acronym, expansion in self.ACRONYMS.items():
            # Case-insensitive replacement that preserves context
            pattern = r'\b' + acronym + r'\b'
            if re.search(pattern, result, re.IGNORECASE):
                result = re.sub(pattern, f"{acronym.upper()} ({expansion})", result, flags=re.IGNORECASE)
        
        return result
    
    def _generate_search_terms(self, query: str) -> List[str]:
        """Generate list of search terms from query"""
        # Remove common stop words
        stop_words = {
            'what', 'is', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to',
            'and', 'or', 'how', 'can', 'i', 'my', 'me', 'under', 'by', 'with',
            'does', 'do', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
            'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might',
            'this', 'that', 'these', 'those', 'it', 'its', 'get', 'getting'
        }
        
        # Tokenize and filter
        words = re.findall(r'\b\w+\b', query.lower())
        search_terms = [w for w in words if w not in stop_words and len(w) > 2]
        
        return list(set(search_terms))
    
    def for_bail_query(self, query: str) -> ReformulatedQuery:
        """
        Specialized reformulation for bail queries.
        Adds bail-specific context and CrPC provisions.
        """
        result = self.reformulate(query)
        
        # Add bail-specific sections if not present
        bail_sections = ['CrPC_436', 'CrPC_437', 'CrPC_438', 'CrPC_439']
        
        # Enhance with bail context
        bail_context = "bail provisions anticipatory bail regular bail CrPC"
        result.enhanced_query = f"{result.enhanced_query} {bail_context}"
        
        # Ensure CrPC is in law types
        if 'CrPC' not in result.extracted_law_types:
            result.extracted_law_types.append('CrPC')
        
        return result


if __name__ == "__main__":
    # Test the reformulator
    reformulator = QueryReformulator()
    
    test_queries = [
        "What is IPC 302?",
        "Punishment for theft under section 379",
        "Can I get bail for murder case?",
        "Explain anticipatory bail under CrPC",
        "Article 21 fundamental rights",
        "What is the difference between bailable and non-bailable offence?",
    ]
    
    print("="*60)
    print("QUERY REFORMULATION TEST")
    print("="*60)
    
    for query in test_queries:
        result = reformulator.reformulate(query)
        print(f"\nOriginal: {query}")
        print(f"Enhanced: {result.enhanced_query}")
        print(f"Sections: {result.extracted_sections}")
        print(f"Law Types: {result.extracted_law_types}")
        print(f"Search Terms: {result.search_terms}")
