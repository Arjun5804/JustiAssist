"""
JustiAssist Data Loader - 2026-Ready MVP
Auto-discovery and classification of legal datasets
"""

import json
import re
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from config import (
    CSV_DATASETS_PATH, 
    JSON_DATASETS_PATH,
    DatasetType,
    classify_dataset,
    discover_datasets,
    CHUNKING_CONFIG
)


@dataclass
class LegalDocument:
    """Represents a legal document/section with metadata"""
    text: str
    law_type: str  # IPC, CrPC, BNS, Constitution, Judgment, QA
    section_number: str
    source_dataset: str
    dataset_type: DatasetType = DatasetType.STATUTORY  # Classification
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "law_type": self.law_type,
            "section_number": self.section_number,
            "source_dataset": self.source_dataset,
            "dataset_type": self.dataset_type.value,
            "metadata": self.metadata
        }


class DataLoader:
    """
    Auto-discovery data loader for legal datasets.
    
    Features:
    - Automatically discovers all CSV/JSON files in dataset folders
    - Classifies datasets by content type (statutory, case_law, qa)
    - Routes to appropriate index
    - Logs all discovered datasets
    """
    
    def __init__(self):
        self.csv_path = CSV_DATASETS_PATH
        self.json_path = JSON_DATASETS_PATH
        self.discovered_datasets: Dict[str, List[Tuple[Path, DatasetType]]] = {}
        
        # Auto-discover on init
        self._discover_all()
    
    def _discover_all(self):
        """Auto-discover all datasets"""
        print("\n" + "=" * 60)
        print("AUTO-DISCOVERING DATASETS")
        print("=" * 60)
        self.discovered_datasets = discover_datasets()
        
        # Summary
        statutory_count = sum(1 for _, dtype in self.discovered_datasets["csv"] + self.discovered_datasets["json"] 
                             if dtype in [DatasetType.STATUTORY, DatasetType.QA])
        case_law_count = sum(1 for _, dtype in self.discovered_datasets["csv"] + self.discovered_datasets["json"]
                            if dtype == DatasetType.CASE_LAW)
        
        print(f"\nSummary: {statutory_count} statutory/QA, {case_law_count} case law datasets")
        print("=" * 60)
    
    def load_all_statutory(self) -> List[LegalDocument]:
        """Load all statutory and QA datasets for the statutory index"""
        documents = []
        
        print("\n--- Loading STATUTORY Documents ---")
        
        # Process CSV files classified as STATUTORY or QA
        for filepath, dtype in self.discovered_datasets.get("csv", []):
            if dtype in [DatasetType.STATUTORY, DatasetType.QA]:
                docs = self._load_csv_file(filepath, dtype)
                documents.extend(docs)
        
        # Process JSON files classified as STATUTORY or QA
        for filepath, dtype in self.discovered_datasets.get("json", []):
            if dtype in [DatasetType.STATUTORY, DatasetType.QA]:
                docs = self._load_json_file(filepath, dtype)
                documents.extend(docs)
        
        print(f"Total statutory documents: {len(documents)}")
        return documents
    
    def load_case_law(self) -> List[LegalDocument]:
        """Load all case law datasets for the case law index"""
        documents = []
        
        print("\n--- Loading CASE LAW Documents ---")
        
        # Process CSV files classified as CASE_LAW
        for filepath, dtype in self.discovered_datasets.get("csv", []):
            if dtype == DatasetType.CASE_LAW:
                docs = self._load_csv_file(filepath, dtype)
                documents.extend(docs)
        
        # Process JSON files classified as CASE_LAW (if any)
        for filepath, dtype in self.discovered_datasets.get("json", []):
            if dtype == DatasetType.CASE_LAW:
                docs = self._load_json_file(filepath, dtype)
                documents.extend(docs)
        
        print(f"Total case law documents: {len(documents)}")
        return documents
    
    def load_bail_judgments(self) -> List[LegalDocument]:
        """Backward compatibility: Load bail judgments (alias for case law)"""
        return self.load_case_law()
    
    # ==================== CSV LOADERS ====================
    
    def _load_csv_file(self, filepath: Path, dtype: DatasetType) -> List[LegalDocument]:
        """Generic CSV loader with auto-detection of structure"""
        documents = []
        filename = filepath.name.lower()
        
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(filepath, encoding='latin-1')
            except Exception as e:
                print(f"  [ERROR] Failed to load {filepath.name}: {e}")
                return documents
        
        # Route to appropriate loader based on filename patterns
        # Check judgments FIRST to avoid bail_judgments.csv being caught by 'bail' check
        if 'judgment' in filename or 'judgement' in filename:
            documents = self._parse_judgments(df, filepath.name, dtype)
        elif 'crpc' in filename and 'bail' in filename:
            # CrPC bail provisions have CrPC-style columns (section, law_type, chapter, description)
            documents = self._parse_crpc_sections(df, filepath.name, dtype)
        elif 'bail' in filename:
            documents = self._parse_bail_provisions(df, filepath.name, dtype)
        elif 'ipc' in filename and 'section' in filename:
            documents = self._parse_ipc_sections(df, filepath.name, dtype)
        elif 'crpc' in filename and 'section' in filename:
            documents = self._parse_crpc_sections(df, filepath.name, dtype)
        elif 'bns' in filename:
            documents = self._parse_bns_sections(df, filepath.name, dtype)
        else:
            documents = self._parse_generic_csv(df, filepath.name, dtype)
        
        print(f"  [CSV] Loaded {len(documents)} docs from {filepath.name}")
        return documents
    
    def _parse_bail_provisions(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse Bail Provisions CSV"""
        documents = []
        
        for _, row in df.iterrows():
            text_parts = []
            
            # Construct rich text representation
            section = str(row.get('section', 'Unknown'))
            law_type = str(row.get('law_type', 'IPC'))
            
            text_parts.append(f"Section: {law_type} {section}")
            
            if pd.notna(row.get('description', '')):
                text_parts.append(f"Description: {row['description']}")
            
            if 'bailable' in df.columns and pd.notna(row.get('bailable', '')):
                text_parts.append(f"Bailable: {row['bailable']}")
            
            if 'cognizable' in df.columns and pd.notna(row.get('cognizable', '')):
                text_parts.append(f"Cognizable: {row['cognizable']}")
                
            if 'max_punishment_years' in df.columns and pd.notna(row.get('max_punishment_years', '')):
                text_parts.append(f"Punishment: {row['max_punishment_years']}")
            
            text = "\n".join(text_parts)
            section_id = f"{law_type}_{section}"
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type=law_type,
                    section_number=section_id,
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={
                        "bailable": str(row.get('bailable', '')) if 'bailable' in df.columns else '',
                        "cognizable": str(row.get('cognizable', '')) if 'cognizable' in df.columns else '',
                        "punishment": str(row.get('max_punishment_years', '')) if 'max_punishment_years' in df.columns else ''
                    }
                )
                documents.append(doc)
        
        return documents

    def _parse_ipc_sections(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse IPC sections CSV"""
        documents = []
        
        for _, row in df.iterrows():
            text_parts = []
            
            if 'Description' in df.columns and pd.notna(row.get('Description')):
                text_parts.append(str(row['Description']))
            elif 'description' in df.columns and pd.notna(row.get('description')):
                text_parts.append(str(row['description']))
                
            if 'Offense' in df.columns and pd.notna(row.get('Offense')):
                text_parts.append(f"Offense: {row['Offense']}")
            elif 'offense' in df.columns and pd.notna(row.get('offense')):
                text_parts.append(f"Offense: {row['offense']}")
                
            if 'Punishment' in df.columns and pd.notna(row.get('Punishment')):
                text_parts.append(f"Punishment: {row['Punishment']}")
            elif 'punishment' in df.columns and pd.notna(row.get('punishment')):
                text_parts.append(f"Punishment: {row['punishment']}")
            
            text = "\n".join(text_parts)
            section_val = str(row.get('Section', 'Unknown'))
            # Clean up "S. " or "Sec. " prefix
            section_val = re.sub(r'^(?:S\.|Sec\.|Section|S)\s*', '', section_val, flags=re.IGNORECASE).strip()
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type="IPC",
                    section_number=f"IPC_{section_val}",
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={
                        "offense": str(row.get('Offense', '')),
                        "punishment": str(row.get('Punishment', ''))
                    }
                )
                documents.append(doc)
        
        return documents
    
    def _parse_crpc_sections(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse CrPC sections CSV"""
        documents = []
        
        for _, row in df.iterrows():
            text_parts = []
            
            if 'Chapter_name' in df.columns and pd.notna(row.get('Chapter_name')):
                text_parts.append(f"Chapter: {row['Chapter_name']}")
            elif 'Chapter name' in df.columns and pd.notna(row.get('Chapter name')):
                text_parts.append(f"Chapter: {row['Chapter name']}")
            elif 'chapter_name' in df.columns and pd.notna(row.get('chapter_name')):
                text_parts.append(f"Chapter: {row['chapter_name']}")

            if 'Section _name' in df.columns and pd.notna(row.get('Section _name')):
                text_parts.append(f"Section: {row['Section _name']}")
            elif 'section_name' in df.columns and pd.notna(row.get('section_name')):
                text_parts.append(f"Section: {row['section_name']}")
                
            if 'Description' in df.columns and pd.notna(row.get('Description')):
                text_parts.append(str(row['Description']))
            elif 'description' in df.columns and pd.notna(row.get('description')):
                text_parts.append(str(row['description']))
            
            text = "\n".join(text_parts)
            section_val = str(row.get('Section', row.get('section', 'Unknown')))
            # Clean up "S. " or "Sec. " prefix
            section_val = re.sub(r'^(?:S\.|Sec\.|Section|S)\s*', '', section_val, flags=re.IGNORECASE).strip()
            section = f"CrPC_{section_val}"
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type="CrPC",
                    section_number=section,
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={
                        "chapter": str(row.get('Chapter', row.get('chapter', ''))),
                        "chapter_name": str(row.get('Chapter_name', row.get('chapter_name', '')))
                    }
                )
                documents.append(doc)
        
        return documents
    
    def _parse_bns_sections(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse BNS sections CSV"""
        documents = []
        
        for _, row in df.iterrows():
            text_parts = []
            
            for col in df.columns:
                if pd.notna(row.get(col, '')) and col.lower() not in ['section', 'chapter']:
                    value = str(row[col]).strip()
                    # Relaxed length check to allow short descriptions like 'Murder'
                    if value and len(value) > 2:
                        text_parts.append(value)
            
            text = "\n".join(text_parts)
            
            section = "BNS_Unknown"
            for col in df.columns:
                if 'section' in col.lower():
                    raw_sec = str(row.get(col, 'Unknown'))
                    clean_sec = re.sub(r'^(?:S\.|Sec\.|Section|S)\s*', '', raw_sec, flags=re.IGNORECASE).strip()
                    section = f"BNS_{clean_sec}"
                    break
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type="BNS",
                    section_number=section,
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={}
                )
                documents.append(doc)
        
        return documents
    
    def _parse_judgments(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse court judgments CSV"""
        documents = []
        
        for _, row in df.iterrows():
            text_parts = []
            
            # Case title
            case_title = ""
            for col in ['case_title', 'title', 'case_name', 'name']:
                if col in df.columns and pd.notna(row.get(col, '')):
                    case_title = str(row[col])
                    text_parts.append(f"Case: {case_title}")
                    break
            
            # Judgment text
            for col in ['judgment_text', 'judgment', 'text', 'content', 'decision', 'facts']:
                if col in df.columns and pd.notna(row.get(col, '')):
                    text_parts.append(str(row[col]))
                    break
            
            # Additional context
            for col in df.columns:
                if col.lower() not in ['case_id', 'case_title', 'title', 'judgment_text', 'judgment', 'text']:
                    if pd.notna(row.get(col, '')):
                        value = str(row[col]).strip()
                        if value and len(value) > 20:
                            text_parts.append(value)
            
            text = "\n".join(text_parts)
            case_id = str(row.get('case_id', row.get('id', 'Unknown')))
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type="Judgment",
                    section_number=case_id,
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={
                        "case_id": case_id,
                        "case_title": case_title
                    }
                )
                documents.append(doc)
        
        return documents
    
    def _parse_generic_csv(self, df: pd.DataFrame, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Generic CSV parser for unknown structures"""
        documents = []
        
        for idx, row in df.iterrows():
            text_parts = []
            
            for col in df.columns:
                if pd.notna(row.get(col, '')):
                    value = str(row[col]).strip()
                    # Relaxed length check
                    if value and len(value) > 2:
                        text_parts.append(f"{col}: {value}")
            
            text = "\n".join(text_parts)
            
            if text.strip():
                doc = LegalDocument(
                    text=text,
                    law_type="General",
                    section_number=f"DOC_{idx}",
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata={}
                )
                documents.append(doc)
        
        return documents
    
    # ==================== JSON LOADERS ====================
    
    def _load_json_file(self, filepath: Path, dtype: DatasetType) -> List[LegalDocument]:
        """Generic JSON loader"""
        documents = []
        filename = filepath.name.lower()
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [ERROR] Failed to load {filepath.name}: {e}")
            return documents
        
        # Ensure data is a list
        if isinstance(data, dict):
            data = [data]
        
        # Route based on content patterns
        if 'constitution' in filename:
            documents = self._parse_constitution_qa(data, filepath.name, dtype)
        elif 'ipc_qa' in filename:
            documents = self._parse_ipc_qa(data, filepath.name, dtype)
        elif 'crpc_qa' in filename:
            documents = self._parse_crpc_qa(data, filepath.name, dtype)
        elif 'indiclegal' in filename or 'legal_qa' in filename:
            documents = self._parse_indiclegal_qa(data, filepath.name, dtype)
        elif 'laws' in filename:
            documents = self._parse_indian_laws(data, filepath.name, dtype)
        else:
            documents = self._parse_generic_json(data, filepath.name, dtype)
        
        print(f"  [JSON] Loaded {len(documents)} docs from {filepath.name}")
        return documents
    
    def _parse_constitution_qa(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse Constitution QA JSON"""
        documents = []
        
        for i, item in enumerate(data):
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            text = f"Question: {question}\nAnswer: {answer}"
            
            section = f"Constitution_QA_{i+1}"
            if 'article' in question.lower():
                match = re.search(r'article\s*(\d+)', question.lower())
                if match:
                    section = f"Article_{match.group(1)}"
            
            doc = LegalDocument(
                text=text,
                law_type="Constitution",
                section_number=section,
                source_dataset=source,
                dataset_type=dtype,
                metadata={"question": question, "answer": answer}
            )
            documents.append(doc)
        
        return documents
    
    def _parse_ipc_qa(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse IPC QA JSON"""
        documents = []
        
        for i, item in enumerate(data):
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            text = f"Question: {question}\nAnswer: {answer}"
            
            section = f"IPC_QA_{i+1}"
            match = re.search(r'(?:ipc|section)\s*(\d+[A-Za-z]*)', question.lower())
            if match:
                section = f"IPC_{match.group(1).upper()}"
            
            doc = LegalDocument(
                text=text,
                law_type="IPC",
                section_number=section,
                source_dataset=source,
                dataset_type=dtype,
                metadata={"question": question, "answer": answer, "qa_type": "ipc_grounding"}
            )
            documents.append(doc)
        
        return documents
    
    def _parse_crpc_qa(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse CrPC QA JSON"""
        documents = []
        
        for i, item in enumerate(data):
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            text = f"Question: {question}\nAnswer: {answer}"
            
            section = f"CrPC_QA_{i+1}"
            match = re.search(r'(?:crpc|section)\s*(\d+[A-Za-z]*)', question.lower())
            if match:
                section = f"CrPC_{match.group(1).upper()}"
            
            doc = LegalDocument(
                text=text,
                law_type="CrPC",
                section_number=section,
                source_dataset=source,
                dataset_type=dtype,
                metadata={"question": question, "answer": answer, "qa_type": "crpc_grounding"}
            )
            documents.append(doc)
        
        return documents
    
    def _parse_indiclegal_qa(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse IndicLegalQA dataset"""
        documents = []
        
        for i, item in enumerate(data):
            case_name = item.get('case_name', '')
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            text_parts = []
            if case_name:
                text_parts.append(f"Case: {case_name}")
            text_parts.append(f"Question: {question}")
            text_parts.append(f"Answer: {answer}")
            
            doc = LegalDocument(
                text="\n".join(text_parts),
                law_type="General",
                section_number=f"IndicLegal_{i+1}",
                source_dataset=source,
                dataset_type=dtype,
                metadata={"case_name": case_name, "question": question, "answer": answer}
            )
            documents.append(doc)
        
        return documents
    
    def _parse_indian_laws(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Parse Indian laws JSON"""
        documents = []
        
        for i, item in enumerate(data):
            # Handle various structures
            text_parts = []
            
            for key in ['title', 'name', 'law_name']:
                if key in item and item[key]:
                    text_parts.append(f"Law: {item[key]}")
                    break
            
            for key in ['description', 'content', 'text', 'provisions']:
                if key in item and item[key]:
                    text_parts.append(str(item[key]))
            
            if text_parts:
                doc = LegalDocument(
                    text="\n".join(text_parts),
                    law_type="IndianLaw",
                    section_number=f"Law_{i+1}",
                    source_dataset=source,
                    dataset_type=dtype,
                    metadata=item
                )
                documents.append(doc)
        
        return documents
    
    def _parse_generic_json(self, data: List, source: str, dtype: DatasetType) -> List[LegalDocument]:
        """Generic JSON parser"""
        documents = []
        
        for i, item in enumerate(data):
            if isinstance(item, dict):
                text_parts = []
                for key, value in item.items():
                    if value and isinstance(value, str) and len(value) > 5:
                        text_parts.append(f"{key}: {value}")
                
                if text_parts:
                    doc = LegalDocument(
                        text="\n".join(text_parts),
                        law_type="General",
                        section_number=f"DOC_{i+1}",
                        source_dataset=source,
                        dataset_type=dtype,
                        metadata=item
                    )
                    documents.append(doc)
        
        return documents
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get loading statistics"""
        statutory = self.load_all_statutory()
        case_law = self.load_case_law()
        
        stats = {
            "total_statutory_documents": len(statutory),
            "total_case_law_documents": len(case_law),
            "total_documents": len(statutory) + len(case_law),
            "datasets_discovered": {
                "csv": len(self.discovered_datasets.get("csv", [])),
                "json": len(self.discovered_datasets.get("json", []))
            }
        }
        
        # Count by law type
        law_type_counts = {}
        for doc in statutory + case_law:
            law_type = doc.law_type
            law_type_counts[law_type] = law_type_counts.get(law_type, 0) + 1
        stats["by_law_type"] = law_type_counts
        
        return stats


if __name__ == "__main__":
    # Test the data loader
    loader = DataLoader()
    stats = loader.get_statistics()
    
    print("\n" + "=" * 60)
    print("DATA LOADING STATISTICS")
    print("=" * 60)
    print(f"Datasets Discovered: CSV={stats['datasets_discovered']['csv']}, JSON={stats['datasets_discovered']['json']}")
    print(f"Total Statutory Documents: {stats['total_statutory_documents']}")
    print(f"Total Case Law Documents: {stats['total_case_law_documents']}")
    print(f"Total Documents: {stats['total_documents']}")
    print("\nBy Law Type:")
    for law_type, count in stats['by_law_type'].items():
        print(f"  - {law_type}: {count}")
