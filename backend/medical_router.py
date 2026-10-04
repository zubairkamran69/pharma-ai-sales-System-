"""
Medical trigger router
======================

Rule: the moment a user message contains a medical / medicine word (or the
name of a medicine in the database), the message MUST go through RAG.
The LLM is never allowed to answer such a message from general knowledge.

Non-medical messages (general chat, AI, programming, sales strategy ...)
keep going to the general assistant.

Words like "doctor", "sales", "company", "pharma" or "RAG" are deliberately
NOT triggers by themselves - they are business words, not medical content.
"""

import re
from typing import Dict, Iterable, List

# ---------------------------------------------------------------------------
# Trigger vocabulary
# ---------------------------------------------------------------------------

# Matched as whole words / phrases.
MEDICAL_WORDS = [
    # medicine & forms
    'medicine', 'medicines', 'medicinal', 'medication', 'medications',
    'drug', 'drugs', 'tablet', 'tablets', 'capsule', 'capsules', 'syrup',
    'injection', 'injections', 'ointment', 'inhaler', 'suspension',
    'pharmaceutical product', 'brand name', 'generic name',
    # composition / product facts
    'active ingredient', 'active ingredients', 'ingredient', 'ingredients',
    'composition', 'formulation', 'strength', 'pack size',
    'manufacturer', 'shelf life', 'storage condition', 'storage conditions',
    'expiry', 'dosage form',
    # dosing
    'dose', 'doses', 'dosage', 'dosing', 'mg', 'mcg', 'overdose',
    'how many tablets', 'how much to take', 'how often',
    # clinical information
    'indication', 'indications', 'indicated', 'contraindication',
    'contraindications', 'contraindicated', 'side effect', 'side effects',
    'adverse event', 'adverse events', 'adverse reaction',
    'drug interaction',
    'precaution', 'precautions', 'efficacy', 'clinical', 'clinical trial',
    'clinical trials', 'pharmacology', 'pharmacokinetics',
    'pharmacodynamics', 'mechanism of action', 'half life', 'half-life',
    'painkiller', 'pain relief', 'pain killer', 'drug interactions',
    'adverse',
    'prescription', 'prescribe', 'prescribed', 'prescribing',
    'package insert', 'leaflet',
    # patient / disease
    'symptom', 'symptoms', 'diagnosis', 'diagnose', 'treatment',
    'therapy', 'disease', 'diseases', 'disorder', 'syndrome', 'infection',
    'fever', 'cough', 'allergy', 'allergic', 'pregnant',
    'pregnancy', 'breastfeeding', 'paediatric', 'pediatric', 'geriatric',
    'patient', 'patients', 'blood pressure', 'hypertension', 'diabetes',
    'diabetic', 'cholesterol', 'asthma', 'ulcer', 'acid reflux', 'gerd',
    'eczema', 'psoriasis', 'acne', 'cancer', 'insulin', 'vaccine',
    'antibiotic', 'antibiotics', 'analgesic', 'antacid', 'steroid',
    'anticoagulant', 'antihypertensive', 'cardiovascular', 'cardiac',
    'cardiology', 'respiratory', 'dermatology', 'gastrointestinal',
    'gastroenterology', 'kidney', 'renal', 'liver', 'hepatic',
]

# Matched as word prefixes (stem + anything), only unambiguous stems.
MEDICAL_STEMS = [
    'cardio', 'hypertens', 'diabet', 'respirat', 'gastro', 'dermat',
    'pharmacolog', 'therapeut', 'pregnan', 'lactat', 'oncolog', 'neurolog',
    'psychiatr', 'contraindic', 'antibio', 'hepat', 'nephr', 'bronch',
]

# Roman Urdu / Urdu script medical words.
URDU_WORDS = [
    'dawa', 'dawai', 'dawaee', 'dawain', 'dawaiyan', 'dawayen', 'dawaiyaan',
    'goli', 'golian', 'golia', 'ilaj', 'ilaaj', 'bimari', 'bemari', 'marz',
    'mareez', 'mareez', 'khurak', 'khuraak', 'khoorak', 'nuskha', 'dard',
    'bukhar', 'bukhaar', 'khansi', 'ulti', 'zukam',
    'alamat', 'alamaat',
    'دوا', 'دوائی', 'دوائیاں', 'گولی', 'علاج', 'بیماری', 'مریض', 'خوراک',
    'بخار', 'درد', 'کھانسی',
]

