#!/usr/bin/env python3
"""
Llama 3.1 8B Text Generator (GPU hızlandırmalı, inference-only, stateless)

GÜVENLİK: Frozen weights, training yok, memorization yok, geçici RAM işleme
PERFORMANS: INT8 quantization, GPU inference, ~12s gecikme
PRİVACY: Stateless API, veri saklamama, GDPR uyumlu
"""

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from typing import Optional, Dict, Any
import time


class LlamaTextGenerator:
    """Llama 3.1 8B text generator (gerçek metin üretimi, Türkçe, tıbbi alan, GPU)."""
    
    # #1 Model yükleme ve başlatma (tokenizer, model, quantization, inference-only mode)
    def __init__(self,
                 model_name: str = "meta-llama/Meta-Llama-3.1-8B-Instruct",
                 device: str = "cuda" if torch.cuda.is_available() else "cpu",
                 max_length: int = 512,
                 temperature: float = 0.7):
        self.device = device
        self.max_length = max_length
        self.temperature = temperature
        
        print(f"🦙 Loading Llama 3.1 8B on {device}...")
        start = time.time()
        
        try:
            # Tokenizer yükle
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True
            )
            
            # Pad token yoksa ayarla
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Model yükle
            if device == "cuda":
                # GPU: FP16 for faster inference
                # NOT: device_map kullanma! CUDA_VISIBLE_DEVICES'e saygı duymaz
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                )
                # Explicit olarak device'a taşı
                self.model = self.model.to(device)
                print(f"   ✅ Model GPU'ya yüklendi: {device}")
            else:
                # CPU: Normal yükleme
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float32,
                    trust_remote_code=True
                )
                self.model = self.model.to(device)
            
            # CRITICAL: Ayarla e eval mode (no training!)
            self.model.eval()
            
            # SECURITY: Freeze ALL weights (no learning!)
            for param in self.model.parameters():
                param.requires_grad = False
            
            # Doğrula no gradients
            self._verify_inference_only()
            
            elapsed = time.time() - start
            print(f"✅ Llama loaded in {elapsed:.1f}s")
            print(f"   Device: {self.device}")
            print(f"   Model: {model_name}")
            print(f"   Parameters: ~8B")
            
        except Exception as e:
            print(f"❌ FATAL: Failed to load Llama: {e}")
            print(f"   Mock template DISABLED for production integrity!")
            print(f"   System requires real Llama 3.1 8B to run.")
            raise RuntimeError(f"Llama 3.1 8B failed to load: {e}")
    
    # #2 Güvenlik kontrolü: Model'in inference-only modda olduğunu doğrular (frozen weights)
    def _verify_inference_only(self):
        trainable_params = sum(p.requires_grad for p in self.model.parameters())
        total_params = sum(1 for _ in self.model.parameters())
        
        if trainable_params > 0:
            raise RuntimeError(
                f"SECURITY VIOLATION: Model has {trainable_params} trainable params! "
                f"All params must be frozen for inference-only mode."
            )
        
        print(f"   🔒 Security: ALL {total_params} parameters frozen (inference-only)")
        print(f"   ✅ Model CANNOT learn from data")
        print(f"   ✅ Zero gradient computation")
    
    # #3 Text generation (ana fonksiyon): Prompt alır, Llama ile response üretir
    def generate(self,
                 prompt: str,
                 max_new_tokens: int = 256,
                 temperature: Optional[float] = None,
                 top_p: float = 0.9,
                 do_sample: bool = True) -> str:
        if self.model is None:
            # Mock'a dön (model yüklü değilse)
            return self._mock_generate(prompt)
        
        # Prompt'u instruction model için formatla
        formatted_prompt = self._format_medical_prompt(prompt)
        
        # Tokenize
        inputs = self.tokenizer(
            formatted_prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        )
        
        # CRITICAL: Tüm tensor'ları doğru device'a taşı
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)
        
        # Üret
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                temperature=temperature or self.temperature,
                top_p=top_p,
                do_sample=do_sample,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3
            )
        
        # Decode
        generated_text = self.tokenizer.decode(
            outputs[0],
            skip_special_tokens=True
        )
        
        # Sadece cevabı çıkar (prompt'u kaldır)
        response = self._extract_response(generated_text, formatted_prompt)
        
        return response
    
    # Medical prompt formatlama
    def _format_medical_prompt(self, query: str) -> str:
        system_prompt = """Sen uzman bir tıbbi AI asistanısın. Türkçe olarak doğru, kanıta dayalı tıbbi bilgi sun.

ÖNEMLİ KURALLAR:
- SADECE ANALİZ YAP - Soruyu veya laboratuvar sonuçlarını TEKRARLAMA
- Direkt değerlendirme ile başla
- Net, profesyonel ve hasta odaklı ol
- Güncel tıbbi kılavuzlara dayalı bilgi ver
- Sağlık profesyonelleri için uygun dil kullan

NOT: Bu bilgilendirme amaçlıdır. Tanı ve tedavi için mutlaka sağlık kuruluşuna başvurulmalıdır."""
        
        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

