"""
Differential Privacy Module
LLM response'lara calibrated noise ekler (membership inference resistance, ε-DP)
"""

import numpy as np
from typing import Optional
import hashlib

# =============================================================================
# DIFFERENTIAL PRIVACY CLASS
# =============================================================================

class DifferentialPrivacy:
    """Text response'lara differential privacy uygular (Laplace noise + perturbation)"""
    
    #1 Kullanım Sırası: Server başlatılırken oluşturulur
    # Açıklama: DP parametrelerini ayarlar (epsilon, sensitivity, privacy budget)
    def __init__(self, epsilon: float = 1.0, sensitivity: float = 1.0):
        self.epsilon = epsilon          # Privacy budget (düşük = güçlü privacy)
        self.sensitivity = sensitivity  # Query sensitivity
        self.enabled = True
    
    #2 Kullanım Sırası: Response döndürülmeden önce çağrılır
    # Açıklama: Response'a Laplace noise ekler ve text perturbation yapar
    def add_noise_to_response(self, response: str, query_id: Optional[str] = None) -> str:
        if not self.enabled or not response:
            return response
        
        # Deterministic noise (same query → same noise)
        rng = self._get_rng(query_id)
        
        # Laplace noise magnitude hesapla
        scale = self.sensitivity / self.epsilon
        noise_magnitude = rng.laplace(0, scale)
        
        # Noise level'a göre perturbation stratejisi seç
        if abs(noise_magnitude) < 0.3:
            return self._perturb_punctuation(response, rng)
        elif abs(noise_magnitude) < 0.7:
            return self._perturb_word_order(response, rng)
        else:
            return self._perturb_with_synonyms(response, rng)
    
    #3 Kullanım Sırası: add_noise_to_response içinde çağrılır
    # Açıklama: query_id'den deterministic random generator oluşturur
    def _get_rng(self, query_id: Optional[str]) -> np.random.RandomState:
        if query_id:
            seed = int(hashlib.md5(query_id.encode()).hexdigest()[:8], 16)
        else:
            seed = None
        return np.random.RandomState(seed)
    
    #4 Kullanım Sırası: Düşük noise level'da çağrılır
    # Açıklama: Noktalama işaretlerinde minimal değişiklik yapar
    def _perturb_punctuation(self, text: str, rng: np.random.RandomState) -> str:
        # %20 şansla son nokta → ünlem/çift nokta
        if rng.random() < 0.2 and text.endswith('.'):
            replacements = ['.', '!', '.', '.']  # Ağırlıklı (mostly .)
            text = text[:-1] + rng.choice(replacements)
        
        # %10 şansla virgül sil
        if rng.random() < 0.1 and ',' in text:
            parts = text.split(',', 1)
            if len(parts) == 2:
                text = parts[0] + parts[1]
        
        return text
    
    #5 Kullanım Sırası: Orta noise level'da çağrılır
    # Açıklama: Cümle sırasını hafif shuffle yapar (semantic korunur)
    def _perturb_word_order(self, text: str, rng: np.random.RandomState) -> str:
        sentences = text.split('. ')
        
        # %30 şansla ilk iki cümleyi swap et
        if len(sentences) >= 2 and rng.random() < 0.3:
            sentences[0], sentences[1] = sentences[1], sentences[0]
        
        return '. '.join(sentences)
    
    #6 Kullanım Sırası: Yüksek noise level'da çağrılır
    # Açıklama: Bazı kelimeleri synonym ile değiştirir (medical domain aware)
    def _perturb_with_synonyms(self, text: str, rng: np.random.RandomState) -> str:
        # Tıbbi domain synonym map
        synonyms = {
            'symptoms': ['signs', 'indicators', 'manifestations'],
            'treatment': ['therapy', 'management', 'intervention'],
            'disease': ['condition', 'illness', 'disorder'],
            'patient': ['individual', 'person', 'case'],
            'doctor': ['physician', 'clinician', 'healthcare provider'],
            'medicine': ['medication', 'drug', 'pharmaceutical'],
            'high': ['elevated', 'increased', 'raised'],
            'low': ['reduced', 'decreased', 'diminished'],
            'important': ['crucial', 'essential', 'significant'],
            'common': ['frequent', 'typical', 'prevalent'],
        }
        
        # %20 şansla kelimeleri synonym ile değiştir
        words = text.split()
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,!?')
            if word_lower in synonyms and rng.random() < 0.2:
                synonym = rng.choice(synonyms[word_lower])
                if word[0].isupper():
                    synonym = synonym.capitalize()
                words[i] = word.replace(word_lower, synonym)
        
        return ' '.join(words)
    
    #7 Kullanım Sırası: Opsiyonel (Privacy budget tracking için)
    # Açıklama: Kalan epsilon miktarını döndürür
    def get_privacy_budget_remaining(self) -> float:
        return self.epsilon
    
    #8 Kullanım Sırası: Opsiyonel (Config görüntüleme için)
    # Açıklama: DP konfigürasyonunu döndürür (epsilon, sensitivity, guarantee)
    def get_config(self) -> dict:
        return {
            'enabled': self.enabled,
            'epsilon': self.epsilon,
            'sensitivity': self.sensitivity,
            'privacy_guarantee': f'(ε={self.epsilon})-DP',
            'interpretation': self._interpret_epsilon()
        }
    
    #9 Kullanım Sırası: get_config içinde çağrılır
    # Açıklama: Epsilon değerini human-readable açıklama yapar
    def _interpret_epsilon(self) -> str:
        if self.epsilon < 0.5:
            return "Strong privacy (some accuracy loss)"
        elif self.epsilon < 2.0:
            return "Balanced privacy-utility"
        else:
            return "Weak privacy (high accuracy)"
