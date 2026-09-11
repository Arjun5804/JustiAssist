"""
Bail Provisions Lookup Service

Quick lookup for section bailability, punishment, and provisions.
Uses the bail_provisions.csv and bns_provisions.csv reference tables.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

@dataclass
class SectionInfo:
    """Information about a legal section"""
    section: str
    law_type: str
    bailable: bool
    max_punishment: str
    cognizable: bool
    compoundable: bool
    description: str
    crpc_section: Optional[str] = None
    bnss_section: Optional[str] = None
    bns_equivalent: Optional[str] = None


class BailProvisionsLookup:
    """
    Fast lookup for section bailability and related info.
    
    Usage:
        lookup = BailProvisionsLookup()
        info = lookup.get_section("302", "IPC")
        print(f"Bailable: {info.bailable}")
    """
    
    def __init__(self):
        self._ipc_data: Optional[pd.DataFrame] = None
        self._bns_data: Optional[pd.DataFrame] = None
        self._load_data()
    
    def _load_data(self):
        """Load CSV data into memory"""
        data_dir = Path(__file__).parent / "data"
        
        ipc_path = data_dir / "bail_provisions.csv"
        bns_path = data_dir / "bns_provisions.csv"
        
        if ipc_path.exists():
            self._ipc_data = pd.read_csv(ipc_path, dtype=str)
            self._ipc_data['section'] = self._ipc_data['section'].astype(str)
        
        if bns_path.exists():
            self._bns_data = pd.read_csv(bns_path, dtype=str)
            self._bns_data['section'] = self._bns_data['section'].astype(str)
    
    def get_section(self, section: str, law_type: str = "IPC") -> Optional[SectionInfo]:
        """
        Get information about a specific section.
        
        Args:
            section: Section number (e.g., "302", "420")
            law_type: "IPC" or "BNS"
            
        Returns:
            SectionInfo or None if not found
        """
        section = str(section).strip().upper()
        law_type = law_type.upper()
        
        if law_type == "BNS" and self._bns_data is not None:
            row = self._bns_data[self._bns_data['section'] == section]
            if not row.empty:
                r = row.iloc[0]
                return SectionInfo(
                    section=r['section'],
                    law_type="BNS",
                    bailable=r.get('bailable', 'No') == 'Yes',
                    max_punishment=r.get('max_punishment_years', 'Unknown'),
                    cognizable=r.get('cognizable', 'No') == 'Yes',
                    compoundable=r.get('compoundable', 'No') == 'Yes',
                    description=r.get('description', ''),
                    bnss_section=r.get('bnss_section'),
                    bns_equivalent=r.get('bns_equivalent'),
                )
        
        if self._ipc_data is not None:
            row = self._ipc_data[self._ipc_data['section'] == section]
            if not row.empty:
                r = row.iloc[0]
                return SectionInfo(
                    section=r['section'],
                    law_type="IPC",
                    bailable=r.get('bailable', 'No') == 'Yes',
                    max_punishment=r.get('max_punishment_years', 'Unknown'),
                    cognizable=r.get('cognizable', 'No') == 'Yes',
                    compoundable=r.get('compoundable', 'No') == 'Yes',
                    description=r.get('description', ''),
                    crpc_section=r.get('crpc_section'),
                    bnss_section=r.get('bnss_equivalent'),
                )
        
        return None
    
    def is_bailable(self, section: str, law_type: str = "IPC") -> Optional[bool]:
        """Quick check if a section is bailable"""
        info = self.get_section(section, law_type)
        return info.bailable if info else None
    
    def get_ipc_for_bns(self, bns_section: str) -> Optional[str]:
        """Get IPC equivalent for a BNS section"""
        if self._bns_data is None:
            return None
        
        row = self._bns_data[self._bns_data['section'] == str(bns_section)]
        if not row.empty:
            return row.iloc[0].get('bns_equivalent')
        return None
    
    def get_all_bailable(self, law_type: str = "IPC") -> List[str]:
        """Get list of all bailable sections"""
        if law_type == "BNS" and self._bns_data is not None:
            return self._bns_data[self._bns_data['bailable'] == 'Yes']['section'].tolist()
        elif self._ipc_data is not None:
            return self._ipc_data[self._ipc_data['bailable'] == 'Yes']['section'].tolist()
        return []
    
    def get_all_non_bailable(self, law_type: str = "IPC") -> List[str]:
        """Get list of all non-bailable sections"""
        if law_type == "BNS" and self._bns_data is not None:
            return self._bns_data[self._bns_data['bailable'] == 'No']['section'].tolist()
        elif self._ipc_data is not None:
            return self._ipc_data[self._ipc_data['bailable'] == 'No']['section'].tolist()
        return []


# Singleton instance
_lookup_instance: Optional[BailProvisionsLookup] = None

def get_bail_lookup() -> BailProvisionsLookup:
    """Get or create the bail provisions lookup singleton"""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = BailProvisionsLookup()
    return _lookup_instance


# Quick helper functions
def is_bailable(section: str, law_type: str = "IPC") -> Optional[bool]:
    """Quick check if a section is bailable"""
    return get_bail_lookup().is_bailable(section, law_type)

def get_section_info(section: str, law_type: str = "IPC") -> Optional[SectionInfo]:
    """Get full section info"""
    return get_bail_lookup().get_section(section, law_type)