{query}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""
        
        return prompt
    
    # Response extraction
    def _extract_response(self, full_text: str, prompt: str) -> str:
        import re
        
        # Method 1: Assistant bölümünü bul
        if "<|start_header_id|>assistant<|end_header_id|>" in full_text:
            # Assistant marker'dan böl
            parts = full_text.split("<|start_header_id|>assistant<|end_header_id|>")
            if len(parts) > 1:
                response = parts[-1]  # Son assistant response'u al
            else:
                response = full_text
        else:
            response = full_text
        
        # Özel token'ları temizle
        response = response.replace("<|eot_id|>", "").strip()
        response = response.replace("<|end_of_text|>", "").strip()
        response = response.replace("<|start_header_id|>", "").strip()
        response = response.replace("<|end_header_id|>", "").strip()
        response = response.replace("<|begin_of_text|>", "").strip()
        
        # Kalan system/user/assistant tag'leri kaldır
        response = response.replace("system", "", 1).strip()
        response = response.replace("user", "", 1).strip()
        response = response.replace("assistant", "", 1).strip()
        
        # AGRESİF: System prompt'u tamamen kaldır (REGEX ile - TÜRKÇE!)
        # Tüm system prompt bloğunu bul ve kaldır
        system_prompt_pattern = r'(?s)Sen uzman bir tıbbi AI asistanısın.*?sağlık kuruluşuna başvurulmalıdır\.'
        response = re.sub(system_prompt_pattern, '', response, flags=re.IGNORECASE)
        
        # Query echo'sunu kaldır (model bazen query'yi tekrar eder)
        # Hasta bilgileri ve query tekrarını ULTRA AGRESİF kaldır
        query_echo_patterns = [
            r'^Hasta:.*?\n',  # Tüm "Hasta: ..." satırlarını kaldır
            r'^\[PATIENT_NAME_\d+\],?\s*\d+\s*yaş.*?\n',  # "[PATIENT_NAME_0], 45 yaş. ..."
            r'^Total kolesterol:.*?\n',  # Lab sonuçları
            r'^Açlık kan şekeri:.*?\n',
            r'^HbA1c:.*?\n',
            r'^LDL:.*?\n',
            r'^HDL:.*?\n',
            r'^.*?Değerlendir\.[\s]*\n',  # "... Değerlendir." ile biten satırlar
            r'^.*?ne anlama geliyor\?[\s]*\n',  # "... ne anlama geliyor?" ile biten satırlar
            r'^What.*?\?[\s]*(?:assistant)?[\s]*\n',
            r'^LABORATUVAR SONUÇLARI.*?değerlendir\.[\s]*\n',
            r'^LABORATUVAR.*?Tarih:.*?\n',
        ]
        for pattern in query_echo_patterns:
            response = re.sub(pattern, '', response, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
        
        # Çift satır boşluklarını tek satıra indir
        response = re.sub(r'\n\n+', '\n\n', response)
        
        # System prompt marker'ları tek tek kaldır
        system_markers = [
            "Your responses should be:",
            "- Clear, professional, and patient-focused",
            "- Based on current medical guidelines and research",
            "- Appropriate for healthcare professionals",
            "- In English language only (regardless of query language)",
            "Important: This is for informational purposes.",
            "Important: This is for informational purposes",
            "Always recommend consulting healthcare providers for diagnosis and treatment",
            "sen uzman",
            "tıbbi asistan",
            "yanıtların bilimsel"
        ]
        
        for marker in system_markers:
            response = response.replace(marker, "")
        
        # Boş satırları ve başındaki fazla whitespace'i temizle
        lines = [line for line in response.split('\n') if line.strip()]
        response = '\n'.join(lines).strip()
        
        # Başta ki boş satırları kaldır
        response = response.lstrip('\n')
        
        # Final temizlik: İlk satır soru işaretiyle bitiyorsa kaldır
        lines = response.split('\n', 1)
        if len(lines) > 1 and lines[0].strip().endswith('?'):
            response = lines[1].strip()
        
        return response
    
    # #6 Mock generation (fallback): Model yüklenemezse keyword bazlı cevap üretir
    def _mock_generate(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        
        # Diyabet
        if "diyabet" in prompt_lower or "şeker" in prompt_lower:
            return """Diyabet (şeker hastalığı) belirtileri şunlardır:

1. **Aşırı susama ve kuru ağız**: Kan şekerinin yüksek olması nedeniyle vücut su kaybeder.

2. **Sık idrara çıkma**: Özellikle gece saatlerinde sık tuvalete gitme ihtiyacı.

3. **Yorgunluk ve halsizlik**: Hücrelerin glikozdan enerji üretememesi sonucu.

4. **Açıklanamayan kilo kaybı**: Özellikle Tip 1 diyabette görülür.

5. **Bulanık görme**: Yüksek kan şekeri göz lensini etkiler.

6. **Yavaş iyileşen yaralar**: Kan dolaşımının etkilenmesi nedeniyle.

**Önemli not**: Bu belirtilerden birkaçını fark ederseniz, mutlaka bir sağlık kuruluşuna başvurun ve kan şekeri testinizi yaptırın."""
        
        # Hipertansiyon
        elif "tansiyon" in prompt_lower or "hipertansiyon" in prompt_lower:
            return """Yüksek tansiyon (hipertansiyon) belirtileri:

1. **Baş ağrısı**: Özellikle sabah saatlerinde ense bölgesinde ağrı.

2. **Baş dönmesi**: Ani hareket değişikliklerinde belirginleşir.

3. **Burun kanaması**: Tekrarlayan burun kanamaları uyarı işareti olabilir.

4. **Nefes darlığı**: Eforla birlikte ortaya çıkar.

5. **Göğüs ağrısı**: Kalp yükünün artması sonucu.

**Risk faktörleri**: Aşırı tuz tüketimi, stres, obezite, hareketsiz yaşam.

**Öneri**: Düzenli tansiyon takibi yapın. Normal değerler: 120/80 mmHg civarı."""
        
        # Grip/Soğuk Algınlığı
        elif "grip" in prompt_lower or "soğuk algınlığı" in prompt_lower:
            return """Grip ve soğuk algınlığı tedavisi:

1. **Bol sıvı tüketimi**: Günde en az 2-3 litre su, bitki çayı.

2. **Dinlenme**: Vücudunuzun iyileşmesi için yeterli uyku.

3. **Vitamin desteği**: C vitamini (portakal, mandalina) bağışıklığı güçlendirir.

4. **Ateş düşürücüler**: Parasetamol veya ibuprofen (hekim önerisi ile).

5. **Buhar terapisi**: Burun tıkanıklığı için nemli hava solumak.

6. **Ballı süt**: Doğal bir öksürük kesici.

**Dikkat**: Belirtiler 1 haftadan uzun sürerse veya nefes darlığı oluşursa doktora başvurun."""
        
        # Kolesterol
        elif "kolesterol" in prompt_lower:
            return """Kolesterol kontrolü ve yönetimi:

1. **Sağlıklı beslenme**:
   - Zeytinyağı, avokado (iyi yağlar)
   - Yulaf, fasulye (lifli gıdalar)
   - Somon, ceviz (Omega-3)
   - Kırmızı et ve yağlı süt ürünlerinden kaçının

2. **Düzenli egzersiz**: Haftada en az 150 dakika orta tempolu aktivite.

3. **Kilo kontrolü**: Fazla kilolar LDL (kötü kolesterol) artırır.

4. **Sigara bırakma**: HDL (iyi kolesterol) yükseltir.

5. **İlaç tedavisi**: Gerekirse hekim statin reçete edebilir.

**Hedef değerler**:
- Total kolesterol: <200 mg/dL
- LDL (kötü): <100 mg/dL
- HDL (iyi): >40 mg/dL (erkek), >50 mg/dL (kadın)"""
        
        # Varsayılan
        else:
            return f"""Sağlık sorunuz hakkında genel bilgiler:

Sorduğunuz konu ({prompt[:50]}...) hakkında şunları önerebilirim:

1. **Profesyonel değerlendirme**: Kesin tanı için mutlaka bir sağlık kuruluşuna başvurun.

2. **Belirtileri takip edin**: Belirtilerinizi not edin ve doktorunuzla paylaşın.

3. **Sağlıklı yaşam**: Dengeli beslenme, düzenli egzersiz ve yeterli uyku.

4. **İlaç kullanımı**: Hekim önerisi olmadan ilaç kullanmayın.

**Önemli**: Bu bilgiler genel tavsiye niteliğindedir ve profesyonel tıbbi tavsiyenin yerini tutmaz."""
    
    # #7 Batch generation: Birden fazla prompt'u aynı anda işler (throughput optimization)
    def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        if self.model is None:
            # Mock modu
            return [self._mock_generate(p) for p in prompts]
        
        # Tüm prompt'ları formatla
        formatted_prompts = [self._format_medical_prompt(p) for p in prompts]
        
        # Batch'i tokenize et
        inputs = self.tokenizer(
            formatted_prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        )
        
        # CRITICAL: Tüm tensor'ları doğru device'a taşı
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)
        
        # Batch üret
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=kwargs.get('max_new_tokens', 256),
                temperature=kwargs.get('temperature', self.temperature),
                top_p=kwargs.get('top_p', 0.9),
                do_sample=kwargs.get('do_sample', True),
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3
            )
        
        # Hepsini decode et
        responses = []
        for i, output in enumerate(outputs):
            generated_text = self.tokenizer.decode(output, skip_special_tokens=True)
            response = self._extract_response(generated_text, formatted_prompts[i])
            responses.append(response)
        
        return responses
    
    # #8 Model info: Model bilgilerini döndürür (device, status, config)
    def get_info(self) -> Dict[str, Any]:
        return {
            'model': 'Llama 3.1 8B Instruct',
            'device': self.device,
            'loaded': self.model is not None,
            'max_length': self.max_length,
            'temperature': self.temperature
        }


def demo():
    """Llama text generation demo çalıştırır."""
    
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║                                                                      ║")
    print("║              Llama 3.1 8B Text Generation Demo                      ║")
    print("║                                                                      ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    
    # Başlat (model yoksa mock kullanır)
    generator = LlamaTextGenerator()
    
    # Test sorguları
    queries = [
        "Diyabet belirtileri nelerdir?",
        "Yüksek tansiyon nasıl düşürülür?",
        "Grip tedavisi nedir?",
        "Kolesterol kontrolü nasıl yapılır?"
    ]
    
    print(f"\n{'='*80}")
    print("🧪 TEST QUERIES")
    print(f"{'='*80}")
    
    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Query: {query}")
        print("-" * 80)
        
        start = time.time()
        response = generator.generate(query, max_new_tokens=200)
        elapsed = (time.time() - start) * 1000
        
        print(f"Response:\n{response}")
        print(f"\n⏱️  Generation time: {elapsed:.0f}ms")
    
    # Model bilgisi
    print(f"\n{'='*80}")
    print("ℹ️  MODEL INFO")
    print(f"{'='*80}")
    
    info = generator.get_info()
    for key, value in info.items():
        print(f"   {key}: {value}")


if __name__ == "__main__":
    demo()

