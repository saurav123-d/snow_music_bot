import re
import unicodedata
URL_PATTERN = re.compile(r'(https?://|www\.)[a-zA-Z0-9.\-]+(\.[a-zA-Z]{2,})+(/[a-zA-Z0-9._%+-]*)*')

def _strip_diacritics(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s or '') if not unicodedata.combining(c))

def _fold_confusables(s: str) -> str:
    return (s.replace('ø', 'o')
             .replace('ö', 'o')
             .replace('ó', 'o')
             .replace('ô', 'o')
             .replace('õ', 'o')
             .replace('œ', 'oe')
             .replace('ß', 'ss')
             .replace('ï', 'i')
             .replace('í', 'i')
             .replace('î', 'i')
             .replace('ì', 'i')
             .replace('ı', 'i')
             .replace('ĺ', 'l')
             .replace('ľ', 'l')
             .replace('ł', 'l'))

class BioLinkDetector:
    def __init__(self):
        self.domain_patterns = [
            r'\b(?:https?://)?(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
            r'\b(?:t\.me|telegram\.me)/[a-zA-Z0-9_\-]+\b',
            r'\b(?:bio\.link|linktr\.ee|lnk\.bio|linkin\.bio|beacons\.ai|tap\.bio|campsite\.bio|solo\.to|carrd\.co)(?:[^\s]*)\b',
            r'\b(?:bit\.ly|tinyurl\.com|goo\.gl|short\.ee)\b',
        ]
        self.target_domains = ("bio.link", "linktr.ee", "lnk.bio", "linkin.bio", "beacons.ai", "tap.bio", "campsite.bio", "solo.to", "carrd.co")
        self.target_synonyms = ("biolink", "linktree", "linkinbio", "bio-link", "link-in-bio")

    def normalize(self, text: str) -> str:
        s = _strip_diacritics(text or '')
        s = _fold_confusables(s)
        return re.sub(r'[\u200B-\u200F\u202A-\u202E\u2060]', '', s).strip()

    def normalize_obfuscations(self, text: str) -> str:
        s = text.lower()
        s = self.normalize(s)
        s = _fold_confusables(s)
        s = re.sub(r'\s*\[\s*dot\s*\]\s*', '.', s)
        s = re.sub(r'\s*dot\s*', '.', s)
        s = s.replace('•', '.').replace('·', '.').replace('∙', '.').replace('●', '.').replace('﹒', '.').replace('．', '.').replace('｡', '.')
        s = s.replace(' ', '').replace('-', '').replace('_', '')
        return s
    
    def contains_confusable_biolink(self, text: str) -> bool:
        s = self.normalize(text).lower()
        s = re.sub(r'[\s\-\._]+', '', s)
        s = (s.replace('0', 'o')
               .replace('1', 'l')
               .replace('¡', 'i'))
        s = _fold_confusables(s)
        collapsed = re.sub(r'[^a-z0-9]+', '', s)
        return ('biolink' in collapsed) or ('linktree' in collapsed) or ('linktr' in collapsed and 'ee' in collapsed)

    def has_link_in_text(self, text: str) -> bool:
        content = self.normalize(text)
        if URL_PATTERN.search(content):
            return True
        for pattern in self.domain_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        obf = self.normalize_obfuscations(text)
        for dom in self.target_domains:
            if dom in obf:
                return True
        for syn in self.target_synonyms:
            if syn in obf:
                return True
        if self.contains_confusable_biolink(text):
            return True
        if re.search(r'bio(\W*|dot)+link', text, re.IGNORECASE):
            return True
        if re.search(r'linktr(\W*|dot)+ee', text, re.IGNORECASE):
            return True
        if re.search(r'bio[\W_]{0,10}link', content, re.IGNORECASE):
            return True
        if re.search(r'link[\W_]{0,10}tree', content, re.IGNORECASE):
            return True
        if re.search(r'link[\W_]{0,10}bio', content, re.IGNORECASE):
            return True
        if re.search(r'b\W*i\W*o\W*l\W*i\W*n\W*k', text, re.IGNORECASE):
            return True
        if re.search(r'l\W*i\W*n\W*k\W*t\W*r\W*e\W*e', text, re.IGNORECASE):
            return True
        base = re.sub(r'\s+', ' ', content.lower())
        if re.search(r'bio.{0,100}link', base) or re.search(r'link.{0,100}bio', base):
            return True
        if re.search(r'\bbio\s*(me|mein|mai|m)\s*link\b', base, re.IGNORECASE):
            return True
        return False

    def has_link_in_message(self, message) -> bool:
        base = message.text or message.caption or ""
        base = self.normalize(base)
        entities = []
        if getattr(message, "entities", None):
            entities += message.entities
        if getattr(message, "caption_entities", None):
            entities += message.caption_entities
        for e in entities:
            if e.type in ("url", "text_link"):
                if e.type == "text_link" and getattr(e, "url", None):
                    return True
                if base:
                    seg = base[e.offset:e.offset + e.length]
                    if seg:
                        return True
        return self.has_link_in_text(base)
    
    def get_link_reason(self, message):
        base = message.text or message.caption or ""
        norm = self.normalize(base)
        entities = []
        if getattr(message, "entities", None):
            entities += message.entities
        if getattr(message, "caption_entities", None):
            entities += message.caption_entities
        for e in entities:
            if e.type == "text_link" and getattr(e, "url", None):
                return "entity:text_link"
            if e.type == "url":
                seg = norm[e.offset:e.offset + e.length]
                if seg:
                    return "entity:url"
        if URL_PATTERN.search(norm):
            return "pattern:url"
        for pattern in self.domain_patterns:
            if re.search(pattern, norm, re.IGNORECASE):
                return "pattern:domain"
        obf = self.normalize_obfuscations(base)
        for dom in self.target_domains:
            if dom in obf:
                return f"domain:{dom}"
        for syn in self.target_synonyms:
            if syn in obf:
                return f"synonym:{syn}"
        if self.contains_confusable_biolink(base):
            return "match:confusable_biolink"
        if re.search(r'bio(\W*|dot)+link', base, re.IGNORECASE):
            return "match:bio*link"
        if re.search(r'linktr(\W*|dot)+ee', base, re.IGNORECASE):
            return "match:linktr*ee"
        if re.search(r'bio[\W_]{0,10}link', norm, re.IGNORECASE):
            return "match:bio..link"
        if re.search(r'link[\W_]{0,10}tree', norm, re.IGNORECASE):
            return "match:link..tree"
        if re.search(r'link[\W_]{0,10}bio', norm, re.IGNORECASE):
            return "match:link..bio"
        if re.search(r'b\W*i\W*o\W*l\W*i\W*n\W*k', base, re.IGNORECASE):
            return "match:spaced-biolink"
        if re.search(r'l\W*i\W*n\W*k\W*t\W*r\W*e\W*e', base, re.IGNORECASE):
            return "match:spaced-linktree"
        base2 = re.sub(r'\s+', ' ', norm.lower())
        if re.search(r'bio.{0,100}link', base2) or re.search(r'link.{0,100}bio', base2):
            return "match:bio..link-heuristic"
        if re.search(r'\bbio\s*(me|mein|mai|m)\s*link\b', base2, re.IGNORECASE):
            return "match:hindi-bio-link"
        return None