# Roman Urdu -> English hints appended to the retrieval query so TF-IDF
# (which is English only) can still find the right passages.
URDU_TO_EN = {
    'dawa': 'medicine', 'dawai': 'medicine', 'dawaee': 'medicine',
    'dawain': 'medicines', 'dawaiyan': 'medicines', 'dawayen': 'medicines',
    'goli': 'tablet', 'golian': 'tablets', 'golia': 'tablets',
    'khurak': 'dose dosage', 'khuraak': 'dose dosage',
    'khoorak': 'dose dosage', 'nuqsan': 'side effects adverse',
    'fayda': 'benefits indication', 'fayde': 'benefits indication',
    'istemal': 'use indication', 'qeemat': 'price', 'keemat': 'price',
    'kimat': 'price', 'ilaj': 'treatment', 'ilaaj': 'treatment',
    'bimari': 'disease', 'bemari': 'disease', 'mareez': 'patient',
    'bukhar': 'fever', 'dard': 'pain', 'khansi': 'cough',
    'alamat': 'symptoms', 'alamaat': 'symptoms',
}

ROMAN_URDU_MARKERS = {
    'kya', 'hai', 'hain', 'ka', 'ki', 'ke', 'ko', 'se', 'mein', 'main',
    'mujhe', 'batao', 'btao', 'bataein', 'batain', 'karo', 'kaise', 'kyun',
    'kitni', 'kitna', 'kitne', 'aur', 'nahi', 'nahin', 'wala', 'wali', 'tha',
    'dawai', 'dawa', 'goli', 'khurak', 'nuqsan', 'fayda', 'bataye',
    'bataiye', 'chahiye', 'hoti', 'hota', 'hoga', 'karna', 'kare', 'karein',
}


def _word_regex(terms: Iterable[str]) -> re.Pattern:
    parts = sorted({re.escape(t.lower()) for t in terms}, key=len, reverse=True)
    parts = [p.replace(r'\ ', r'\s+') for p in parts]
    return re.compile(r'(?<![a-z0-9])(?:' + '|'.join(parts) + r')(?![a-z0-9])', re.I)


def _stem_regex(stems: Iterable[str]) -> re.Pattern:
    parts = sorted({re.escape(s.lower()) for s in stems}, key=len, reverse=True)
    return re.compile(r'(?<![a-z0-9])(?:' + '|'.join(parts) + r')[a-z]*', re.I)


_WORD_RE = _word_regex(MEDICAL_WORDS)
_STEM_RE = _stem_regex(MEDICAL_STEMS)
_URDU_LATIN_RE = _word_regex([w for w in URDU_WORDS if w.isascii()])
_URDU_SCRIPT = [w for w in URDU_WORDS if not w.isascii()]


# ---------------------------------------------------------------------------
# Medicine names (from the database)
# ---------------------------------------------------------------------------

def _name_regex(name: str) -> re.Pattern:
    tokens = [t for t in re.split(r'\s+', name.strip()) if t]
    body = r'\s*'.join(re.escape(t) for t in tokens)
    return re.compile(r'(?<![a-z0-9])' + body + r'(?![a-z0-9])', re.I)


