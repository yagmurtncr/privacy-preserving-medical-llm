"""
PII Masker Module - GDPR/KVKK/HIPAA Compliant
==============================================

Türk sağlık verileri için kişisel bilgi maskeleme (client-side)

Modes:
  - 'regex': Pure regex-based (fast, ~1ms)
  - 'ner': NER model-based (smart, ~50ms)  
  - 'hybrid': Regex + NER (best, ~10-50ms) ✅ RECOMMENDED

Usage:
    >>> masker = PIIMasker(aggressive=True, language='tr', mode='hybrid')
    >>> masked_text, mapping = masker.mask("Zeynep Arslan, 28 yaş, TC: 11223344556")
    >>> print(masked_text)  # "[PATIENT_NAME_1], [AGE_1], [TC_NO_1]"
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

# Optional NER model imports
try:
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    import torch
    NER_AVAILABLE = True
except ImportError:
    NER_AVAILABLE = False


# =============================================================================
# CONSTANTS
# =============================================================================

# Turkish NER model for context-aware name detection
NER_MODEL_NAME = "savasy/bert-base-turkish-ner-cased"
NER_MAX_LENGTH = 512

# NO HARD-CODED NAME LISTS! 
# Names are detected via NER model (context-aware AI detection)
# This approach is more intelligent and avoids false positives

# Medical terms (must NOT be masked!)
MEDICAL_TERMS = {
    'açlık kan', 'kan şekeri', 'glukoz', 'hba1c', 'insülin', 'hemoglobin',
    'kolesterol', 'trigliserid', 'kreatinin', 'üre', 'ast', 'alt', 'ggt',
    'tsh', 'vitamin', 'ferritin', 'nötrofil', 'lenfosit', 'trombosit',
    'sedimentasyon', 'crp', 'tansiyon', 'nabız', 'ateş', 'kilo', 'boy',
    'vücut', 'bmi', 'kalp', 'akciğer', 'böbrek', 'karaciğer', 'pankreas',
    'tiroid', 'mide', 'bağırsak', 'beyin', 'damar', 'kan', 'idrar', 'dışkı',
    'hemogram', 'egfr', 'ldl', 'hdl', 'trigliserit', 'bun', 'potasyum',
    'sodyum', 'klor', 'kalsiyum', 'magnezyum', 'fosfor', 'albumin', 'globulin',
    # Add common abbreviations and parts that NER might incorrectly tag
    'rbc', 'mcv', 'mch', 'mchc', 'wbc', 'plt', 'hct', 'hgb', 'rdw',
    'hem', 'fer', 'glo', 'alb', 'pro', 'ret', 'neo', 'bas', 'eos', 'mon',
    # Turkish medical term parts
    'tan', 'ted', 'ani', 'yok', 'var', 'dur', 'kon', 'tek', 'çok', 'ort',
    # Elements that are also surnames (context matters!)
    'demir', 'kaya', 'taş'
}

# Medical context patterns (phrases that indicate medical usage, not names)
MEDICAL_CONTEXT_PATTERNS = [
    # Iron/Demir related
    r'\bdemir\s+(eksikliği|takviyesi|deposu|seviyesi|ihtiyacı|preparatı|tedavisi)',
    r'\b(düşük|yüksek|normal|anormal|oral|intravenöz)\s+demir\b',
    r'\bdemir\s+(ile|için|gibi|olarak|olduğu)',
    # Administration routes (should not be masked)
    r'\boral\s+(demir|vitamin|ilaç|tedavi|tablet)',
    r'\bintravenöz\s+(demir|vitamin|ilaç|tedavi)',
    # General medical phrases
    r'\b(tedavi|tanı|test|sonuç|değer|seviye)\s+\w+',
    r'\b\w+\s+(eksikliği|takviyesi|tedavisi|hastalığı)',
]

# Regex patterns
PATTERN_TC_WITH_PREFIX = r'(?:T\.?C\.?\s*[:\-]?\s*)([1-9]\d{10})\b'
PATTERN_TC_PLAIN = r'\b([1-9]\d{10})\b'
PATTERN_PHONE = r'(\+90\s?|0)?[5]\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
PATTERN_EMAIL = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
PATTERN_DATE = r'\b\d{1,2}[./\-]\d{1,2}[./\-]\d{4}\b'
PATTERN_AGE_TR = r'\b\d{1,3}\s*ya[şs][ışı]?n?[dıa]?\b'
PATTERN_AGE_YIL = r'\b\d{1,3}\s*y[ıi]l[lıı]?n?[dıa]?\b'
PATTERN_AGE_EN = r'\b\d{1,3}\s*yea?rs?\s*old\b'
PATTERN_NAME_MULTI = r'\b[A-ZÇĞIÖŞÜ][a-zçğiöşü]+(\s+[A-ZÇĞIÖŞÜ][a-zçğiöşü]+){0,2}\b'
PATTERN_NAME_SINGLE = r'\b[A-ZÇĞIÖŞÜ][a-zçğiöşü]+\b'

# Turkish TC ID validation constants
TC_LENGTH = 11
TC_CHECKSUM_MULTIPLIER = 7


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PIIEntity:
    """Detected PII entity with metadata"""
    type: str           # PII type: 'name', 'tc_no', 'phone', 'email', 'age', 'date'
    value: str          # Original value
    start: int          # Start position in text
    end: int            # End position in text
    placeholder: str    # Masked placeholder: [PATIENT_NAME_1], [TC_NO_1], etc.


# =============================================================================
# MAIN CLASS
# =============================================================================

class PIIMasker:
    """
    AI-powered health PII detection and masking (Turkish + English)
    
    Detection modes:
      - 'ner': AI model-based (context-aware, intelligent) ✅ RECOMMENDED
      - 'hybrid': NER + Regex fallback (best reliability)
      - 'regex': Pattern matching only (fast but limited)
    
    Name detection: NER model only (no hard-coded lists!)
    Structured PII: Regex patterns (TC, phone, email, age)
    """
    
    def __init__(self, aggressive: bool = True, language: str = 'tr', mode: str = 'ner', ner_gpu_id: int = 0):
        """
        Initialize PII masker
        
        Args:
            aggressive: If True, use stricter medical term filtering
            language: 'tr' for Turkish, 'en' for English  
            mode: 'ner' (recommended), 'hybrid', or 'regex'
            ner_gpu_id: GPU ID for NER model (default: 0)
        """
        self.aggressive = aggressive
        self.language = language.lower()
        self.mode = mode
        self.ner_gpu_id = ner_gpu_id
        
        # NER model (lazy loaded)
        self.ner_model = None
        self.ner_tokenizer = None
        self.ner_device = None
        
        # Load NER model if needed
        if mode in ['ner', 'hybrid'] and NER_AVAILABLE:
            self._load_ner_model()
    
    def _load_ner_model(self) -> None:
        """Load Turkish NER model for context-aware name detection"""
        try:
            print(f"   🤖 Loading Turkish NER model on GPU {self.ner_gpu_id}...")
            tokenizer = AutoTokenizer.from_pretrained(NER_MODEL_NAME)
            model = AutoModelForTokenClassification.from_pretrained(NER_MODEL_NAME)
            
            # Use specific GPU
            if torch.cuda.is_available():
                device = f"cuda:{self.ner_gpu_id}"
            else:
                device = "cpu"
            
            _ = model.to(device)
            _ = model.eval()
            
            # Only assign after successful load
            self.ner_tokenizer = tokenizer  # type: ignore[assignment]
            self.ner_model = model  # type: ignore[assignment]
            self.ner_device = device  # type: ignore[assignment]
            print(f"   ✅ NER model loaded on {device}")
        except Exception as e:
            print(f"   ⚠️  NER model load failed: {e}")
            print("   ℹ️  Falling back to regex-only mode (aggressive)")
            # IMPORTANT: Change mode to regex if NER fails!
            self.mode = 'regex'
            self.ner_model = None
            self.ner_tokenizer = None
            self.ner_device = None
    
    # =========================================================================
    # REGEX-BASED DETECTION (Fast path - ~1ms)
    # =========================================================================
    
    def _detect_tc_no(self, text: str) -> List[PIIEntity]:
        """Detect Turkish ID numbers (TC Kimlik No) - 11 digits"""
        entities = []
        patterns = [PATTERN_TC_WITH_PREFIX, PATTERN_TC_PLAIN]
        found_positions = set()
        
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                tc_no = match.group(1) if match.lastindex else match.group()
                tc_start = match.start(1) if match.lastindex else match.start()
                full_start = match.start()
                full_value = match.group()
                
                if tc_start in found_positions:
                    continue
                
                # Aggressive mode: Skip checksum validation (for test TCs)
                if self.aggressive or self._validate_tc_checksum(tc_no):
                    entities.append(PIIEntity(
                        type='tc_no',
                        value=full_value,
                        start=full_start,
                        end=match.end(),
                        placeholder=''
                    ))
                    found_positions.add(tc_start)
        
        return entities
    
    def _validate_tc_checksum(self, tc: str) -> bool:
        """Validate Turkish ID checksum algorithm"""
        if len(tc) != TC_LENGTH:
            return False
        
        try:
            digits = [int(d) for d in tc]
            
            # 10th digit check
            sum_odd = sum(digits[0:9:2])
            sum_even = sum(digits[1:8:2])
            check_10 = (sum_odd * TC_CHECKSUM_MULTIPLIER - sum_even) % 10
            
            if digits[9] != check_10:
                return False
            
            # 11th digit check
            check_11 = sum(digits[0:10]) % 10
            return digits[10] == check_11
            
        except (ValueError, IndexError):
            return False
    
    def _detect_phone(self, text: str) -> List[PIIEntity]:
        """Detect Turkish phone numbers (+90 532 123 45 67, 0532-123-4567, etc.)"""
        entities = []
        for match in re.finditer(PATTERN_PHONE, text):
            entities.append(PIIEntity(
                type='phone',
                value=match.group(),
                start=match.start(),
                end=match.end(),
                placeholder=''
            ))
        return entities
    
    def _detect_email(self, text: str) -> List[PIIEntity]:
        """Detect email addresses"""
        entities = []
        for match in re.finditer(PATTERN_EMAIL, text):
            entities.append(PIIEntity(
                type='email',
                value=match.group(),
                start=match.start(),
                end=match.end(),
                placeholder=''
            ))
        return entities
    
    def _detect_dates(self, text: str) -> List[PIIEntity]:
        """Detect dates (DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY)"""
        entities = []
        for match in re.finditer(PATTERN_DATE, text):
            entities.append(PIIEntity(
                type='date',
                value=match.group(),
                start=match.start(),
                end=match.end(),
                placeholder=''
            ))
        return entities
    
    def _detect_age(self, text: str) -> List[PIIEntity]:
        """Detect age patterns (28 yaş, 35 yıl, 28 years old)"""
        entities = []
        patterns = [PATTERN_AGE_TR, PATTERN_AGE_YIL, PATTERN_AGE_EN]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(PIIEntity(
                    type='age',
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    placeholder=''
                ))
        return entities
    
    def _is_medical_context(self, text: str, start: int, end: int) -> bool:
        """Check if a word is in medical context (e.g., 'demir eksikliği')"""
        # Get surrounding context (20 chars before and after)
        context_start = max(0, start - 20)
        context_end = min(len(text), end + 20)
        context = text[context_start:context_end].lower()
        
        # Check if any medical pattern matches
        for pattern in MEDICAL_CONTEXT_PATTERNS:
            if re.search(pattern, context, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_names_regex(self, text: str) -> List[PIIEntity]:
        """
        Fallback regex-based name detection (only used if NER fails)
        Minimal rules - just multi-word capitalized patterns with medical term filtering
        """
        entities = []
        
        # Only detect multi-word capitalized phrases (e.g., "Zeynep Arslan")
        # Single words are too ambiguous without NER context
        for match in re.finditer(PATTERN_NAME_MULTI, text):
            phrase = match.group()
            words = phrase.split()
            
            # Must be at least 2 words (FirstName LastName)
            if len(words) < 2:
                continue
            
            # Filter 1: Skip single-letter words (M, R, H, etc.)
            if any(len(word) <= 1 for word in words):
                continue
            
            # Filter 2: Skip if ANY word is a medical term
            if any(word.lower() in MEDICAL_TERMS for word in words):
                continue
            
            # Filter 3: Skip common medical abbreviations (uppercase only)
            if phrase.isupper() and len(phrase) <= 5:  # RBC, MCV, HDL, etc.
                continue
            
            # Filter 4: Context-aware check - skip medical context
            if self._is_medical_context(text, match.start(), match.end()):
                continue
            
            # Looks like a name! (FirstName LastName format)
            entities.append(PIIEntity(
                type='name',
                value=phrase,
                start=match.start(),
                end=match.end(),
                placeholder=''
            ))
        
        return entities
    
    # =========================================================================
    # NER-BASED DETECTION (Smart path - ~50ms)
    # =========================================================================
    
    def _detect_names_ner(self, text: str) -> List[PIIEntity]:
        """Detect names using NER model (context-aware, intelligent)"""
        entities: List[PIIEntity] = []
        
        if not NER_AVAILABLE or self.ner_model is None:
            return entities
        
        try:
            # Tokenize
            inputs = self.ner_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=NER_MAX_LENGTH,
                return_offsets_mapping=True
            )
            
            offset_mapping = inputs.pop("offset_mapping")[0]
            inputs = {k: v.to(self.ner_device) for k, v in inputs.items()}
            
            # Inference
            with torch.no_grad():
                outputs = self.ner_model(**inputs)
                predictions = torch.argmax(outputs.logits, dim=2)[0]
            
            # Decode labels (B-PER = Begin Person, I-PER = Inside Person)
            label_list = ['O', 'B-PER', 'I-PER', 'B-LOC', 'I-LOC', 'B-ORG', 'I-ORG']
            
            current_entity: Optional[str] = None
            current_start: Optional[int] = None
            current_end: Optional[int] = None
            
            def _save_entity():
                """Helper to save and validate current entity"""
                if current_entity != 'PERSON' or current_start is None or current_end is None:
                    return
                
                entity_text = text[current_start:current_end].strip()
                entity_lower = entity_text.lower()
                
                # Filter 1: Must be at least 3 chars (not "M", "R", "Hem", "Fer")
                if len(entity_text) < 3:
                    return
                
                # Filter 2: Must not be a medical term
                if entity_lower in MEDICAL_TERMS:
                    return
                
                # Filter 3: Check each word in entity (for multi-word entities)
                words = entity_text.split()
                for word in words:
                    word_lower = word.lower()
                    # Skip if any word is medical
                    if word_lower in MEDICAL_TERMS:
                        return
                    # Skip common medical prefixes
                    if word_lower in ['oral', 'intravenöz', 'sublingual', 'topikal', 'sistemik']:
                        return
                
                # Filter 4: Must not be part of a medical term (check word boundaries)
                if current_start > 0 and text[current_start - 1].isalnum():
                    return  # Part of a larger word
                if current_end < len(text) and text[current_end].isalnum():
                    return  # Part of a larger word
                
                # Filter 5: Context-aware check - skip medical context
                if self._is_medical_context(text, current_start, current_end):
                    return
                
                # Filter 6: Must start with capital letter (proper noun)
                if not entity_text[0].isupper():
                    return
                
                entities.append(PIIEntity(
                    type='name',
                    value=entity_text,
                    start=current_start,
                    end=current_end,
                    placeholder=''
                ))
            
            for label_id, (start, end) in zip(predictions, offset_mapping):
                if start == end:  # Special tokens
                    continue
                
                label = label_list[label_id] if label_id < len(label_list) else 'O'
                
                if label.startswith('B-PER'):  # Begin person
                    _save_entity()  # Save previous if any
                    current_entity = 'PERSON'
                    current_start = int(start.item())
                    current_end = int(end.item())
                    
                elif label.startswith('I-PER') and current_entity == 'PERSON':  # Inside person
                    current_end = int(end.item())
                    
                else:  # Other label
                    _save_entity()
                    current_entity = None
            
            # Save last entity
            _save_entity()
        
        except Exception as e:
            print(f"[WARNING] NER detection failed: {e}")
        
        return entities
    
    # =========================================================================
    # MAIN API
    # =========================================================================
    
    def mask(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Detect and mask all PII in text
        
        Args:
            text: Input text with potential PII
            
        Returns:
            (masked_text, unmask_mapping)
            
        Example:
            >>> masker = PIIMasker(mode='hybrid')
            >>> masked, mapping = masker.mask("Zeynep Arslan, 28 yaş, TC: 11223344556")
            >>> print(masked)  # "[PATIENT_NAME_1], [AGE_1], [TC_NO_1]"
        """
        all_entities: List[PIIEntity] = []
        
        # FAST PATH: Regex-based (deterministic, fast)
        all_entities.extend(self._detect_tc_no(text))
        all_entities.extend(self._detect_phone(text))
        all_entities.extend(self._detect_email(text))
        all_entities.extend(self._detect_dates(text))
        all_entities.extend(self._detect_age(text))
        
        # SMART PATH: Name detection (NER-based, context-aware)
        if self.mode == 'regex':
            # Regex-only mode (fallback, less accurate)
            all_entities.extend(self._detect_names_regex(text))
        elif self.mode == 'ner':
            # NER-only mode (AI-powered, recommended)
            # Try NER first, fallback to regex if fails
            ner_entities = self._detect_names_ner(text)
            if ner_entities:
                all_entities.extend(ner_entities)
            else:
                # NER failed (OOM or model not loaded) - use regex fallback!
                all_entities.extend(self._detect_names_regex(text))
        elif self.mode == 'hybrid':
            # Hybrid: NER primary, regex fallback
            ner_entities = self._detect_names_ner(text)
            if ner_entities:
                # NER found entities - use them!
                all_entities.extend(ner_entities)
            else:
                # NER failed - fallback to regex
                all_entities.extend(self._detect_names_regex(text))
        
        # Remove overlapping entities
        all_entities = self._remove_overlapping_entities(all_entities)
        
        # Sort by position (reverse for safe replacement)
        all_entities.sort(key=lambda e: e.start, reverse=True)
        
        # Assign placeholders
        type_counters: Dict[str, int] = {}
        for entity in all_entities:
            type_counters[entity.type] = type_counters.get(entity.type, 0) + 1
            counter = type_counters[entity.type]
            
            placeholder_map = {
                'tc_no': f'[TC_NO_{counter}]',
                'phone': f'[PHONE_{counter}]',
                'email': f'[EMAIL_{counter}]',
                'name': f'[PATIENT_NAME_{counter}]',
                'date': f'[DATE_{counter}]',
                'age': f'[AGE_{counter}]'
            }
            entity.placeholder = placeholder_map.get(entity.type, f'[PII_{counter}]')
        
        # Mask text
        masked_text = text
        unmask_mapping = {}
        
        for entity in all_entities:
            masked_text = masked_text[:entity.start] + entity.placeholder + masked_text[entity.end:]
            unmask_mapping[entity.placeholder] = entity.value
        
        return masked_text, unmask_mapping
    
    def unmask(self, masked_text: str, unmask_mapping: Dict[str, str]) -> str:
        """
        Restore original PII values
        
        Args:
            masked_text: Text with PII placeholders
            unmask_mapping: Placeholder -> original value mapping
            
        Returns:
            Text with original PII values restored
        """
        unmasked_text = masked_text
        for placeholder, original_value in unmask_mapping.items():
            unmasked_text = unmasked_text.replace(placeholder, original_value)
        return unmasked_text
    
    def get_stats(self, unmask_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Get PII detection statistics
        
        Args:
            unmask_mapping: Placeholder -> original value mapping
            
        Returns:
            Statistics dict with total count and breakdown by type
        """
        type_counts: Dict[str, int] = {}
        
        type_keywords = {
            'TC_NO': 'tc_no',
            'PHONE': 'phone',
            'EMAIL': 'email',
            'PATIENT_NAME': 'name',
            'DATE': 'date',
            'AGE': 'age'
        }
        
        for placeholder in unmask_mapping.keys():
            pii_type = 'unknown'
            for keyword, type_name in type_keywords.items():
                if keyword in placeholder:
                    pii_type = type_name
                    break
            type_counts[pii_type] = type_counts.get(pii_type, 0) + 1
        
        return {
            'total_pii': len(unmask_mapping),
            'by_type': type_counts
        }
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _remove_overlapping_entities(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Remove overlapping entities, prefer longer matches"""
        if not entities:
            return entities
        
        # Sort by start position, then by length (descending)
        sorted_entities = sorted(entities, key=lambda e: (e.start, -(e.end - e.start)))
        
        result = []
        last_end = -1
        
        for entity in sorted_entities:
            if entity.start >= last_end:
                result.append(entity)
                last_end = entity.end
        
        return result