def find_medicines(message: str, medicines: List[dict]) -> List[dict]:
    """
    Return every medicine whose name appears in the message.

    Matches the full name ("Cardiovex 10", "cardiovex10") and also the brand
    root ("Cardiovex") so users do not have to type the strength.
    """
    found = []
    for m in medicines:
        name = (m.get('name') or '').strip()
        if not name:
            continue
        if _name_regex(name).search(message):
            found.append(m)
            continue
        root = name.split()[0]
        if len(root) >= 4 and root.lower() != name.lower():
            if _name_regex(root).search(message):
                found.append(m)
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def medical_triggers(message: str) -> List[str]:
    """List of medical trigger words found in the message (empty = none)."""
    hits: List[str] = []
    for rx in (_WORD_RE, _STEM_RE, _URDU_LATIN_RE):
        hits += [m.group(0).lower() for m in rx.finditer(message)]
    hits += [w for w in _URDU_SCRIPT if w in message]
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def is_business_count_or_catalog_question(message: str) -> bool:
    """Keep inventory/analytics questions out of the medical RAG path."""
    q = message.lower()
    if not re.search(r'\b(how many|count|show|list|what|which)\b', q):
        return False
    if not re.search(r'\b(medicine|medicines|product|products|catalog|inventory|stock)\b', q):
        return False
    if re.search(r'\b(dose|dosage|side effect|side effects|indication|indications|contraindication|contraindications|composition|ingredient|ingredients|manufacturer|strength|warning|warnings|prescription|adverse|allergic|storage|expiry|pack size)\b', q):
        return False
    return True


def classify(message: str, medicines: List[dict]) -> Dict:
    """
    Decide the route for a message.

    returns {
        'medical': bool,       # True  -> RAG is mandatory
        'medicines': [dict],   # medicines named in the message
        'triggers': [str],     # medical words that fired
    }
    """
    meds = find_medicines(message, medicines)
    triggers = medical_triggers(message)
    business_query = is_business_count_or_catalog_question(message)
    if business_query:
        triggers = []
    return {
        'medical': bool(meds or triggers) and not business_query,
        'medicines': meds,
        'triggers': ([m['name'] for m in meds] + triggers),
    }


def retrieval_query(message: str) -> str:
    """Original message + English hints for Roman Urdu medical words."""
    words = re.findall(r"[A-Za-z]+", message.lower())
    extra = [URDU_TO_EN[w] for w in words if w in URDU_TO_EN]
    return (message + ' ' + ' '.join(extra)).strip() if extra else message


def is_roman_urdu(message: str) -> bool:
    words = set(re.findall(r"[a-z]+", message.lower()))
    if re.search(r'[\u0600-\u06FF]', message):
        return True
    return len(words & ROMAN_URDU_MARKERS) >= 2


# ---------------------------------------------------------------------------
# Unknown-medicine guard
# ---------------------------------------------------------------------------
# "side effects of Aspirin" must not be answered with the generic side-effect
# paragraph of some *other* medicine just because both contain "side effects".
# If the message names a drug-looking word that appears in none of the
# retrieved sources, the knowledge base has no evidence for it.

_DRUG_SUFFIX = re.compile(
    r'(?:in|ol|ine|ide|ate|one|pam|mab|vir|pril|olol|azole|mycin|oxacin|'
    r'ptan|dine|fen|ium|cillin|statin|sartan|formin|profen|vastatin)$'
)

_NOT_DRUG = {
    'medicine', 'medicines', 'medicinal', 'medication', 'medications',
    'online', 'routine', 'pipeline', 'machine', 'discipline', 'examine',
    'determine', 'combine', 'decline', 'define', 'outline', 'baseline',
    'timeline', 'guideline', 'guidelines', 'hotline', 'deadline',
    'condition', 'conditions', 'information', 'indication', 'indications',
    'composition', 'formulation', 'description', 'prescription', 'dosing',
    'warning', 'warnings', 'evidence', 'clinical', 'strength', 'approved',
    'manufacturer', 'company', 'portfolio', 'product', 'products',
    'database', 'knowledge', 'document', 'documents', 'question',
}


def unknown_drug_terms(message: str, source_text: str) -> List[str]:
    """Drug-looking words in the message that none of the sources mention."""
    src = source_text.lower()
    out = []
    for w in re.findall(r"[a-z]{6,}", message.lower()):
        if w in _NOT_DRUG or w in URDU_TO_EN or w in ROMAN_URDU_MARKERS:
            continue
        if not _DRUG_SUFFIX.search(w):
            continue
        if w in src or w.rstrip('s') in src:
            continue
        out.append(w)
    return out